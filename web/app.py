# Python standard libraries
import os
import hashlib
from datetime import date, datetime
import logging
from flask import Flask, request, render_template, Response, send_from_directory, jsonify
from werkzeug.security import safe_join
from helpers.middleware import setup_metrics
import prometheus_client
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import io
import json

picFolder = os.environ.get('PHOTOS_DIR', '/photos')
CACHE_DIR = os.path.join(picFolder, '.thumb_cache')
# H.264 MP4 stand-ins for clips Chrome cannot play (HEVC .mov and other odd containers).
# Filled by scripts/takeout_processor/transcode_videos.py. Key is md5(relpath:size).
VIDEO_CACHE_DIR = os.path.join(picFolder, '.video_cache')
SETTINGS_FILE = os.path.join(picFolder, 'settings.json')
# React build (web/frontend). Lives outside static/ because static/ is a PVC mount in k8s.
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

# Media URLs carrying ?v=<mtime> never change content, so browsers may keep them for a year.
IMMUTABLE_MAX_AGE = 31536000

# WARNING only — no debug spam in prod
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask app setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = picFolder
# DEBUG must be False — Werkzeug reloader + stat polling burned the CPU
app.config['DEBUG'] = False
setup_metrics(app)
register_heif_opener()

# Pre-create cache directories (on the mounted volume — survive pod restarts)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)

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
            for entry in sorted(os.scandir(past_path), key=lambda e: e.name):
                fl = entry.name.lower()
                if fl.endswith(IMAGE_EXTS):
                    kind = 'images'
                elif fl.endswith(VIDEO_EXTS):
                    kind = 'videos'
                else:
                    continue
                media[kind].append({
                    'path': os.path.join('photos', past_folder, entry.name),
                    'year': past_date.year,
                    'date': past_date,
                    'v': entry.stat().st_mtime_ns // 1_000_000,
                })
        except Exception as e:
            logging.error("Error reading %s: %s", past_path, e)

    return media, years_found


SETTINGS_DEFAULTS = {'image_scale': 2.0, 'font_scale': 2.0, 'year_order': 'newer', 'play_seconds': 3}


def _clamp(value, low, high, default):
    try:
        return round(min(high, max(low, float(value))), 1)
    except (TypeError, ValueError):
        return default


def _clean_settings(data):
    """Whitelist + clamp whatever the UI sends so a bad payload cannot break the page."""
    data = data if isinstance(data, dict) else {}
    d = SETTINGS_DEFAULTS
    return {
        'image_scale': _clamp(data.get('image_scale'), 0.5, 4.0, d['image_scale']),
        'font_scale': _clamp(data.get('font_scale'), 0.5, 4.0, d['font_scale']),
        'year_order': 'older' if data.get('year_order') == 'older' else 'newer',
        'play_seconds': _clamp(data.get('play_seconds'), 0.2, 15, d['play_seconds']),
    }


def _load_settings():
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            return _clean_settings(json.load(f))
    except Exception:
        return dict(SETTINGS_DEFAULTS)


def _year_order():
    """'newer' or 'older'. Read from the settings file the UI writes."""
    return _load_settings()['year_order']


def _photo_path(filename):
    """Absolute path inside the photo folder, or None if the request tries to escape it."""
    return safe_join(picFolder, filename)


def _cache_headers(response):
    if request.args.get('v'):
        response.headers['Cache-Control'] = f'public, max-age={IMMUTABLE_MAX_AGE}, immutable'
    return response


def video_cache_path(filename, size):
    """Path of the browser-safe MP4 for this video, if one has been built."""
    key = hashlib.md5(f"{filename}:{size}".encode()).hexdigest()
    return os.path.join(VIDEO_CACHE_DIR, f"{key}.mp4")


def _thumb_cache_path(filename, width, height, quality, mtime):
    """Return the cache file path for a given resize request.

    mtime is part of the key so a rotated photo never serves its old thumbnail.
    """
    key_str = f"{filename}:{width}:{height}:{quality}:{mtime}"
    key = hashlib.md5(key_str.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.jpg")


@app.route("/")
@app.route("/date/<selected_date>")
def index(selected_date=None):
    if os.path.isfile(os.path.join(FRONTEND_DIST, 'index.html')):
        response = send_from_directory(FRONTEND_DIST, 'index.html')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    # Legacy Jinja page, used only when the React build is missing (e.g. local dev without npm).
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
    years_found = sorted(years_found, reverse=(_year_order() != 'older'))
    return render_template("index.html", media=media, date=target_date,
                           years_found=years_found, selected_date=selected_date,
                           img_w=img_w, img_q=img_q, is_mobile=is_mobile)


@app.route('/assets/<path:filename>')
def frontend_assets(filename):
    """Vite build output. File names are content-hashed, so they are cached forever."""
    response = send_from_directory(os.path.join(FRONTEND_DIST, 'assets'), filename)
    response.headers['Cache-Control'] = f'public, max-age={IMMUTABLE_MAX_AGE}, immutable'
    return response


@app.route('/manifest.webmanifest')
def web_manifest():
    return send_from_directory(FRONTEND_DIST, 'manifest.webmanifest',
                               mimetype='application/manifest+json', max_age=3600)


@app.route('/icons/<path:filename>')
def frontend_icons(filename):
    return send_from_directory(os.path.join(FRONTEND_DIST, 'icons'), filename, max_age=86400)


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

    file_path = _photo_path(filename)
    if not file_path or not os.path.isfile(file_path):
        return "Photo not found", 404

    fl = filename.lower()

    # Video: serve the H.264 cache when this clip had to be converted.
    if fl.endswith(VIDEO_EXTS):
        cached = video_cache_path(filename, os.path.getsize(file_path))
        if os.path.isfile(cached) and os.path.getsize(cached) > 0:
            return _cache_headers(send_from_directory(VIDEO_CACHE_DIR, os.path.basename(cached),
                                                      mimetype='video/mp4', conditional=True))
        return _cache_headers(send_from_directory(picFolder, filename, conditional=True))

    # Auto-shrink for mobile
    ua = request.headers.get('User-Agent', '').lower()
    is_mobile = any(d in ua for d in ('mobile', 'android', 'iphone', 'ipad', 'ipod'))
    if is_mobile and not width and not height:
        width = 800

    # No resize needed — serve raw file
    if not width and not height:
        return _cache_headers(send_from_directory(picFolder, filename))

    # ── Thumbnail cache hit ───────────────────────────────────────────────────
    cache_path = _thumb_cache_path(filename, width, height, quality, os.stat(file_path).st_mtime_ns)
    if os.path.exists(cache_path):
        return _cache_headers(send_from_directory(CACHE_DIR, os.path.basename(cache_path),
                                                  mimetype='image/jpeg'))

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
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    with open(cache_path, 'wb') as cf:
                        cf.write(img_bytes)
                except Exception as cache_err:
                    logging.warning("Thumb cache write failed for %s: %s", filename, cache_err)

                return _cache_headers(Response(img_bytes, mimetype='image/jpeg'))

            finally:
                if transposed is not img:
                    transposed.close()

    except Exception as e:
        logging.error("Error processing photo %s: %s", filename, e)
        try:
            return send_from_directory(picFolder, filename)
        except Exception:
            return "Photo not found", 404


@app.route('/rotate/photos/<path:filename>', methods=['POST'])
def rotate_photo(filename):
    file_path = _photo_path(filename)
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'error': 'Not found'}), 404

    try:
        with Image.open(file_path) as img:
            # Rotate raw pixels clockwise
            rotated = img.rotate(-90, expand=True)
            if 'exif' in img.info:
                rotated.save(file_path, quality=95, exif=img.info['exif'])
            else:
                rotated.save(file_path, quality=95)

        return jsonify({'status': 'success', 'v': os.stat(file_path).st_mtime_ns // 1_000_000})
    except Exception as e:
        logging.error("Rotate error: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings', methods=['GET'])
def get_settings():
    response = jsonify(_load_settings())
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/settings', methods=['POST'])
def save_settings():
    try:
        settings = _clean_settings(request.get_json(silent=True))
        tmp_path = SETTINGS_FILE + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f)
        os.replace(tmp_path, SETTINGS_FILE)
        return jsonify({'status': 'success', 'settings': settings})
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