# Padrão de testes do projeto

Todo teste deste repositório segue a estrutura **AAA** (preparar → agir →
verificar). Este documento é a referência; o exemplo executável está em
[`docs/exemplos/codigo.py`](exemplos/codigo.py) (o SUT) e
[`docs/exemplos/test_codigo.py`](exemplos/test_codigo.py) (os testes).

> Os exemplos em `docs/` são **só didáticos** — não fazem parte da suíte do
> projeto (`make test`, CI). O `testpaths` e o `norecursedirs` do
> `pyproject.toml` mantêm `pytest`/`make test` fora de `docs/`. Para rodar um
> exemplo à mão, aponte o arquivo:
> `pytest docs/exemplos/test_codigo.py` (cobertura: `--cov=docs.exemplos.codigo`, o nome pelo qual o
> SUT é importado).

## Taxonomia

- **AAA = Arrange, Act, Assert** — as três seções visíveis de cada teste.
- **GWT = Given, When, Then** (Dado, Quando, Então) — o MESMO padrão com outros
  nomes (popularizado por Dan North/BDD). `Given` = Arrange, `When` = Act,
  `Then` = Assert. Neste repo padronizamos os comentários em **AAA**, mas os
  dois vocabulários são intercambiáveis.
- **4 fases do teste** (xUnit Test Patterns, Gerard Meszaros): Setup, Exercise,
  Verify, Teardown. As três primeiras correspondem ao AAA; o **Teardown** fica
  a cargo das *fixtures* do pytest (ex.: a SparkSession fecha sozinha ao fim da
  sessão, o `tmp_path` é apagado pelo pytest) — o corpo do teste não limpa nada
  na mão.
- **SUT (System Under Test)** — a unidade sendo exercitada na seção Act.
  Cada teste exercita **um** comportamento de **um** SUT.

## Regras

1. **Nome**: `test_<unidade>_<cenario>`, em PT-BR, lendo como frase —
   `test_chave_hash_normaliza_caixa_e_espacos`. Quem lê a lista de falhas do
   pytest entende o que quebrou sem abrir o arquivo.
2. **Estrutura AAA em todo teste**: preparar → agir → verificar, nessa ordem,
   separados por linha em branco. Essa **estrutura é obrigatória**; os rótulos
   `# Arrange`/`# Act`/`# Assert` são **didáticos** — use-os em exemplos e nos
   testes que ganham clareza com eles, não em todos. Quando usar, o comentário
   pode ganhar contexto: `# Assert — o valor voltou (A -> B -> A): reativa`.
3. **Um assert lógico por teste**: vários `assert` são aceitáveis quando
   verificam o MESMO comportamento (ex.: várias colunas da mesma linha);
   comportamentos diferentes viram testes diferentes.
4. **Setup compartilhado vira fixture ou helper** com nome em PT-BR
   (`_com_metadados`, `_df_de_satellite`), nunca copy/paste entre testes.
5. **Dublês simples antes de mocks**: preferir classes falsas pequenas
   (`FakeSpark`, `FakeConf`) ou `monkeypatch` a mocks mágicos — o dublê
   documenta exatamente o que o SUT usa.
6. **Onde mora cada tipo**: `tests/unit/` (rápidos, sem AWS), `tests/integration/`
   (marker `integration`), `tests/taac/` (marker `taac`; live faz *skip*
   gracioso sem credenciais). Todo teste desses dois últimos diretórios DEVE
   ter o marker do diretório.
7. **Gates**: `make quality` roda tudo local; cobertura mínima de 90 %
   (`make test-cov`, mesmo threshold do SonarCloud).

## Exemplo canônico (didático): função original vs teste

A função original — o **SUT**:

```python
def romeu_e_julieta(val: int) -> str:
    """
    Se val for divisivel por 3 -> 'Queijo'
    Se val for divisivel por 5 -> 'Goiabada'
    Se val for divisivel por 3 e 5 -> 'Romeu e Julieta'
    Se val não for divisivel por 3 ou 5 -> val
    """
    match val % 3 == 0, val % 5 == 0:
        case [True, False]:
            return 'Queijo'
        case [False, True]:
            return 'Goiabada'
        case [True, True]:
            return 'Romeu e Julieta'
        case _:
            return str(val)
```

O teste que exercita UM comportamento dela:

```python
def test_romeu_e_julieta_deve_retornar_queijo():
    # Arrange
    valor_de_input = 3
    resultado_esperado = 'Queijo'

    # Act — chamada do SUT (System Under Test)
    resultado_obtido = romeu_e_julieta(valor_de_input)

    # Assert
    assert resultado_obtido == resultado_esperado
```

Repare que o teste cobre só o cenário "divisível por 3": os outros três
comportamentos da função (Goiabada, Romeu e Julieta, o próprio número) viram
três OUTROS testes, cada um com seu nome de cenário — é exatamente o que
[`docs/exemplos/test_codigo.py`](exemplos/test_codigo.py) faz, com quatro testes
(`..._retornar_queijo`, `..._goiabada`, `..._ReJ`, `..._valor`).

## Exemplo real do projeto: função original vs teste

A função original, de
[`src/glue_silver_runtime/iceberg.py`](../src/glue_silver_runtime/iceberg.py) —
decide quais linhas de satellite (Data Vault) devem entrar:

```python
def novas_linhas_de_satellite(
    stage: DataFrame, current: DataFrame, hk: str
) -> DataFrame:
    """Mantém as linhas cujo hashdiff difere do registro MAIS RECENTE da chave."""
    mais_recente_primeiro = Window.partitionBy(hk).orderBy(F.col('load_dts').desc())
    ultima_versao = (
        current.withColumn('_rn', F.row_number().over(mais_recente_primeiro))
        .where(F.col('_rn') == 1)
        .select(F.col(hk).alias('_hk'), F.col('hashdiff').alias('_hashdiff'))
    )
    return (
        stage.join(ultima_versao, stage[hk] == ultima_versao['_hk'], 'left')
        .where(F.col('_hashdiff').isNull() | (F.col('hashdiff') != F.col('_hashdiff')))
        .drop('_hk', '_hashdiff')
    )
```

O teste, de
[`tests/unit/glue_silver/test_iceberg.py`](../tests/unit/glue_silver/test_iceberg.py),
exercitando o comportamento mais sutil dela com Spark local:

```python
def test_novas_linhas_de_satellite_insere_reativacao_de_valor_antigo(spark):
    # Arrange — hd_a existe na HISTÓRIA, mas o MAIS RECENTE é hd_b
    historico = _df_de_satellite(
        spark,
        [('k1', 'SP', 'hd_a', '2026-01-01'), ('k1', 'RJ', 'hd_b', '2026-01-02')],
    )
    stage = _df_de_satellite(spark, [('k1', 'SP', 'hd_a', '2026-01-03')])

    # Act
    novas = novas_linhas_de_satellite(stage, historico, 'x_hk')

    # Assert — o valor voltou (A -> B -> A): a reativação deve entrar
    assert novas.count() == 1
```

Repare nas quatro fases: o **Setup** pesado (SparkSession) veio da fixture
`spark`; Arrange monta só os dados do cenário; Act chama o SUT; Assert verifica
o comportamento; o **Teardown** (fechar o Spark) é automático.

## Ferramentas do pytest

O que segue é o repertório de pytest que usamos no dia a dia. Cada recurso vem
com a sintaxe e quando aplicá-lo.

### Fixtures — preparar (e limpar) sem repetição

Fixture é a maneira do pytest de fornecer o recurso pronto ao teste e limpar
depois, centralizando Setup + Teardown. O teste só declara a fixture como
parâmetro e o pytest injeta.

```python
@pytest.fixture
def retangulo():
    return Retangulo(2, 3)          # Setup

def test_valida_comprimento(retangulo):
    assert retangulo.comprimento != retangulo.largura
```

Para Setup **e** Teardown, use `yield`: o que vem antes é o Setup, o que vem
depois roda no fim (é o padrão da fixture `spark` deste repo).

```python
@pytest.fixture(scope='session')
def spark():
    session = SparkSession.builder.master('local[2]').getOrCreate()
    yield session                   # entrega ao teste
    session.stop()                  # Teardown, após o último teste da sessão
```

- **`scope`**: `function` (padrão, uma por teste), `session` (uma para toda a
  suíte — usada em recursos caros como o Spark).
- **Fixtures built-in** que já aproveitamos: `tmp_path` (diretório temporário
  apagado no fim), `capsys` (captura `stdout`/`stderr`), `caplog` (captura logs
  — usada para verificar o log JSON), `monkeypatch` (troca atributos/env vars).

### Parametrização — o mesmo teste, vários dados

Evita copiar o teste para cada caso. Cada tupla vira um caso independente que
aparece separado no relatório.

```python
@pytest.mark.parametrize(
    'a, b, valor_esperado',
    [
        (3, 5, 8),
        (10, 15, 25),
        (6, 7, 13),
    ],
)
def test_soma(a, b, valor_esperado):
    assert somar(a, b) == valor_esperado
```

Fixtures também parametrizam, via `params` + `request.param` — útil quando o
recurso preparado é que varia:

```python
@pytest.fixture(params=[(2, 3), (4, 5), (6, 7)])
def retangulos(request):
    comprimento, largura = request.param
    return Retangulo(comprimento, largura)
```

### Testar exceções

Quando o comportamento esperado é **falhar**, o Act vai dentro do
`pytest.raises`; o Assert é o próprio contexto (usamos isto em
`test_escrever_frame_do_vault_rejeita_tipo_desconhecido`).

```python
def test_dividir_por_zero_gera_erro():
    # Act / Assert
    with pytest.raises(ValueError):
        dividir(10, 0)
```

### Markers — rotular e selecionar testes

Marker é um rótulo. Serve para agrupar (`integration`, `taac`) e para controlar
execução. Markers customizados devem ser **declarados** (no `pyproject.toml`
deste repo; era o `pytest.ini` no curso) senão viram warning.

```python
@pytest.mark.taac          # roda com: pytest -m taac
def test_infra_valida(): ...

@pytest.mark.skip(reason='ainda não implementado')      # nunca roda
@pytest.mark.skipif(sys.platform == 'win32', reason='...')  # pula condicional
@pytest.mark.xfail(reason='bug conhecido')              # falha esperada
```

Regra do repo: todo teste em `tests/integration/` e `tests/taac/` **precisa** do
marker do diretório — sem ele, `pytest -m taac` o ignora silenciosamente (0
testes = verde falso).

### Agrupar em classe (opcional)

Testes de um mesmo SUT podem viver numa classe `TestX` (sem `__init__`) para
compartilhar fixtures e aplicar um marker a todos de uma vez.

```python
class TestGameThinkAboutIt:
    def test_retorna_inteiro(self): ...
    def test_retorna_par(self): ...
```

### Flags do dia a dia

| Flag | Para quê |
| --- | --- |
| `-v` | saída verbosa (um teste por linha) |
| `-ra` | resumo de tudo que não passou (falhas, skips, xfails) |
| `-x` | para no primeiro erro |
| `-k <padrão>` | roda só os testes cujo nome casa com o padrão |
| `-m <marker>` | roda só os testes com aquele marker |
| `-s` | mostra os `print`/stdout durante a execução |
| `--pdb` | abre o debugger no ponto da falha (sair: `q` + Enter) |
| `--fixtures` | lista as fixtures disponíveis |
| `--markers` | lista os markers declarados |

### Cobertura (coverage)

Cobertura mede quais linhas do código foram exercitadas pelos testes. Roda pelo
plugin `pytest-cov`; `--cov=<pacote>` diz **qual código** medir (não confundir
com o caminho dos testes).

No exemplo didático — o SUT é importado como `codigo` (via `from codigo import`),
então é esse o nome a medir:

```bash
pytest docs/exemplos/test_codigo.py --cov=docs.exemplos.codigo
```

Formatos de relatório (`--cov-report`), combináveis na mesma chamada:

```bash
# Terminal, apontando as linhas NÃO cobertas:
pytest docs/exemplos/test_codigo.py --cov=docs.exemplos.codigo --cov-report=term-missing

# HTML navegável — gera a pasta htmlcov/; abra htmlcov/index.html no navegador:
pytest docs/exemplos/test_codigo.py --cov=docs.exemplos.codigo --cov-report=html
```

> Dica: `--cov=docs.codigo` avisa *"module never imported"* — o módulo foi
> importado como `codigo`, não `docs.codigo`. Use o nome pelo qual ele é
> importado. Os artefatos gerados (`htmlcov/`, `.coverage`, `coverage.xml`) já
> estão no `.gitignore` do repo — não versione.

No **projeto** (não nos exemplos) isso já está encapsulado: `make test-cov`
mede `--cov=src`, gera `term-missing` + `html` + `xml` e aplica o gate de 90 %
(`--cov-fail-under=90`, mesmo threshold do SonarCloud).

## Referências (teoria de testes)

- **Test-Driven Development: By Example** — Kent Beck.
- **Growing Object-Oriented Software, Guided by Tests** — Freeman & Pryce.
- **xUnit Test Patterns** — Gerard Meszaros (origem das 4 fases e do termo SUT).
- **Pytest Quick Start Guide** — Bruno Oliveira.
