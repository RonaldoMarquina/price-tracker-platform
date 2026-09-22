variable "project" {
  description = "Project name prefix"
  type        = string
  default     = "price-tracker"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "demo"
}

variable "aws_region" {
  description = "AWS region for provisioning bootstrap resources"
  type        = string
  default     = "us-east-1"
}

variable "budget_notification_email" {
  description = "Email address for AWS Budgets notifications"
  type        = string
  default     = "operator@example.com"
}
