#!/usr/bin/env python3
"""Hook PostToolUse: formata o arquivo recém-escrito para casar com os gates do CI.

Espelha os mesmos formatadores da esteira (make check-format / terraform fmt), de
modo que todo arquivo editado pelo agente já saia no estilo aprovado — evita
retrabalho e falha de gate.

- .py           -> blue + isort
- .tf / .tfvars -> terraform fmt

Regras de robustez:
- Lê o payload do hook (JSON) do stdin; extrai tool_input.file_path.
- No-op silencioso se o arquivo não existir ou a ferramenta não estiver no PATH.
- NUNCA falha a operação do agente (sai sempre com código 0).

Multiplataforma (Windows/macOS/Linux). Requer apenas Python 3.11+.
"""
import json
import os
import shutil
import subprocess
import sys


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except Exception:
        pass  # advisory: nunca propaga erro para o agente


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path or not os.path.isfile(path):
        return 0

    lower = path.lower()
    if lower.endswith(".py"):
        if shutil.which("blue"):
            _run(["blue", path])
        if shutil.which("isort"):
            _run(["isort", path])
        print(f"[hook] format_on_write: blue+isort -> {path}")
    elif lower.endswith((".tf", ".tfvars")):
        if shutil.which("terraform"):
            _run(["terraform", "fmt", path])
            print(f"[hook] format_on_write: terraform fmt -> {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
