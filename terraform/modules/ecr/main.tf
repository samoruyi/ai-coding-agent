/**
 * ECR repository with image scanning + a small lifecycle policy.
 *
 * Lifecycle: keep the 20 most recent images, expire untagged images
 * after 14 days. Tuned for a take-home / dev environment; bump for prod.
 */

variable "name" {
  description = "Repository name."
  type        = string
}

resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  # AWS requires rules with tagStatus "any" to have the *highest* rulePriority
  # (lowest precedence / evaluated last) within each storage class.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 20 tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = { type = "expire" }
      },
    ]
  })
}

output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "repository_name" {
  value = aws_ecr_repository.this.name
}
