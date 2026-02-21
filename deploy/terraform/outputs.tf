output "api_url" {
  description = "Base URL of the OrQuanta API"
  value       = var.domain_name != "" ? "https://api.${var.domain_name}" : "http://${aws_lb.main.dns_name}"
}

output "frontend_url" {
  description = "URL of the OrQuanta frontend dashboard"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_lb.main.dns_name}"
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain (if enabled)"
  value       = length(aws_cloudfront_distribution.frontend) > 0 ? aws_cloudfront_distribution.frontend[0].domain_name : ""
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "db_endpoint" {
  description = "Aurora PostgreSQL cluster endpoint"
  value       = aws_rds_cluster.main.endpoint
  sensitive   = true
}

output "db_reader_endpoint" {
  description = "Aurora PostgreSQL read replica endpoint"
  value       = aws_rds_cluster.main.reader_endpoint
  sensitive   = true
}

output "db_secret_arn" {
  description = "ARN of the database credentials Secrets Manager secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "app_secrets_arn" {
  description = "ARN of the application secrets Secrets Manager secret"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
  sensitive   = true
}

output "s3_artifacts_bucket" {
  description = "S3 bucket name for job artifacts"
  value       = aws_s3_bucket.artifacts.id
}

output "s3_artifacts_arn" {
  description = "S3 bucket ARN for job artifacts"
  value       = aws_s3_bucket.artifacts.arn
}

output "api_security_group_id" {
  description = "Security group ID for API tasks"
  value       = aws_security_group.api.id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "ecs_task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "IAM role ARN for ECS task (app permissions)"
  value       = aws_iam_role.ecs_task.arn
}

output "acm_certificate_arn" {
  description = "ACM certificate ARN (if domain configured)"
  value       = length(aws_acm_certificate.main) > 0 ? aws_acm_certificate.main[0].arn : ""
}

output "deployment_summary" {
  description = "Human-readable deployment summary"
  value = <<-EOT
    ═══════════════════════════════════════════════════════════
    OrQuanta Agentic v1.0 — ${var.environment} Deployment
    ═══════════════════════════════════════════════════════════
    API URL:     ${var.domain_name != "" ? "https://api.${var.domain_name}" : "http://${aws_lb.main.dns_name}"}
    Dashboard:   ${var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_lb.main.dns_name}"}
    Health:      ${var.domain_name != "" ? "https://api.${var.domain_name}/health" : "http://${aws_lb.main.dns_name}/health"}
    ECS Cluster: ${aws_ecs_cluster.main.name}
    Region:      ${var.aws_region}
    ═══════════════════════════════════════════════════════════
  EOT
}
