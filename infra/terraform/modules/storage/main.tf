# Buckets das camadas do lakehouse (raw, silver): 100% privados, versionados e
# criptografados. Paths de dados seguem partição year/month/day (convenção do
# repo) — isso é responsabilidade de quem escreve (Lambda/Glue), não do bucket.
resource "aws_s3_bucket" "layer" {
  for_each = var.layers

  bucket        = "${var.prefix}-${each.value}"
  force_destroy = var.force_destroy # teardown do lab: esvazia antes de destruir

  tags = merge(var.tags, {
    Name  = "${var.prefix}-${each.value}"
    Layer = each.value
  })
}

# Critério de aceitação da story: Block Public Access ativo (4 flags) em todos.
resource "aws_s3_bucket_public_access_block" "layer" {
  for_each = aws_s3_bucket.layer

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Higiene: aborta multipart incompleto e expira versões antigas (custo).
resource "aws_s3_bucket_lifecycle_configuration" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id

  rule {
    id     = "hygiene"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }
}

# Criptografia em trânsito: nega qualquer acesso não-TLS.
data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.layer

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      each.value.arn,
      "${each.value.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id
  policy = data.aws_iam_policy_document.tls_only[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.layer]
}
