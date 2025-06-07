from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os
import logging
import requests
import time
import json

logger = logging.getLogger(__name__)


class GooglePhotosPickerApi:
    def __init__(self,
                 account_name: str,
                 client_secret_path=r'/app/',
                 scopes=None):
        """
        Initialize the Google Photos Picker API
        """
        if scopes is None:
            # Updated scopes for the new Picker API
            scopes = [
                'https://www.googleapis.com/auth/photospicker.mediaitems.readonly',
            ]
        self.account_name = account_name
        self.client_secret_file = os.path.join(client_secret_path + f"gcp-credentials-{account_name}" + f"/gPhoto_credentials_{account_name}" + ".json")
        self.scopes = scopes
        self.cred_pickle_file = f'/app/credentials/token_{self.account_name}_picker_api.pickle'
        self.cred = None
        self.base_url = 'https://photospicker.googleapis.com/v1'

    def run_local_server(self):
        os.makedirs(os.path.dirname(self.cred_pickle_file), exist_ok=True)
        if os.path.exists(self.cred_pickle_file):
            with open(self.cred_pickle_file, 'rb') as token:
                self.cred = pickle.load(token)
            if not self.cred or not self.cred.valid:
                if self.cred and self.cred.expired and self.cred.refresh_token:
                    logger.info(f"Refreshing token for {self.account_name}")
                    self.cred.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secret_file, 
                        self.scopes
                    )
                    self.cred = flow.run_local_server(
                        port=8080,
                        prompt='consent',
                        access_type='offline'
                    )
                with open(self.cred_pickle_file, 'wb') as token:
                    pickle.dump(self.cred, token)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_file, 
                self.scopes
            )
            self.cred = flow.run_local_server(
                port=8080,
                prompt='consent',
                access_type='offline'
            )
            with open(self.cred_pickle_file, 'wb') as token:
                pickle.dump(self.cred, token)
        return self.cred

    def refresh_token_if_needed(self):
        """Refresh the token if needed"""
        try:
            if self.cred.expired:
                request = Request()
                self.cred.refresh(request)
                logger.info(f"Token refreshed successfully for user: {self.account_name}")
                return True
        except Exception as e:
            logger.error(f"Error refreshing token for user {self.account_name}: {e}")
            return False
        return True

    def create_session(self):
        """Create a new Picker API session"""
        if not self.refresh_token_if_needed():
            return None
            
        url = f'{self.base_url}/sessions'
        headers = {
            'Authorization': f'Bearer {self.cred.token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers)
            if response.status_code == 401:
                logger.warning(f"Token expired for user: {self.account_name}. Attempting to refresh...")
                if self.refresh_token_if_needed():
                    headers['Authorization'] = f'Bearer {self.cred.token}'
                    response = requests.post(url, headers=headers)
                else:
                    logger.error(f"Failed to refresh token for user: {self.account_name}")
                    return None
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f'Error creating session: {e}')
            return None

    def get_session(self, session_id):
        """Get session details"""
        if not self.refresh_token_if_needed():
            return None
            
        url = f'{self.base_url}/sessions/{session_id}'
        headers = {
            'Authorization': f'Bearer {self.cred.token}'
        }
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 401:
                if self.refresh_token_if_needed():
                    headers['Authorization'] = f'Bearer {self.cred.token}'
                    response = requests.get(url, headers=headers)
                else:
                    return None
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f'Error getting session: {e}')
            return None

    def list_media_items(self, session_id, page_size=50, page_token=None):
        """List media items from a session"""
        if not self.refresh_token_if_needed():
            return None
            
        url = f'{self.base_url}/mediaItems'
        params = {
            'sessionId': session_id,
            'pageSize': page_size,
        }
        if page_token:
            params['pageToken'] = page_token
            
        headers = {
            'Authorization': f'Bearer {self.cred.token}',
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 401:
                if self.refresh_token_if_needed():
                    headers['Authorization'] = f'Bearer {self.cred.token}'
                    response = requests.get(url, headers=headers, params=params)
                else:
                    return None
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f'Error listing media items: {e}')
            return None

    def poll_session_until_complete(self, session_id, max_wait_time=300, poll_interval=5):
        """Poll a session until mediaItemsSet is True or timeout"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            session_data = self.get_session(session_id)
            if session_data and session_data.get('mediaItemsSet', False):
                logger.info(f"Session {session_id} completed - user has selected media items")
                return True
            
            logger.info(f"Session {session_id} not yet complete, waiting {poll_interval} seconds...")
            time.sleep(poll_interval)
            
            # Adjust poll interval based on API recommendations if available
            if session_data and 'pollingConfig' in session_data:
                poll_interval = session_data['pollingConfig'].get('pollInterval', poll_interval)
        
        logger.warning(f"Session {session_id} timed out after {max_wait_time} seconds")
        return False


# Legacy API class for backward compatibility (limited functionality)
class GooglePhotosApi:
    def __init__(self,
                 account_name: str,
                 api_name='photoslibrary',
                 client_secret_path=r'/app/',
                 api_version='v1',
                 scopes=None):
        """
        Initialize the Google Photos Library API (limited functionality after March 2025)
        This class is kept for backward compatibility but only works with app-created content.
        """
        if scopes is None:
            # Updated scopes that will remain available
            scopes = [
                'https://www.googleapis.com/auth/photoslibrary.appendonly',
                'https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata',
                'https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata',
            ]
        self.api_name = api_name
        self.account_name = account_name
        self.client_secret_file = os.path.join(client_secret_path + f"gcp-credentials-{account_name}" + f"/gPhoto_credentials_{account_name}" + ".json")
        self.api_version = api_version
        self.scopes = scopes
        self.cred_pickle_file = f'/app/credentials/token_{self.account_name}_{self.api_name}_{self.api_version}.pickle'
        self.cred = None

    def run_local_server(self):
        os.makedirs(os.path.dirname(self.cred_pickle_file), exist_ok=True)
        if os.path.exists(self.cred_pickle_file):
            with open(self.cred_pickle_file, 'rb') as token:
                self.cred = pickle.load(token)
            if not self.cred or not self.cred.valid:
                if self.cred and self.cred.expired and self.cred.refresh_token:
                    logger.info(f"Refreshing token for {self.account_name}")
                    self.cred.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secret_file, 
                        self.scopes
                    )
                    self.cred = flow.run_local_server(
                        port=8080,
                        prompt='consent',
                        access_type='offline'
                    )
                with open(self.cred_pickle_file, 'wb') as token:
                    pickle.dump(self.cred, token)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_file, 
                self.scopes
            )
            self.cred = flow.run_local_server(
                port=8080,
                prompt='consent',
                access_type='offline'
            )
            with open(self.cred_pickle_file, 'wb') as token:
                pickle.dump(self.cred, token)
        return self.cred

