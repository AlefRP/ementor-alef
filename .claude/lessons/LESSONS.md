# Banco de lições — erros cometidos e regras aprendidas

Formato de cada entrada (mantenha curto — 4 linhas no máximo):

```
## AAAA-MM-DD · tipo · título curto
- Sintoma: o que deu errado, observável.
- Causa raiz: por quê.
- Regra: o que fazer diferente da próxima vez.
```

Tipos: `tool` (uso das ferramentas), `terraform`, `python`, `ci`, `aws`, `pesquisa`, `processo`.
Lição aplicada 2x com sucesso → promover a regra para a skill/agent correspondente e marcar aqui como `[promovida]`.

---

## 2026-07-06 · tool · Write/Edit em arquivo existente sem Read prévio [recorrente 2x]
- Sintoma: `Write` falhou em `.claude/agents/data-engineer.md`; depois `Edit` falhou em `CLAUDE.md` ("File has not been read yet").
- Causa raiz: Write E Edit exigem Read na sessão antes de tocar arquivo existente — inclusive CLAUDE.md, que vem no contexto mas não conta como "lido".
- Regra: SEMPRE Read (tool) antes de Write/Edit em arquivo existente; conteúdo injetado no system prompt não satisfaz o requisito.

## 2026-07-06 · tool · Arquivo mudou entre Read e Edit
- Sintoma: `Edit` em `.claude/settings.json` falhou ("File has been modified since read").
- Causa raiz: o harness/usuário alterou o arquivo depois da minha leitura (permissões adicionadas automaticamente).
- Regra: em arquivos que o harness também escreve (settings.json), reler imediatamente antes de editar.

## 2026-07-06 · processo · Guard bloqueia auto-modificação de settings.json
- Sintoma: escrever hooks/permissões em `.claude/settings.json` foi negado pelo classifier ("Self-Modification").
- Causa raiz: adicionar hooks e permissões amplas que o usuário não pediu explicitamente é mudança sensível.
- Regra: preparar o snippet e pedir aprovação explícita do usuário (ou deixar documentado no README) em vez de aplicar direto.

## 2026-07-06 · pesquisa · Confiar em resumo de busca sem verificar o repo
- Sintoma: planejei usar dump SQL do `fortunewalla/olist` que, verificado via API do GitHub, só tem README+LICENSE.
- Causa raiz: resumo de busca sugeria conteúdo que o repo não tem; não chequei antes de desenhar a solução.
- Regra: antes de basear design em repo externo, listar o conteúdo real (`api.github.com/repos/<owner>/<repo>/contents/`) e testar a URL do artefato (`curl -sI` → 200).

## 2026-07-06 · tool · Diagnóstico do IDE defasado em lote de Writes
- Sintoma: IDE apontou "No declaration found for var.*" em `main.tf` recém-escrito, mas `terraform validate` passou.
- Causa raiz: diagnostics rodaram antes do `variables.tf` (escrito no mesmo lote) ser indexado.
- Regra: para Terraform, a verdade é `terraform validate`; diagnostics de IDE logo após Writes em lote podem estar defasados.

## 2026-07-06 · aws · Região fixada no backend sem verificar a conta do usuário
- Sintoma: backend s3 escrito com `us-east-1`; a conta do usuário usa `sa-east-1` (perfil default do CLI).
- Causa raiz: assumi região padrão em vez de checar `~/.aws/config` antes de hardcodar.
- Regra: antes de fixar região/conta em backend ou providers, ler o perfil real (`aws configure list` / `~/.aws/config`).

## 2026-07-06 · aws · Free tier novo limita retenção de backup do RDS
- Sintoma: `CreateDBInstance` falhou com `FreeTierRestrictionError` (retenção 7 dias > máximo do plano).
- Causa raiz: contas no free tier novo (2025+) restringem parâmetros do RDS; assumi limites de conta paga.
- Regra: em conta free tier, `backup_retention_period = 1`; parametrizar limites de RDS como variável com default compatível.

## 2026-07-06 · aws · GrantPermissions do Lake Formation exige data lake admin (root não pode)
- Sintoma: `aws_lakeformation_permissions` falhou com `AccessDeniedException` mesmo com credencial root.
- Causa raiz: só administradores do data lake concedem permissões; a AWS não aceita root como admin do Lake Formation.
- Regra: criar `aws_lakeformation_data_lake_settings` com o caller como admin + `depends_on` nas permissions; aplicar sempre com IAM user/role, nunca root.

## 2026-07-07 · python · blue exige aspas simples (CLAUDE.md dizia o contrário)
- Sintoma: `make check-format` quebrou no CI — blue reformataria os 3 arquivos de `tests/taac/` (aspas duplas → simples).
- Causa raiz: blue é black + aspas SIMPLES (duplas só em docstrings); o CLAUDE.md documentava "aspas duplas" e o código novo seguiu a doc.
- Regra: código Python novo com aspas simples; rodar `make format` antes de commitar; doc corrigida no CLAUDE.md.

## 2026-07-07 · processo · Feature entregue sem a infra correspondente
- Sintoma: entreguei API + Lambda com código e testes, mas sem Terraform; usuário corrigiu.
- Causa raiz: tratei infra como story separada; neste projeto a entrega é vertical (código + testes + IaC).
- Regra: toda feature com componente de runtime inclui módulo Terraform + composição no environment + TAAC estático no MESMO PR.

## 2026-07-07 · ci · Bump de action sem checar o runtime declarado na tag
- Sintoma: warning de Node 20 deprecado persistiu após bump do upload-artifact v4→v5.
- Causa raiz: assumi que o major novo rodava node24; o v5 ainda declara `runs.using: node20` (node24 só a partir do v6).
- Regra: antes de fixar versão de action, checar `runs.using` no action.yml da tag (`raw.githubusercontent.com/<owner>/<repo>/<tag>/action.yml`) e as release notes do major.

## 2026-07-07 · ci · sonar.projectKey/organization inventados quebram o scan
- Sintoma: SonarCloud falhou com "Not authorized or project not found" (binding NONEXISTENT).
- Causa raiz: `sonar-project.properties` com projectKey/organization que não existem no SonarCloud; as chaves devem ser copiadas do produto.
- Regra: copiar Project Key e Organization Key da tela Information do projeto; dá para validar sem login via `api/components/search_projects` (projetos públicos).

## 2026-07-09 · tool · Receita de Makefile com comandos Unix quebra no Windows
- Sintoma: `make tf-apply` falhou no PowerShell do usuário — `rm -rf build/hot-producer` → "CreateProcess(NULL, rm -rf ...) failed" (e=2).
- Causa raiz: adicionei `hot-producer-bundle` (rm/mkdir -p/cp) como prerequisite de `tf-apply`; o make no Windows executa a receita via `cmd.exe`, que não tem esses comandos. O repo é usado no Windows e no Ubuntu do CI.
- Regra: receita de Makefile que manipula arquivos deve chamar um script Python (shutil/subprocess), nunca rm/mkdir/cp/tar. `api-bundle` ainda tem essa dívida.

## 2026-07-09 · tool · Formatar "no olho" quando o formatador não roda local [recorrente 2x — promovida ao CLAUDE.md]
- Sintoma: `make check-format` quebrou no CI (`would reformat tests/taac/test_terraform_static.py`) depois que eu declarei o código formatado sem conseguir rodar o blue (crash no Python 3.14 local).
- Causa raiz: assumi o estilo do black para `assert cond, msg` — ele envolve a CONDIÇÃO em parênteses, não a mensagem. Ausência de ferramenta virou suposição.
- Regra: se o formatador não roda na versão local do Python, rode na versão do CI com `uv run --python 3.11 --with blue==0.9.1 --no-project blue --check src tests`. Nunca dizer "formatado" sem executar o gate.

## 2026-07-09 · python · `pip wheel` compila para o host, não para o alvo do deploy
- Sintoma: `make api-bundle` no Windows gerava wheels `win_amd64` (psycopg[binary], pydantic-core); o `pip install --no-index` do user_data na EC2 (AL2023 x86_64/py3.11) falharia — bundle que "builda" mas não deploya.
- Causa raiz: `pip wheel` resolve para a plataforma corrente e NÃO aceita `--platform`. Só `pip download` aceita alvo cruzado (exige `--only-binary=:all:`).
- Regra: artefato de deploy = `pip download --platform manylinux*_x86_64 --python-version 3.11 --abi cp311 --only-binary=:all:` para deps nativas; `pip wheel --no-deps` só para o projeto (Python puro). Valide com `ls wheelhouse | grep win_amd64` → 0.

## 2026-07-09 · tool · Padrão `build/` do .gitignore engole `scripts/build/`
- Sintoma: `git add scripts/build/` recusou ("paths are ignored by one of your .gitignore files").
- Causa raiz: `build/` no .gitignore é padrão sem âncora — casa com QUALQUER diretório `build` na árvore, não só o da raiz.
- Regra: não nomeie diretórios de código como `build`/`dist`; ou ancore o ignore (`/build/`). Movi para `scripts/bundle/`.

## 2026-07-09 · aws · Free tier novo limita concorrência total de Lambda a 10
- Sintoma: `terraform apply` falhou nas 3 Lambdas: `InvalidParameterValueException: Specified ReservedConcurrentExecutions ... decreases account's UnreservedConcurrentExecution below its minimum value of [10]`.
- Causa raiz: a AWS exige que o pool NÃO-reservado fique >= 10; com a quota total da conta em 10, reservar qualquer valor (era 1, 1 e 2) já viola a regra. Assumi a quota padrão de 1000.
- Regra: em conta free tier, `reserved_concurrent_executions = -1` (sem reserva) como default, exposto em variável. Para limitar consumo de SQS use `scaling_config.maximum_concurrency` no event source mapping — não consome a cota da conta.

## 2026-07-09 · processo · Falha previsível no fim de operação longa precisa de precheck
- Sintoma: 2x no mesmo dia, `make tf-destroy` sem FORCE rodou ~20 min e falhou no último recurso (BucketNotEmpty) — estado parcial + retrabalho.
- Causa raiz: a condição de falha (bucket com dados) era conhecível em segundos ANTES do destroy, mas nada a checava; o usuário esquece o FORCE=1 e paga caro.
- Regra: operação longa com pré-condição verificável ganha precheck fail-fast que aponta o comando certo (alvo `tf-destroy-precheck`); não deixar a AWS descobrir no minuto 20 o que um list de 1s responde.

## 2026-07-09 · terraform · Gate via data source também trava o destroy
- Sintoma: `make tf-destroy` falhou no refresh — `data.aws_s3_object.bundle` não achou o objeto; infra com bundle ausente ficou indestrutível.
- Causa raiz: data sources são lidos também no plano de DESTROY; um data source usado como gate de apply vira trava de teardown quando a pré-condição não vale mais.
- Regra: todo data source-gate precisa de escape (`count = var.validate_* ? 1 : 0`) e os alvos de destroy (tf-destroy, tf-plan-out DESTROY=1) passam a var como false.

## 2026-07-09 · aws · EC2 privada sem SSM/log shipping é indiagnosticável
- Sintoma: API da camada fria nunca subiu (`Connection refused` na Lambda); a instância não tinha SSH, IP público nem SSM — impossível ler /var/log/user-data.log; destruída, a causa morreu junto.
- Causa raiz: postura 100% privada sem NENHUM canal de diagnóstico; e o user_data roda 1x sob `set -e` — bundle ausente no boot = instância quebrada e muda.
- Regra: EC2 privada nasce com Session Manager (managed policy + interface endpoints ssm/ssmmessages/ec2messages) e trap no user_data enviando o log ao S3; `data aws_s3_object` do bundle gate o apply e o etag no user_data força replace no redeploy.

## 2026-07-09 · terraform · `-var` no destroy não muda atributo lido do state
- Sintoma: `make tf-destroy` falhou com `BucketNotEmpty` no bucket raw; e `FORCE=1` não teria salvado — o `-var="force_destroy=true"` é ignorado num destroy.
- Causa raiz: o plano de destroy vem do STATE, não da config. O provider lê `force_destroy` do estado anterior na hora do delete; um `-var` só afeta recursos que o plano vai criar/atualizar.
- Regra: para deletar bucket com dados, primeiro persista o flag no state (`terraform apply -var="force_destroy=true" -target=module.storage.aws_s3_bucket.layer`, update in-place) e só então destrua. Alvo `tf-force-arm` no Makefile.

## 2026-07-09 · terraform · `force_destroy` não remove versões de bucket versionado
- Sintoma: `make tf-destroy FORCE=1` falhou com `BucketNotEmpty` mesmo com `force_destroy=true`.
- Causa raiz: `force_destroy` do Terraform só apaga objetos correntes, não versões/delete markers. Buckets com versionamento habilitado exigem deleção explícita via API S3.
- Regra: antes de destruir bucket versionado, esvaziar todas as versões + delete markers via `boto3`/`aws s3api` em loop paginado. Adicionar target `tf-empty-buckets` como pré-requisito de `tf-force-arm`.

## 2026-07-06 · processo · Makefile referencia alvo antes de ele existir
- Sintoma: `sonar.yml` chama `make test-cov` — o alvo existia, mas o `pytest -m taac tests/taac` só seleciona testes marcados; um teste sem marker seria silenciosamente ignorado (0 testes = verde falso).
- Causa raiz: seleção por marker (`-m taac`) exige `@pytest.mark.taac`/`pytestmark` em TODO teste do diretório.
- Regra: todo teste em `tests/taac/` e `tests/integration/` DEVE ter o marker do diretório; verificar com `pytest -m <marker> --collect-only`.

## 2026-07-10 · tool · Git Bash converte args com "/" do AWS CLI em paths Windows
- Sintoma: `--log-group-name /aws/lambda/...` falhou (InvalidParameterException) e `--delimiter '/'` virou `C:/Program Files/Git` — o list-objects do S3 voltou vazio SILENCIOSAMENTE e quase virou diagnóstico errado.
- Causa raiz: o MSYS (Git Bash) faz path conversion em qualquer argumento que começa com `/`; o caso do delimitador corrompe sem erro.
- Regra: AWS CLI no Bash do Windows sempre com `MSYS_NO_PATHCONV=1` (ou rodar no PowerShell); resultado vazio com arg contendo `/` é suspeito até provar o contrário.

## 2026-07-10 · aws · Nome concatenado prefixo+dataset estoura limite de 64 chars
- Sintoma: `make tf-plan` falhou no FIM (`"name" cannot be longer than 64 characters`) na regra EventBridge de `product_category_name_translation`; validate/tflint não pegam (a validação é do provider, só roda no plan com o valor real).
- Causa raiz: nome = prefixo (26) + sufixo fixo (13) + dataset (33) = 73 chars; assumi que nome composto "cabe" sem somar.
- Regra: nome derivado de lista/variável ganha `substr(..., 0, <limite>)` com comentário; o valor íntegro vai em campo sem limite apertado (input/tag). Conferir limites: EventBridge rule 64, IAM role 64, statement_id 100.

## 2026-07-10 · processo · Docstrings dos jobs Glue entregues em inglês
- Sintoma: usuário corrigiu — os arquivos novos do Glue silver saíram com docstrings/descriptions em inglês; o projeto inteiro deve ser PT-BR.
- Causa raiz: "Docs e commits em PT-BR" do CLAUDE.md foi lido como README/commits apenas; docstrings, comentários e descriptions de Terraform ficaram fora.
- Regra: TODO texto autoral em PT-BR — docstrings, comentários, descriptions de Terraform, READMEs de módulo. CLAUDE.md atualizado para explicitar.

## 2026-07-10 · ci · Precheck de apply só no alvo manual; a esteira aplicava sem ele
- Sintoma: rollback.yml (mode=apply) num ambiente do zero morreu após ~11 min: `data.aws_s3_object.bundle` "couldn't find resource" — infra parcial.
- Causa raiz: ensure_api_bundle.py ligado só no `make tf-apply`; o caminho da esteira (tf-plan-out → tf-apply-plan) não publica o bundle, e no bootstrap o gate é adiado para o apply (bucket unknown no plan).
- Regra: invariante de pré-apply mora num alvo make único (tf-ensure-bundle) chamado por TODOS os caminhos que aplicam — manual e esteira (AUTO_APPROVE=1 OVERWRITE=1).

## 2026-07-13 · tool · Here-string do PowerShell (`@'...'@`) usada na tool Bash
- Sintoma: `git commit -m @'...'@` no Bash gravou a mensagem com um `@` solto na 1ª e na última linha; precisou de `--amend`.
- Causa raiz: `@'...'@` é sintaxe PowerShell; o Bash só concatena os `@` literais à string. As duas tools coexistem e eu misturei as sintaxes.
- Regra: mensagem multilinha na tool Bash vai por heredoc (`git commit -F - <<'EOF'`); `@'...'@` só na tool PowerShell.

## 2026-07-13 · python · TestClient sem `with` não roda o lifespan
- Sintoma: 6 testes da Event API falharam com `'State' object has no attribute 'sqs'` — o endpoint lia `app.state.sqs`, criado no lifespan.
- Causa raiz: `TestClient(app)` só dispara startup/shutdown quando usado como CONTEXT MANAGER. Os testes da API fria não pegam isso porque usam `dependency_overrides` e nunca tocam o `app.state`.
- Regra: app com recurso aberto no lifespan (pool, client boto3) exige `with TestClient(app) as cliente` (ou `ExitStack` quando a fixture é fábrica); só `dependency_overrides` dispensa o `with`.

## 2026-07-13 · processo · Falha de gate em código que não era meu
- Sintoma: TAAC e checkov reprovaram em `aws_iam_policy_document.glue_security_kms` — quase "consertei" achando que era regressão da minha mudança.
- Causa raiz: a árvore tinha alteração NÃO-COMMITADA do usuário (KMS + security configuration no glue_silver), feita em paralelo durante a sessão; o `git status` do início da sessão dizia clean.
- Regra: gate vermelho em arquivo que você não editou → `git status --short` + `git diff HEAD -- <arquivo>` ANTES de mexer. Se o código é do usuário, reporte e pergunte; nunca reverta nem "corrija" trabalho em andamento dele.

## 2026-07-13 · terraform · Key policy da KMS sem `kms:ListResourceTags` trava plan/apply/destroy
- Sintoma: `make tf-destroy FORCE=1` morreu no refresh — `AccessDeniedException: user/terraform is not authorized to perform kms:ListResourceTags ... no resource-based policy allows`.
- Causa raiz: o read do `aws_kms_key` chama DescribeKey + GetKeyPolicy + GetKeyRotationStatus + **ListResourceTags**; a lista fechada de ações do statement do root não tinha a última, e o que a key policy não lista a policy de identidade não delega. Pior: o Terraform não conserta a si mesmo — o refresh da chave é justamente o que falha.
- Regra: statement de administração de key policy inclui `kms:ListResourceTags` (não basta Tag/UntagResource). Chave já criada com o gap só se corrige fora do Terraform (`aws kms put-key-policy`) ou com `-refresh=false`.

## 2026-07-13 · ci · CVE ignorado por alias GHSA mascarou um CVE distinto
- Sintoma: `make security` quebrou com PYSEC-2026-2120 (black); ao reproduzir, o pip-audit acusou 3 CVEs — o PYSEC-2026-2121 já vinha silencioso, e o comentário do Makefile o descrevia como se fosse o ReDoS.
- Causa raiz: o ignore list usava `GHSA-3936-cmfr-pm3m`, alias de OUTRA vuln; um CVE novo entrou na lista sem revisão porque o alias casou sozinho.
- Regra: ignorar CVE pelo ID que o pip-audit reporta (PYSEC-*), um comentário por ID dizendo por que não nos atinge; antes de ignorar, ler a advisory no OSV (`api.osv.dev/v1/vulns/<ID>`) e reproduzir o gate (`uv run --with pip-audit --with <pkg>==<ver> --no-project pip-audit`).

## 2026-07-14 · ci · CVE em pacote do ambiente que ninguém declara
- Sintoma: `make security` quebrou com PYSEC-2026-3447 no setuptools 79.0.1 — versão que o `pip install -e .[prod]` nunca instalou nem sobe.
- Causa raiz: o pip-audit audita o ambiente INTEIRO, incluindo o que o `setup-python` já traz (setuptools/pip/wheel). Sem ninguém declarar o pacote, o pip não tem motivo para atualizá-lo e a versão do toolcache fica congelada, vulnerável.
- Regra: CVE com fix disponível se corrige com upgrade, não com ignore (o ignore é só para o que não tem saída, como o black fixado pelo blue). Para pacote do ambiente, declare-o no extra que o job audita (`setuptools>=83` em `[prod]`) — assim o pip sobe a versão corrigida e o Dependabot mantém.

## 2026-07-14 · aws · EventBridge Rule não dispara job Glue (só workflow)
- Sintoma: `tf-apply` na master quebrou em `PutTargets` — "Parameter arn:aws:glue:...:job/... is not valid. Reason: Provided Arn is not in correct format" — com o ARN do job correto.
- Causa raiz: a lista de targets nativos da EventBridge *Rule* tem Glue **workflow**, não Glue **job**; o erro de "formato" é a API dizendo que o TIPO de destino não existe, não que o ARN está malformado. `terraform validate`/`plan` não pegam isso (o ARN é uma string válida) — só o apply.
- Regra: para agendar `glue:StartJobRun`, use `aws_scheduler_schedule` (EventBridge Scheduler) com o target universal `arn:aws:scheduler:::aws-sdk:glue:startJobRun` e `input = jsonencode({ JobName = ... })`; trust da execution role é `scheduler.amazonaws.com` (não `events.amazonaws.com`). Antes de apontar um target de Rule, confira se o serviço está na lista de targets suportados.

## 2026-07-15 · terraform · Athena workgroup com histórico não deleta sem force_destroy
- Sintoma: `tf-apply-plan` (destroy) da esteira morreu no fim — `DeleteWorkGroup ... InvalidRequestException: WorkGroup ...-gold is not empty`, depois de ~20 min destruindo a rede.
- Causa raiz: as queries do consumer deixam histórico no workgroup; `DeleteWorkGroup` sem `RecursiveDeleteOption` recusa workgroup não-vazio. O recurso não tinha `force_destroy`, e — igual ao bucket — o provider lê esse flag do STATE ao deletar, então `-var` no destroy não resolveria.
- Regra: `aws_athena_workgroup` (e todo recurso com histórico/objetos: bucket, workgroup) ganha `force_destroy = var.force_destroy` e entra no `tf-force-arm` (um `-target` cada) para gravar o flag no state ANTES do destroy. Precondição de teardown conhecível não pode aparecer no minuto 20.

## 2026-07-14 · tool · Here-string do PowerShell na tool Bash corrompeu o commit
- Sintoma: `git commit -m @'...'@` pela tool Bash gerou a mensagem com assunto `@` e um `@` solto no fim; precisou de `--amend`.
- Causa raiz: a tool Bash é Git Bash (POSIX sh), não PowerShell — `@'...'@` não é here-string ali, é texto literal. As duas tools coexistem e cada uma tem a sua sintaxe.
- Regra: mensagem multi-linha na tool Bash vai por `git commit -F <arquivo>` (ou heredoc `<<'EOF'`); `@'...'@` só na tool PowerShell. Depois de commitar, conferir com `git log -1 --format=%B`.

## 2026-07-16 · terraform · EC2 boota antes da própria IAM policy em apply do zero
- Sintoma: Event API nunca subiu (Connection refused no producer); user_data falhou 12x com 403 no bundle e AccessDenied no ship do log — "no identity-based policy allows". CloudTrail: instância às 11:55:54, policy da role só às 12:02:05.
- Causa raiz: a EC2 referencia só o NOME do instance profile (string imediata); a policy da role espera o RDS (~7 min, rds_resource_id no rds-db:connect). O grafo não tem aresta instância→policy, e user_data roda 1x — a corrida é fatal e silenciosa (o ShipBootLog estava na mesma policy ausente). A api-cold só sobreviveu porque TAMBÉM espera o RDS.
- Regra: recurso cujo bootstrap USA permissões (user_data, init container) ganha aresta explícita para a policy — `depends_on` no OUTPUT que entrega o profile/role (cirúrgico; module depends_on difere data sources à toa). Conferir no CloudTrail (PutRolePolicy vs LaunchTime) quando IAM "que existe" foi negada no passado.

## 2026-07-16 · python · spark.conf.set de config ESTÁTICA quebra só em runtime (dublê mascara)
- Sintoma: jobs Glue silver morreram em `configurar_iceberg` — `AnalysisException: Cannot modify the value of a static config: spark.sql.extensions`; os 42 testes unitários passavam.
- Causa raiz: `spark.sql.extensions` é config estática — só vale na CRIAÇÃO da sessão; `spark.conf.set` numa sessão ativa lança em qualquer Spark. O teste usava `FakeSpark`, que aceita qualquer set, e a sessão local dos testes nunca chamava a função de verdade.
- Regra: função que configura Spark separa estática (extensions, warehouse.dir — via `--conf` do job/builder) de dinâmica (`spark.sql.catalog.*` — pode em runtime); dublê de `spark.conf` não valida semântica — para config, ou testa contra sessão real ou confia no `--conf` do Terraform como fonte única.

## 2026-07-16 · aws · Security configuration SSE-KMS exige logs:AssociateKmsKey na role do Glue
- Sintoma: os 2 jobs Glue silver falharam no bootstrap em prod — `Failed to AssociateKmsKey for logGroup ... not authorized to perform: logs:AssociateKmsKey`; silver ficou vazia com a raw ok.
- Causa raiz: security configuration com `cloudwatch_encryption_mode = "SSE-KMS"` faz o runner chamar `logs:AssociateKmsKey` ao criar o log group; a managed `AWSGlueServiceRole` para em Create*/PutLogEvents. Nenhum gate estático pega — a exigência só aparece quando o job RODA.
- Regra: ligou cifra KMS nos logs de um serviço (Glue, mas vale geral), a role de execução ganha `logs:AssociateKmsKey` escopado a `log-group:/aws-glue/*` E a key policy permite `logs.<region>.amazonaws.com` — as DUAS pontas, no mesmo PR da security configuration.

## 2026-07-15 · processo · Renomear "funções em PT-BR" virou exagero (main → principal)
- Sintoma: pedido de "funções em PT-BR" me levou a traduzir `main`→`principal` em ~12 arquivos e a reescrever tooling 100% inglês (release.py, ensure_api_bundle.py); o usuário corrigiu: "main pode ser main, sem exagero".
- Causa raiz: tratei "PT-BR" como tradução literal de TODO identificador, ignorando que `main`/`handler` são idiomas de entrypoint e que plumbing de CI/release não é domínio do lakehouse.
- Regra: PT-BR mira funções de DOMÍNIO; preserve idiomas universais (`main`, `handler`) e alinhe cada arquivo à sua convenção MAJORITÁRIA existente (traduzir o holdout inglês de um arquivo já-PT-BR é alinhamento; traduzir arquivo 100% inglês de tooling é exagero). Na dúvida de escopo amplo, confirmar a fronteira antes de reescrever.
