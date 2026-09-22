# ==========================================
# S3 Frontend Bucket
# ==========================================
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-${var.environment}-frontend-${var.bucket_suffix}"

  # ACADEMIC DEMO: force_destroy ensures clean deletion of all assets on terraform destroy
  force_destroy = true

  tags = {
    Name = "${var.project}-${var.environment}-frontend"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==========================================
# CloudFront Origin Access Control (OAC)
# ==========================================
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project}-${var.environment}-oac"
  description                       = "OAC for S3 frontend assets distribution"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ==========================================
# CloudFront Distribution
# ==========================================
resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project}-${var.environment} CloudFront CDN"
  default_root_object = "index.html"

  # Origin 1: S3 Bucket for Frontend SPA
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Origin 2: Application Load Balancer for /api/*
  origin {
    domain_name = var.alb_dns_name
    origin_id   = "alb-api"

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only" # Academic demo without custom ACM cert on ALB
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_keepalive_timeout = 5
      origin_read_timeout      = 30
    }

    # Secret header injected by CloudFront and validated by ALB listener rule
    custom_header {
      name  = "X-Origin-Verify"
      value = var.x_origin_verify_secret
    }
  }

  # Default behavior: Serve Frontend static SPA from S3
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
    compress    = true
  }

  # Ordered behavior: Forward /api/* requests to ALB
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "alb-api"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]

    # Cache explicitly disabled for dynamic API
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Accept"]

      cookies {
        forward = "none"
      }
    }

    compress = true
  }

  # SPA Routing Fallback: Route 403 and 404 to /index.html with status 200
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Default CloudFront SSL Certificate (*.cloudfront.net)
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project}-${var.environment}-cloudfront"
  }
}

# ==========================================
# S3 Bucket Policy for OAC
# ==========================================
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipalReadOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.this.arn
          }
        }
      }
    ]
  })
}
