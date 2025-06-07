#!/usr/bin/env python3
"""
Google Photos Picker API Web Application
This application provides a web interface for users to select and download photos
using the new Google Photos Picker API.
"""

import os
import shutil
import json
import pandas as pd
import requests
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from gphoto.api import GooglePhotosPickerApi
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("application.log"),
                        logging.StreamHandler()
                    ])

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this')

# Global variables to store session data
active_sessions = {}
downloaded_items = []

def get_users():
    """Get list of users from environment variable"""
    users_json = os.getenv('USERS', '[]')
    return json.loads(users_json)

def download_media_item(item, destination_folder, user):
    """Download a single media item"""
    try:
        url = item['baseUrl']
        # Add video download parameter if it's a video
        if 'video' in item.get('mediaMetadata', {}):
            url += '=dv'
        
        response = requests.get(url)
        if response.status_code == 200:
            name_part, extension = item['filename'].rsplit('.', 1)
            file_name = f"{name_part}_{user}.{extension}"
            
            # Create year folder based on creation time
            creation_time = item.get('mediaMetadata', {}).get('creationTime', '')
            if creation_time:
                year = creation_time[:4]
                year_folder = os.path.join(destination_folder, year)
                os.makedirs(year_folder, exist_ok=True)
                file_path = os.path.join(year_folder, file_name)
            else:
                file_path = os.path.join(destination_folder, file_name)
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f'Downloaded: {file_name}')
            return True
        else:
            logger.warning(f'Failed to download: {item["filename"]}, Status Code: {response.status_code}')
            return False
    except Exception as e:
        logger.error(f'Error downloading {item.get("filename", "unknown")}: {e}')
        return False

def download_session_media_items(session_id, user, api):
    """Download all media items from a completed session"""
    destination_folder = '/app/static/pics'
    os.makedirs(destination_folder, exist_ok=True)
    
    downloaded_count = 0
    page_token = None
    
    while True:
        try:
            result = api.list_media_items(session_id, page_size=50, page_token=page_token)
            if not result:
                break
            
            media_items = result.get('mediaItems', [])
            if not media_items:
                break
            
            for item in media_items:
                if download_media_item(item, destination_folder, user):
                    downloaded_count += 1
                    downloaded_items.append({
                        'filename': item.get('filename'),
                        'user': user,
                        'session_id': session_id,
                        'download_time': datetime.now().isoformat()
                    })
            
            page_token = result.get('nextPageToken')
            if not page_token:
                break
                
        except Exception as e:
            logger.error(f'Error downloading media items: {e}')
            break
    
    logger.info(f'Downloaded {downloaded_count} items for user {user} from session {session_id}')
    return downloaded_count

@app.route('/')
def index():
    """Main page showing available users and active sessions"""
    users = get_users()
    return render_template('index.html', users=users, active_sessions=active_sessions)

@app.route('/create_session/<user>')
def create_session(user):
    """Create a new Picker API session for a user"""
    try:
        api = GooglePhotosPickerApi(user)
        creds = api.run_local_server()
        
        if not creds:
            flash(f'Failed to authenticate user {user}', 'error')
            return redirect(url_for('index'))
        
        session_data = api.create_session()
        if not session_data:
            flash(f'Failed to create session for user {user}', 'error')
            return redirect(url_for('index'))
        
        session_id = session_data.get('id')
        picker_uri = session_data.get('pickerUri')
        
        if session_id and picker_uri:
            active_sessions[session_id] = {
                'user': user,
                'picker_uri': picker_uri,
                'created_at': datetime.now().isoformat(),
                'status': 'waiting_for_user',
                'api': api
            }
            
            flash(f'Session created for user {user}. Please use the picker link to select photos.', 'success')
            return render_template('session.html', 
                                 session_id=session_id, 
                                 picker_uri=picker_uri, 
                                 user=user)
        else:
            flash('Invalid session response from Google Photos API', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f'Error creating session for user {user}: {e}')
        flash(f'Error creating session for user {user}: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/check_session/<session_id>')
def check_session(session_id):
    """Check the status of a session"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_info = active_sessions[session_id]
    api = session_info['api']
    
    try:
        session_data = api.get_session(session_id)
        if session_data:
            media_items_set = session_data.get('mediaItemsSet', False)
            session_info['media_items_set'] = media_items_set
            
            if media_items_set and session_info['status'] == 'waiting_for_user':
                session_info['status'] = 'ready_for_download'
            
            return jsonify({
                'session_id': session_id,
                'status': session_info['status'],
                'media_items_set': media_items_set,
                'user': session_info['user']
            })
        else:
            return jsonify({'error': 'Failed to get session data'}), 500
    except Exception as e:
        logger.error(f'Error checking session {session_id}: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/download_session/<session_id>')
def download_session(session_id):
    """Download all media items from a completed session"""
    if session_id not in active_sessions:
        flash('Session not found', 'error')
        return redirect(url_for('index'))
    
    session_info = active_sessions[session_id]
    api = session_info['api']
    user = session_info['user']
    
    try:
        # Check if session is ready
        session_data = api.get_session(session_id)
        if not session_data or not session_data.get('mediaItemsSet', False):
            flash('Session is not ready for download. Please ensure you have selected photos.', 'warning')
            return redirect(url_for('index'))
        
        # Start download in background
        session_info['status'] = 'downloading'
        
        def download_task():
            downloaded_count = download_session_media_items(session_id, user, api)
            session_info['status'] = 'completed'
            session_info['downloaded_count'] = downloaded_count
            session_info['completed_at'] = datetime.now().isoformat()
        
        download_thread = threading.Thread(target=download_task)
        download_thread.daemon = True
        download_thread.start()
        
        flash(f'Download started for session {session_id}. Check the status page for progress.', 'info')
        return redirect(url_for('session_status', session_id=session_id))
        
    except Exception as e:
        logger.error(f'Error starting download for session {session_id}: {e}')
        flash(f'Error starting download: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/session_status/<session_id>')
def session_status(session_id):
    """Show detailed status of a session"""
    if session_id not in active_sessions:
        flash('Session not found', 'error')
        return redirect(url_for('index'))
    
    session_info = active_sessions[session_id]
    return render_template('session_status.html', 
                         session_id=session_id, 
                         session_info=session_info)

@app.route('/downloads')
def downloads():
    """Show list of downloaded items"""
    return render_template('downloads.html', downloaded_items=downloaded_items)

@app.route('/api/sessions')
def api_sessions():
    """API endpoint to get all active sessions"""
    return jsonify(active_sessions)

if __name__ == '__main__':
    logger.info("Starting Google Photos Picker API web application")
    app.run(host='0.0.0.0', port=5000, debug=True) 