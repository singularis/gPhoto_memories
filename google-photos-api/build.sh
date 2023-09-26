#!/bin/bash
docker build -t singularis314/gphoto_downloader:0.3 .
docker push singularis314/gphoto_downloader:0.3
kubectl delete -f gphoto.yaml --force
kubectl apply -f gphoto.yaml