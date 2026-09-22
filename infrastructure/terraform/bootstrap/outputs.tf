output "state_bucket_name" {
  description = "S3 bucket for Terraform remote backend state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "backend_repository_url" {
  description = "ECR repository URL for backend container images"
  value       = aws_ecr_repository.backend.repository_url
}

output "worker_repository_url" {
  description = "ECR repository URL for worker container images"
  value       = aws_ecr_repository.worker.repository_url
}

output "internal_api_key_secret_arn" {
  description = "ARN of the Secrets Manager secret for internal API key"
  value       = aws_secretsmanager_secret.internal_api_key.arn
}

output "internal_api_key_secret_name" {
  description = "Exact name of the Secrets Manager secret for internal API key"
  value       = aws_secretsmanager_secret.internal_api_key.name
}

output "budget_name" {
  description = "Name of the provisioned AWS Budget"
  value       = aws_budgets_budget.demo.name
}
