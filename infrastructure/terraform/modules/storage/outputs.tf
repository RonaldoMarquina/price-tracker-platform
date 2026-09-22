output "s3_bucket_name" {
  description = "Name of the S3 bucket hosting frontend static files"
  value       = aws_s3_bucket.frontend.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket hosting frontend static files"
  value       = aws_s3_bucket.frontend.arn
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.this.id
}

output "cloudfront_domain_name" {
  description = "Generated domain name of the CloudFront distribution (HTTPS)"
  value       = aws_cloudfront_distribution.this.domain_name
}
