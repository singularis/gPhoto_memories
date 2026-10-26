# Processing Google Takeout archives (v3)

`google_takeout_processor.py` turns a Google Photos Takeout (many `.zip` parts)
into `YYYY_MM_DD/` folders that match the Google Photos timeline 1:1.
The Flask UI (`web/app.py`) lists only files directly inside `YYYY_MM_DD/`.

## How it works
1. **Index all zips** – every JSON sidecar from every zip is read (cached in
   `.cache/sidecars.json`). Google puts most sidecars in the first zips, so a
   photo's JSON is usually in a different zip than the photo.
2. **Match photo ↔ JSON** – exact name, `title` field, truncated names (51-char
   limit: `.supplemental-.json`, `.sup.json`, `..json`), `(n)` duplicates
   (`IMG_1(1).jpg` ↔ `IMG_1.jpg.supplemental-metadata(1).json`), `-edited`.
3. **Classify**
   - visible → `YYYY_MM_DD/`
   - Live Photo / Motion Photo clips and pre-edit originals → `YYYY_MM_DD/.live/`
   - `archived: true` → `_archived/`, `trashed: true` → `_trash/`
   - album copies of the same item (same JSON `url`) → skipped
   - no JSON and no date in filename → `_undated/`
4. **Date** – `photoTakenTime` (UTC) converted to local time using the GPS
   timezone, or the timezone of the nearest geotagged photo (±3 days), or the
   month's dominant timezone. This is the date Google Photos shows.
5. **Extract** – members are streamed from the zips straight to their final
   path (no temp extraction). Re-running skips files already written.
6. **Manifest** – `.manifests/index.json` in the output records every source
   member, its destination, sidecar, timezone and date source.

## Commands (run from this folder)
```bash
.venv/bin/python google_takeout_processor.py plan            # stats only, no writes
.venv/bin/python google_takeout_processor.py sample -n 50    # extract 50 random items, compare with EXIF
nohup .venv/bin/python google_takeout_processor.py run --out /other_hdd/google_phots_memories_new \
    > processor_v3.log 2>&1 &
```
First-time setup: `python3 -m venv .venv && .venv/bin/pip install timezonefinder`.

## New takeout
A Takeout is a full export, so rebuild instead of merging. Write straight into the
folder the site serves (`/other_hdd/google_phots_all_take_for_processing`).
Do not extract into a second folder: the zips plus one library is about 1 TB,
and a second library pushes the disk to about 1.5 TB.

1. Replace the zips in `/other_hdd/google_phots_all_take_out/` with the new ones.
2. Run `plan` and `sample -n 50`; check the EXIF agreement and the role counts.
3. Remove the old library (the site is empty until the new files land), then extract:
   ```bash
   cp /other_hdd/google_phots_all_take_for_processing/settings.json /tmp/gphoto_settings.json
   rm -rf /other_hdd/google_phots_all_take_for_processing
   mkdir -p /other_hdd/google_phots_all_take_for_processing
   cp /tmp/gphoto_settings.json /other_hdd/google_phots_all_take_for_processing/settings.json
   kubectl rollout restart -n gphoto deployment/gphoto-flask-deployment
   setsid nohup .venv/bin/python google_takeout_processor.py run \
     --out /other_hdd/google_phots_all_take_for_processing \
     > processor_v3.log 2>&1 < /dev/null &
   ```
4. The pod must be restarted after the folder is recreated, otherwise it keeps
   the old deleted directory. Files written after that restart show up immediately.
5. Make iPhone videos play in Chrome (HEVC `.mov` does not). This writes H.264
   copies into `.video_cache/` and leaves the originals in place:
   ```bash
   setsid nohup .venv/bin/python transcode_videos.py > transcode_videos.log 2>&1 < /dev/null &
   ```
