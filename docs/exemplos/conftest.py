"""Torna os exemplos de docs/ rodáveis isoladamente, fora da suíte do projeto.

Coloca a RAIZ do projeto no sys.path para que o import absoluto
`from docs.exemplos.codigo import ...` resolva — necessário porque o projeto
usa `--import-mode=importlib`, que não ajusta o path sozinho.

Escopo: só docs/. A suíte real usa testpaths=["tests"] e norecursedirs=["docs"]
no pyproject.toml, e nunca coleta esta pasta — este conftest não afeta o projeto.
"""
import sys
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_DO_PROJETO))
