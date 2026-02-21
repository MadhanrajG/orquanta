variable "environment" {
  description = "Deployment environment: dev, staging, or production"
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, production."
  }
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "availability_zones" {
  description = "List of AZs to deploy into (at least 2 for HA)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "domain_name" {
  description = "Root domain for the platform (e.g. orquanta.ai). Leave empty to use ALB DNS."
  type        = string
  default     = ""
}

variable "api_image" {
  description = "Full ECR URI for the API Docker image (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/orquanta-api:production)"
  type        = string
}

variable "agents_image" {
  description = "Full ECR URI for the Agents / Celery Docker image"
  type        = string
}

# ─── Database ─────────────────────────────────────────────────────────────────
variable "db_instance_class" {
  description = "Aurora instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Database storage in GB"
  type        = number
  default     = 20
}

# ─── ECS API Service ─────────────────────────────────────────────────────────
variable "api_cpu" {
  description = "ECS task CPU units (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "ECS task memory in MB"
  type        = number
  default     = 2048
}

variable "min_api_tasks" {
  description = "Minimum number of API ECS tasks (auto-scales up from this)"
  type        = number
  default     = 1
}

variable "max_api_tasks" {
  description = "Maximum number of API ECS tasks"
  type        = number
  default     = 5
}

# ─── ECS Celery/Agents Service ────────────────────────────────────────────────
variable "celery_cpu" {
  description = "Celery worker task CPU units"
  type        = number
  default     = 512
}

variable "celery_memory" {
  description = "Celery worker task memory in MB"
  type        = number
  default     = 1024
}

variable "min_celery_tasks" {
  description = "Minimum Celery worker tasks"
  type        = number
  default     = 1
}

variable "max_celery_tasks" {
  description = "Maximum Celery worker tasks"
  type        = number
  default     = 10
}
