#!/bin/bash
docker build -t singularis314/gphoto_downloader:0.3 .
docker push singularis314/gphoto_downloader:0.3
kubectl create job -n gphoto --from=cronjob/gphoto-downloader  test-downloader