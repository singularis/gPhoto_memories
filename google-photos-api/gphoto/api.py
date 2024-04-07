from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os
import logging
import google.auth.exceptions


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
            scopes = ['https://www.googleapis.com/auth/photoslibrary']
        self.api_name = api_name
        self.account_name = account_name
        self.client_secret_file = os.path.join(client_secret_path + f"gcp-credentials-{account_name}"
                                               + f"/gPhoto_credentials_{account_name}" + ".json")
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
                try:
                    self.cred.refresh(Request())
                except google.auth.exceptions.RefreshError as e:
                    logger.critical(f"Cannot refresh creds, {e}, cleaning up existing token")
                    os.unlink(self.cred_pickle_file)
                    logger.info(f"Cleaned up configs, starting clean flow")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.scopes)
                self.cred = flow.run_local_server()

                with open(self.cred_pickle_file, 'wb') as token:
                    pickle.dump(self.cred, token)
            except Exception as e:
                logger.critical(f"Unknown except {e}, exiting")
                exit()

        return self.cred
