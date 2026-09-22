resource "aws_db_subnet_group" "this" {
  name        = "${var.project}-${var.environment}-db-subnet-group"
  description = "Subnet group for isolated RDS PostgreSQL in private subnets"
  subnet_ids  = var.private_subnet_ids

  tags = {
    Name = "${var.project}-${var.environment}-db-subnet-group"
  }
}

resource "aws_db_instance" "postgres" {
  identifier            = "${var.project}-${var.environment}-postgres"
  engine                = "postgres"
  engine_version        = "16"
  instance_class        = "db.t4g.micro"
  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true
  multi_az              = false # Cost optimization: Single-AZ for demo environment

  db_name  = var.db_name
  username = var.db_username

  # Automatic password management in AWS Secrets Manager (no plaintext passwords in Terraform)
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.database_security_group_id]
  publicly_accessible    = false

  # ============================================================================
  # ACADEMIC DEMO SETTINGS (Strictly prohibited in production environments)
  # ============================================================================
  # skip_final_snapshot and deletion_protection=false ensure total destruction
  # and zero lingering storage costs upon running 'terraform destroy'.
  skip_final_snapshot = true
  deletion_protection = false

  auto_minor_version_upgrade = true

  tags = {
    Name = "${var.project}-${var.environment}-postgres"
  }
}
