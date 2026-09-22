output "cloudfront_domain_name" {
  description = "Public HTTPS endpoint for the application (CloudFront CDN)"
  value       = module.storage.cloudfront_domain_name
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = module.storage.cloudfront_distribution_id
}

output "alb_dns_name" {
  description = "Internal ALB DNS name (accessible only via CloudFront with X-Origin-Verify)"
  value       = module.compute.alb_dns_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster"
  value       = module.compute.ecs_cluster_name
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket storing frontend build assets"
  value       = module.storage.s3_bucket_name
}

output "sqs_queue_url" {
  description = "URL of the primary SQS queue"
  value       = module.messaging.queue_url
}

output "sqs_dlq_url" {
  description = "URL of the Dead Letter Queue"
  value       = module.messaging.dlq_url
}

output "db_endpoint" {
  description = "Endpoint of the isolated PostgreSQL RDS instance (internal to VPC)"
  value       = module.database.db_endpoint
}
