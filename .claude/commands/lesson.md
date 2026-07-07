---
description: Registra uma lição aprendida (erro → causa raiz → regra) no banco de lições do projeto.
argument-hint: "[descrição do erro ou vazio para usar o último erro da conversa]"
---

Registre uma lição no banco `.claude/lessons/LESSONS.md`.

1. Identifique o erro: use $ARGUMENTS se informado; senão, o erro/correção mais recente
   desta conversa (tool que falhou, gate que quebrou, retrabalho, correção do usuário).
2. Destile em **4 linhas no máximo**, no formato do arquivo:
   ```
   ## AAAA-MM-DD · tipo · título curto
   - Sintoma: o que deu errado, observável.
   - Causa raiz: por quê.
   - Regra: o que fazer diferente da próxima vez.
   ```
   Tipos válidos: `tool`, `terraform`, `python`, `ci`, `aws`, `pesquisa`, `processo`.
3. **Antes de adicionar**: verifique se já existe lição com a mesma causa raiz.
   - Se existir e esta é a 2ª ocorrência: promova a regra para a skill/agent
     correspondente (edite o arquivo em `.claude/skills/` ou `.claude/agents/`)
     e marque a entrada como `[promovida]`.
   - Se não existir: adicione ao final do arquivo.
4. Confirme mostrando a entrada registrada e onde ela será aplicada.
