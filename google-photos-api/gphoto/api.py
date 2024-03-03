from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os


class GooglePhotosApi:
    def __init__(self,
                 account_name: str,
                 api_name='photoslibrary',
                 client_secret_file=r'./gcp-credentials/gPhoto_credentials.json',
                 api_version='v1',
                 scopes=None):
        """
        Initialize the Google Photos API
        """
        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/photoslibrary']
        self.api_name = api_name
        self.account_name = account_name
        self.client_secret_file = client_secret_file
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
                self.cred.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.scopes)
                self.cred = flow.run_local_server()

            with open(self.cred_pickle_file, 'wb') as token:
                pickle.dump(self.cred, token)

        return self.cred
