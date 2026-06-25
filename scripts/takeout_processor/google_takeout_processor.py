#!/usr/bin/env python3
"""
Google Takeout photo/video processor — v2.

Extracts Google Takeout zip archives one at a time, organises every media file
into PROCESSING_PATH/<YYYY_MM_DD>/ folders, then deletes the temporary
extraction tree.

Date detection uses a 4-level fallback chain:
  1. Exact JSON sidecar  (file.supplemental-metadata.json)
  2. Stem-match sidecar  (same filename stem, different extension's sidecar)
  3. Filename date parse  (IMG_20180701_095141.jpg → 2018_07_01)
  4. Zip folder year      ("Photos from 2022" → 2022_01_01)

After each zip is fully processed a per-zip checksum manifest is written to
PROCESSING_PATH/.manifests/<archive_name>.json so every source→dest mapping
is auditable.
"""

import os
import re
import json
import shutil
import zipfile
import glob
import sys
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TAKEOUT_PATH    = "/other_hdd/google_phots_all_take_out"
PROCESSING_PATH = "/other_hdd/google_phots_all_take_for_processing"
MANIFEST_DIR    = os.path.join(PROCESSING_PATH, ".manifests")

DISK_HEADROOM_FACTOR = 1.3

# ---------------------------------------------------------------------------
# Logging  (rotating file + console)
# ---------------------------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file   = os.path.join(script_dir, "google_takeout_processor.log")

_rotating_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[_rotating_handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------
STATE_FILE = os.path.join(script_dir, "processed_archives.json")


def _load_state() -> set:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f).get("processed", []))
        except Exception as exc:
            logger.warning("Could not read state file (%s: %s) – starting fresh.", type(exc).__name__, exc)
    return set()


def _save_state(processed: set) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed": sorted(processed)}, f, indent=2)
    except Exception as exc:
        logger.error("Could not save state file (%s: %s).", type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Media & sidecar extensions
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Regex for dates embedded in filenames: IMG_20180701_095141, VID_20200315, etc.
_FILENAME_DATE_RE = re.compile(r"(?:^|[_\-])(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:[_\-]|$)")

# Regex for folder names like "Photos from 2022"
_FOLDER_YEAR_RE = re.compile(r"Photos from (\d{4})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_folder_name(name: str) -> str:
    return re.sub(r"[()\"'\\]", "", name).strip()


def _unique_dest(dest_path: str) -> str:
    if not os.path.exists(dest_path):
        return dest_path
    p = Path(dest_path)
    suffix = p.suffix
    stem   = p.name[: len(p.name) - len(suffix)]
    parent = p.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not os.path.exists(candidate):
            return str(candidate)
        counter += 1


def _free_bytes(path: str) -> int:
    return shutil.disk_usage(path).free


def _check_disk_space(zip_path: str, extract_to: str) -> bool:
    zip_size  = os.path.getsize(zip_path)
    needed    = int(zip_size * DISK_HEADROOM_FACTOR)
    available = _free_bytes(extract_to)
    if available < needed:
        logger.error(
            "Not enough disk space to extract %s. Need ~%d GB, have %d GB free.",
            os.path.basename(zip_path), needed // (1024**3), available // (1024**3),
        )
        return False
    return True


def _validate_zip(zip_path: str) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
        if bad is not None:
            logger.error("Corrupt entry in %s: %s", os.path.basename(zip_path), bad)
            return False
        return True
    except zipfile.BadZipFile as exc:
        logger.error("Bad zip file %s: %s", os.path.basename(zip_path), exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error validating %s (%s: %s)", os.path.basename(zip_path), type(exc).__name__, exc)
        return False


# ---------------------------------------------------------------------------
# Date detection — 4-level fallback
# ---------------------------------------------------------------------------

def _date_from_json(json_path: str) -> str | None:
    """Level 1 & 2: read photoTakenTime / creationTime from a JSON sidecar."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        for key in ("photoTakenTime", "creationTime"):
            ts_str = metadata.get(key, {}).get("timestamp")
            if ts_str:
                ts = int(ts_str)
                if ts > 0:
                    return datetime.fromtimestamp(ts).strftime("%Y_%m_%d")
    except Exception:
        pass
    return None


def _date_from_filename(filename: str) -> str | None:
    """Level 3: parse YYYYMMDD from filenames like IMG_20180701_095141.jpg."""
    m = _FILENAME_DATE_RE.search(filename)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
        y = int(year)
        if 1990 <= y <= 2030:
            return f"{year}_{month}_{day}"
    return None


def _date_from_folder(zip_internal_path: str) -> str | None:
    """Level 4: extract year from folder name like 'Photos from 2022' → 2022_01_01."""
    m = _FOLDER_YEAR_RE.search(zip_internal_path)
    if m:
        year = m.group(1)
        y = int(year)
        if 1990 <= y <= 2030:
            return f"{year}_01_01"
    return None


# ---------------------------------------------------------------------------
# Build sidecar index for a folder
# ---------------------------------------------------------------------------

def _build_sidecar_index(search_path: str) -> dict:
    """
    Walk search_path and build a lookup:
      {(folder, stem): [list of json paths]}

    This allows us to match IMG_2635.MP4 to IMG_2635.JPG.supplemental-metadata.json
    by sharing the stem 'IMG_2635'.
    """
    index = defaultdict(list)
    for root, _dirs, files in os.walk(search_path):
        for f in files:
            if not f.lower().endswith(".json"):
                continue
            full_path = os.path.join(root, f)
            # Extract stem: remove .supplemental-metadata.json or .json suffix
            cleaned = f
            if cleaned.endswith(".supplemental-metadata.json"):
                cleaned = cleaned[:-len(".supplemental-metadata.json")]
            elif cleaned.endswith(".json"):
                cleaned = cleaned[:-len(".json")]
            stem = os.path.splitext(cleaned)[0]
            index[(root, stem)].append(full_path)
    return index


# ---------------------------------------------------------------------------
# Core processing for one archive
# ---------------------------------------------------------------------------

def process_single_archive(zip_file: str) -> bool:
    archive_name = os.path.basename(zip_file)
    safe_stem    = _safe_folder_name(archive_name.replace(".zip", ""))
    temp_path    = os.path.join(TAKEOUT_PATH, f"temp_extract_{safe_stem}")

    logger.info("=" * 60)
    logger.info("Archive: %s", archive_name)

    # 1. Validate
    logger.info("Validating archive integrity…")
    if not _validate_zip(zip_file):
        return False

    # 2. Disk space
    logger.info("Checking disk space…")
    if not _check_disk_space(zip_file, TAKEOUT_PATH):
        return False

    # 3. Extract
    try:
        logger.info("Extracting…")
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(temp_path)
            # Count expected media files from the zip listing
            zip_media_count = sum(
                1 for n in zf.namelist()
                if os.path.splitext(n.lower())[1] in MEDIA_EXTS
            )
        logger.info("Extraction complete. Expected media files: %d", zip_media_count)
    except Exception as exc:
        logger.error("Extraction failed (%s: %s).", type(exc).__name__, exc)
        shutil.rmtree(temp_path, ignore_errors=True)
        return False

    # 4. Build sidecar index for the entire extracted tree
    logger.info("Building JSON sidecar index…")
    sidecar_index = _build_sidecar_index(temp_path)
    logger.info("Sidecar index: %d unique (folder, stem) entries.", len(sidecar_index))

    # 5. Find all media files
    media_files = []
    for root, _dirs, files in os.walk(temp_path):
        for f in files:
            if os.path.splitext(f.lower())[1] in MEDIA_EXTS:
                media_files.append(os.path.join(root, f))

    logger.info("Found %d media files to organise.", len(media_files))

    # 6. Organise
    manifest = {}  # source_zip_path → dest_path
    date_method_counts = {"json_exact": 0, "json_stem": 0, "filename": 0, "folder": 0, "unknown": 0}
    processed_count = 0
    total = len(media_files)

    for i, media_path in enumerate(media_files, 1):
        if i % 500 == 0 or i == total:
            logger.info("  Progress: %d/%d (%.1f%%)", i, total, i / total * 100)

        try:
            media_basename = os.path.basename(media_path)
            media_dir = os.path.dirname(media_path)
            media_stem = os.path.splitext(media_basename)[0]

            # Compute the original zip-internal path for the manifest
            zip_internal = os.path.relpath(media_path, temp_path)

            # --- Level 1: Exact JSON sidecar ---
            date_folder = None
            matched_json = None

            exact_suppl = media_path + ".supplemental-metadata.json"
            exact_json  = media_path + ".json"

            if os.path.exists(exact_suppl):
                date_folder = _date_from_json(exact_suppl)
                matched_json = exact_suppl
                if date_folder:
                    date_method_counts["json_exact"] += 1

            if not date_folder and os.path.exists(exact_json):
                date_folder = _date_from_json(exact_json)
                matched_json = exact_json
                if date_folder:
                    date_method_counts["json_exact"] += 1

            # --- Level 2: Stem-match sidecar ---
            if not date_folder:
                stem_jsons = sidecar_index.get((media_dir, media_stem), [])
                for sj in stem_jsons:
                    date_folder = _date_from_json(sj)
                    if date_folder:
                        matched_json = sj
                        date_method_counts["json_stem"] += 1
                        break

            # --- Level 3: Filename date pattern ---
            if not date_folder:
                date_folder = _date_from_filename(media_basename)
                if date_folder:
                    date_method_counts["filename"] += 1

            # --- Level 4: Folder name year ---
            if not date_folder:
                date_folder = _date_from_folder(zip_internal)
                if date_folder:
                    date_method_counts["folder"] += 1

            # --- Fallback: unknown ---
            if not date_folder:
                date_folder = "unknown_date"
                date_method_counts["unknown"] += 1

            # --- Move media file ---
            dest_dir = Path(PROCESSING_PATH) / date_folder
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_media = _unique_dest(str(dest_dir / media_basename))
            shutil.move(media_path, dest_media)
            manifest[zip_internal] = os.path.relpath(dest_media, PROCESSING_PATH)

            # --- Move matched JSON sidecar alongside media ---
            if matched_json and os.path.exists(matched_json):
                json_basename = os.path.basename(matched_json)
                dest_json = _unique_dest(str(dest_dir / json_basename))
                shutil.move(matched_json, dest_json)

            processed_count += 1

        except Exception as exc:
            logger.error("Error processing %s (%s: %s) – skipping.", media_path, type(exc).__name__, exc)

    logger.info("Organised %d/%d media files.", processed_count, total)
    logger.info("Date method breakdown: %s", dict(date_method_counts))

    # 7. Write manifest
    try:
        os.makedirs(MANIFEST_DIR, exist_ok=True)
        manifest_path = os.path.join(MANIFEST_DIR, f"{safe_stem}.json")
        manifest_data = {
            "archive": archive_name,
            "expected_media": zip_media_count,
            "processed_media": processed_count,
            "date_methods": dict(date_method_counts),
            "files": manifest,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        logger.info("Manifest written: %s", manifest_path)
    except Exception as exc:
        logger.error("Could not write manifest (%s: %s).", type(exc).__name__, exc)

    # 8. Verify counts
    if processed_count != zip_media_count:
        logger.warning(
            "⚠️  COUNT MISMATCH for %s: zip had %d media, processed %d (diff=%d)",
            archive_name, zip_media_count, processed_count, zip_media_count - processed_count,
        )
    else:
        logger.info("✅ Count verified: %d/%d media files processed.", processed_count, zip_media_count)

    # 9. Cleanup
    logger.info("Cleaning up extracted files…")
    shutil.rmtree(temp_path, ignore_errors=True)

    logger.info("Archive %s complete.", archive_name)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 60)
    logger.info("Google Takeout processor v2 started at %s", datetime.now().isoformat())
    logger.info("TAKEOUT_PATH    : %s", TAKEOUT_PATH)
    logger.info("PROCESSING_PATH : %s", PROCESSING_PATH)

    if not os.path.exists(TAKEOUT_PATH):
        logger.error("Takeout folder does not exist: %s → aborting.", TAKEOUT_PATH)
        sys.exit(1)

    free_gb = _free_bytes(TAKEOUT_PATH) / (1024**3)
    logger.info("Free space: %.1f GB", free_gb)

    Path(PROCESSING_PATH).mkdir(parents=True, exist_ok=True)

    zip_files = sorted(glob.glob(os.path.join(TAKEOUT_PATH, "*.zip")))
    logger.info("Found %d zip archive(s).", len(zip_files))
    for zf in zip_files:
        logger.info("  %-60s  %.2f GB", os.path.basename(zf), os.path.getsize(zf) / (1024**3))

    if not zip_files:
        logger.warning("No zip archives found. Nothing to do.")
        return

    already_done = _load_state()
    pending = [z for z in zip_files if os.path.basename(z) not in already_done]

    if len(zip_files) - len(pending) > 0:
        logger.info("Skipping %d already-processed archive(s).", len(zip_files) - len(pending))
    logger.info("Archives to process: %d", len(pending))

    successful = 0
    failed_archives = []
    grand_total_methods = {"json_exact": 0, "json_stem": 0, "filename": 0, "folder": 0, "unknown": 0}

    for i, zip_file in enumerate(pending, 1):
        name = os.path.basename(zip_file)
        logger.info("Processing archive %d/%d: %s", i, len(pending), name)

        if process_single_archive(zip_file):
            successful += 1
            already_done.add(name)
            _save_state(already_done)

            # Accumulate method counts from manifest
            try:
                safe = _safe_folder_name(name.replace(".zip", ""))
                mf = os.path.join(MANIFEST_DIR, f"{safe}.json")
                with open(mf) as f:
                    mdata = json.load(f)
                for k, v in mdata.get("date_methods", {}).items():
                    grand_total_methods[k] = grand_total_methods.get(k, 0) + v
            except Exception:
                pass
        else:
            failed_archives.append(name)
            logger.error("Archive FAILED: %s", name)

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Archives processed: %d/%d", successful, len(pending))
    logger.info("  Date method totals: %s", grand_total_methods)
    if failed_archives:
        logger.error("  Failed archives (%d): %s", len(failed_archives), failed_archives)

    # Count output
    total_output = 0
    folder_count = 0
    for d in os.listdir(PROCESSING_PATH):
        dp = os.path.join(PROCESSING_PATH, d)
        if os.path.isdir(dp) and d not in (".manifests", ".thumb_cache"):
            count = sum(1 for f in os.listdir(dp) if os.path.splitext(f.lower())[1] in MEDIA_EXTS)
            if count > 0:
                folder_count += 1
                total_output += count

    logger.info("  Output: %d media files across %d date folders", total_output, folder_count)
    logger.info("Processor finished at %s", datetime.now().isoformat())


if __name__ == "__main__":
    main()