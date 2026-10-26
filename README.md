# Get google photos and render your memories 

## Web UI (`web/`)

Flask serves the photo API and resizing; the page is a React 19 + Vite + Tailwind 4 app in `web/frontend`.

```
cd web/frontend
npm install
API_ORIGIN=http://racoon:30500 npm run dev   # hot reload against the cluster's API
npm run build                                # what the Docker image runs
```

`scripts/deploy_web.sh` builds the image (frontend included), pushes it and rolls out the deployment.
Vite 8 needs Node 20.19+ locally; the image builds with Node 22.


## google-client-app
Flask, Flask-Login, Login with Google, App setup as Google Client

Installation with Pipenv:

```
pipenv install
```

Installation without Pipenv:

```
pip install -r requirements.txt
```

Initalize the database by running app.py for the first time:

```
python app.py

 docker build --progress plain -t gphoto:0.1 . --network=host
```

Should see "Initialized the database."

Run the command again to start the Flask web server locally:

```
python app.py
```
https://towardsdatascience.com/how-to-download-images-from-google-photos-using-python-and-photos-library-api-6f9c1e60a3f3

https://geekyhumans.com/how-to-implement-google-login-in-flask-app/

https://realpython.com/flask-google-login/