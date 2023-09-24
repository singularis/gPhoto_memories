import os
import shutil
import json
import pickle
import pandas
import requests
import pandas as pd
from googleapiclient.discovery import build
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

class GooglePhotosApi:
    def __init__(self,
                 api_name = 'photoslibrary',
                 client_secret_file= r'./gcp-credentials/gPhoto_credentials.json',
                 api_version = 'v1',
                 scopes = ['https://www.googleapis.com/auth/photoslibrary']):
        '''
        Args:
            client_secret_file: string, location where the requested credentials are saved
            api_version: string, the version of the service
            api_name: string, name of the api e.g."docs","photoslibrary",...
            api_version: version of the api
        '''

        self.api_name = api_name
        self.client_secret_file = client_secret_file
        self.api_version = api_version
        self.scopes = scopes
        self.cred_pickle_file = f'/app/credentials/token_{self.api_name}_{self.api_version}.pickle'

        self.cred = None

    def run_local_server(self):
        # is checking if there is already a pickle file with relevant credentials
        if os.path.exists(self.cred_pickle_file):
            with open(self.cred_pickle_file, 'rb') as token:
                self.cred = pickle.load(token)

        # if there is no pickle file with stored credentials, create one using google_auth_oauthlib.flow
        if not self.cred or not self.cred.valid:
            if self.cred and self.cred.expired and self.cred.refresh_token:
                self.cred.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.scopes)
                self.cred = flow.run_local_server()

            with open(self.cred_pickle_file, 'wb') as token:
                pickle.dump(self.cred, token)
        
        return self.cred

# initialize photos api and create service
google_photos_api = GooglePhotosApi()
creds = google_photos_api.run_local_server()

def get_response_from_medium_api(year, month, day):
    url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
    payload = {
                  "filters": {
                    "dateFilter": {
                      "dates": [
                        {
                          "day": day,
                          "month": month,
                          "year": year
                        }
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
    except:
        print('Request error') 
    
    return(res)


def get_response_from_medium_api(year, month, day):
    url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
    payload = {
                  "filters": {
                    "dateFilter": {
                      "dates": [
                        {
                          "day": day,
                          "month": month,
                          "year": year
                        }
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
    except:
        print('Request error') 
    
    return(res)


def list_of_media_items(year, month, day, media_items_df):
    '''
    Args:
        year, month, day: day for the filter of the API call 
        media_items_df: existing data frame with all find media items so far
    Return:
        media_items_df: data frame for media articles, extended by the articles found for the specified tag
        items_df: data frame with media items uploaded on specified date
    '''

    items_list_df = pd.DataFrame()
    
    # create request for specified date
    response = get_response_from_medium_api(year, month, day)

    try:
        for item in response.json()['mediaItems']:
            items_df = pd.DataFrame(item)
            items_df = items_df.rename(columns={"mediaMetadata": "creationTime"})
            items_df.set_index('creationTime')
            items_df = items_df[items_df.index == 'creationTime']

            #append the existing media_items data frame
            items_list_df = pd.concat([items_list_df, items_df])
            media_items_df = pd.concat([media_items_df, items_df])
    
    except:
        print(response.text)

    return(items_list_df, media_items_df)


# Images should only be downloaded if they are not already available in downloads
# Herefor the following code snippet, creates a list with all filenames in the /downloads/ folder
files_list = os.listdir(r'/app/static/pics')
files_list_df = pd.DataFrame(files_list)
files_list_df = files_list_df.rename(columns={0: "filename"})
files_list_df.head(2)

# create a list with all dates between start date and today
date_list = pandas.date_range(date.today() - relativedelta(years=20),periods=20,freq=pd.DateOffset(years=1))
print(date_list)

media_items_df = pd.DataFrame()

destination_folder = '/app/static/pics'

#Remove all files
shutil.rmtree(destination_folder)

os.mkdir(destination_folder)


for date in date_list:
    
    # get a list with all media items for specified date (year, month, day)
    items_df, media_items_df = list_of_media_items(year = date.year, month = date.month, day = date.day, media_items_df = media_items_df)

    if len(items_df) > 0:
        # full outer join of items_df and files_list_df, the result is a list of items of the given 
        #day that have not been downloaded yet
        # items_not_yet_downloaded_df = pd.merge(items_df, files_list_df,on='filename',how='left')
        # items_not_yet_downloaded_df.head(2)
    
        # download all items in items_not_yet_downloaded
        for index, item in items_df.iterrows():
            url = item.baseUrl
            response = requests.get(url)

            file_name = item.filename
            year_folder = os.path.join(destination_folder, str(date.year))
            if not os.path.exists(year_folder):
                os.mkdir(year_folder)
            with open(os.path.join(destination_folder,  str(date.year), file_name), 'wb') as f:
                f.write(response.content)
                f.close()
                
        print(f'Downloaded items for date: {date.year} / {date.month} / {date.day}')
    else:
        print(f'No media items found for date: {date.year} / {date.month} / {date.day}')
            
#save a list of all media items to a csv file
current_datetime = str(datetime.now())
filename = f'item-list-{current_datetime}.csv'

#save a list with all items in specified time frame
media_items_df.to_csv(f'/app/media_items_list/{filename}', index=True)
print("Сycle is done")
