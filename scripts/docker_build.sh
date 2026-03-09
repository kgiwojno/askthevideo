#!/usr/bin/env bash
set -e

IMAGE_NAME="${IMAGE_NAME:-askthevideo}"
TAG="${TAG:-latest}"

echo "Building $IMAGE_NAME:$TAG ..."
docker build -t "$IMAGE_NAME:$TAG" .

echo ""
echo "Done. To run locally:"
echo "  docker run --env-file .env.docker -p 8000:8000 $IMAGE_NAME:$TAG"
