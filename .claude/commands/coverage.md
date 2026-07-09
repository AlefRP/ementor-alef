---
description: Roda os testes com cobertura e verifica o gate de 90% (critério do SonarCloud), listando o que falta cobrir.
allowed-tools: Bash(make:*), Bash(pytest:*)
---

Rode a suíte com cobertura e avalie contra o **gate de ≥ 90%** — o mesmo critério que o SonarCloud aplica na esteira.

```bash
make test-cov
```

Isso gera `coverage.xml` (usado pelo Sonar), `htmlcov/` e o relatório `term-missing`.

Ao final:
- Informe a **cobertura total** (%) e se atinge o gate de 90%.
- Se estiver **abaixo de 90%**, liste os arquivos de `src/` com menor cobertura e as
  **linhas não cobertas** (coluna `Missing` do term-missing), priorizando o que mais
  aproxima do gate.
- Sugira testes concretos no padrão `test_<unidade>_<cenario>` para fechar as lacunas.
- Se algum teste **falhar**, reporte a falha primeiro (o gate de teste bloqueia antes da cobertura).
