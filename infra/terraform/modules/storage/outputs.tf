output "bucket_ids" {
  description = "Nome dos buckets por camada (raw, silver)."
  value       = { for k, b in aws_s3_bucket.layer : k => b.id }
}

output "bucket_arns" {
  description = "ARN dos buckets por camada (consumidos por governance/IAM)."
  value       = { for k, b in aws_s3_bucket.layer : k => b.arn }
}
