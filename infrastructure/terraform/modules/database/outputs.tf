output "db_endpoint" {
  description = "The connection endpoint for the RDS PostgreSQL database"
  value       = aws_db_instance.postgres.endpoint
}

output "db_host" {
  description = "The hostname of the RDS instance"
  value       = aws_db_instance.postgres.address
}

output "db_port" {
  description = "The port the database accepts connections on"
  value       = aws_db_instance.postgres.port
}

output "db_name" {
  description = "The database name"
  value       = aws_db_instance.postgres.db_name
}

output "master_user_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret holding the master user password"
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}
