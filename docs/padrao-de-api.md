# Padrão de API (curso GU FastAPI) e como este repo o aplica

Referência do padrão ensinado no curso **Geek University — FastAPI**
(`D:\Cursos\Programação\Geek University\GU_Fast_API`, seção 06, a mais
completa) e o mapeamento para a API deste projeto
([`src/cold/api_orders`](../src/cold/api_orders)).

## A estrutura do curso

```text
secao_06/
├── main.py                  # cria o FastAPI e pluga o api_router com prefixo /api/v1
├── .env                     # segredos/conexão — NUNCA no código
├── core/
│   ├── configs.py           # Settings(BaseSettings) lida do .env; singleton `settings`
│   ├── database.py          # engine async + async_sessionmaker
│   ├── deps.py              # dependências injetáveis: get_session (yield), get_current_user
│   ├── auth.py              # OAuth2/JWT: criação e validação de token
│   └── security.py          # hash/verificação de senha (bcrypt)
├── models/                  # SQLAlchemy (Mapped/mapped_column) — o formato do BANCO
├── schemas/                 # Pydantic (from_attributes) — o CONTRATO da API
└── api/v1/
    ├── api.py               # agregador: include_router por recurso, com prefix e tags
    └── endpoints/<recurso>.py  # um APIRouter por recurso, CRUD completo
```

## As regras que o padrão carrega

1. **Uma camada por responsabilidade** — endpoint não conhece engine; ele pede
   a sessão via `Depends(get_session)`. `models/` (banco) e `schemas/` (contrato
   HTTP) são coisas DIFERENTES: o schema expõe só o que a API promete.
2. **Configuração é classe, não constante espalhada** — `Settings(BaseSettings)`
   lê o `.env`; o resto do código importa o singleton `settings`.
3. **Async de ponta a ponta** — engine async, sessão async, endpoints `async def`.
4. **Contrato explícito em cada rota** — `response_model=`, `status_code=`
   (201 no POST, 204 no DELETE, 404 com `HTTPException` quando não achou).
5. **Versionamento na URL** — tudo sob `/api/v1`; o agregador `api/v1/api.py`
   monta os routers por recurso com `prefix` e `tags` (organiza o Swagger).
6. **Autenticação como dependência** — `Depends(get_current_user)` protege a
   rota; JWT assinado com segredo do `.env`; senha nunca em texto puro
   (`security.py` com bcrypt).

## Fluxo de um request (o desenho mental)

```text
request → api/v1/api.py → endpoints/<recurso>.py
        → Depends(get_session) abre a sessão   (core/deps.py)
        → Depends(get_current_user) valida JWT (core/auth.py)
        → consulta via model                   (models/)
        → resposta validada pelo schema        (schemas/) → JSON
```

## Como a API deste repo aplica o padrão

A [`api_orders`](../src/cold/api_orders) segue o MESMO esqueleto do curso —
`main.py`, `core/{configs,database,deps}`, `schemas/`, `api/v1/{api.py,endpoints/}` —
com adaptações conscientes ao contexto (data product de LEITURA servindo o
lakehouse, rodando em EC2 privada):

| Curso (secao_06) | Este repo | Por que mudou |
|---|---|---|
| SQLAlchemy async + `models/` | `psycopg_pool` async + SQL explícito | API só de leitura analítica; SQL direto com cursor keyset é mais simples e rápido que ORM |
| JWT + usuário no banco | token estático opcional + rede privada + IAM | não há usuários finais; quem chama é a Lambda dentro da VPC (defesa em profundidade) |
| `.env` com `DB_URL` | env vars + Secrets Manager/token IAM | segredo nunca em arquivo; a senha do RDS vem do Secrets Manager ou de token IAM de 15 min |
| retorno = lista inteira | paginação por cursor (`next_cursor`) | dataset de ~100k linhas; a Lambda consome em páginas resumíveis |
| — | cache-aside (`fastapi-cache2`), lifespan do pool, access log JSON com correlation id | necessidades de produção que o curso não cobre |

O que se mantém idêntico ao curso: `Settings(BaseSettings)` singleton,
dependências com `Depends`, um router por recurso agregado em `api/v1/api.py`,
schemas Pydantic com `from_attributes`, contrato explícito
(`response_model`/`status_code`) e async de ponta a ponta.
