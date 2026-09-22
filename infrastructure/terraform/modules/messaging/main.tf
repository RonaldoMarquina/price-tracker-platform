resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project}-${var.environment}-scraping-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${var.project}-${var.environment}-scraping-jobs-dlq"
    Type = "DeadLetterQueue"
  }
}

resource "aws_sqs_queue" "main" {
  name                       = "${var.project}-${var.environment}-scraping-jobs"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.project}-${var.environment}-scraping-jobs"
    Type = "PrimaryQueue"
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main.arn]
  })
}
