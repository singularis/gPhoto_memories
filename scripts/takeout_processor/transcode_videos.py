#!/usr/bin/env python3
"""
Build browser-safe copies of videos Chrome cannot play.

iPhone .mov files are usually HEVC inside a QuickTime container. Chrome does
not play that, so each such clip gets an H.264 MP4 in
<library>/.video_cache/<md5(relpath:size)>.mp4, which is what web/app.py serves.

MP4 files that are already H.264, VP9 or AV1 are left alone.
H.264 inside .mov is remuxed (no re-encode). Everything else is transcoded.

Resume-safe: a finished cache file is skipped. Re-run the same command.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys

ROOT = "/other_hdd/google_phots_all_take_for_processing"
CACHE = os.path.join(ROOT, ".video_cache")
STATE = os.path.join(CACHE, "status.json")
FFMPEG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "ffmpeg")
FFPROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "ffprobe")

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}
# Containers and codecs Chrome plays without help.
NATIVE = {(".mp4", "h264"), (".mp4", "vp9"), (".mp4", "av1"), (".webm", "vp9"), (".webm", "vp8"), (".webm", "av1")}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                               "transcode_videos.log"))])
log = logging.getLogger("transcode")


def cache_path(rel, size):
    key = hashlib.md5(f"{rel}:{size}".encode()).hexdigest()
    return os.path.join(CACHE, f"{key}.mp4")


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", path],
        capture_output=True, text=True)
    try:
        streams = json.loads(out.stdout or "{}").get("streams", [])
    except json.JSONDecodeError:
        return None, None
    video = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
    return video, audio


def needs(rel, vcodec, acodec):
    ext = os.path.splitext(rel)[1].lower()
    if (ext, vcodec) in NATIVE:
        return "native"
    if vcodec == "h264" and acodec in (None, "aac", "mp3"):
        return "remux"
    return "transcode"


def build(src, dest, mode):
    if mode == "remux":
        cmd = [FFMPEG, "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
               "-c", "copy", "-movflags", "+faststart", dest]
    else:
        cmd = [FFMPEG, "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "2", "-pix_fmt", "yuv420p",
               "-vf", "scale='min(1920,iw)':-2",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dest]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log.error("ffmpeg failed for %s: %s", src, res.stderr[-400:])
        return False
    return os.path.getsize(dest) > 0


def videos():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # .live holds the hidden live-photo clips. _archived/_trash/_undated are not on the timeline.
        dirnames[:] = [d for d in dirnames
                       if d not in (".video_cache", ".thumb_cache", ".manifests", ".live")
                       and not d.startswith("_")]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
                full = os.path.join(dirpath, name)
                found.append(os.path.relpath(full, ROOT))
    return sorted(found)


def main():
    if not (os.path.isfile(FFMPEG) and os.path.isfile(FFPROBE)):
        sys.exit(f"ffmpeg not found at {FFMPEG}")
    os.makedirs(CACHE, exist_ok=True)
    state = {}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE))
        except Exception:
            state = {}

    counts = {"native": 0, "remux": 0, "transcode": 0, "failed": 0, "skipped": 0}
    for rel in videos():
        src = os.path.join(ROOT, rel)
        try:
            size = os.path.getsize(src)
        except OSError:
            continue
        dest = cache_path(rel, size)
        if state.get(rel) == f"native:{size}":
            counts["skipped"] += 1
            continue
        # A cache file is only renamed into place after ffmpeg succeeds.
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            state[rel] = f"done:{size}"
            counts["skipped"] += 1
            continue

        vcodec, acodec = probe(src)
        mode = needs(rel, vcodec, acodec)
        if mode == "native":
            state[rel] = f"native:{size}"
            counts["native"] += 1
            continue

        # Keep a .mp4 suffix or ffmpeg will not pick the MP4 muxer.
        tmp = dest + ".part.mp4"
        log.info("%s %s (%s/%s, %.1f MB)", mode, rel, vcodec, acodec, size / 1024**2)
        if build(src, tmp, mode):
            os.replace(tmp, dest)
            state[rel] = f"done:{size}"
            counts[mode] += 1
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
            state[rel] = f"fail:{size}"
            counts["failed"] += 1
        with open(STATE, "w") as f:
            json.dump(state, f)

    with open(STATE, "w") as f:
        json.dump(state, f)
    log.info("finished %s", counts)


if __name__ == "__main__":
    main()
