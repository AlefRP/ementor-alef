# Observabilidade — a metade do CloudWatch que faltava na governança.
#
# Log group todo componente já tem; o que não existia era ALARME: sem isso, a
# ingestão podia parar de gravar e ninguém saberia até alguém abrir o Athena e
# achar o dado velho. Cada alarme aqui responde a uma pergunta operacional:
#
#   Lambda Errors      -> a ingestão está falhando?
#   DLQ com mensagem   -> algum evento não conseguiu virar dado (nunca é normal)?
#   Idade da fila      -> o consumo parou / não vence o ritmo do produtor?
#   EC2 StatusCheck    -> a API privada morreu? (sem SSH, o alarme é o aviso)
#
# Falhas de job Glue já têm caminho próprio (EventBridge -> SNS no glue_silver):
# são evento de estado, não métrica, e a regra lá pega FAILED e TIMEOUT.

resource "aws_sns_topic" "alerts" {
  #checkov:skip=CKV_AWS_26: notificação de alarme não carrega dado do lakehouse (só nome da métrica e estado); CMK dedicada custaria US$1/mês por nada. Alarme do CloudWatch, aliás, não publica em tópico cifrado com a chave gerenciada da AWS.
  name = "${var.prefix}-alerts"

  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---- Ingestão: erro em qualquer Lambda do pipeline ----
# treat_missing_data = notBreaching: Lambda sem invocação no período não publica
# a métrica Errors; sem isso, um pipeline OCIOSO dispararia alarme de INSUFFICIENT_DATA.
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = var.lambda_function_names

  alarm_name          = "${var.prefix}-${each.key}-errors"
  alarm_description   = "Erros na Lambda ${each.value} (ingestao do lakehouse)"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# ---- Camada quente: mensagem na DLQ ----
# Qualquer mensagem aqui é um evento que esgotou o redrive: nunca é rotina.
resource "aws_cloudwatch_metric_alarm" "dlq_nao_vazia" {
  alarm_name          = "${var.prefix}-events-dlq-nao-vazia"
  alarm_description   = "Evento na DLQ: esgotou o redrive e nao virou dado na raw"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.events_dlq_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# ---- Camada quente: backlog envelhecendo ----
# A fila não estar vazia é normal; a mensagem mais antiga passar de N minutos
# significa que o consumo parou ou não vence o produtor.
resource "aws_cloudwatch_metric_alarm" "fila_envelhecendo" {
  alarm_name          = "${var.prefix}-events-backlog-antigo"
  alarm_description   = "Mensagem mais antiga na fila passou de ${var.max_message_age_seconds}s: consumo parado ou lento"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.max_message_age_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.events_queue_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# ---- APIs: a instância privada caiu ----
# A EC2 não tem SSH nem IP público: se o status check falhar, este alarme é o
# único aviso (a lição do repo: instância privada muda é indiagnosticável).
resource "aws_cloudwatch_metric_alarm" "ec2_status_check" {
  for_each = var.api_instance_ids

  alarm_name          = "${var.prefix}-${each.key}-status-check"
  alarm_description   = "Status check falhando na EC2 da ${each.key}"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching" # instância sumiu = métrica some: isso É a falha

  dimensions = {
    InstanceId = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}
