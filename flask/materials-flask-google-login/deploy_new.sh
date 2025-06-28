#! /bin/bash

docker build -t singularis314/gphoto:0.4 .
docker push singularis314/gphoto:0.4
kubectl rollout restart -n gphoto deployment gphoto-flask-deployment
