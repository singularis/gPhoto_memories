# Python standard libraries
import os
import hashlib
from datetime import date, datetime
import logging
from flask import Flask, request, render_template, Response, send_from_directory, jsonify
from helpers.middleware import setup_metrics
import prometheus_client
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import io
import json

picFolder = '/photos'
CACHE_DIR = '/photos/.thumb_cache'

# WARNING only — no debug spam in prod
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask app setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = picFolder
# DEBUG must be False — Werkzeug reloader + stat polling burned the CPU
app.config['DEBUG'] = False
setup_metrics(app)
register_heif_opener()

# Pre-create thumbnail cache directory (on the mounted volume — survives pod restarts)
os.makedirs(CACHE_DIR, exist_ok=True)

CONTENT_TYPE_LATEST = str('text/plain; version=0.0.4; charset=utf-8')

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.heic', '.heif', '.bmp', '.tiff', '.webp')
VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp')


def _get_media_for_date(target_date):
    """Shared logic: scan folders for the given date across up to 100 prior years."""
    media = {'images': [], 'videos': []}
    years_found = []

    for years_back in range(1, 100):
        try:
            past_date = date(target_date.year - years_back, target_date.month, target_date.day)
        except ValueError:
            # Feb 29 on non-leap year
            continue

        past_folder = past_date.strftime("%Y_%m_%d")
        past_path = os.path.join(picFolder, past_folder)

        if not (os.path.exists(past_path) and os.path.isdir(past_path)):
            continue

        years_found.append(past_date.year)
        try:
            for file in os.listdir(past_path):
                file_path = os.path.join('photos', past_folder, file)
                fl = file.lower()
                if fl.endswith(IMAGE_EXTS):
                    media['images'].append({'path': file_path, 'year': past_date.year, 'date': past_date})
                elif fl.endswith(VIDEO_EXTS):
                    media['videos'].append({'path': file_path, 'year': past_date.year, 'date': past_date})
        except Exception as e:
            logging.error("Error reading %s: %s", past_path, e)

    return media, years_found


def _thumb_cache_path(filename, width, height, quality, cb=None):
    """Return the cache file path for a given resize request."""
    key_str = f"{filename}:{width}:{height}:{quality}"
    if cb:
        key_str += f":{cb}"
    key = hashlib.md5(key_str.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.jpg")


@app.route("/")
@app.route("/date/<selected_date>")
def index(selected_date=None):
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    ua = request.headers.get('User-Agent', '').lower()
    is_mobile = any(d in ua for d in ('mobile', 'android', 'iphone', 'ipad', 'ipod'))
    img_w = 400 if is_mobile else 800
    img_q = 65 if is_mobile else 85

    media, years_found = _get_media_for_date(target_date)
    return render_template("index.html", media=media, date=target_date,
                           years_found=years_found, selected_date=selected_date,
                           img_w=img_w, img_q=img_q, is_mobile=is_mobile)


@app.route('/get_photos/<selected_date>')
def get_photos_for_date(selected_date):
    """API endpoint to get photos for a specific date."""
    try:
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    media, years_found = _get_media_for_date(target_date)

    # Dates must be strings for JSON serialisation
    for img in media['images']:
        img['date'] = img['date'].strftime('%Y-%m-%d')
    for vid in media['videos']:
        vid['date'] = vid['date'].strftime('%Y-%m-%d')

    return jsonify({
        'media': media,
        'years_found': years_found,
        'date': target_date.strftime('%Y-%m-%d'),
        'formatted_date': target_date.strftime('%B %d, %Y')
    })


@app.route('/photos/<path:filename>')
def serve_photos(filename):
    """Serve photos with resize + persistent disk thumbnail cache."""
    width   = request.args.get('w', type=int)
    height  = request.args.get('h', type=int)
    quality = request.args.get('q', 85, type=int)

    # Auto-shrink for mobile
    ua = request.headers.get('User-Agent', '').lower()
    is_mobile = any(d in ua for d in ('mobile', 'android', 'iphone', 'ipad', 'ipod'))
    if is_mobile and not width and not height:
        width = 800

    # No resize needed — serve raw file
    if not width and not height:
        return send_from_directory('/photos', filename)

    file_path = os.path.join('/photos', filename)

    if not os.path.exists(file_path):
        return "Photo not found", 404

    fl = filename.lower()

    # Non-image files (videos etc.) — pass through
    if not fl.endswith(IMAGE_EXTS):
        return send_from_directory('/photos', filename)

    # ── Thumbnail cache hit ───────────────────────────────────────────────────
    cb = request.args.get('cb')
    cache_path = _thumb_cache_path(filename, width, height, quality, cb)
    if os.path.exists(cache_path):
        return send_from_directory(CACHE_DIR, os.path.basename(cache_path),
                                   mimetype='image/jpeg')

    # ── Generate thumbnail ────────────────────────────────────────────────────
    try:
        with Image.open(file_path) as img:
            # exif_transpose may return a *new* image object
            transposed = ImageOps.exif_transpose(img)
            try:
                # Normalise everything to RGB/JPEG for the cache
                if fl.endswith('.heic') or transposed.mode not in ('RGB', 'L'):
                    converted = transposed.convert('RGB')
                    if transposed is not img:
                        transposed.close()
                    transposed = converted

                orig_w, orig_h = transposed.size

                # Compute target dimensions
                if width and height:
                    new_w, new_h = width, height
                elif width:
                    new_w = width
                    new_h = int((width / orig_w) * orig_h)
                elif height:
                    new_h = height
                    new_w = int((height / orig_h) * orig_w)
                else:
                    new_w, new_h = orig_w, orig_h

                if new_w < orig_w or new_h < orig_h:
                    resized = transposed.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    if transposed is not img:
                        transposed.close()
                    transposed = resized

                # Encode once into memory
                buffer = io.BytesIO()
                transposed.save(buffer, format='JPEG', quality=quality, optimize=True)
                img_bytes = buffer.getvalue()

                # Persist to cache (best-effort — ignore write errors)
                try:
                    with open(cache_path, 'wb') as cf:
                        cf.write(img_bytes)
                except Exception as cache_err:
                    logging.warning("Thumb cache write failed for %s: %s", filename, cache_err)

                return Response(img_bytes, mimetype='image/jpeg')

            finally:
                if transposed is not img:
                    transposed.close()

    except Exception as e:
        logging.error("Error processing photo %s: %s", filename, e)
        try:
            return send_from_directory('/photos', filename)
        except Exception:
            return "Photo not found", 404


@app.route('/rotate/<path:filename>', methods=['POST'])
def rotate_photo(filename):
    file_path = os.path.join('/photos', filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'Not found'}), 404

    try:
        with Image.open(file_path) as img:
            # Rotate raw pixels clockwise
            rotated = img.rotate(-90, expand=True)
            if 'exif' in img.info:
                rotated.save(file_path, quality=95, exif=img.info['exif'])
            else:
                rotated.save(file_path, quality=95)

        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error("Rotate error: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def save_settings():
    try:
        data = request.json
        with open(os.path.join('/photos', 'settings.json'), 'w') as f:
            json.dump(data, f)
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error("Settings save error: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/')
def metrics():
    return Response(prometheus_client.generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    # This block is only hit in local dev.
    # Production uses gunicorn (see Dockerfile).
    logging.getLogger().setLevel(logging.INFO)
    app.run(host="0.0.0.0", debug=False)