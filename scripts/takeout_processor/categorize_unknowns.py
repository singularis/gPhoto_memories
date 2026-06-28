#!/usr/bin/env python3
import os
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROCESSING_PATH = "/other_hdd/google_phots_all_take_for_processing"
UNKNOWN_DIR = os.path.join(PROCESSING_PATH, "unknown_date")

def _unique_dest(dest_path_str: str) -> str:
    """If file exists, append _1, _2 etc to stem."""
    p = Path(dest_path_str)
    if not p.exists():
        return dest_path_str
    
    stem = p.stem
    ext = p.suffix
    directory = p.parent
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{ext}"
        new_path = directory / new_name
        if not new_path.exists():
            return str(new_path)
        counter += 1

def main():
    if not os.path.exists(UNKNOWN_DIR):
        logger.info(f"Directory {UNKNOWN_DIR} does not exist. Nothing to do.")
        return

    files = [os.path.join(UNKNOWN_DIR, f) for f in os.listdir(UNKNOWN_DIR) if os.path.isfile(os.path.join(UNKNOWN_DIR, f))]
    total_files = len(files)
    logger.info(f"Found {total_files} files in {UNKNOWN_DIR}. Running exiftool...")

    if total_files == 0:
        return

    # Run exiftool on the directory
    # -json: output JSON
    # -DateTimeOriginal -CreateDate: Only extract these to save memory and time
    # -q: quiet
    cmd = ["exiftool", "-json", "-DateTimeOriginal", "-CreateDate", UNKNOWN_DIR]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        metadata_list = json.loads(result.stdout)
    except Exception as e:
        logger.error(f"Failed to run exiftool or parse output: {e}")
        metadata_list = []

    # Map filename to metadata dict
    metadata_map = {item.get('SourceFile'): item for item in metadata_list}

    processed = 0
    method_counts = {'exif_datetimeoriginal': 0, 'exif_createdate': 0, 'fallback_mtime': 0}

    for file_path in files:
        if processed % 1000 == 0:
            logger.info(f"Progress: {processed}/{total_files} ({(processed/total_files)*100:.1f}%)")
        
        meta = metadata_map.get(file_path, {})
        date_str = None
        method = None

        # ExifTool formats dates like "2024:05:01 12:34:56"
        for tag in ['DateTimeOriginal', 'CreateDate']:
            val = meta.get(tag)
            if val and len(val) >= 10:
                # Replace colons in the date part (first 10 chars) with underscores
                d_part = val[:10].replace(':', '_')
                if len(d_part) == 10 and d_part.count('_') == 2:
                    date_str = d_part
                    method = f"exif_{tag.lower()}"
                    break
        
        if not date_str:
            # Fallback to filesystem mtime
            try:
                mtime = os.path.getmtime(file_path)
                dt = datetime.fromtimestamp(mtime)
                date_str = dt.strftime("%Y_%m_%d")
                method = "fallback_mtime"
            except Exception as e:
                logger.error(f"Could not get mtime for {file_path}: {e}")
                date_str = "1970_01_01"
                method = "fallback_mtime"

        if method:
            method_counts[method] += 1

        dest_dir = os.path.join(PROCESSING_PATH, date_str)
        os.makedirs(dest_dir, exist_ok=True)

        media_basename = os.path.basename(file_path)
        dest_media = _unique_dest(os.path.join(dest_dir, media_basename))
        shutil.move(file_path, dest_media)
        processed += 1

    logger.info(f"Finished processing {processed} files.")
    logger.info(f"Categorization methods: {method_counts}")
    
    # Remove directory if empty
    try:
        os.rmdir(UNKNOWN_DIR)
        logger.info(f"Removed empty directory {UNKNOWN_DIR}")
    except Exception as e:
        logger.info(f"Directory {UNKNOWN_DIR} not empty or could not be removed: {e}")

if __name__ == "__main__":
    main()
