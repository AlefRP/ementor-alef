output "state_bucket_name" {
  description = "Bucket a referenciar no backend s3 dos ambientes."
  value       = aws_s3_bucket.tf_state.id
}

output "state_bucket_arn" {
  description = "ARN do bucket de state."
  value       = aws_s3_bucket.tf_state.arn
}
