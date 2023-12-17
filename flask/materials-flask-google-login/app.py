# Python standard libraries
import os
from datetime import date
import logging
from flask import Flask, redirect, request, url_for, render_template, Response
from helpers.middleware import setup_metrics
import prometheus_client


picFolder = '/app/static/pics/'

logging.basicConfig()

# Flask app setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = picFolder
setup_metrics(app)

CONTENT_TYPE_LATEST = str('text/plain; version=0.0.4; charset=utf-8')


@app.route("/")
def index():
    media = {}
    years = os.listdir(picFolder)
    logging.info(f"years {years}")
    for year in years:
        mediaFolder = os.path.join(picFolder, str(year))
        fileList = os.listdir(mediaFolder)
        year_media = {'images': [], 'videos': []}
        for file in fileList:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.heic')):
                year_media['images'].append(os.path.join('pics', str(year), file))
            elif file.lower().endswith(('.mp4', '.mov', '.avi')):
                year_media['videos'].append(os.path.join('pics', str(year), file))
        media[int(year)] = year_media
    return render_template("index.html", years=[int(x) for x in years], media=media, date=date.today())

@app.route('/metrics/')
def metrics():
    return Response(prometheus_client.generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    logger = logging.getLogger('werkzeug')
    logger.setLevel(logging.ERROR)
app.run(host="0.0.0.0")