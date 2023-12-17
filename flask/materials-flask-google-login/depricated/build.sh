#!/bin/bash
docker build -t singularis314/gphoto:0.2 .
docker push singularis314/gphoto:0.2
kubectl delete -f gphoto.yaml
kubectl apply -f gphoto.yaml