# ==========================================
# CloudWatch Logs
# ==========================================
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project}-${var.environment}"
  retention_in_days = 7 # Cost control for academic demo

  tags = {
    Name = "${var.project}-${var.environment}-ecs-logs"
  }
}

# ==========================================
# ECS Cluster
# ==========================================
resource "aws_ecs_cluster" "this" {
  name = "${var.project}-${var.environment}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # Cost control for academic demo
  }

  tags = {
    Name = "${var.project}-${var.environment}-cluster"
  }
}

# ==========================================
# Application Load Balancer
# ==========================================
resource "aws_lb" "this" {
  name               = "${var.project}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true

  tags = {
    Name = "${var.project}-${var.environment}-alb"
  }
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project}-${var.environment}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "8000"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.project}-${var.environment}-backend-tg"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  # Default action: 403 Forbidden if X-Origin-Verify header is absent or invalid
  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({ error = "Access denied: direct access prohibited" })
      status_code  = "403"
    }
  }
}

resource "aws_lb_listener_rule" "api_origin_verify" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [var.x_origin_verify_secret]
    }
  }
}

# ==========================================
# IAM Roles
# ==========================================
resource "aws_iam_role" "ecs_execution" {
  name = "${var.project}-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_execution" {
  name = "${var.project}-${var.environment}-ecs-execution-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRImagePull"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ecs.arn}:*"
      },
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          var.master_user_secret_arn,
          var.internal_api_key_secret_arn
        ]
      }
    ]
  })
}

# Task Roles (Minimal Privilege)
resource "aws_iam_role" "api_task" {
  name = "${var.project}-${var.environment}-api-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role" "worker_task" {
  name = "${var.project}-${var.environment}-worker-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "worker_sqs" {
  name = "${var.project}-${var.environment}-worker-sqs-policy"
  role = aws_iam_role.worker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WorkerPrimaryQueueAccess"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = [var.sqs_queue_arn]
      }
    ]
  })
}

resource "aws_iam_role" "outbox_publisher_task" {
  name = "${var.project}-${var.environment}-outbox-publisher-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "outbox_publisher_sqs" {
  name = "${var.project}-${var.environment}-outbox-publisher-sqs-policy"
  role = aws_iam_role.outbox_publisher_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "OutboxPublishPrimaryQueue"
        Effect = "Allow"
        # Note: sqs:SendMessage authorizes both single and SendMessageBatch operations
        Action   = ["sqs:SendMessage"]
        Resource = [var.sqs_queue_arn]
      }
    ]
  })
}

resource "aws_iam_role" "dlq_indexer_task" {
  name = "${var.project}-${var.environment}-dlq-indexer-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "dlq_indexer_sqs" {
  name = "${var.project}-${var.environment}-dlq-indexer-sqs-policy"
  role = aws_iam_role.dlq_indexer_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DlqIndexerQueueAccess"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = [var.sqs_dlq_arn]
      }
    ]
  })
}

resource "aws_iam_role" "dispatcher_task" {
  name = "${var.project}-${var.environment}-dispatcher-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role" "migration_task" {
  name = "${var.project}-${var.environment}-migration-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# EventBridge Scheduler Role
resource "aws_iam_role" "scheduler" {
  name = "${var.project}-${var.environment}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "${var.project}-${var.environment}-scheduler-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RunDispatcherTaskOnly"
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = [aws_ecs_task_definition.dispatcher.arn]
      },
      {
        Sid    = "PassExecutionAndTaskRole"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          aws_iam_role.ecs_execution.arn,
          aws_iam_role.dispatcher_task.arn
        ]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      }
    ]
  })
}

# ==========================================
# Task Definitions
# ==========================================

# 1. Backend API Task Definition (Backend Image)
resource "aws_ecs_task_definition" "backend_api" {
  family                   = "${var.project}-${var.environment}-backend-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.backend_image_uri
      essential = true
      command   = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "ENVIRONMENT", value = "production" },
        { name = "DOCS_ENABLED", value = "false" }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        },
        {
          name      = "INTERNAL_API_KEY"
          valueFrom = var.internal_api_key_secret_arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

# 2. Scraping Worker Task Definition (Worker Image)
resource "aws_ecs_task_definition" "scraping_worker" {
  family                   = "${var.project}-${var.environment}-scraping-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.worker_image_uri
      essential = true
      command   = ["python", "-m", "app.main"]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "QUEUE_BACKEND", value = "sqs" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "SCRAPING_QUEUE_URL", value = var.sqs_queue_url },
        { name = "QUEUE_NAME", value = var.sqs_queue_name },
        { name = "ENVIRONMENT", value = var.environment }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# 3. Outbox Publisher Task Definition (Backend Image)
resource "aws_ecs_task_definition" "outbox_publisher" {
  family                   = "${var.project}-${var.environment}-outbox-publisher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.outbox_publisher_task.arn

  container_definitions = jsonencode([
    {
      name      = "outbox-publisher"
      image     = var.backend_image_uri
      essential = true
      command   = ["python", "-m", "app.services.outbox_publisher"]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "QUEUE_BACKEND", value = "sqs" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "SCRAPING_QUEUE_URL", value = var.sqs_queue_url },
        { name = "QUEUE_NAME", value = var.sqs_queue_name },
        { name = "ENVIRONMENT", value = var.environment }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "outbox-publisher"
        }
      }
    }
  ])
}

# 4. DLQ Indexer Task Definition (Worker Image)
resource "aws_ecs_task_definition" "dlq_indexer" {
  family                   = "${var.project}-${var.environment}-dlq-indexer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.dlq_indexer_task.arn

  container_definitions = jsonencode([
    {
      name      = "dlq-indexer"
      image     = var.worker_image_uri
      essential = true
      command   = ["python", "-m", "app.services.dlq_indexer"]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "QUEUE_BACKEND", value = "sqs" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "SCRAPING_DLQ_URL", value = var.sqs_dlq_url },
        { name = "DLQ_NAME", value = var.sqs_dlq_name },
        { name = "ENVIRONMENT", value = var.environment }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "dlq-indexer"
        }
      }
    }
  ])
}

# 5. Dispatcher Task Definition (Backend Image - One-Shot)
resource "aws_ecs_task_definition" "dispatcher" {
  family                   = "${var.project}-${var.environment}-dispatcher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.dispatcher_task.arn

  container_definitions = jsonencode([
    {
      name      = "dispatcher"
      image     = var.backend_image_uri
      essential = true
      command   = ["python", "-m", "app.dispatcher", "--once"]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "DISPATCH_MODE", value = "once" },
        { name = "ENVIRONMENT", value = var.environment }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "dispatcher"
        }
      }
    }
  ])
}

# 6. Alembic Migration Task Definition (Backend Image - Manual One-Shot)
resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.project}-${var.environment}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.migration_task.arn

  container_definitions = jsonencode([
    {
      name      = "migration"
      image     = var.backend_image_uri
      essential = true
      command   = ["alembic", "upgrade", "head"]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "ENVIRONMENT", value = var.environment }
      ]
      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.master_user_secret_arn}:password::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "migration"
        }
      }
    }
  ])
}


# ==========================================
# Permanent ECS Services
# ==========================================

# Service 1: Backend API (Attached to ALB Target Group)
resource "aws_ecs_service" "backend_api" {
  name            = "${var.project}-${var.environment}-backend-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend_api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.api_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

# Service 2: Scraping Worker
resource "aws_ecs_service" "scraping_worker" {
  name            = "${var.project}-${var.environment}-scraping-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.scraping_worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.worker_security_group_id]
    assign_public_ip = true
  }
}

# Service 3: Outbox Publisher
resource "aws_ecs_service" "outbox_publisher" {
  name            = "${var.project}-${var.environment}-outbox-publisher"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.outbox_publisher.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.worker_security_group_id]
    assign_public_ip = true
  }
}

# Service 4: DLQ Indexer
resource "aws_ecs_service" "dlq_indexer" {
  name            = "${var.project}-${var.environment}-dlq-indexer"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.dlq_indexer.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.worker_security_group_id]
    assign_public_ip = true
  }
}

# ==========================================
# EventBridge Scheduler (Periodic Dispatcher)
# ==========================================
resource "aws_scheduler_schedule" "dispatcher" {
  name       = "${var.project}-${var.environment}-dispatcher"
  group_name = "default"
  state      = "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 hour)"

  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.dispatcher.arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = var.public_subnet_ids
        security_groups  = [var.worker_security_group_id]
        assign_public_ip = true
      }
    }
  }
}
