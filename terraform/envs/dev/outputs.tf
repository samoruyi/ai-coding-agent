output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "kubeconfig_command" {
  description = "Run this to update your local kubeconfig."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "ecr_gateway_repository_url" {
  value = module.ecr_gateway.repository_url
}

output "ecr_worker_repository_url" {
  value = module.ecr_worker.repository_url
}

output "secrets_gateway_arn" {
  value = module.secrets_gateway.secret_arn
}

output "secrets_worker_arn" {
  value = module.secrets_worker.secret_arn
}

output "irsa_gateway_role_arn" {
  description = "Annotate the slack-gateway ServiceAccount with this ARN."
  value       = module.irsa_gateway.iam_role_arn
}

output "irsa_worker_role_arn" {
  description = "Annotate the temporal-worker ServiceAccount with this ARN."
  value       = module.irsa_worker.iam_role_arn
}
