import os
import shutil
import json
import pandas as pd
import requests
import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from gphoto import api
from google.auth.transport.requests import Request

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("application.log"),
                        logging.StreamHandler()
                    ])

# Create a logger
logger = logging.getLogger(__name__)

users_json = os.getenv('USERS', '[]')  # Default to an empty list if not set
users = json.loads(users_json)

logger.info("Starting downloader job")

destination_folder = '/app/static/pics'
# Remove all files and recreate the directory
shutil.rmtree(destination_folder, ignore_errors=True)
os.makedirs(destination_folder, exist_ok=True)

for user in users:
    logger.info(f"Processing user: {user}")
    google_photos_api = api.GooglePhotosApi(user)
    creds = google_photos_api.run_local_server()

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        logger.info("Token refreshed successfully.")

    def get_response_from_google_photos_api(year, month, day):
        photo_url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
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
            res = requests.request("POST", photo_url, data=json.dumps(payload), headers=headers)
            logger.debug(f"Response Raw: {res.raw}")
        except Exception as e:
            logger.error(f'Request error: {e}')
            return None

        return res

    def list_of_media_items(year, month, day, media_items_df):
        items_list_df = pd.DataFrame()

        response = get_response_from_google_photos_api(year, month, day)
        if response is None:
            return pd.DataFrame(), media_items_df

        try:
            logger.debug(f'Received data: {response.json()}')
            for item in response.json().get('mediaItems', []):
                item_data = pd.DataFrame([item])
                items_list_df = pd.concat([items_list_df, item_data])
                media_items_df = pd.concat([media_items_df, item_data])
        except Exception as e:
            logger.error(f'Error processing response: {e}')

        return items_list_df, media_items_df

    # Create a list with all dates between start date and today
    date_list = pd.date_range(date.today() - relativedelta(years=20), periods=20, freq=pd.DateOffset(years=1))
    logger.debug(f"Dates list to fetch: {date_list}")
    media_items_df_init = pd.DataFrame()
    for single_date in date_list:
        items_df, media_items_df = list_of_media_items(year=single_date.year, month=single_date.month,
                                                       day=single_date.day,
                                                       media_items_df=media_items_df_init)

        if not items_df.empty:
            for index, item in items_df.iterrows():
                url = item['baseUrl'] + '=dv' if 'video' in item.get('mediaMetadata', {}) else item['baseUrl']
                response = requests.get(url)

                if response.status_code == 200:
                    name_part, extension = item['filename'].rsplit('.', 1)
                    file_name = f"{name_part}_{user}.{extension}"
                    year_folder = os.path.join(destination_folder, str(single_date.year))
                    os.makedirs(year_folder, exist_ok=True)

                    with open(os.path.join(year_folder, file_name), 'wb') as f:
                        f.write(response.content)

                    logger.debug(f'Downloaded: {file_name}')
                else:
                    logger.warning(f'Failed to download: {item["filename"]}, Status Code: {response.status_code}')

            logger.info(f'Downloaded items for date: {single_date.year}/{single_date.month}/{single_date.day}')
        else:
            logger.info(f'No media items found for date: {single_date.year}/{single_date.month}/{single_date.day}')

    # Save a list of all media items to a csv file
    current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'item-list-{current_datetime}.csv'
logger.info("Cycle is done")