# Methodology for Future Agents: Automatically Processing New Google Takeouts

This document outlines the standard operating procedure for AI agents when the user wants to add new Google Takeout archives to their `gPhoto_memories` system. 

## Incremental Processing (The "Automatic" Way)
The `google_takeout_processor.py` script has built-in **resume support**. This means it maintains a `processed_archives.json` file to track exactly which `.zip` files it has already fully extracted and organized. 

When the user uploads a *new* set of Takeout files, **DO NOT do a full wipe/rewrite** of the old photos! 

Follow these steps for an automatic, incremental update:

### Step 1: Copy the New Archives
1. Copy the new `.zip` files from the user's source (e.g., Windows drive) directly into the processing input directory: `/other_hdd/google_phots_all_take_out/`.
2. **Important:** You can leave the old `.zip` files in that folder if you want. The script will automatically ignore them because their filenames are logged in `processed_archives.json`.

### Step 2: Run the Processor
1. Simply start the processor script in the background:
   ```bash
   nohup python3 gphoto_take_out/google_takeout_processor.py > takeout_processor.log 2>&1 &
   ```
2. **What the script will do automatically:**
   - It will read `processed_archives.json`.
   - It will skip any `.zip` files it has seen before.
   - It will only extract the *new* `.zip` files.
   - It will parse the dates and merge the new photos directly into the existing `/other_hdd/google_phots_all_take_for_processing/` directory structure.
   - It will add the new `.zip` filenames to `processed_archives.json` when finished.

### Step 3: Verify the App
1. The Kubernetes Pod (`gphoto-flask-deployment`) is bind-mounted to the output directory. 
2. As soon as the processor drops new folders/files in the output directory, the Flask app will instantly have access to them. No pod restart is required for *incremental* folder additions (unless the container lost its volume mount context, as seen in previous edge cases).

---

## Complete Wipe & Restart (The "Fresh Start" Way)
*Only use this method if the user explicitly asks to wipe everything and start from zero (e.g., if their previous takeout was flawed).*

1. **Kill running jobs:** `pkill -f google_takeout_processor.py`
2. **Wipe temporary extractions:** `rm -rf /other_hdd/google_phots_all_take_out/temp_extract_*`
3. **Wipe processed output:** `rm -rf /other_hdd/google_phots_all_take_for_processing/*` (Safest way: `kubectl exec -n gphoto <POD_NAME> -- sh -c 'rm -rf /photos/* /photos/.thumb_cache'`)
4. **CRITICAL:** You **must** delete the resume state file so the script forgets what it has processed: 
   ```bash
   rm -f gphoto_take_out/processed_archives.json
   ```
5. Copy the new files over and start the processor as usual.
