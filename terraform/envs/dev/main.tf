/**
 * Coding Agent Platform - dev environment.
 *
 * Provisioning order (each block has a comment explaining "why" rather
 * than "what"; the `what` is in the resource names):
 *   1. VPC          - private subnets for the EKS data plane.
 *   2. EKS          - managed control plane + a single managed node group.
 *   3. ECR repos    - one each for the gateway and worker images.
 *   4. Secrets      - placeholders the application reads from at runtime.
 *   5. IRSA roles   - per-service IAM role bound to a Kubernetes SA so the
 *                     workload can fetch secrets without long-lived keys.
 */

provider "aws" {
  region = var.region
  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}

# We default to public-only EKS API for simplicity. Lock down via
# `cluster_endpoint_public_access_cidrs` for a real prod environment.
locals {
  cluster_name = "${var.name}-${var.region}"
}

# -----------------------------------------------------------------------------
# 1. VPC
# Three private subnets (one per AZ) with a single NAT gateway for outbound
# traffic. We tag the subnets so the AWS Load Balancer Controller picks them
# up automatically when slack-gateway provisions an ALB.
# -----------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.7"

  name = "${var.name}-vpc"
  cidr = var.vpc_cidr
  azs  = var.azs

  private_subnets = [for i, _ in var.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in var.azs : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  enable_nat_gateway      = true
  single_nat_gateway      = true # cost optimization for dev
  enable_dns_hostnames    = true
  enable_dns_support      = true
  map_public_ip_on_launch = false

  public_subnet_tags = {
    "kubernetes.io/role/elb"                      = 1
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"             = 1
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }
}


module "irsa_ebs_csi" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.39"
  role_name             = "${var.name}-ebs-csi"
  attach_ebs_csi_policy = true
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# -----------------------------------------------------------------------------
# 2. EKS
# We use the upstream module so we get IRSA OIDC, addons, and node-group
# IAM "for free". Public endpoint access is on for ease of `kubectl` from
# laptops; restrict via `cluster_endpoint_public_access_cidrs` for prod.
# -----------------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.13"

  cluster_name    = local.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  cluster_addons = {
    coredns            = {}
    kube-proxy         = {}
    vpc-cni            = {}
    aws-ebs-csi-driver = {}
    aws-ebs-csi-driver = {
      service_account_role_arn = module.irsa_ebs_csi.iam_role_arn
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      ami_type       = "AL2_x86_64"
      desired_size   = var.node_desired_size
      min_size       = var.node_min_size
      max_size       = var.node_max_size

      labels = {
        workload = "coding-agent"
      }
    }
  }
}

# -----------------------------------------------------------------------------
# 3. ECR
# One repo per service. Image scanning on push gives us a free first line
# of defense; the lifecycle policy keeps the registry from growing forever.
# -----------------------------------------------------------------------------
module "ecr_gateway" {
  source = "../../modules/ecr"
  name   = "${var.name}-slack-gateway"
}

module "ecr_worker" {
  source = "../../modules/ecr"
  name   = "${var.name}-temporal-worker"
}

# -----------------------------------------------------------------------------
# 4. Secrets
# We provision *empty* Secrets Manager secrets and let an operator populate
# them via the AWS console / CLI / secrets pipeline. The secret name is
# what the External Secrets Operator references from the cluster.
# -----------------------------------------------------------------------------
module "secrets_gateway" {
  source = "../../modules/secrets"
  name   = "${var.name}-slack-gateway"
  keys   = ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"]
}

module "secrets_worker" {
  source = "../../modules/secrets"
  name   = "${var.name}-temporal-worker"
  keys   = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN", "GITHUB_TOKEN"]
}

# -----------------------------------------------------------------------------
# 5. IRSA roles
# Each role trusts the cluster's OIDC provider and is scoped to a specific
# Kubernetes ServiceAccount via a StringEquals condition on `sub`.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "secrets_read_gateway" {
  statement {
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [module.secrets_gateway.secret_arn]
  }
}

data "aws_iam_policy_document" "secrets_read_worker" {
  statement {
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [module.secrets_worker.secret_arn]
  }
}

module "irsa_gateway" {
  source           = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version          = "~> 5.39"
  role_name        = "${var.name}-slack-gateway"
  role_policy_arns = {}
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["coding-agent:agent-slack-gateway"]
    }
  }
}

module "irsa_worker" {
  source           = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version          = "~> 5.39"
  role_name        = "${var.name}-temporal-worker"
  role_policy_arns = {}
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["coding-agent:agent-temporal-worker"]
    }
  }
}

resource "aws_iam_role_policy" "irsa_gateway_secrets" {
  name   = "${var.name}-slack-gateway-secrets"
  role   = module.irsa_gateway.iam_role_name
  policy = data.aws_iam_policy_document.secrets_read_gateway.json
}

resource "aws_iam_role_policy" "irsa_worker_secrets" {
  name   = "${var.name}-temporal-worker-secrets"
  role   = module.irsa_worker.iam_role_name
  policy = data.aws_iam_policy_document.secrets_read_worker.json
}
