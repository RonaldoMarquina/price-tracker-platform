variable "project" {
  description = "Project name used as a prefix for all resources"
  type        = string
  default     = "price-tracker"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo", "dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: demo, dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region for infrastructure provisioning"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the Virtual Private Cloud"
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_username" {
  description = "Master username for PostgreSQL RDS instance"
  type        = string
  default     = "postgres"
}

variable "db_name" {
  description = "Default database name for PostgreSQL"
  type        = string
  default     = "price_tracker"
}

variable "backend_image_uri" {
  description = "Immutable ECR container image URI for backend, outbox publisher, and dispatcher"
  type        = string
  default     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/price-tracker-backend:sha-6ddb0d3"

  validation {
    condition     = !endswith(var.backend_image_uri, ":latest")
    error_message = "Using ':latest' as an image tag is prohibited. Use immutable commit SHA tags."
  }
}

variable "worker_image_uri" {
  description = "Immutable ECR container image URI for scraping worker and DLQ indexer"
  type        = string
  default     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/price-tracker-worker:sha-6ddb0d3"

  validation {
    condition     = !endswith(var.worker_image_uri, ":latest")
    error_message = "Using ':latest' as an image tag is prohibited. Use immutable commit SHA tags."
  }
}

variable "x_origin_verify_secret" {
  description = "Shared secret header value sent from CloudFront to ALB to verify request origin"
  type        = string
  sensitive   = true
  default     = "demo-origin-verify-secret-token-32chars"

  validation {
    condition     = length(var.x_origin_verify_secret) >= 16
    error_message = "The X-Origin-Verify secret must be at least 16 characters in length."
  }
}

variable "bucket_suffix" {
  description = "Unique suffix appended to S3 bucket names to prevent global collisions"
  type        = string
  default     = "demo-assets"
}

variable "internal_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret storing the internal API key"
  type        = string
  default     = "arn:aws:secretsmanager:us-east-1:123456789012:secret:price-tracker/internal-api-key-demo"
}
