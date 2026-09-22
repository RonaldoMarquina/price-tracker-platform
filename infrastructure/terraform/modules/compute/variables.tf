variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "aws_region" {
  description = "AWS Region"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ECS tasks and ALB"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for the ALB"
  type        = string
}

variable "api_security_group_id" {
  description = "Security group ID for Backend API tasks"
  type        = string
}

variable "worker_security_group_id" {
  description = "Security group ID for Worker, Dispatcher, Outbox and DLQ Indexer tasks"
  type        = string
}

variable "db_host" {
  description = "RDS PostgreSQL hostname"
  type        = string
}

variable "db_port" {
  description = "RDS PostgreSQL port"
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Database master username"
  type        = string
}

variable "master_user_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for master user password"
  type        = string
}

variable "backend_image_uri" {
  description = "Immutable ECR container image URI for backend, outbox publisher and dispatcher"
  type        = string
}

variable "worker_image_uri" {
  description = "Immutable ECR container image URI for scraping worker and DLQ indexer"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the primary SQS queue"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the primary SQS queue"
  type        = string
}

variable "sqs_queue_name" {
  description = "Name of the primary SQS queue"
  type        = string
}

variable "sqs_dlq_url" {
  description = "URL of the SQS Dead Letter Queue"
  type        = string
}

variable "sqs_dlq_arn" {
  description = "ARN of the SQS Dead Letter Queue"
  type        = string
}

variable "sqs_dlq_name" {
  description = "Name of the SQS Dead Letter Queue"
  type        = string
}

variable "x_origin_verify_secret" {
  description = "Secret value expected in X-Origin-Verify header"
  type        = string
  sensitive   = true
}
