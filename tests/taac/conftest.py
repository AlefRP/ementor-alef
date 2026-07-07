"""Fixtures e helpers dos testes TAAC (arquitetura em cloud).

O parser de HCL aqui é intencionalmente leve (contagem de chaves): suficiente
para asserções de arquitetura sem adicionar dependência de parser completo.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / 'infra' / 'terraform'

_BLOCK_RE = re.compile(
    r'^(?P<kind>resource|data)\s+"(?P<type>[\w-]+)"\s+"(?P<name>[\w-]+)"\s*\{',
    re.MULTILINE,
)


@dataclass
class TerraformBlock:
    """Um bloco resource/data extraído de um arquivo .tf."""

    kind: str
    type: str
    name: str
    body: str
    file: Path

    @property
    def address(self) -> str:
        return f'{self.type}.{self.name}'


def _extract_body(text: str, brace_start: int) -> str:
    """Retorna o corpo do bloco a partir da chave de abertura (balanceada)."""
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : i]
    return text[brace_start + 1 :]


def parse_terraform_blocks(paths: list[Path]) -> list[TerraformBlock]:
    blocks: list[TerraformBlock] = []
    for path in paths:
        text = path.read_text(encoding='utf-8')
        for match in _BLOCK_RE.finditer(text):
            brace = text.index('{', match.start())
            blocks.append(
                TerraformBlock(
                    kind=match.group('kind'),
                    type=match.group('type'),
                    name=match.group('name'),
                    body=_extract_body(text, brace),
                    file=path,
                )
            )
    return blocks


@pytest.fixture(scope='session')
def terraform_dir() -> Path:
    return TERRAFORM_DIR


@pytest.fixture(scope='session')
def tf_files() -> list[Path]:
    files = sorted(TERRAFORM_DIR.rglob('*.tf'))
    assert files, f'nenhum .tf encontrado em {TERRAFORM_DIR}'
    return files


@pytest.fixture(scope='session')
def terraform_blocks(tf_files: list[Path]) -> list[TerraformBlock]:
    return parse_terraform_blocks(tf_files)


@pytest.fixture(scope='session')
def resources(terraform_blocks: list[TerraformBlock]) -> list[TerraformBlock]:
    return [b for b in terraform_blocks if b.kind == 'resource']
