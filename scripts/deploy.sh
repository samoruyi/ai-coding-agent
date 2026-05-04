#!/usr/bin/env bash
# Deploy the umbrella Helm chart against the EKS cluster from `terraform apply`.
# Usage: ./scripts/deploy.sh <tag> [namespace] [release]
set -euo pipefail

TAG="${1:-0.1.0}"
NAMESPACE="${2:-coding-agent}"
RELEASE="${3:-agent}"
AWS_REGION="${AWS_REGION:-us-west-2}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${ROOT}/terraform/envs/dev"

echo "==> Reading Terraform outputs"
pushd "${TF_DIR}" >/dev/null
CLUSTER_NAME="$(terraform output -raw cluster_name)"
ECR_GATEWAY="$(terraform output -raw ecr_gateway_repository_url)"
ECR_WORKER="$(terraform output -raw ecr_worker_repository_url)"
ROLE_GATEWAY="$(terraform output -raw irsa_gateway_role_arn)"
ROLE_WORKER="$(terraform output -raw irsa_worker_role_arn)"
popd >/dev/null

echo "==> Updating kubeconfig for ${CLUSTER_NAME}"
aws eks update-kubeconfig --region "${AWS_REGION}" --name "${CLUSTER_NAME}"

echo "==> Resolving Helm dependencies"
helm dependency update "${ROOT}/helm/platform"

echo "==> Installing release ${RELEASE} in namespace ${NAMESPACE}"
helm upgrade --install "${RELEASE}" "${ROOT}/helm/platform" \
  -n "${NAMESPACE}" --create-namespace \
  -f "${ROOT}/helm/platform/values.eks.yaml" \
  --set "slack-gateway.image.repository=${ECR_GATEWAY}" \
  --set "slack-gateway.image.tag=${TAG}" \
  --set "slack-gateway.serviceAccount.annotations.eks\.amazonaws\.com/role-arn=${ROLE_GATEWAY}" \
  --set "temporal-worker.image.repository=${ECR_WORKER}" \
  --set "temporal-worker.image.tag=${TAG}" \
  --set "temporal-worker.serviceAccount.annotations.eks\.amazonaws\.com/role-arn=${ROLE_WORKER}"

echo "==> Status"
kubectl -n "${NAMESPACE}" get pods,svc,ingress

echo "==> Done."
echo "    Populate Secrets Manager values, then re-roll the deployments:"
echo "      kubectl -n ${NAMESPACE} rollout restart deploy"
