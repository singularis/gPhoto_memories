from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os
import logging

logger = logging.getLogger(__name__)


class GooglePhotosApi:
    def __init__(self,
                 account_name: str,
                 api_name='photoslibrary',
                 client_secret_path=r'/app/',
                 api_version='v1',
                 scopes=None):
        """
        Initialize the Google Photos API
        """
        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/photoslibrary.readonly']
        self.api_name = api_name
        self.account_name = account_name
        self.client_secret_file = os.path.join(client_secret_path + f"gcp-credentials-{account_name}" + f"/gPhoto_credentials_{account_name}" + ".json")
        self.api_version = api_version
        self.scopes = scopes
        self.cred_pickle_file = f'/app/credentials/token_{self.account_name}_{self.api_name}_{self.api_version}.pickle'
        self.cred = None

    def run_local_server(self):
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
                        self.scopes,
                        redirect_uri='http://localhost:8080'
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
                self.scopes,
                redirect_uri='http://localhost:8080'
            )
            self.cred = flow.run_local_server(
                port=8080,
                prompt='consent',
                access_type='offline'
            )
            with open(self.cred_pickle_file, 'wb') as token:
                pickle.dump(self.cred, token)
        return self.cred

