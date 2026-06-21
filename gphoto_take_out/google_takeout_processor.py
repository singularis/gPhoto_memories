#!/usr/bin/env python3
"""
Google Takeout photo/video processor.

Extracts Google Takeout zip archives one at a time to conserve disk space,
organises every media file into PROCESSING_PATH/<YYYY_MM_DD>/ folders using
the embedded JSON metadata (or file mtime as a fallback), then deletes the
temporary extraction tree.

Key improvements over original:
  - Disk-space guard before each extraction (~1.2× zip size required free)
  - Archive integrity check (CRC) before extraction
  - Resume support: processed archives are recorded in a state file so a
    re-run after a crash/reboot skips already-completed zips
  - Correct duplicate-filename counter for any extension (including
    .supplemental-metadata.json)
  - Videos (.mp4 .mov .avi .mkv) are now collected alongside images
  - Log rotation (10 MB cap, 3 backups) so the log never grows unbounded
  - Sanitised temp-folder names (parentheses stripped) to avoid shell issues
  - Actionable error messages include the full exception type
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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TAKEOUT_PATH    = "/other_hdd/google_phots_all_take_out"
PROCESSING_PATH = "/other_hdd/google_phots_all_take_for_processing"

# Fraction of the zip file size that must be free on the target filesystem
# before extraction starts (1.3 = 30 % headroom for metadata overhead etc.)
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
# State file – tracks which archives have already been processed successfully
# ---------------------------------------------------------------------------
STATE_FILE = os.path.join(script_dir, "processed_archives.json")


def _load_state() -> set:
    """Return the set of archive basenames that were already processed."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("processed", []))
        except Exception as exc:
            logger.warning("Could not read state file (%s: %s) – starting fresh.", type(exc).__name__, exc)
    return set()


def _save_state(processed: set) -> None:
    """Persist the set of completed archive basenames."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed": sorted(processed)}, f, indent=2)
    except Exception as exc:
        logger.error("Could not save state file (%s: %s).", type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Media extensions
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_folder_name(name: str) -> str:
    """Strip characters that are awkward in shell / filesystem paths."""
    return re.sub(r"[()\"'\\]", "", name).strip()


def _unique_dest(dest_path: str) -> str:
    """
    Return a destination path that does not collide with an existing file.

    Handles any number of dots in the filename correctly, e.g.
      photo.supplemental-metadata.json  →  photo.supplemental-metadata_1.json
      IMG_1234.JPG                       →  IMG_1234_1.JPG
    """
    if not os.path.exists(dest_path):
        return dest_path
    p = Path(dest_path)
    # suffix = last extension only (e.g. ".json" or ".JPG")
    suffix = p.suffix
    stem   = p.name[: len(p.name) - len(suffix)]   # everything before last ext
    parent = p.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not os.path.exists(candidate):
            return str(candidate)
        counter += 1


def _free_bytes(path: str) -> int:
    """Return free bytes on the filesystem containing *path*."""
    stat = shutil.disk_usage(path)
    return stat.free


def _check_disk_space(zip_path: str, extract_to: str) -> bool:
    """
    Return True if there is enough free space to extract *zip_path*.
    Uses DISK_HEADROOM_FACTOR × zip size as a conservative estimate.
    """
    zip_size  = os.path.getsize(zip_path)
    needed    = int(zip_size * DISK_HEADROOM_FACTOR)
    available = _free_bytes(extract_to)
    if available < needed:
        logger.error(
            "Not enough disk space to extract %s. "
            "Need ~%d GB, have %d GB free on %s.",
            os.path.basename(zip_path),
            needed  // (1024 ** 3),
            available // (1024 ** 3),
            extract_to,
        )
        return False
    return True


def _validate_zip(zip_path: str) -> bool:
    """
    Run a CRC-only integrity test on the zip.
    Returns True if the archive is intact, False (+ logs) if corrupt.
    """
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
        logger.error(
            "Unexpected error validating %s (%s: %s)",
            os.path.basename(zip_path), type(exc).__name__, exc,
        )
        return False


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def create_processing_folder() -> None:
    """Create the processing folder if it doesn't exist."""
    Path(PROCESSING_PATH).mkdir(parents=True, exist_ok=True)
    logger.info("Processing folder ready: %s", PROCESSING_PATH)


def list_zip_archives() -> list:
    """List all zip archives in the takeout folder, sorted by name."""
    zip_files = sorted(glob.glob(os.path.join(TAKEOUT_PATH, "*.zip")))
    logger.info("Found %d zip archive(s):", len(zip_files))
    for zf in zip_files:
        size_gb = os.path.getsize(zf) / (1024 ** 3)
        logger.info("  %-60s  %.2f GB", os.path.basename(zf), size_gb)
    return zip_files


def get_all_media_files_from_path(search_path: str) -> list:
    """
    Recursively scan *search_path* for media files.
    Returns a list of (media_path, json_path_or_None) tuples.
    """
    media_files = []
    for root, _dirs, files in os.walk(search_path):
        for file in files:
            if not any(file.lower().endswith(ext) for ext in MEDIA_EXTS):
                continue
            file_path = os.path.join(root, file)

            # Try .supplemental-metadata.json first, then plain .json sidecar
            supplemental = file_path + ".supplemental-metadata.json"
            base_json    = os.path.splitext(file_path)[0] + ".json"

            if os.path.exists(supplemental):
                media_files.append((file_path, supplemental))
            elif os.path.exists(base_json):
                media_files.append((file_path, base_json))
            else:
                logger.debug("No metadata sidecar found for: %s", file)
                media_files.append((file_path, None))

    return media_files


def get_date_from_metadata(json_file: str) -> str | None:
    """Extract a YYYY_MM_DD string from a Google Takeout JSON sidecar."""
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        for key in ("photoTakenTime", "creationTime"):
            entry = metadata.get(key, {})
            ts_str = entry.get("timestamp")
            if ts_str:
                try:
                    ts = int(ts_str)
                    if ts > 0:
                        return datetime.fromtimestamp(ts).strftime("%Y_%m_%d")
                except (ValueError, OSError):
                    pass  # fall through to next key / fallback

    except json.JSONDecodeError as exc:
        logger.warning("Malformed JSON in %s: %s", json_file, exc)
    except Exception as exc:
        logger.error("Error reading metadata %s (%s: %s)", json_file, type(exc).__name__, exc)

    return None


def get_date_from_file(file_path: str) -> str:
    """Return YYYY_MM_DD from file mtime; 'unknown_date' if that fails too."""
    try:
        ts = os.path.getmtime(file_path)
        return datetime.fromtimestamp(ts).strftime("%Y_%m_%d")
    except Exception as exc:
        logger.error("Cannot read mtime for %s (%s: %s)", file_path, type(exc).__name__, exc)
        return "unknown_date"


def process_media_files(media_files: list) -> int:
    """
    Move every media file (and its sidecar JSON) into
    PROCESSING_PATH/<YYYY_MM_DD>/.

    Returns the number of successfully processed files.
    """
    processed_count = 0
    total = len(media_files)
    logger.info("Organising %d media file(s)…", total)

    for i, (media_file, json_file) in enumerate(media_files, 1):
        try:
            if i % 100 == 0 or i == total:
                logger.info("  Progress: %d/%d (%.1f%%)", i, total, i / total * 100)

            # --- Determine destination date folder ---
            date_folder = (get_date_from_metadata(json_file) if json_file else None) \
                          or get_date_from_file(media_file)

            dest_dir = Path(PROCESSING_PATH) / date_folder
            dest_dir.mkdir(parents=True, exist_ok=True)

            # --- Move media file ---
            dest_media = _unique_dest(str(dest_dir / os.path.basename(media_file)))
            shutil.move(media_file, dest_media)
            logger.debug("Moved: %s → %s/%s", os.path.basename(media_file), date_folder, os.path.basename(dest_media))

            # --- Move sidecar JSON ---
            if json_file and os.path.exists(json_file):
                dest_json = _unique_dest(str(dest_dir / os.path.basename(json_file)))
                shutil.move(json_file, dest_json)

            processed_count += 1

        except OSError as exc:
            logger.error(
                "OS error processing %s (%s: %s) – skipping.",
                media_file, type(exc).__name__, exc,
            )
        except Exception as exc:
            logger.error(
                "Unexpected error processing %s (%s: %s) – skipping.",
                media_file, type(exc).__name__, exc,
            )

    logger.info("Organised %d/%d media file(s) successfully.", processed_count, total)
    return processed_count


def process_single_archive(zip_file: str) -> bool:
    """
    Full lifecycle for one archive:
      validate → disk-space check → extract → organise → cleanup.
    Returns True on success, False on any unrecoverable error.
    """
    archive_name = os.path.basename(zip_file)
    # Sanitise name for use as a directory component
    safe_stem    = _safe_folder_name(archive_name.replace(".zip", ""))
    temp_path    = os.path.join(TAKEOUT_PATH, f"temp_extract_{safe_stem}")

    logger.info("=" * 60)
    logger.info("Archive: %s", archive_name)

    # 1. Integrity check
    logger.info("Validating archive integrity…")
    if not _validate_zip(zip_file):
        return False

    # 2. Disk space
    logger.info("Checking disk space…")
    # Use the parent of temp_path as the reference filesystem
    if not _check_disk_space(zip_file, TAKEOUT_PATH):
        return False

    # 3. Extract
    try:
        logger.info("Extracting…")
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(temp_path)
        logger.info("Extraction complete.")
    except zipfile.BadZipFile as exc:
        logger.error("Extraction failed – corrupt archive (%s).", exc)
        shutil.rmtree(temp_path, ignore_errors=True)
        return False
    except OSError as exc:
        logger.error("Extraction failed – OS error (%s: %s).", type(exc).__name__, exc)
        shutil.rmtree(temp_path, ignore_errors=True)
        return False
    except Exception as exc:
        logger.error("Extraction failed – unexpected error (%s: %s).", type(exc).__name__, exc)
        shutil.rmtree(temp_path, ignore_errors=True)
        return False

    # 4. Organise
    try:
        media_files = get_all_media_files_from_path(temp_path)
        if media_files:
            logger.info("Found %d media file(s) in archive.", len(media_files))
            process_media_files(media_files)
        else:
            logger.warning("No media files found in archive.")
    except Exception as exc:
        logger.error("Error during organisation phase (%s: %s).", type(exc).__name__, exc)
        # Don't return False here – we still want to clean up
    finally:
        # 5. Cleanup extracted tree regardless of success/failure above
        logger.info("Cleaning up extracted files…")
        shutil.rmtree(temp_path, ignore_errors=True)

    logger.info("Archive %s complete.", archive_name)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("Google Takeout processor started at %s", datetime.now().isoformat())
    logger.info("TAKEOUT_PATH    : %s", TAKEOUT_PATH)
    logger.info("PROCESSING_PATH : %s", PROCESSING_PATH)

    # Sanity checks
    if not os.path.exists(TAKEOUT_PATH):
        logger.error("Takeout folder does not exist: %s  →  aborting.", TAKEOUT_PATH)
        sys.exit(1)

    free_gb = _free_bytes(TAKEOUT_PATH) / (1024 ** 3)
    logger.info("Free space on takeout filesystem: %.1f GB", free_gb)

    create_processing_folder()

    zip_files = list_zip_archives()

    if not zip_files:
        # Fallback: no zips – organise loose files already in TAKEOUT_PATH
        logger.info("No zip archives found – organising loose files in TAKEOUT_PATH…")
        media_files = get_all_media_files_from_path(TAKEOUT_PATH)
        if not media_files:
            logger.warning("No media files found. Nothing to do.")
            return
        process_media_files(media_files)
        logger.info("Done.")
        return

    # Load resume state
    already_done = _load_state()
    skipped = [z for z in zip_files if os.path.basename(z) in already_done]
    pending  = [z for z in zip_files if os.path.basename(z) not in already_done]

    if skipped:
        logger.info("Skipping %d already-processed archive(s).", len(skipped))
    logger.info("Archives to process: %d", len(pending))

    successful = 0
    failed_archives = []

    for i, zip_file in enumerate(pending, 1):
        name = os.path.basename(zip_file)
        logger.info("Processing archive %d/%d: %s", i, len(pending), name)

        if process_single_archive(zip_file):
            successful += 1
            already_done.add(name)
            _save_state(already_done)          # persist after every success
        else:
            failed_archives.append(name)
            logger.error("Archive FAILED: %s", name)

    logger.info("=" * 60)
    logger.info("Summary: %d/%d archives processed successfully.", successful, len(pending))
    if failed_archives:
        logger.error("Failed archives (%d):", len(failed_archives))
        for fa in failed_archives:
            logger.error("  - %s", fa)
    logger.info("Output folder : %s", PROCESSING_PATH)
    logger.info("State file    : %s", STATE_FILE)
    logger.info("Log file      : %s", log_file)
    logger.info("Processor finished at %s", datetime.now().isoformat())


if __name__ == "__main__":
    main()