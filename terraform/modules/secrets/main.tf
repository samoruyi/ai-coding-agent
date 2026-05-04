/**
 * AWS Secrets Manager secret with a JSON key/value structure.
 *
 * We pre-create the secret with empty placeholders for each key in
 * `var.keys`, then operators populate them out-of-band. The Kubernetes
 * workload reads them via External Secrets Operator (recommended) or
 * via direct GetSecretValue calls.
 *
 * Note: the `recovery_window_in_days = 0` lets `terraform destroy`
 * actually delete the secret immediately rather than scheduling a
 * 7-30 day recovery window. Convenient for take-home cleanup; for
 * production set this to >= 7.
 */

variable "name" {
  description = "Logical name; used as the Secrets Manager secret name."
  type        = string
}

variable "keys" {
  description = "Keys to seed in the secret JSON, all set to empty strings."
  type        = list(string)
}

resource "aws_secretsmanager_secret" "this" {
  name                    = var.name
  description             = "Coding Agent Platform secret: ${var.name}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id     = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({ for k in var.keys : k => "" })

  # We don't want Terraform to clobber any values an operator pasted in
  # via the AWS console after the initial seed.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "secret_arn" {
  value = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  value = aws_secretsmanager_secret.this.name
}
