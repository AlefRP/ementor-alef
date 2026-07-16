#!/usr/bin/env python3
"""Limpa ou checa WorkGroups Athena antes do teardown.

Sem ``force_destroy`` no state, o Terraform chama DeleteWorkGroup sem
RecursiveDeleteOption e a AWS falha se o workgroup ainda tiver conteudo. Mesmo
com FORCE, limpamos consultas nomeadas e instrucoes preparadas explicitamente para
evitar que o DeleteWorkGroup pare no "WorkGroup is not empty".
"""
from __future__ import annotations

import sys

import boto3
from botocore.exceptions import ClientError

ATHENA = boto3.client('athena')


def _tem_consultas_nomeadas(workgroup: str) -> bool:
    paginator = ATHENA.get_paginator('list_named_queries')
    for page in paginator.paginate(WorkGroup=workgroup):
        if page.get('NamedQueryIds'):
            return True
    return False


def _deletar_consultas_nomeadas(workgroup: str) -> int:
    paginator = ATHENA.get_paginator('list_named_queries')
    deleted = 0
    for page in paginator.paginate(WorkGroup=workgroup):
        for query_id in page.get('NamedQueryIds', []):
            ATHENA.delete_named_query(NamedQueryId=query_id)
            deleted += 1
    return deleted


def _tem_instrucoes_preparadas(workgroup: str) -> bool:
    next_token = None
    while True:
        kwargs = {'WorkGroup': workgroup}
        if next_token:
            kwargs['NextToken'] = next_token
        page = ATHENA.list_prepared_statements(**kwargs)
        if page.get('PreparedStatements'):
            return True
        next_token = page.get('NextToken')
        if not next_token:
            break
    return False


def _deletar_instrucoes_preparadas(workgroup: str) -> int:
    deleted = 0
    next_token = None
    while True:
        kwargs = {'WorkGroup': workgroup}
        if next_token:
            kwargs['NextToken'] = next_token
        page = ATHENA.list_prepared_statements(**kwargs)
        for statement in page.get('PreparedStatements', []):
            ATHENA.delete_prepared_statement(
                StatementName=statement['StatementName'],
                WorkGroup=workgroup,
            )
            deleted += 1
        next_token = page.get('NextToken')
        if not next_token:
            break
    return deleted


def _workgroup_nao_existe(exc: ClientError) -> bool:
    error = exc.response.get('Error', {})
    code = error.get('Code')
    message = error.get('Message', '')
    return code in {'InvalidRequestException', 'ResourceNotFoundException'} and (
        'not found' in message.lower() or 'does not exist' in message.lower()
    )


def principal() -> int:
    args = sys.argv[1:]
    check_only = '--check' in args
    workgroups = [a for a in args if a != '--check']
    if not workgroups:
        print('Uso: python check_athena_workgroup.py [--check] <workgroup1> [workgroup2 ...]')
        return 1

    dirty: list[str] = []
    for workgroup in workgroups:
        try:
            if check_only:
                if _tem_consultas_nomeadas(workgroup) or _tem_instrucoes_preparadas(workgroup):
                    dirty.append(workgroup)
                continue

            print(f'>> Limpando conteudo do WorkGroup Athena: {workgroup}')
            named = _deletar_consultas_nomeadas(workgroup)
            prepared = _deletar_instrucoes_preparadas(workgroup)
            print(
                f'>> {workgroup}: concluido '
                f'({named} consultas nomeadas, {prepared} instrucoes preparadas removidos)'
            )
        except ClientError as exc:
            if _workgroup_nao_existe(exc):
                print(f'>> {workgroup}: nao existe (ok, teardown parcial ja o removeu)')
                continue
            print(f'!! ERRO em {workgroup}: {exc}')
            return 1

    if dirty:
        print(f'!! WorkGroups Athena com conteudo: {", ".join(dirty)}')
        print('!! O destroy falharia com WorkGroup is not empty. Rode: make tf-destroy FORCE=1')
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(principal())
