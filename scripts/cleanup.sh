#!/usr/bin/env bash
# Tear everything down: Helm release, then Terraform.
# Usage: ./scripts/cleanup.sh [namespace] [release]
set -euo pipefail

NAMESPACE="${1:-coding-agent}"
RELEASE="${2:-agent}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Uninstalling Helm release '${RELEASE}' in '${NAMESPACE}'"
helm uninstall "${RELEASE}" -n "${NAMESPACE}" || true
kubectl delete namespace "${NAMESPACE}" --ignore-not-found

echo "==> Destroying Terraform infra"
cd "${ROOT}/terraform/envs/dev"
terraform destroy -auto-approve

echo "==> Done. Remember to revoke any GitHub PATs / Slack tokens you minted."
