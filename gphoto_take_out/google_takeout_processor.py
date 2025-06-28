#!/usr/bin/env python3

import os
import json
import shutil
import zipfile
import glob
from datetime import datetime
from pathlib import Path
import logging

# Configure logging to file in the same directory as the script
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(script_dir, 'google_takeout_processor.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # Also keep console output
    ]
)
logger = logging.getLogger(__name__)

# Constants
TAKEOUT_PATH = "/other_hdd/google_phots_all_take_out"
PROCESSING_PATH = "/other_hdd/google_phots_all_take_for_processing"

def create_processing_folder():
    """Create the processing folder if it doesn't exist"""
    Path(PROCESSING_PATH).mkdir(parents=True, exist_ok=True)
    logger.info(f"Created processing folder: {PROCESSING_PATH}")

def list_zip_archives():
    """List all zip archives in the takeout folder"""
    zip_files = glob.glob(os.path.join(TAKEOUT_PATH, "*.zip"))
    logger.info(f"Found {len(zip_files)} zip archives:")
    for zip_file in zip_files:
        logger.info(f"  - {os.path.basename(zip_file)}")
    return zip_files

def process_single_archive(zip_file):
    """Process a single archive: extract, process photos, then cleanup"""
    archive_name = os.path.basename(zip_file)
    logger.info(f"Starting processing of archive: {archive_name}")
    
    # Create temporary extraction folder for this archive
    temp_extract_path = os.path.join(TAKEOUT_PATH, f"temp_extract_{archive_name.replace('.zip', '')}")
    
    try:
        # Extract the archive to temporary folder
        logger.info(f"Extracting {archive_name}...")
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_path)
        logger.info(f"Successfully extracted {archive_name}")
        
        # Process photos in this archive
        photo_files = get_all_photo_files_from_path(temp_extract_path)
        if photo_files:
            logger.info(f"Found {len(photo_files)} photos in {archive_name}")
            process_photos(photo_files)
        else:
            logger.warning(f"No photos found in {archive_name}")
        
        # Cleanup extracted files to save disk space
        logger.info(f"Cleaning up extracted files for {archive_name}...")
        shutil.rmtree(temp_extract_path, ignore_errors=True)
        logger.info(f"Completed processing of {archive_name}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing archive {zip_file}: {e}")
        # Try to cleanup even if there was an error
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path, ignore_errors=True)
        return False

def get_all_photo_files_from_path(search_path):
    """Scan all subfolders in given path and find photo files with their metadata"""
    photo_files = []
    
    # Walk through all subdirectories
    for root, dirs, files in os.walk(search_path):
        for file in files:
            # Skip zip files
            if file.endswith('.zip'):
                continue
                
            file_path = os.path.join(root, file)
            
            # Check if it's an image file (common formats)
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic')):
                # Look for corresponding JSON metadata file
                json_file = file_path + '.supplemental-metadata.json'
                if os.path.exists(json_file):
                    photo_files.append((file_path, json_file))
                else:
                    # Sometimes the JSON file might have a different naming pattern
                    # Try alternative JSON file names
                    base_name = os.path.splitext(file_path)[0]
                    alt_json = base_name + '.json'
                    if os.path.exists(alt_json):
                        photo_files.append((file_path, alt_json))
                    else:
                        logger.debug(f"No metadata found for {file}")
                        # Add photo without metadata (will use file modification time)
                        photo_files.append((file_path, None))
    
    return photo_files

def get_all_photo_files():
    """Scan all subfolders and find photo files with their metadata (legacy function for non-archive files)"""
    photo_files = get_all_photo_files_from_path(TAKEOUT_PATH)
    logger.info(f"Found {len(photo_files)} photo files")
    return photo_files

def get_date_from_metadata(json_file):
    """Extract date from JSON metadata"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Try to get photoTakenTime timestamp
        if 'photoTakenTime' in metadata and 'timestamp' in metadata['photoTakenTime']:
            timestamp = int(metadata['photoTakenTime']['timestamp'])
            date = datetime.fromtimestamp(timestamp)
            return date.strftime('%Y_%m_%d')
        
        # Try alternative timestamp fields
        if 'creationTime' in metadata and 'timestamp' in metadata['creationTime']:
            timestamp = int(metadata['creationTime']['timestamp'])
            date = datetime.fromtimestamp(timestamp)
            return date.strftime('%Y_%m_%d')
            
    except Exception as e:
        logger.error(f"Error reading metadata from {json_file}: {e}")
    
    return None

def get_date_from_file(file_path):
    """Get date from file modification time as fallback"""
    try:
        timestamp = os.path.getmtime(file_path)
        date = datetime.fromtimestamp(timestamp)
        return date.strftime('%Y_%m_%d')
    except Exception as e:
        logger.error(f"Error getting file timestamp from {file_path}: {e}")
        return "unknown_date"

def process_photos(photo_files):
    """Process all photos and organize them by date"""
    processed_count = 0
    total_files = len(photo_files)
    
    logger.info(f"Starting to process {total_files} photos...")
    
    for i, (photo_file, json_file) in enumerate(photo_files, 1):
        try:
            # Log progress every 100 files or at specific intervals
            if i % 100 == 0 or i == total_files:
                logger.info(f"Processing photo {i}/{total_files} ({(i/total_files)*100:.1f}%)")
            
            # Determine the date folder
            if json_file:
                date_folder = get_date_from_metadata(json_file)
            else:
                date_folder = None
                
            # Use file modification time as fallback
            if not date_folder:
                date_folder = get_date_from_file(photo_file)
            
            # Create date folder
            date_folder_path = os.path.join(PROCESSING_PATH, date_folder)
            Path(date_folder_path).mkdir(parents=True, exist_ok=True)
            
            # Move photo file
            photo_filename = os.path.basename(photo_file)
            dest_photo = os.path.join(date_folder_path, photo_filename)
            
            # Handle duplicate filenames
            counter = 1
            original_dest_photo = dest_photo
            while os.path.exists(dest_photo):
                name, ext = os.path.splitext(original_dest_photo)
                dest_photo = f"{name}_{counter}{ext}"
                counter += 1
            
            shutil.move(photo_file, dest_photo)
            logger.debug(f"Moved photo: {photo_filename} -> {date_folder}")
            
            # Move JSON file if it exists
            if json_file:
                json_filename = os.path.basename(json_file)
                dest_json = os.path.join(date_folder_path, json_filename)
                
                # Handle duplicate JSON filenames
                counter = 1
                original_dest_json = dest_json
                while os.path.exists(dest_json):
                    name, ext = os.path.splitext(original_dest_json)
                    dest_json = f"{name}_{counter}{ext}"
                    counter += 1
                
                shutil.move(json_file, dest_json)
                logger.debug(f"Moved metadata: {json_filename} -> {date_folder}")
            
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Error processing {photo_file}: {e}")
    
    logger.info(f"Successfully processed {processed_count}/{total_files} photos")

def main():
    """Main function to orchestrate the entire process"""
    logger.info("Starting Google Takeout photo processing...")
    
    # Check if takeout folder exists
    if not os.path.exists(TAKEOUT_PATH):
        logger.error(f"Takeout folder does not exist: {TAKEOUT_PATH}")
        return
    
    # Create processing folder
    create_processing_folder()
    
    # List zip archives
    zip_files = list_zip_archives()
    
    total_processed = 0
    successful_archives = 0
    
    if zip_files:
        logger.info(f"Processing {len(zip_files)} archives one by one...")
        
        # Process each archive individually
        for i, zip_file in enumerate(zip_files, 1):
            logger.info(f"Processing archive {i}/{len(zip_files)}: {os.path.basename(zip_file)}")
            
            if process_single_archive(zip_file):
                successful_archives += 1
                logger.info(f"Successfully processed archive {i}/{len(zip_files)}")
            else:
                logger.error(f"Failed to process archive {i}/{len(zip_files)}")
        
        logger.info(f"Archive processing summary: {successful_archives}/{len(zip_files)} archives processed successfully")
    
    else:
        logger.info("No zip archives found, processing existing files...")
        
        # Find all photo files in existing folders
        photo_files = get_all_photo_files()
        
        if not photo_files:
            logger.warning("No photo files found!")
            return
        
        # Process and organize photos
        process_photos(photo_files)
    
    logger.info("Google Takeout photo processing completed!")
    logger.info(f"All photos have been organized in: {PROCESSING_PATH}")
    logger.info("Check the log file for detailed processing information.")

if __name__ == "__main__":
    main() 