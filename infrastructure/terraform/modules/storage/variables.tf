variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "bucket_suffix" {
  description = "Unique suffix for the S3 bucket"
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  type        = string
}

variable "x_origin_verify_secret" {
  description = "Shared secret header value for CloudFront to ALB validation"
  type        = string
  sensitive   = true
}
