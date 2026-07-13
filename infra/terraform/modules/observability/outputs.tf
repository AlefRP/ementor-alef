output "alerts_topic_arn" {
  description = "Tópico SNS que recebe os alarmes operacionais do lakehouse."
  value       = aws_sns_topic.alerts.arn
}

output "alarm_names" {
  description = "Alarmes criados (útil para o TAAC live conferir a governança)."
  value = concat(
    [for alarme in aws_cloudwatch_metric_alarm.lambda_errors : alarme.alarm_name],
    [for alarme in aws_cloudwatch_metric_alarm.ec2_status_check : alarme.alarm_name],
    [
      aws_cloudwatch_metric_alarm.dlq_nao_vazia.alarm_name,
      aws_cloudwatch_metric_alarm.fila_envelhecendo.alarm_name,
    ],
  )
}
