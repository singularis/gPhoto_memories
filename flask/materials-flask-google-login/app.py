# Python standard libraries
import os
from datetime import date, datetime
import logging
from flask import Flask, redirect, request, url_for, render_template, Response, send_from_directory, jsonify
from helpers.middleware import setup_metrics
import prometheus_client
from PIL import Image, ImageOps
import io


picFolder = '/photos'

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Flask app setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = picFolder
app.config['DEBUG'] = True
setup_metrics(app)

CONTENT_TYPE_LATEST = str('text/plain; version=0.0.4; charset=utf-8')


@app.route("/")
@app.route("/date/<selected_date>")
def index(selected_date=None):
    logging.debug("Starting index route")
    media = {'images': [], 'videos': []}
    years_found = []
    
    # If a date is provided, use it; otherwise use today's date
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            logging.error(f"Invalid date format: {selected_date}")
            target_date = date.today()
    else:
        target_date = date.today()
    
    logging.debug(f"Target date: {target_date}")
    logging.debug(f"Base photo folder: {picFolder}")
    
    # Look for this same day in previous years (going back up to 10 years)
    for years_back in range(1, 11):
        try:
            past_date = date(target_date.year - years_back, target_date.month, target_date.day)
            past_folder = past_date.strftime("%Y_%m_%d")
            past_path = os.path.join(picFolder, past_folder)
            
            logging.debug(f"Checking for folder: {past_folder} ({years_back} years ago)")
            
            if os.path.exists(past_path) and os.path.isdir(past_path):
                logging.debug(f"Found folder for {past_date}: {past_path}")
                years_found.append(past_date.year)
                
                try:
                    fileList = os.listdir(past_path)
                    logging.debug(f"Found {len(fileList)} files in {past_folder}")
                    
                    for file in fileList:
                        file_path = os.path.join('photos', past_folder, file)
                        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.heic')):
                            media['images'].append({'path': file_path, 'year': past_date.year, 'date': past_date})
                            logging.debug(f"Added image from {past_date.year}: {file_path}")
                        elif file.lower().endswith(('.mp4', '.mov', '.avi')):
                            media['videos'].append({'path': file_path, 'year': past_date.year, 'date': past_date})
                            logging.debug(f"Added video from {past_date.year}: {file_path}")
                        else:
                            logging.debug(f"Skipped file (unknown type): {file}")
                except Exception as e:
                    logging.error(f"Error reading files from {past_path}: {e}")
            else:
                logging.debug(f"No folder found for {past_folder}")
                
        except ValueError as e:
            # Handle leap year issues (Feb 29 on non-leap years)
            logging.debug(f"Date calculation error for {years_back} years back: {e}")
            continue
    
    logging.debug(f"Years found with photos: {years_found}")
    logging.debug(f"Final media count - Images: {len(media['images'])}, Videos: {len(media['videos'])}")
    logging.debug("Rendering template")
    
    return render_template("index.html", media=media, date=target_date, years_found=years_found, selected_date=selected_date)

@app.route('/get_photos/<selected_date>')
def get_photos_for_date(selected_date):
    """API endpoint to get photos for a specific date"""
    logging.debug(f"Getting photos for date: {selected_date}")
    try:
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    media = {'images': [], 'videos': []}
    years_found = []
    
    # Look for this same day in previous years
    for years_back in range(1, 11):
        try:
            past_date = date(target_date.year - years_back, target_date.month, target_date.day)
            past_folder = past_date.strftime("%Y_%m_%d")
            past_path = os.path.join(picFolder, past_folder)
            
            if os.path.exists(past_path) and os.path.isdir(past_path):
                years_found.append(past_date.year)
                
                try:
                    fileList = os.listdir(past_path)
                    for file in fileList:
                        file_path = os.path.join('photos', past_folder, file)
                        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.heic')):
                            media['images'].append({'path': file_path, 'year': past_date.year, 'date': past_date.strftime('%Y-%m-%d')})
                        elif file.lower().endswith(('.mp4', '.mov', '.avi')):
                            media['videos'].append({'path': file_path, 'year': past_date.year, 'date': past_date.strftime('%Y-%m-%d')})
                except Exception as e:
                    logging.error(f"Error reading files from {past_path}: {e}")
                    
        except ValueError:
            continue
    
    return jsonify({
        'media': media, 
        'years_found': years_found,
        'date': target_date.strftime('%Y-%m-%d'),
        'formatted_date': target_date.strftime('%B %d, %Y')
    })

@app.route('/photos/<path:filename>')
def serve_photos(filename):
    """Serve photos from the /photos directory with optional resizing"""
    logging.debug(f"Serving photo: {filename}")
    
    # Get resize parameters from query string
    width = request.args.get('w', type=int)
    height = request.args.get('h', type=int)
    quality = request.args.get('q', 85, type=int)  # Default quality 85%
    
    # Auto-detect mobile devices and apply default sizing
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod'])
    
    # Default mobile sizing if no dimensions specified
    if is_mobile and not width and not height:
        width = 800  # Max width for mobile devices
        
    try:
        file_path = os.path.join('/photos', filename)
        
        if not width and not height:
            return send_from_directory('/photos', filename)
        
        if not os.path.exists(file_path):
            return "Photo not found", 404
            
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.heic')):
            return send_from_directory('/photos', filename)
        
        with Image.open(file_path) as img:
            # Preserve original orientation using EXIF data
            img = ImageOps.exif_transpose(img)
            
            if filename.lower().endswith('.heic'):
                img = img.convert('RGB')
                output_format = 'JPEG'
                mimetype = 'image/jpeg'
            else:
                output_format = img.format if img.format else 'JPEG'
                mimetype = f'image/{output_format.lower()}'
            
            original_width, original_height = img.size
            
            if width and height:
                new_width, new_height = width, height
            elif width:
                new_height = int((width / original_width) * original_height)
                new_width = width
            elif height:
                new_width = int((height / original_height) * original_width)
                new_height = height
            else:
                new_width, new_height = original_width, original_height
            
            if new_width < original_width or new_height < original_height:
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logging.debug(f"Resized {filename} from {original_width}x{original_height} to {new_width}x{new_height}")
            
            # Save to memory buffer
            buffer = io.BytesIO()
            img.save(buffer, format=output_format, quality=quality, optimize=True)
            buffer.seek(0)
            
            return Response(buffer.getvalue(), mimetype=mimetype)
            
    except Exception as e:
        logging.error(f"Error processing photo {filename}: {e}")
        try:
            return send_from_directory('/photos', filename)
        except:
            return "Photo not found", 404

@app.route('/metrics/')
def metrics():
    logging.debug("Metrics endpoint accessed")
    metrics_data = prometheus_client.generate_latest()
    logging.debug(f"Generated metrics data size: {len(metrics_data)} bytes")
    return Response(metrics_data, mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    logger = logging.getLogger('werkzeug')
    logger.setLevel(logging.INFO)  # Keep werkzeug at INFO to avoid too much noise
    logging.debug("Starting Flask app with debug logging enabled")
    app.run(host="0.0.0.0", debug=True)