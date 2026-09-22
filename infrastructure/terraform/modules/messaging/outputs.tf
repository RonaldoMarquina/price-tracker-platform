output "queue_id" {
  description = "The ID of the primary SQS queue"
  value       = aws_sqs_queue.main.id
}

output "queue_arn" {
  description = "The ARN of the primary SQS queue"
  value       = aws_sqs_queue.main.arn
}

output "queue_url" {
  description = "The URL of the primary SQS queue"
  value       = aws_sqs_queue.main.url
}

output "queue_name" {
  description = "The name of the primary SQS queue"
  value       = aws_sqs_queue.main.name
}

output "dlq_id" {
  description = "The ID of the SQS Dead Letter Queue"
  value       = aws_sqs_queue.dlq.id
}

output "dlq_arn" {
  description = "The ARN of the SQS Dead Letter Queue"
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "The URL of the SQS Dead Letter Queue"
  value       = aws_sqs_queue.dlq.url
}

output "dlq_name" {
  description = "The name of the SQS Dead Letter Queue"
  value       = aws_sqs_queue.dlq.name
}
