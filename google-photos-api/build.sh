#!/bin/bash
docker build -t singularis314/gphoto_downloader:0.7 .
docker push singularis314/gphoto_downloader:0.7
kubectl delete job -n gphoto test-downloader --force --grace-period=0
kubectl create job -n gphoto --from=cronjob/gphoto-downloader  test-downloader