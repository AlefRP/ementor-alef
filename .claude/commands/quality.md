---
description: Roda o gate de qualidade local (format, lint, security, testes) espelhando o CI e resume falhas.
allowed-tools: Bash(make:*), Bash(pytest:*), Bash(blue:*), Bash(isort:*), Bash(bandit:*), Bash(pip-audit:*)
---

Rode o gate de qualidade completo do projeto, o mesmo que a esteira (`.github/workflows/ci.yml`) executa, e reporte o resultado de forma acionável.

Execute na ordem e **não pare no primeiro erro** — colete tudo:

```bash
make check-format
make lint
make security
make test
```

Depois:
- Para cada etapa que falhou, mostre o trecho relevante da saída e o arquivo:linha.
- Se `check-format` falhar, ofereça rodar `make format` para corrigir automaticamente (blue + isort).
- Se um teste quebrar, resuma qual e por quê — nunca diga "passou" sem a saída comprovando.
- Termine com um veredito: ✅ pronto para commit / ❌ bloqueado, com a lista do que corrigir.

Argumento opcional ($ARGUMENTS): se informado um alvo específico (ex.: `test-unit`), rode `make $ARGUMENTS` em vez do gate completo.
