terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50, < 6.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.13"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.30"
    }
  }

  # Enable a remote backend for shared state. Commented out so a reviewer
  # can run `terraform init` locally without S3 setup.
  #
  # backend "s3" {
  #   bucket         = "coding-agent-tfstate-<account>"
  #   key            = "envs/dev/terraform.tfstate"
  #   region         = "us-west-2"
  #   dynamodb_table = "coding-agent-tflock"
  #   encrypt        = true
  # }
}
