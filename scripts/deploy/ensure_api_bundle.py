#!/usr/bin/env python3
"""Garante o bundle da API publicado ANTES do `terraform apply`.

O apply da EC2 privada tem um gate (``data aws_s3_object`` em
``modules/api_ec2``) que exige o bundle em ``s3://<artifacts>/api/...``.
Sem este precheck, dois modos de falha custam caro:

1. Bucket existe mas o bundle não: o provider fica ~12 min em retry no data
   source e o apply morre no meio (infra parcial).
2. Bootstrap do zero: o bucket nasce NO MESMO apply que o gate lê, então o
   apply sempre quebrava, exigindo o fluxo manual apply -> upload -> apply.

Este script torna ``make tf-apply`` um comando só, de qualquer estado:

- bucket + bundle existem   -> libera o apply em ~1s;
- bucket existe, sem bundle -> builda (se preciso) e publica o bundle;
- bucket não existe         -> fase 1: ``terraform apply -target=<storage>``
  (com confirmação), depois builda/publica o bundle; o apply completo do
  Makefile vira a fase 2.

NUNCA sobrescreve um bundle já publicado (a esteira também publica; redeploy
explícito continua sendo ``make api-bundle-upload``).

Script Python (não receita shell) pela mesma razão dos bundles: roda igual no
Windows (make -> cmd.exe) e no Ubuntu do CI.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[2]
TARBALL = ROOT / 'build' / 'api-bundle.tar.gz'
BUNDLE_SCRIPT = ROOT / 'scripts' / 'bundle' / 'api_bundle.py'

_MISSING_CODES = {'404', 'NotFound', 'NoSuchBucket', 'NoSuchKey'}


def _say(message: str) -> None:
    print(f'>> {message}', flush=True)


def _error_code(error: ClientError) -> str:
    return error.response.get('Error', {}).get('Code', '')


def _bucket_exists(s3, bucket: str) -> bool:
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as error:
        if _error_code(error) in _MISSING_CODES:
            return False
        raise


def _object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as error:
        if _error_code(error) in _MISSING_CODES:
            return False
        raise


def _ensure_tarball() -> None:
    if TARBALL.exists():
        _say(
            f'reutilizando {TARBALL.relative_to(ROOT)} ja buildado '
            '(rode `make api-bundle` antes se quiser rebuildar)'
        )
        return
    _say('bundle local ausente - gerando via scripts/bundle/api_bundle.py')
    subprocess.run([sys.executable, str(BUNDLE_SCRIPT)], check=True)


def _publish_bundle(s3, bucket: str, key: str) -> None:
    _ensure_tarball()
    _say(f'publicando {TARBALL.name} em s3://{bucket}/{key}')
    s3.upload_file(str(TARBALL), bucket, key)
    etag = s3.head_object(Bucket=bucket, Key=key)['ETag'].strip('"')
    _say(f'bundle publicado (etag {etag}) - apply liberado')


def _bootstrap_storage(tf_dir: str, target: str) -> None:
    _say(f'bucket de artefatos nao existe - fase 1/2: apply de -target={target}')
    _say('(o gate do bundle e lido no mesmo apply que criaria o bucket)')
    subprocess.run(
        ['terraform', f'-chdir={tf_dir}', 'apply', f'-target={target}'],
        check=True,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tf-dir', required=True, help='environment do terraform')
    parser.add_argument('--bucket', required=True, help='bucket de artefatos')
    parser.add_argument('--key', default='api/api-bundle.tar.gz')
    parser.add_argument(
        '--storage-target',
        default='module.storage',
        help='alvo do apply da fase 1 no bootstrap do zero',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        s3 = boto3.client('s3')
        if not _bucket_exists(s3, args.bucket):
            _bootstrap_storage(args.tf_dir, args.storage_target)
            if not _bucket_exists(s3, args.bucket):
                _say(f'ERRO: fase 1 terminou mas o bucket {args.bucket} nao apareceu')
                return 1
            _publish_bundle(s3, args.bucket, args.key)
        elif not _object_exists(s3, args.bucket, args.key):
            _publish_bundle(s3, args.bucket, args.key)
        else:
            _say(f'bundle OK em s3://{args.bucket}/{args.key} - apply liberado')
        return 0
    except subprocess.CalledProcessError as error:
        _say(f'ERRO: subprocesso terminou com exit {error.returncode}')
        return error.returncode or 1
    except (BotoCoreError, ClientError) as error:
        _say(f'ERRO de AWS: {error}')
        _say('verifique as credenciais (aws sts get-caller-identity) e rode de novo')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
