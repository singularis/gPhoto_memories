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
    photos = {}
    years = os.listdir(picFolder)
    logging.info(f"years {years}")
    for year in years:
        imageFolder = os.path.join(picFolder, str(year))
        imageList = os.listdir(imageFolder)
        imagelist = [os.path.join('pics', str(year)) + "/" + image for image in imageList]
        photos[int(year)] = imagelist
    logging.info(f"photos {photos}")
    return (
        render_template("index.html", years=[int(x) for x in years], photos=photos, date=date.today())
    )

@app.route('/metrics/')
def metrics():
    return Response(prometheus_client.generate_latest(), mimetype=CONTENT_TYPE_LATEST)



if __name__ == "__main__":
    logging.getLogger().setLevel(logging.ERROR)
    logger = logging.getLogger('werkzeug')
    logger.setLevel(logging.ERROR)
app.run(host="0.0.0.0")