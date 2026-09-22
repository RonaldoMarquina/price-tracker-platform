variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for the DB subnet group"
  type        = list(string)
}

variable "database_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

variable "db_username" {
  description = "Master username for PostgreSQL"
  type        = string
  default     = "postgres"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "price_tracker"
}
