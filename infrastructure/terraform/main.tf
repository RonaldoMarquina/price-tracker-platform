module "networking" {
  source      = "./modules/networking"
  project     = var.project
  environment = var.environment
  vpc_cidr    = var.vpc_cidr
}

module "database" {
  source                     = "./modules/database"
  project                    = var.project
  environment                = var.environment
  private_subnet_ids         = module.networking.private_subnet_ids
  database_security_group_id = module.networking.database_security_group_id
  db_username                = var.db_username
  db_name                    = var.db_name
}

module "messaging" {
  source      = "./modules/messaging"
  project     = var.project
  environment = var.environment
}

module "compute" {
  source                      = "./modules/compute"
  project                     = var.project
  environment                 = var.environment
  aws_region                  = var.aws_region
  vpc_id                      = module.networking.vpc_id
  public_subnet_ids           = module.networking.public_subnet_ids
  alb_security_group_id       = module.networking.alb_security_group_id
  api_security_group_id       = module.networking.api_security_group_id
  worker_security_group_id    = module.networking.worker_security_group_id
  db_host                     = module.database.db_host
  db_port                     = module.database.db_port
  db_name                     = module.database.db_name
  db_username                 = var.db_username
  master_user_secret_arn      = module.database.master_user_secret_arn
  backend_image_uri           = var.backend_image_uri
  worker_image_uri            = var.worker_image_uri
  sqs_queue_url               = module.messaging.queue_url
  sqs_queue_arn               = module.messaging.queue_arn
  sqs_queue_name              = module.messaging.queue_name
  sqs_dlq_url                 = module.messaging.dlq_url
  sqs_dlq_arn                 = module.messaging.dlq_arn
  sqs_dlq_name                = module.messaging.dlq_name
  x_origin_verify_secret      = var.x_origin_verify_secret
  internal_api_key_secret_arn = var.internal_api_key_secret_arn
}

module "storage" {
  source                 = "./modules/storage"
  project                = var.project
  environment            = var.environment
  bucket_suffix          = var.bucket_suffix
  alb_dns_name           = module.compute.alb_dns_name
  x_origin_verify_secret = var.x_origin_verify_secret
}
