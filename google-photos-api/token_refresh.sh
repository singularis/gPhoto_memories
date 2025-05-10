
#!/bin/bash
rm -f /other_hdd/gphoto-credentials/token_dante_photoslibrary_v1.pickle
kubectl delete job -n gphoto test-downloader --force --grace-period=0
kubectl create job -n gphoto --from=cronjob/gphoto-downloader  test-downloader
echo "Waiting for pod to be ready..."
while [[ $(kubectl get pods -n gphoto -l job-name=test-downloader -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do
    sleep 1
done
POD_NAME=$(kubectl get pods -n gphoto -l job-name=test-downloader -o jsonpath="{.items[0].metadata.name}")
echo "Waiting for logs..."
sleep 10
kubectl logs -n gphoto pod/$POD_NAME
kubectl port-forward -n gphoto pod/$POD_NAME 8080:8080
