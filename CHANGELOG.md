# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versionamento [SemVer](https://semver.org/) derivado de [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
Gerado automaticamente pelo workflow `release.yml` a cada push na master/main com commit `feat`/`fix`/`BREAKING CHANGE` — não editar manualmente.

## [0.2.0] - 2026-07-10
### Adicionado
- feat(make): tf-apply em um comando com precheck do bundle da API (0b4ff92)
- feat(infra): diagnostico e gate de deploy na EC2 privada da API (41350a8)
- feat(cold): lambda de bootstrap semeia o RDS privado e cria o api_reader (b4d00c1)
- feat(ci): entrega continua com versionamento semver e changelog (66967e0)
- feat(data): seed sintetico multi-tabela do Olist com Faker (12a8120)
- feat(seguranca): trafego criptografado no SQS e na API, sem custo adicional (ff23198)
- feat(hot): eventos realistas com Faker no producer e bundle multiplataforma (a0287ae)
- feat(hot): camada quente serverless - producer de eventos, SQS e ingestao na raw (224aba9)
- feat(infra): camada fria 100% privada - Lambda VPC, EC2 sem IP publico e IAM auth no RDS (bc0ee0e)
- feat(cold): API FastAPI async de pedidos e Lambda de ingestao para a raw (a9485a7)
- feat: infra base do lakehouse, governanca, TAAC, esteira e building blocks (998487d)
### Corrigido
- fix(ci): tf-ensure-bundle no apply automatico do merge a master (b3294cf)
- fix(ci): garantir bundle da API antes do apply da esteira (rollback) (fdc7e0a)
- fix(sonar): suprimir S5332 na validacao de esquema da lambda de ingestao (dc4abe4)
- fix(security): eliminar B311 do bandit com RNG proprio na simulacao (4f1cf84)
- fix(make): teardown fail-fast e correcao do upload do bundle (953b933)
- fix(terraform): armar force_destroy no state antes do destroy dos buckets (3d1d6e9)
- fix(build): api-bundle multiplataforma e fixado no alvo linux da EC2 (c5f0c16)
- fix(ci): passar arquivo (nao diretorio) ao output-file-path do checkov (89f88d5)
- fix(sonar): usar projectKey aws_ementor-alef criado no SonarCloud (3c4817d)
- fix(ci): gerar SARIF do bandit via plugin e atualizar upload-sarif para v4 (9ff5f5d)
- fix(security): atualizar pytest 9.0.3/pytest-cov 7.1.0 e suprimir CVEs do black (57e262b)
- fix(sonar): apontar analise para a organizacao alefrp (conta propria) (4384362)
- fix(sonar): usar projectKey real do SonarCloud (julioszeferino_ementor-alef) (51b8c2b)
### Modificado
- refactor(arch): separar simulacao da arquitetura em codigo e terraform (5fc14d7)
- refactor(synthetic): isolar a simulacao de dados num pacote proprio (f4f5bb7)
- refactor(cold): renomear api_fastapi para api_orders (7284fa6)

