data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# ==========================================
# VPC and Subnets
# ==========================================
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project}-${var.environment}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.project}-${var.environment}-igw"
  }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 1)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project}-${var.environment}-public-subnet-${count.index + 1}"
    Type = "Public"
  }
}

resource "aws_subnet" "private" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project}-${var.environment}-private-subnet-${count.index + 1}"
    Type = "Private"
  }
}

# ==========================================
# Route Tables
# ==========================================
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${var.project}-${var.environment}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  # Isolated private subnets: no route to Internet Gateway or NAT Gateway for demo
  tags = {
    Name = "${var.project}-${var.environment}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ==========================================
# Security Groups
# ==========================================
resource "aws_security_group" "alb" {
  name        = "${var.project}-${var.environment}-alb-sg"
  description = "Controls ingress to ALB exclusively from CloudFront origin prefix list"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.project}-${var.environment}-alb-sg"
  }
}

resource "aws_security_group_rule" "alb_ingress_cloudfront" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  prefix_list_ids   = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  security_group_id = aws_security_group.alb.id
  description       = "Allow HTTP from CloudFront origin-facing IPs only"
}

resource "aws_security_group_rule" "alb_egress_api" {
  type                     = "egress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
  security_group_id        = aws_security_group.alb.id
  description              = "Forward HTTP to Backend API container port"
}

resource "aws_security_group" "api" {
  name        = "${var.project}-${var.environment}-api-sg"
  description = "Controls ingress and egress for Backend API ECS tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.project}-${var.environment}-api-sg"
  }
}

resource "aws_security_group_rule" "api_ingress_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  security_group_id        = aws_security_group.api.id
  description              = "Allow traffic to API exclusively from ALB"
}

resource "aws_security_group_rule" "api_egress_database" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.database.id
  security_group_id        = aws_security_group.api.id
  description              = "PostgreSQL connection to RDS"
}

resource "aws_security_group_rule" "api_egress_https" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.api.id
  description       = "HTTPS egress for AWS APIs (ECR, CloudWatch, SecretsManager)"
}

resource "aws_security_group_rule" "api_egress_dns_udp" {
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "udp"
  cidr_blocks       = ["10.0.0.2/32"]
  security_group_id = aws_security_group.api.id
  description       = "DNS resolution via AmazonProvidedDNS"
}

resource "aws_security_group_rule" "api_egress_dns_tcp" {
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "tcp"
  cidr_blocks       = ["10.0.0.2/32"]
  security_group_id = aws_security_group.api.id
  description       = "DNS resolution via AmazonProvidedDNS"
}

resource "aws_security_group" "worker" {
  name        = "${var.project}-${var.environment}-worker-sg"
  description = "Controls egress for Scraping Worker, Dispatcher, Outbox and DLQ Indexer (0 Ingress)"
  vpc_id      = aws_vpc.this.id

  # ZERO ingress rules: No incoming connections permitted
  tags = {
    Name = "${var.project}-${var.environment}-worker-sg"
  }
}

resource "aws_security_group_rule" "worker_egress_database" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.database.id
  security_group_id        = aws_security_group.worker.id
  description              = "PostgreSQL connection to RDS"
}

resource "aws_security_group_rule" "worker_egress_https" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.worker.id
  description       = "HTTPS egress to external e-commerce stores and AWS APIs"
}

resource "aws_security_group_rule" "worker_egress_dns_udp" {
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "udp"
  cidr_blocks       = ["10.0.0.2/32"]
  security_group_id = aws_security_group.worker.id
  description       = "DNS resolution via AmazonProvidedDNS"
}

resource "aws_security_group_rule" "worker_egress_dns_tcp" {
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "tcp"
  cidr_blocks       = ["10.0.0.2/32"]
  security_group_id = aws_security_group.worker.id
  description       = "DNS resolution via AmazonProvidedDNS"
}

resource "aws_security_group" "database" {
  name        = "${var.project}-${var.environment}-db-sg"
  description = "Controls ingress to RDS PostgreSQL strictly from API and Worker SGs (0 Egress)"
  vpc_id      = aws_vpc.this.id

  # ZERO egress rules: Isolated database without Internet access
  tags = {
    Name = "${var.project}-${var.environment}-db-sg"
  }
}

resource "aws_security_group_rule" "db_ingress_api" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.api.id
  security_group_id        = aws_security_group.database.id
  description              = "PostgreSQL access from Backend API tasks"
}

resource "aws_security_group_rule" "db_ingress_worker" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.worker.id
  security_group_id        = aws_security_group.database.id
  description              = "PostgreSQL access from Worker/Dispatcher tasks"
}
