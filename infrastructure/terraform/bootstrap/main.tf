data "aws_caller_identity" "current" {}

# ==============================================================================
# 1. Terraform Remote State S3 Bucket
# ==============================================================================
resource "aws_s3_bucket" "terraform_state" {
  bucket        = "${var.project}-${var.environment}-tfstate-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # Controlled for academic demonstration

  tags = {
    Name = "${var.project}-${var.environment}-tfstate"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==============================================================================
# 2. Immutable ECR Repositories with Vulnerability Scanning & Force Delete
# ==============================================================================
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project}-backend"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project}-backend"
  }
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.project}-worker"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project}-worker"
  }
}

# ==============================================================================
# 3. AWS Secrets Manager Secret Shell for INTERNAL_API_KEY (No Value in Terraform)
# ==============================================================================
resource "aws_secretsmanager_secret" "internal_api_key" {
  name                    = "${var.project}/internal-api-key-demo"
  description             = "Internal API Key for Price Tracker Platform manual scraping dispatch"
  recovery_window_in_days = 0

  tags = {
    Name = "${var.project}-internal-api-key-demo"
  }
}

# ==============================================================================
# 4. AWS Budgets ($5.00 USD Budget with $1, $3, $5 Alerts)
# ==============================================================================
resource "aws_budgets_budget" "demo" {
  name              = "${var.project}-${var.environment}-budget"
  budget_type       = "COST"
  limit_amount      = "5.0"
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2026-01-01_00:00"

  # Alert 1: $1.00 USD (20% actual spend)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 20.0
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_notification_email]
  }

  # Alert 2: $3.00 USD (60% actual spend)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 60.0
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_notification_email]
  }

  # Alert 3: $5.00 USD (100% actual or forecasted spend)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100.0
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_notification_email]
  }
}
