#!/usr/bin/env python3
"""CD: calcula a proxima versao semver a partir de Conventional Commits e
aplica o bump em ``pyproject.toml`` (fonte unica da versao) + ``CHANGELOG.md``.

Uso:
    python scripts/release/release.py plan
    python scripts/release/release.py apply --version X.Y.Z

``plan`` le os commits desde a ultima tag ``vX.Y.Z`` (ou desde o inicio do
historico, se nao houver tag), classifica pela especificacao Conventional
Commits (https://www.conventionalcommits.org/en/v1.0.0/) e escreve o
resultado em ``$GITHUB_OUTPUT`` (ou no stdout, para dry-run local via
``make release-plan``). Tambem grava um rascunho do changelog da versao em
``CHANGELOG_LATEST.md`` (nao versionado - ver .gitignore).

``apply`` recebe a versao decidida pelo ``plan`` e atualiza o campo
``version = "..."`` de ``[project]`` em ``pyproject.toml`` + faz merge do
rascunho em ``CHANGELOG.md`` (formato Keep a Changelog:
https://keepachangelog.com/en/1.1.0/).

Por que nao um arquivo VERSION separado: manter duas fontes da versao
(pyproject.toml + VERSION) exige sincronizacao manual e diverge com o tempo.
A documentacao oficial de empacotamento Python lista "version in
pyproject.toml" como uma fonte-unica valida (ver
https://packaging.python.org/en/latest/discussions/single-source-version/);
este projeto so tem um artefato Python (o pacote em src/), entao nao ha
motivo para duplicar.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / 'pyproject.toml'
CHANGELOG = ROOT / 'CHANGELOG.md'
CHANGELOG_LATEST = ROOT / 'CHANGELOG_LATEST.md'

CONVENTIONAL_RE = re.compile(
    r'^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<subject>.+)$'
)
SECTIONS = {
    'feat': 'Adicionado',
    'fix': 'Corrigido',
    'perf': 'Performance',
    'refactor': 'Modificado',
    'revert': 'Revertido',
}
RANK = {None: 0, 'patch': 1, 'minor': 2, 'major': 3}


def run(*args: str) -> str:
    result = subprocess.run(
        args, cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def last_tag() -> str | None:
    try:
        return run('git', 'describe', '--tags', '--abbrev=0', '--match', 'v*')
    except subprocess.CalledProcessError:
        return None


def commits_since(ref: str | None) -> list[tuple[str, str, str]]:
    range_spec = f'{ref}..HEAD' if ref else 'HEAD'
    log = run(
        'git',
        'log',
        range_spec,
        '--no-merges',
        '--pretty=format:%H%x01%s%x01%b%x02',
    )
    commits = []
    if not log:
        return commits
    for raw in log.split('\x02'):
        raw = raw.strip('\n')
        if not raw:
            continue
        sha, subject, body = raw.split('\x01', 2)
        commits.append((sha[:7], subject.strip(), body.strip()))
    return commits


def classify(
    commits: list[tuple[str, str, str]]
) -> tuple[str | None, dict[str, list[str]]]:
    bump: str | None = None
    grouped: dict[str, list[str]] = {}
    for sha, subject, body in commits:
        match = CONVENTIONAL_RE.match(subject)
        is_breaking = 'BREAKING CHANGE' in body or 'BREAKING-CHANGE' in body
        ctype = None
        if match:
            ctype = match.group('type').lower()
            is_breaking = is_breaking or bool(match.group('breaking'))

        candidate = None
        if is_breaking:
            candidate = 'major'
        elif ctype == 'feat':
            candidate = 'minor'
        elif ctype == 'fix':
            candidate = 'patch'
        if candidate and RANK[candidate] > RANK[bump]:
            bump = candidate

        section = 'BREAKING CHANGES' if is_breaking else SECTIONS.get(ctype)
        if section:
            grouped.setdefault(section, []).append(f'{subject} ({sha})')
    return bump, grouped


def current_version() -> str:
    text = PYPROJECT.read_text(encoding='utf-8')
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit('pyproject.toml sem `version = "..."` em [project]')
    return match.group(1)


def bump_version(current: str, kind: str) -> str:
    major, minor, patch = (int(part) for part in current.split('.')[:3])
    if kind == 'major':
        return f'{major + 1}.0.0'
    if kind == 'minor':
        return f'{major}.{minor + 1}.0'
    return f'{major}.{minor}.{patch + 1}'


def write_output(pairs: dict[str, str]) -> None:
    target = os.environ.get('GITHUB_OUTPUT')
    lines = [f'{key}={value}' for key, value in pairs.items()]
    if target:
        with open(target, 'a', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
    else:
        for line in lines:
            print(line)


def cmd_plan(_args: argparse.Namespace) -> None:
    tag = last_tag()
    commits = commits_since(tag)
    bump, grouped = classify(commits)

    if not bump:
        write_output({'has_release': 'false', 'previous_tag': tag or ''})
        print(
            'Nenhum commit feat/fix/BREAKING desde '
            f'{tag or "o inicio do historico"} - release nao sera criado.',
            file=sys.stderr,
        )
        return

    base = current_version()
    next_version = bump_version(base, bump)
    today = date.today().isoformat()

    body_lines = [f'## [{next_version}] - {today}']
    for section in (
        'BREAKING CHANGES',
        'Adicionado',
        'Corrigido',
        'Performance',
        'Modificado',
        'Revertido',
    ):
        items = grouped.get(section)
        if not items:
            continue
        body_lines.append(f'### {section}')
        body_lines.extend(f'- {item}' for item in items)
    CHANGELOG_LATEST.write_text('\n'.join(body_lines) + '\n', encoding='utf-8')

    write_output(
        {
            'has_release': 'true',
            'bump': bump,
            'next_version': next_version,
            'previous_tag': tag or '',
        }
    )
    print(
        f'Proxima versao: {next_version} (bump={bump}, base={base})',
        file=sys.stderr,
    )


def cmd_apply(args: argparse.Namespace) -> None:
    version = args.version
    text = PYPROJECT.read_text(encoding='utf-8')
    new_text, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"', f'version = "{version}"', text, count=1
    )
    if count != 1:
        raise SystemExit(
            'Nao foi possivel localizar `version = "..."` em pyproject.toml'
        )
    PYPROJECT.write_text(new_text, encoding='utf-8')

    entry = (
        CHANGELOG_LATEST.read_text(encoding='utf-8')
        if CHANGELOG_LATEST.exists()
        else f'## [{version}] - {date.today().isoformat()}\n'
    )
    header = (
        '# Changelog\n\n'
        'Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), '
        'versionamento [SemVer](https://semver.org/) derivado de '
        '[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).\n'
        'Gerado automaticamente pelo workflow `release.yml` a cada push na '
        'master/main com commit `feat`/`fix`/`BREAKING CHANGE` — não editar '
        'manualmente.\n\n'
    )
    if CHANGELOG.exists():
        existing = CHANGELOG.read_text(encoding='utf-8')
        # Descarta o preambulo (titulo + explicacao do formato) e mantem só
        # as entradas de versao ja publicadas (a partir do primeiro "## [").
        marker = existing.find('## [')
        rest = existing[marker:] if marker != -1 else ''
        new_changelog = header + entry.rstrip() + '\n\n' + rest
    else:
        new_changelog = header + entry.rstrip() + '\n'
    CHANGELOG.write_text(new_changelog, encoding='utf-8')

    print(f'pyproject.toml e CHANGELOG.md atualizados para v{version}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan')
    apply_parser = sub.add_parser('apply')
    apply_parser.add_argument('--version', required=True)

    args = parser.parse_args()
    if args.command == 'plan':
        cmd_plan(args)
    else:
        cmd_apply(args)


if __name__ == '__main__':
    main()
