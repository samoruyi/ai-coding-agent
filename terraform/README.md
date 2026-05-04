# Terraform

Provisions the AWS infrastructure that hosts the Coding Agent Platform.

## Layout

```
terraform/
├── envs/
│   └── dev/        # The deployable root module (one per environment)
└── modules/
    ├── ecr/        # ECR repo with scan-on-push + lifecycle rules
    └── secrets/    # Empty-by-default Secrets Manager secrets
```

VPC and EKS are provisioned via the upstream `terraform-aws-modules/vpc/aws`
and `terraform-aws-modules/eks/aws` modules to avoid reinventing
well-tested infra.

## What it creates

| Resource | Purpose |
| --- | --- |
| VPC + 3 public/private subnets + 1 NAT gateway | EKS data plane |
| EKS cluster (`<name>-<region>`) + managed node group | Hosts workloads |
| EKS addons: vpc-cni, coredns, kube-proxy, ebs-csi | Cluster basics |
| ECR repo `coding-agent-slack-gateway` | Slack gateway image |
| ECR repo `coding-agent-temporal-worker` | Worker image |
| Secrets Manager `coding-agent-slack-gateway` | Slack tokens |
| Secrets Manager `coding-agent-temporal-worker` | LLM + GitHub tokens |
| IRSA role `coding-agent-slack-gateway` | KSA `agent-slack-gateway` |
| IRSA role `coding-agent-temporal-worker` | KSA `agent-temporal-worker` |

## Usage

```bash
cd terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

After apply, hook your kubeconfig and read outputs:

```bash
$(terraform output -raw kubeconfig_command)
terraform output -raw irsa_gateway_role_arn
terraform output -raw ecr_gateway_repository_url
```

## Destroying

```bash
terraform destroy
```

Secrets Manager uses `recovery_window_in_days = 0` so destroy deletes
immediately. Bump that for prod environments.
