#!/usr/bin/env python3
"""Esvazia buckets S3 versionados (todas as versões + delete markers).

Usado pelo Makefile antes do ``terraform destroy`` para evitar o erro
``BucketNotEmpty`` em buckets com versionamento ativado.

Com ``--check`` não deleta nada: só falha (exit 1) se algum bucket tiver
conteúdo — precheck do ``tf-destroy`` sem FORCE, que sem isso queimaria
~20 min de destroy para falhar no último recurso. Bucket inexistente é
tratado como vazio (teardown parcial já o removeu).

Uso::

    python scripts/teardown/empty_versioned_bucket.py [--check] <bucket1> [bucket2 ...]

Requer: boto3, credenciais AWS configuradas.
"""
from __future__ import annotations

import sys

import boto3

S3 = boto3.client('s3')
# Nomes de bucket são globais: se o bucket foi destruído e o nome tomado por
# outra conta, as chamadas abaixo falham (403) em vez de operar no alheio.
ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']


def _deletar_todas_versoes(bucket: str) -> None:
    """Deleta TODAS as versões e delete markers de um bucket versionado."""
    paginator = S3.get_paginator('list_object_versions')
    deleted_total = 0

    for page in paginator.paginate(Bucket=bucket, ExpectedBucketOwner=ACCOUNT_ID):
        objects: list[dict] = []

        if 'Versions' in page:
            for v in page['Versions']:
                objects.append({'Key': v['Key'], 'VersionId': v['VersionId']})

        if 'DeleteMarkers' in page:
            for m in page['DeleteMarkers']:
                objects.append({'Key': m['Key'], 'VersionId': m['VersionId']})

        if not objects:
            continue

        S3.delete_objects(
            Bucket=bucket,
            Delete={'Objects': objects},
            ExpectedBucketOwner=ACCOUNT_ID,
        )
        deleted_total += len(objects)
        print(f'  >> {bucket}: {deleted_total} objetos/versoes deletados')

    print(f'>> {bucket}: concluido ({deleted_total} objetos/versoes removidos)')


def _tem_conteudo(bucket: str) -> bool:
    """True se o bucket tem ao menos uma versão ou delete marker."""
    page = S3.list_object_versions(
        Bucket=bucket, MaxKeys=1, ExpectedBucketOwner=ACCOUNT_ID
    )
    return bool(page.get('Versions') or page.get('DeleteMarkers'))


def principal() -> int:
    args = sys.argv[1:]
    check_only = '--check' in args
    buckets = [a for a in args if a != '--check']
    if not buckets:
        print('Uso: python empty_versioned_bucket.py [--check] <bucket1> [bucket2 ...]')
        return 1

    dirty: list[str] = []
    for bucket in buckets:
        try:
            if check_only:
                if _tem_conteudo(bucket):
                    dirty.append(bucket)
                continue
            print(f'>> Esvaziando bucket versionado: {bucket}')
            _deletar_todas_versoes(bucket)
        except S3.exceptions.NoSuchBucket:
            print(f'>> {bucket}: nao existe (ok, teardown parcial ja o removeu)')
        except Exception as exc:
            print(f'!! ERRO em {bucket}: {exc}')
            return 1

    if dirty:
        print(f'!! Buckets com dados: {", ".join(dirty)}')
        print('!! O destroy falharia com BucketNotEmpty. Rode: make tf-destroy FORCE=1')
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(principal())
