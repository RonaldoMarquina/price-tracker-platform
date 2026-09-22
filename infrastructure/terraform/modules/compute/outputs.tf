output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster"
  value       = aws_ecs_cluster.this.name
}

output "ecs_cluster_id" {
  description = "ID of the ECS Fargate cluster"
  value       = aws_ecs_cluster.this.id
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.this.arn
}

output "target_group_arn" {
  description = "ARN of the Backend API target group"
  value       = aws_lb_target_group.backend.arn
}

output "backend_service_name" {
  description = "Name of the Backend API ECS service"
  value       = aws_ecs_service.backend_api.name
}

output "worker_service_name" {
  description = "Name of the Scraping Worker ECS service"
  value       = aws_ecs_service.scraping_worker.name
}

output "outbox_publisher_service_name" {
  description = "Name of the Outbox Publisher ECS service"
  value       = aws_ecs_service.outbox_publisher.name
}

output "dlq_indexer_service_name" {
  description = "Name of the DLQ Indexer ECS service"
  value       = aws_ecs_service.dlq_indexer.name
}
