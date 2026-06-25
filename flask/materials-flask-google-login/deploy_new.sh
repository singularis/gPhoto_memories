#! /bin/bash
# Deploy gPhoto Memories app
# The PVC at /other_hdd/gphoto is mounted as /app/static/ in the pod,
# so we must sync static files there after every build.

set -e

TAG="0.8"
STATIC_PVC="/other_hdd/gphoto"

echo "── Building docker.io/singularis314/gphoto:$TAG ──"
docker build -t docker.io/singularis314/gphoto:$TAG .

echo "── Pushing ──"
docker push docker.io/singularis314/gphoto:$TAG

echo "── Syncing static files to PVC ($STATIC_PVC) ──"
cp -r static/styles/main.css "$STATIC_PVC/styles/main.css"
cp -f static/brand.jpeg "$STATIC_PVC/brand.jpeg" 2>/dev/null || true

echo "── Rolling out ──"
kubectl set image -n gphoto deployment/gphoto-flask-deployment gphoto-flask=docker.io/singularis314/gphoto:$TAG
kubectl rollout status -n gphoto deployment/gphoto-flask-deployment

echo "✅ Deployed gphoto:$TAG"
