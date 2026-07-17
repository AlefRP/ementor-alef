#!/usr/bin/env python3
"""Dispara uma carga inicial fria da camada raw apos o terraform apply.

O apply cria a infraestrutura e semeia o RDS, mas a carga fria que grava no S3
raw depende da agenda EventBridge -> Lambda -> API EC2 -> raw. Este script
antecipa apenas essa primeira execucao, para que um ambiente recem-subido ja
tenha dados historicos no bucket raw sem esperar o primeiro intervalo.

A camada quente fica fora deste bootstrap de proposito: eventos devem chegar pela
Event API quando um produtor real ou a simulacao explicita rodar.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[2]

DATASETS_FRIOS_PADRAO = [
    'orders',
    'customers',
    'sellers',
    'products',
    'geolocation',
    'product_category_name_translation',
    'order_items',
    'order_payments',
    'order_reviews',
]


def _avisar(mensagem: str) -> None:
    print(f'>> {mensagem}', flush=True)


def _rodar_comando(comando: list[str]) -> str:
    resultado = subprocess.run(
        comando,
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout


def _ler_outputs_terraform(tf_dir: str) -> dict[str, Any]:
    saida = _rodar_comando(['terraform', f'-chdir={tf_dir}', 'output', '-json'])
    bruto = json.loads(saida)
    return {chave: valor['value'] for chave, valor in bruto.items()}


def _payload_do_dataset(dataset: str) -> dict[str, Any]:
    if dataset == 'orders':
        return {'dataset': dataset, 'cursor_mode': 'orders'}
    return {'dataset': dataset, 'cursor_mode': 'pk'}


def _invocar_lambda(
    cliente_lambda, nome: str, payload: dict[str, Any]
) -> dict[str, Any]:
    resposta = cliente_lambda.invoke(
        FunctionName=nome,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload).encode('utf-8'),
    )
    corpo = resposta['Payload'].read()
    resposta_payload = json.loads(corpo or b'{}')
    if resposta.get('FunctionError'):
        raise RuntimeError(
            f'lambda {nome} falhou ({resposta["FunctionError"]}): {resposta_payload}'
        )
    return resposta_payload


def _invocar_com_retry(
    cliente_lambda,
    nome: str,
    payload: dict[str, Any],
    tentativas: int,
    espera_segundos: int,
) -> dict[str, Any]:
    ultima_falha: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            return _invocar_lambda(cliente_lambda, nome, payload)
        except Exception as erro:
            ultima_falha = erro
            if tentativa == tentativas:
                break
            _avisar(
                f'{nome}: tentativa {tentativa}/{tentativas} falhou; '
                f'aguardando {espera_segundos}s ({erro})'
            )
            time.sleep(espera_segundos)
    raise RuntimeError(f'{nome}: falhou apos {tentativas} tentativas') from ultima_falha


def _contar_prefixo_raw(bucket: str, prefixo: str) -> int:
    cliente_s3 = boto3.client('s3')
    resposta = cliente_s3.list_objects_v2(
        Bucket=bucket,
        Prefix=f'{prefixo}/',
        MaxKeys=1000,
    )
    return len(resposta.get('Contents', []))


def _interpretar_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tf-dir', required=True, help='environment do Terraform')
    parser.add_argument(
        '--datasets-frios',
        nargs='+',
        default=DATASETS_FRIOS_PADRAO,
        help='datasets da API fria a ingerir inicialmente',
    )
    parser.add_argument(
        '--tentativas',
        type=int,
        default=8,
        help='tentativas por invocacao; cobre API EC2 ainda subindo',
    )
    parser.add_argument(
        '--espera-segundos',
        type=int,
        default=30,
        help='espera entre tentativas',
    )
    parser.add_argument(
        '--somente-se-vazio',
        action='store_true',
        help=(
            'so ingere dataset cujo prefixo da raw esta vazio; com dados, pula '
            '(modo da esteira: carga inicial no ambiente do zero, no-op depois)'
        ),
    )
    return parser.parse_args(argv)


def principal(argv: list[str] | None = None) -> int:
    args = _interpretar_args(argv)
    try:
        outputs = _ler_outputs_terraform(args.tf_dir)
        cliente_lambda = boto3.client('lambda')

        bucket_raw = outputs['buckets']['raw']
        funcao_fria = outputs['ingest_cold_function']

        _avisar(f'carga fria inicial via {funcao_fria}')
        for dataset in args.datasets_frios:
            # Checagem por dataset: ambiente do zero carrega tudo, ambiente
            # vivo vira no-op, e um dataset novo adicionado depois entra sozinho.
            if args.somente_se_vazio and _contar_prefixo_raw(bucket_raw, dataset):
                _avisar(f'{dataset}: raw ja tem dados, pulando (--somente-se-vazio)')
                continue
            resposta = _invocar_com_retry(
                cliente_lambda,
                funcao_fria,
                _payload_do_dataset(dataset),
                args.tentativas,
                args.espera_segundos,
            )
            _avisar(
                f'{dataset}: {resposta.get("ingested", 0)} registros '
                f'em {resposta.get("pages", 0)} paginas'
            )

        objetos_orders = _contar_prefixo_raw(bucket_raw, 'orders')
        _avisar(f'raw em s3://{bucket_raw}: orders={objetos_orders} objetos')
        return 0
    except subprocess.CalledProcessError as erro:
        _avisar(f'ERRO: terraform output falhou com exit {erro.returncode}')
        return erro.returncode or 1
    except (BotoCoreError, ClientError, RuntimeError, KeyError) as erro:
        _avisar(f'ERRO: {erro}')
        return 1


if __name__ == '__main__':
    raise SystemExit(principal())
