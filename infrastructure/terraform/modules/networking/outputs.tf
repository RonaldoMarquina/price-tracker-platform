output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "List of IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "List of IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security Group ID for the ALB"
  value       = aws_security_group.alb.id
}

output "api_security_group_id" {
  description = "Security Group ID for the Backend API"
  value       = aws_security_group.api.id
}

output "worker_security_group_id" {
  description = "Security Group ID for Worker and Dispatcher tasks"
  value       = aws_security_group.worker.id
}

output "database_security_group_id" {
  description = "Security Group ID for the RDS PostgreSQL database"
  value       = aws_security_group.database.id
}
