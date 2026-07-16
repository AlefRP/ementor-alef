#!/usr/bin/env python3
"""Remove do SARIF do checkov os resultados já suprimidos no código.

O checkov emite no SARIF **também** os achados cobertos por ``#checkov:skip``,
marcados com ``suppressions: [{"kind": "inSource", ...}]``. O GitHub ingere
esses resultados e abre um alerta de code scanning para cada um — dispensado,
mas visível na lista de checks do PR como "Checkov / <descrição da regra>".
O efeito é um PR que parece ter dezenas de falhas de segurança quando o gate
(``make tf-security``) passou com zero.

Este filtro corta só o que já tem justificativa escrita no HCL. O gate não
muda: qualquer achado NÃO suprimido continua reprovando o job e continua
subindo para o code scanning. Em outras palavras, o que sobe é exatamente o
que ainda não foi decidido.

Uso:
    python scripts/ci/filter_sarif.py infra/terraform/results_sarif.sarif
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def resultados_abertos(resultados: list[dict]) -> list[dict]:
    """Mantém apenas os resultados sem supressão in-source."""
    return [r for r in resultados if not r.get('suppressions')]


def filtrar(caminho: Path) -> int:
    """Reescreve o SARIF sem os suprimidos; devolve quantos foram removidos."""
    sarif = json.loads(caminho.read_text(encoding='utf-8'))

    removidos = 0
    for run in sarif.get('runs', []):
        antes = run.get('results', [])
        depois = resultados_abertos(antes)
        removidos += len(antes) - len(depois)
        run['results'] = depois

    caminho.write_text(
        json.dumps(sarif, ensure_ascii=False), encoding='utf-8'
    )
    return removidos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sarif', type=Path, help='SARIF gerado pelo checkov')
    args = parser.parse_args()

    # O passo do checkov roda com `if: always()`: quando ele reprova de fato, o
    # SARIF existe e é filtrado normalmente. Ausente, o upload segue sem nós —
    # este script nunca é o motivo de um job vermelho.
    if not args.sarif.is_file():
        print(f'::warning::SARIF file not found: {args.sarif}; skipping filter.')
        return 0

    removidos = filtrar(args.sarif)
    print(f'{removidos} resultado(s) suprimido(s) removido(s) do SARIF.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
