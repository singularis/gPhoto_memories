#!/usr/bin/env python3
"""
Google Takeout photo/video processor — v3.

Rebuilds the memories library so every date folder holds exactly the items
Google Photos shows for that day.

Why v3 (findings from the 2026-06 takeout, 10 zips, 183k media files):
  * Google packs most JSON sidecars into the first zips (zip 1: 37k JSON,
    zip 10: 88 JSON for 3.8k media). Sidecars must be indexed across ALL zips.
  * Sidecar names are capped at 51 chars, so ".supplemental-metadata" gets
    truncated (".supplemental-.json", ".sup.json", "..json", ...) and long
    media names are truncated too.
  * Duplicates: "IMG_1(1).jpg" pairs with "IMG_1.jpg.supplemental-metadata(1).json".
  * Album folders repeat items that are also in "Photos from YYYY"; the JSON
    "url" is the unique Google Photos item id, used for de-duplication.
  * Live Photo (.MOV/.MP4/no extension) and Pixel Motion Photo (.MP) clips
    have no JSON and are not separate items in Google Photos.
  * "-edited" files share the original's JSON; Google Photos shows only the
    edited version.
  * Trash items ("trashed": true) and archived items are not in the timeline.
  * photoTakenTime is UTC; Google Photos shows the local capture date, so the
    timestamp is converted with the timezone of the GPS location (or of the
    nearest geotagged item in time).

Output layout (PROCESSING_PATH):
  YYYY_MM_DD/<file>             visible items (what the UI lists)
  YYYY_MM_DD/.live/<file>       live/motion clips and pre-edit originals
  _archived/YYYY_MM_DD/<file>   archived items
  _trash/<file>                 trashed items
  _undated/<file>               no sidecar and no date in the filename
  .manifests/index.json         every source member -> destination + metadata

Usage:
  .venv/bin/python google_takeout_processor.py plan
  .venv/bin/python google_takeout_processor.py sample -n 50
  .venv/bin/python google_takeout_processor.py run [--out DIR]
"""

import argparse
import bisect
import glob
import json
import logging
import logging.handlers
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TAKEOUT_PATH    = "/other_hdd/google_phots_all_take_out"
PROCESSING_PATH = "/other_hdd/google_phots_all_take_for_processing"

script_dir = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(script_dir, ".cache")
SIDECAR_CACHE = os.path.join(CACHE_DIR, "sidecars.json")
DEFAULT_TZ = "Europe/Kyiv"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_file = os.path.join(script_dir, "google_takeout_processor.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024,
                                             backupCount=3, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File types
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif", ".dng"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}
MOTION_EXTS = {".mp", ".mp~2"}  # Pixel motion photo video part

SUPPLEMENTAL = "supplemental-metadata"
_DUP_RE = re.compile(r"^(?P<stem>.*)\((?P<n>\d+)\)(?P<ext>\.[^.]*)?$")
_JSON_DUP_RE = re.compile(r"^(?P<body>.*?)(?:\((?P<n>\d+)\))?\.json$", re.IGNORECASE)
_EDITED_RE = re.compile(r"-(edited|bearbeitet|modifié|modificato|editado|bewerkt)$", re.IGNORECASE)
_YEAR_FOLDER_RE = re.compile(r"^Photos from \d{4}$")
# IMG_20180701_095141, PXL_20210831_171945007, VID_20200315_..., 20251227_145103
_FN_DT_RE = re.compile(r"(?:^|[^\d])(20\d{2}|19\d{2})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})")
# Screenshot_2019-12-31-23-11-37
_FN_DT_DASH_RE = re.compile(r"(20\d{2}|19\d{2})-(\d{2})-(\d{2})[-_ ](\d{2})[-.](\d{2})[-.](\d{2})")


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in MOTION_EXTS:
        return "motion"
    if ext == "":
        return "noext"
    return "other"


def date_from_filename(name: str) -> datetime | None:
    """Local wall-clock datetime embedded in the filename, if any."""
    for rx in (_FN_DT_RE, _FN_DT_DASH_RE):
        m = rx.search(name)
        if m:
            try:
                dt = datetime(*map(int, m.groups()))
            except ValueError:
                continue
            if 1990 <= dt.year <= 2035:
                return dt
    return None


# ---------------------------------------------------------------------------
# Sidecar index (all zips)
# ---------------------------------------------------------------------------
def list_zips(takeout_path: str) -> list[str]:
    return sorted(glob.glob(os.path.join(takeout_path, "*.zip")))


def load_sidecars(zips: list[str]) -> tuple[dict, dict]:
    """
    Returns (members, sidecars):
      members  = {zip_name: [(member_name, size), ...]}
      sidecars = {member_name: parsed_json}
    Sidecar contents are cached per zip (keyed by size + mtime).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = {}
    if os.path.exists(SIDECAR_CACHE):
        try:
            with open(SIDECAR_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception as exc:
            logger.warning("Sidecar cache unreadable (%s) – rebuilding.", exc)

    members, sidecars, dirty = {}, {}, False
    for zp in zips:
        zname = os.path.basename(zp)
        st = os.stat(zp)
        key = f"{st.st_size}:{int(st.st_mtime)}"
        entry = cache.get(zname)
        if entry and entry.get("key") == key:
            members[zname] = [tuple(x) for x in entry["members"]]
            sidecars.update(entry["sidecars"])
            continue

        logger.info("Indexing %s …", zname)
        zmembers, zsidecars = [], {}
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                zmembers.append((info.filename, info.file_size))
                if info.filename.lower().endswith(".json") and info.file_size < 1_000_000:
                    try:
                        zsidecars[info.filename] = json.loads(zf.read(info))
                    except Exception:
                        pass
        cache[zname] = {"key": key, "members": zmembers, "sidecars": zsidecars}
        members[zname] = zmembers
        sidecars.update(zsidecars)
        dirty = True
        logger.info("  %d members, %d sidecars", len(zmembers), len(zsidecars))

    if dirty:
        with open(SIDECAR_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    return members, sidecars


def sidecar_media_key(json_basename: str) -> tuple[str, int] | None:
    """
    'IMG_1.jpg.supplemental-metadata(1).json' -> ('IMG_1.jpg', 1)
    'PXL_x.NIGHT.jpg.supplemental-.json'      -> ('PXL_x.NIGHT.jpg', 0)
    'Screenshot_..._com.solante.json'         -> ('Screenshot_..._com.solante', 0)  (truncated)
    """
    m = _JSON_DUP_RE.match(json_basename)
    if not m:
        return None
    body, n = m.group("body"), int(m.group("n") or 0)
    head, dot, tail = body.rpartition(".")
    if dot and SUPPLEMENTAL.startswith(tail) and head:
        body = head
    return body, n


class SidecarIndex:
    def __init__(self, sidecars: dict):
        self.by_key = {}                      # (folder, media_name_lower, dup) -> member
        self.by_title = {}                    # (folder, title_lower, dup) -> member
        self.by_folder = defaultdict(list)    # folder -> [(key_lower, dup, member)]
        self.data = sidecars
        for member, meta in sidecars.items():
            if "photoTakenTime" not in meta and "creationTime" not in meta:
                continue  # album metadata.json, print orders, etc.
            folder, base = os.path.split(member)
            parsed = sidecar_media_key(base)
            if not parsed:
                continue
            key, dup = parsed
            self.by_key.setdefault((folder, key.lower(), dup), member)
            title = meta.get("title")
            if title:
                self.by_title.setdefault((folder, title.lower(), dup), member)
            self.by_folder[folder].append((key.lower(), dup, member))

    def find(self, folder: str, name: str, dup: int) -> tuple[str | None, str]:
        low = name.lower()
        hit = self.by_key.get((folder, low, dup))
        if hit:
            return hit, "exact"
        hit = self.by_title.get((folder, low, dup))
        if hit:
            return hit, "title"
        # Truncated media name inside the sidecar filename.
        best = None
        for key, d, member in self.by_folder.get(folder, ()):
            if d == dup and len(key) >= 25 and low.startswith(key):
                if best is None or len(key) > len(best[0]):
                    best = (key, member)
        if best:
            return best[1], "truncated"
        return None, "none"


# ---------------------------------------------------------------------------
# Timezone resolution
# ---------------------------------------------------------------------------
_tzf = TimezoneFinder()


def geo_of(meta: dict) -> tuple[float, float] | None:
    for k in ("geoData", "geoDataExif"):
        g = meta.get(k) or {}
        lat, lon = g.get("latitude", 0.0), g.get("longitude", 0.0)
        if lat or lon:
            return lat, lon
    return None


class TzResolver:
    """GPS timezone, else timezone of the nearest geotagged item in time."""

    NEAREST_WINDOW = 3 * 24 * 3600

    def __init__(self):
        self._cache = {}
        self._points = []   # sorted (ts, tz)
        self._monthly = {}  # "YYYY-MM" -> dominant tz

    def tz_at(self, lat: float, lon: float) -> str | None:
        key = (round(lat, 2), round(lon, 2))
        if key not in self._cache:
            self._cache[key] = _tzf.timezone_at(lat=lat, lng=lon)
        return self._cache[key]

    def train(self, samples: list[tuple[int, str]]) -> None:
        self._points = sorted(samples)
        monthly = defaultdict(Counter)
        for ts, tz in self._points:
            monthly[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")][tz] += 1
        self._monthly = {m: c.most_common(1)[0][0] for m, c in monthly.items()}

    def guess(self, ts: int) -> tuple[str, str]:
        if self._points:
            i = bisect.bisect_left(self._points, (ts, ""))
            best = None
            for j in (i - 1, i):
                if 0 <= j < len(self._points):
                    d = abs(self._points[j][0] - ts)
                    if d <= self.NEAREST_WINDOW and (best is None or d < best[0]):
                        best = (d, self._points[j][1])
            if best:
                return best[1], "nearest"
        month = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
        if month in self._monthly:
            return self._monthly[month], "month"
        return DEFAULT_TZ, "default"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
@dataclass
class Item:
    zip: str
    member: str
    size: int
    kind: str
    sidecar: str | None = None
    match: str = "none"
    url: str | None = None
    taken_ts: int | None = None
    tz: str | None = None
    tz_source: str | None = None
    date: str | None = None          # YYYY_MM_DD (local)
    date_source: str | None = None
    role: str = "visible"            # visible | companion | duplicate | trash | archived | undated
    parent: str | None = None        # member of the photo a companion belongs to
    dest: str | None = None          # relative to output root
    extra: dict = field(default_factory=dict)


def _split_dup(base: str) -> tuple[str, int]:
    m = _DUP_RE.match(base)
    if m:
        return m.group("stem") + (m.group("ext") or ""), int(m.group("n"))
    return base, 0


def build_plan(members: dict, sidecars: dict) -> list[Item]:
    index = SidecarIndex(sidecars)
    tzr = TzResolver()

    items: list[Item] = []
    for zname, entries in members.items():
        for member, size in entries:
            if member.lower().endswith(".json") or "/Google Photos/" not in member:
                continue
            kind = kind_of(member)
            if kind == "other":
                continue
            items.append(Item(zip=zname, member=member, size=size, kind=kind))

    by_member = {it.member: it for it in items}
    # (folder, stem_lower, dup) -> image items, used to attach live/motion clips
    images_by_stem = defaultdict(list)
    for it in items:
        if it.kind == "image":
            folder, base = os.path.split(it.member)
            name, dup = _split_dup(base)
            stem = os.path.splitext(name)[0].lower()
            images_by_stem[(folder, stem, dup)].append(it)

    # 1. Sidecar matching
    for it in items:
        folder, base = os.path.split(it.member)
        name, dup = _split_dup(base)
        sc, how = index.find(folder, name, dup)
        if not sc:
            stem, ext = os.path.splitext(name)
            m = _EDITED_RE.search(stem)
            if m:
                sc, how = index.find(folder, stem[: m.start()] + ext, dup)
                if sc:
                    how = "edited"
        if sc:
            it.sidecar, it.match = sc, how
            meta = sidecars[sc]
            it.url = meta.get("url")
            ts = int((meta.get("photoTakenTime") or {}).get("timestamp") or 0)
            if ts <= 0:
                ts = int((meta.get("creationTime") or {}).get("timestamp") or 0)
            it.taken_ts = ts or None
            if meta.get("trashed") or folder.endswith("/Trash"):
                it.role = "trash"
            elif meta.get("archived"):
                it.role = "archived"

    # 2. Live photo / motion photo clips without their own sidecar.
    # "IMG_1(1).MP4" can be the clip of a second photo sharing the stem
    # (IMG_1.HEIC + IMG_1.JPG), so fall back to dup 0 and prefer unclaimed photos.
    claimed = set()
    clips = [it for it in items if not it.sidecar and it.kind in ("video", "motion", "noext")]
    for it in sorted(clips, key=lambda x: _split_dup(os.path.basename(x.member))[1]):
        folder, base = os.path.split(it.member)
        name, dup = _split_dup(base)
        stem = (os.path.splitext(name)[0] if it.kind != "noext" else name).lower()
        cands = []
        for d in dict.fromkeys((dup, 0)):
            cands = images_by_stem.get((folder, stem, d), [])
            if not cands and it.kind == "motion":
                # PXL_x.MP pairs with PXL_x.MP.jpg
                cands = images_by_stem.get((folder, stem + ".mp", d), [])
            if cands:
                break
        cands = [c for c in cands if c.sidecar] or cands
        if cands:
            parent = next((c for c in cands if c.member not in claimed), cands[0])
            claimed.add(parent.member)
            it.role = "companion"
            it.parent = parent.member
            it.match = "companion"

    # 3. "-edited" wins; the original becomes a hidden companion
    edited_urls = {it.url for it in items if it.match == "edited" and it.url}
    for it in items:
        if it.url in edited_urls and it.match != "edited" and it.role == "visible":
            it.role = "companion"
            it.extra["pre_edit_original"] = True

    # 4. Timezones: learn from geotagged items, then resolve every timestamp
    samples = []
    for it in items:
        if it.taken_ts and it.sidecar:
            g = geo_of(sidecars[it.sidecar])
            if g:
                tz = tzr.tz_at(*g)
                if tz:
                    it.tz, it.tz_source = tz, "gps"
                    samples.append((it.taken_ts, tz))
    tzr.train(samples)

    for it in items:
        if it.taken_ts:
            if not it.tz:
                it.tz, it.tz_source = tzr.guess(it.taken_ts)
            local = datetime.fromtimestamp(it.taken_ts, ZoneInfo(it.tz))
            it.date = local.strftime("%Y_%m_%d")
            it.date_source = "json"

    for it in items:
        if it.role == "companion" and it.parent and not it.date:
            p = by_member[it.parent]
            it.date, it.date_source, it.tz, it.taken_ts = p.date, "parent", p.tz, p.taken_ts

    for it in items:
        if not it.date:
            dt = date_from_filename(os.path.basename(it.member))
            if dt:
                it.date, it.date_source = dt.strftime("%Y_%m_%d"), "filename"
            elif it.role == "visible":
                it.role, it.date_source = "undated", "none"

    # 5. De-duplicate album copies. Prefer "Photos from YYYY" as canonical.
    def canon_rank(it: Item) -> tuple:
        folder = os.path.basename(os.path.dirname(it.member))
        return (0 if _YEAR_FOLDER_RE.match(folder) else 1, it.member)

    groups = defaultdict(list)
    for it in items:
        if it.role == "companion" and it.parent:
            pu = by_member[it.parent].url
            key = ("c", pu, os.path.basename(it.member).lower()) if pu else ("m", it.member)
        elif it.url:
            key = ("u", it.url, it.match == "edited", it.kind)
        else:
            key = ("n", os.path.basename(it.member).lower(), it.size)
        groups[key].append(it)
    for group in groups.values():
        if len(group) > 1:
            group.sort(key=canon_rank)
            for dup_it in group[1:]:
                dup_it.extra["duplicate_of"] = group[0].member
                dup_it.role = "duplicate"

    assign_destinations(items)
    return items


def assign_destinations(items: list[Item]) -> None:
    used = set()

    def unique(rel: str) -> str:
        if rel.lower() not in used:
            used.add(rel.lower())
            return rel
        root, ext = os.path.splitext(rel)
        n = 1
        while f"{root}_{n}{ext}".lower() in used:
            n += 1
        out = f"{root}_{n}{ext}"
        used.add(out.lower())
        return out

    for it in sorted(items, key=lambda x: x.member):
        base = os.path.basename(it.member)
        if it.role == "visible":
            it.dest = unique(f"{it.date}/{base}")
        elif it.role == "companion":
            it.dest = unique(f"{it.date or '_undated'}/.live/{base}")
        elif it.role == "archived":
            it.dest = unique(f"_archived/{it.date or 'undated'}/{base}")
        elif it.role == "trash":
            it.dest = unique(f"_trash/{base}")
        elif it.role == "undated":
            it.dest = unique(f"_undated/{base}")
        else:
            it.dest = None


def plan_report(items: list[Item]) -> dict:
    roles = Counter(it.role for it in items)
    report = {
        "media_members": len(items),
        "roles": dict(roles),
        "match": dict(Counter(it.match for it in items)),
        "date_source_visible": dict(Counter(it.date_source for it in items if it.role == "visible")),
        "tz_source_visible": dict(Counter(it.tz_source for it in items if it.role == "visible")),
        "kinds_visible": dict(Counter(it.kind for it in items if it.role == "visible")),
        "bytes_to_write_gb": round(sum(it.size for it in items if it.dest) / 1024**3, 1),
    }
    # Cross-check: local date vs date embedded in filename (camera wall clock)
    agree = disagree = 0
    for it in items:
        if it.role != "visible" or it.date_source != "json":
            continue
        dt = date_from_filename(os.path.basename(it.member))
        if dt:
            if dt.strftime("%Y_%m_%d") == it.date:
                agree += 1
            else:
                disagree += 1
    report["filename_date_check"] = {"agree": agree, "disagree": disagree}
    return report


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
_MAGIC = [(b"ftypqt", ".mov"), (b"ftypheic", ".heic"), (b"ftypmif1", ".heic"),
          (b"ftypisom", ".mp4"), (b"ftypmp42", ".mp4"), (b"\xff\xd8\xff", ".jpg"),
          (b"\x89PNG", ".png")]


def sniff_ext(head: bytes) -> str:
    for magic, ext in _MAGIC:
        if magic in head[:16]:
            return ext
    return ""


def execute(items: list[Item], out_root: str, takeout_path: str) -> None:
    os.makedirs(out_root, exist_ok=True)
    todo = defaultdict(list)
    for it in items:
        if it.dest:
            todo[it.zip].append(it)

    written = skipped = failed = 0
    for zname in sorted(todo):
        batch = sorted(todo[zname], key=lambda x: x.member)
        logger.info("=" * 60)
        logger.info("Extracting %d items from %s", len(batch), zname)
        with zipfile.ZipFile(os.path.join(takeout_path, zname)) as zf:
            for i, it in enumerate(batch, 1):
                if i % 2000 == 0:
                    logger.info("  %s: %d/%d", zname, i, len(batch))
                dest = os.path.join(out_root, it.dest)
                try:
                    if os.path.exists(dest) and os.path.getsize(dest) == it.size:
                        skipped += 1
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    tmp = dest + ".part"
                    with zf.open(it.member) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
                    os.replace(tmp, dest)
                    if it.taken_ts:
                        os.utime(dest, (it.taken_ts, it.taken_ts))
                    written += 1
                except Exception as exc:
                    failed += 1
                    logger.error("Failed %s -> %s (%s: %s)", it.member, it.dest, type(exc).__name__, exc)

    # Extensionless clips: add a real extension so players recognise them
    for it in items:
        if it.dest and it.kind == "noext":
            dest = os.path.join(out_root, it.dest)
            if os.path.exists(dest):
                with open(dest, "rb") as f:
                    ext = sniff_ext(f.read(32))
                if ext:
                    os.replace(dest, dest + ext)
                    it.dest += ext

    manifest_dir = os.path.join(out_root, ".manifests")
    os.makedirs(manifest_dir, exist_ok=True)
    with open(os.path.join(manifest_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(),
                   "report": plan_report(items),
                   "items": [asdict(it) for it in items]}, f)
    logger.info("Written %d, already present %d, failed %d", written, skipped, failed)
    if failed:
        sys.exit(2)


# ---------------------------------------------------------------------------
# Sampling / verification against EXIF
# ---------------------------------------------------------------------------
def exif_dates(paths: list[str]) -> dict:
    if not paths:
        return {}
    cmd = ["exiftool", "-json", "-q", "-DateTimeOriginal", "-CreateDate",
           "-OffsetTimeOriginal", "-api", "QuickTimeUTC=0"] + paths
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return {d["SourceFile"]: d for d in json.loads(res.stdout or "[]")}
    except json.JSONDecodeError:
        return {}


def sample(items: list[Item], n: int, takeout_path: str, seed: int) -> None:
    rng = random.Random(seed)
    visible = [it for it in items if it.role == "visible"]
    picks = rng.sample(visible, min(n, len(visible)))
    hidden = [it for it in items if it.role in ("companion", "duplicate", "trash", "archived")]
    picks_hidden = rng.sample(hidden, min(10, len(hidden)))

    tmpdir = tempfile.mkdtemp(prefix="takeout_sample_")
    paths = {}
    by_zip = defaultdict(list)
    for it in picks:
        by_zip[it.zip].append(it)
    for zname, its in by_zip.items():
        with zipfile.ZipFile(os.path.join(takeout_path, zname)) as zf:
            for it in its:
                p = os.path.join(tmpdir, f"{len(paths):03d}_{os.path.basename(it.member)}")
                with zf.open(it.member) as src, open(p, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                paths[it.member] = p
    exif = exif_dates(list(paths.values()))

    ok = mismatch = noexif = 0
    print(f"\n{'#':>2}  {'file':<40} {'json UTC':<17} {'tz':<18} {'date':<10} {'exif local':<19} verdict")
    for i, it in enumerate(picks, 1):
        e = exif.get(paths[it.member], {})
        raw = e.get("DateTimeOriginal") or e.get("CreateDate") or ""
        exif_date = raw[:10].replace(":", "_") if raw and not raw.startswith("0000") else ""
        utc = datetime.fromtimestamp(it.taken_ts, timezone.utc).strftime("%Y-%m-%d %H:%M") if it.taken_ts else "-"
        if not exif_date:
            verdict, noexif = "no-exif", noexif + 1
        elif exif_date == it.date:
            verdict, ok = "OK", ok + 1
        else:
            verdict, mismatch = "DIFF", mismatch + 1
        print(f"{i:>2}  {os.path.basename(it.member)[:40]:<40} {utc:<17} "
              f"{(it.tz or '-')[:12]+'/'+(it.tz_source or '-')[:5]:<18} {it.date:<10} {raw[:19]:<19} {verdict}")
    print(f"\nEXIF agrees: {ok}, differs: {mismatch}, no EXIF date: {noexif}")

    print("\nHidden from the timeline (sample):")
    for it in picks_hidden:
        why = it.role
        if it.role == "duplicate":
            why += f" of {it.extra.get('duplicate_of')}"
        elif it.role == "companion":
            why += " (pre-edit original)" if it.extra.get("pre_edit_original") else f" of {os.path.basename(it.parent or '')}"
        print(f"  {it.member}  ->  {why}")
    shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "sample", "run"])
    ap.add_argument("--takeout", default=TAKEOUT_PATH)
    ap.add_argument("--out", default=PROCESSING_PATH)
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    zips = list_zips(args.takeout)
    if not zips:
        logger.error("No zip archives in %s", args.takeout)
        sys.exit(1)
    logger.info("Takeout processor v3: %d zip(s) in %s", len(zips), args.takeout)

    members, sidecars = load_sidecars(zips)
    items = build_plan(members, sidecars)
    report = plan_report(items)
    logger.info("Plan: %s", json.dumps(report, indent=2))

    if args.command == "sample":
        sample(items, args.n, args.takeout, args.seed)
    elif args.command == "run":
        free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(args.out)) or "/").free / 1024**3
        if free_gb < report["bytes_to_write_gb"] * 1.02:
            logger.error("Not enough space: need %.1f GB, have %.1f GB", report["bytes_to_write_gb"], free_gb)
            sys.exit(1)
        execute(items, args.out, args.takeout)


if __name__ == "__main__":
    main()
