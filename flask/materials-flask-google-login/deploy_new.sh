#! /bin/bash

docker build -t docker.io/singularis314/gphoto:0.8 .
docker push docker.io/singularis314/gphoto:0.8
kubectl set image -n gphoto deployment/gphoto-flask-deployment gphoto-flask=docker.io/singularis314/gphoto:0.8
kubectl rollout status -n gphoto deployment/gphoto-flask-deployment
