import os
import shutil
import json
import pickle
import pandas as pd
import requests
from googleapiclient.discovery import build
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

class GooglePhotosApi:
    def __init__(self,
                 api_name='photoslibrary',
                 client_secret_file=r'./gcp-credentials/gPhoto_credentials.json',
                 api_version='v1',
                 scopes=['https://www.googleapis.com/auth/photoslibrary']):
        '''
        Initialize the Google Photos API
        '''
        self.api_name = api_name
        self.client_secret_file = client_secret_file
        self.api_version = api_version
        self.scopes = scopes
        self.cred_pickle_file = f'/app/credentials/token_{self.api_name}_{self.api_version}.pickle'
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

# Initialize photos api and create service
google_photos_api = GooglePhotosApi()
creds = google_photos_api.run_local_server()

def get_response_from_google_photos_api(year, month, day):
    url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
    payload = {
        "filters": {
            "dateFilter": {
                "dates": [
                    {"day": day, "month": month, "year": year}
                ]
            }
        }
    }
    headers = {
        'content-type': 'application/json',
        'Authorization': 'Bearer {}'.format(creds.token)
    }

    try:
        res = requests.request("POST", url, data=json.dumps(payload), headers=headers)
    except Exception as e:
        print('Request error:', e)
        return None

    return res

def list_of_media_items(year, month, day, media_items_df):
    items_list_df = pd.DataFrame()

    response = get_response_from_google_photos_api(year, month, day)
    if response is None:
        return pd.DataFrame(), media_items_df

    try:
        for item in response.json()['mediaItems']:
            item_data = pd.DataFrame([item])
            items_list_df = pd.concat([items_list_df, item_data])
            media_items_df = pd.concat([media_items_df, item_data])
    except Exception as e:
        print('Error processing response:', e)

    return items_list_df, media_items_df

# Create a list with all dates between start date and today
date_list = pd.date_range(date.today() - relativedelta(years=20), periods=20, freq=pd.DateOffset(years=1))
print(date_list)

media_items_df = pd.DataFrame()
destination_folder = '/app/static/pics'

# Remove all files and recreate the directory
shutil.rmtree(destination_folder, ignore_errors=True)
os.makedirs(destination_folder, exist_ok=True)

for single_date in date_list:
    items_df, media_items_df = list_of_media_items(year=single_date.year, month=single_date.month, day=single_date.day, media_items_df=media_items_df)

    if not items_df.empty:
        for index, item in items_df.iterrows():
            url = item['baseUrl'] + '=dv' if 'video' in item.get('mediaMetadata', {}) else item['baseUrl']
            response = requests.get(url)

            if response.status_code == 200:
                file_name = item['filename']
                year_folder = os.path.join(destination_folder, str(single_date.year))
                os.makedirs(year_folder, exist_ok=True)

                with open(os.path.join(year_folder, file_name), 'wb') as f:
                    f.write(response.content)

                print(f'Downloaded: {file_name}')
            else:
                print(f'Failed to download: {item["filename"]}, Status Code: {response.status_code}')

        print(f'Downloaded items for date: {single_date.year}/{single_date.month}/{single_date.day}')
    else:
        print(f'No media items found for date: {single_date.year}/{single_date.month}/{single_date.day}')

# Save a list of all media items to a csv file
current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f'item-list-{current_datetime}.csv'
media_items_df.to_csv(f'/app/media_items_list/{filename}', index=False)
print("Cycle is complete")
