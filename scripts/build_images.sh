#!/usr/bin/env bash
# Build and push both service images to ECR.
# Usage: ./scripts/build_images.sh <tag>
set -euo pipefail

TAG="${1:-0.1.0}"
AWS_REGION="${AWS_REGION:-us-west-2}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building images (tag=${TAG})"
docker build -f "${ROOT}/apps/slack_gateway/Dockerfile"  -t "slack-gateway:${TAG}"  "${ROOT}"
docker build -f "${ROOT}/apps/temporal_worker/Dockerfile" -t "temporal-worker:${TAG}" "${ROOT}"

echo "==> Tagging for ECR"
docker tag "slack-gateway:${TAG}"   "${REGISTRY}/coding-agent-slack-gateway:${TAG}"
docker tag "temporal-worker:${TAG}" "${REGISTRY}/coding-agent-temporal-worker:${TAG}"

echo "==> Pushing"
docker push "${REGISTRY}/coding-agent-slack-gateway:${TAG}"
docker push "${REGISTRY}/coding-agent-temporal-worker:${TAG}"

echo "Pushed:"
echo "  ${REGISTRY}/coding-agent-slack-gateway:${TAG}"
echo "  ${REGISTRY}/coding-agent-temporal-worker:${TAG}"
