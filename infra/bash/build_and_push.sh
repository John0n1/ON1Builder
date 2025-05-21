#!/bin/bash
# ON1Builder Build and Push Docker Image Script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY=${DOCKER_REGISTRY:-"ghcr.io"}
REPOSITORY=${DOCKER_REPOSITORY:-"john0n1/on1builder"}
TAG=${DOCKER_TAG:-"latest"}
FULL_IMAGE_NAME="${REGISTRY}/${REPOSITORY}:${TAG}"

# Print banner
echo "============================================================"
echo "ON1Builder Docker Image Build and Push"
echo "============================================================"
echo "Project directory: $PROJECT_DIR"
echo "Docker image: $FULL_IMAGE_NAME"
echo "============================================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Build the Docker image
echo "Building Docker image..."
cd "$PROJECT_DIR"
docker build -t "$FULL_IMAGE_NAME" .

# Check if we need to push the image
if [ -z "$SKIP_PUSH" ]; then
    # Check if we need to login to the Docker registry
    if [ -n "$DOCKER_USERNAME" ] && [ -n "$DOCKER_PASSWORD" ]; then
        echo "Logging in to Docker registry..."
        echo "$DOCKER_PASSWORD" | docker login "$REGISTRY" -u "$DOCKER_USERNAME" --password-stdin
    elif [ -n "$GITHUB_TOKEN" ]; then
        echo "Logging in to GitHub Container Registry..."
        echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
    fi

    # Push the Docker image
    echo "Pushing Docker image..."
    docker push "$FULL_IMAGE_NAME"
    
    # Push latest tag if specified
    if [ "$TAG" != "latest" ] && [ -n "$PUSH_LATEST" ]; then
        LATEST_IMAGE_NAME="${REGISTRY}/${REPOSITORY}:latest"
        echo "Tagging and pushing as latest..."
        docker tag "$FULL_IMAGE_NAME" "$LATEST_IMAGE_NAME"
        docker push "$LATEST_IMAGE_NAME"
    fi
    
    echo "Docker image pushed successfully!"
else
    echo "Skipping push to registry"
fi

echo "============================================================"
echo "Build completed successfully!"
echo "============================================================"