
from docs.exemplos.codigo import romeu_e_julieta, Tarefa, ListaDeTarefas


# Teste de Comportamento (Behavior Test)

# Pytest / Unit Test
def test_romeu_e_julieta_deve_retornar_queijo():
    """
    Taxinomia dos testes
    
    AAA = Arrange, Act, Assert
    4 fases do teste: Setup, Exercise, Verify, Teardown
    """
    
    # Arrange

    valor_de_input = 3
    resultado_esperado = 'Queijo'

    # Act / Exercise / Chamada do SUT (System Under Test)
    resultado_obtido = romeu_e_julieta(valor_de_input)
    
    # Assert / Verify
    assert resultado_obtido == resultado_esperado
    
    
def test_romeu_e_julieta_deve_retornar_goiabada():
    # Arrange
    valor_de_input = 5
    resultado_esperado = 'Goiabada'

    # Act
    resultado_obtido = romeu_e_julieta(valor_de_input)
    
    # Assert
    assert resultado_obtido == resultado_esperado
    
    
def test_romeu_e_julieta_deve_retornar_ReJ():
    # Arrange
    valor_de_input = 15
    resultado_esperado = 'Romeu e Julieta'

    # Act
    resultado_obtido = romeu_e_julieta(valor_de_input)
    
    # Assert
    assert resultado_obtido == resultado_esperado


def test_romeu_e_julieta_deve_retornar_valor():
    # Arrange
    valor_de_input = 7
    resultado_esperado = '7'

    # Act
    resultado_obtido = romeu_e_julieta(valor_de_input)
    
    # Assert
    assert resultado_obtido == resultado_esperado




# ---------------------------------------------------------------------------
# Testando a classe Tarefa - Caso 2

def test_tarefa_deve_conter_os_campos_id_nome_status():
    # Arrange
    tarefa = Tarefa(id=1, nome="Estudar Pytest")
    
    # Act
    id_obtido = tarefa.id
    nome_obtido = tarefa.nome
    status_obtido = tarefa.status
    
    # Assert
    assert id_obtido == 1
    assert nome_obtido == "Estudar Pytest"
    assert status_obtido == "a fazer"
    
# ---------------------------------------------------------------------------
# Caso 3 - Testando a classe ListaDeTarefas

def test_lista_de_tarefas_criar_tarefa():
    # Arrange
    lista = ListaDeTarefas()
    
    # Act
    tarefa = lista.criar_tarefa("Estudar Pytest")
    
    # Assert
    assert lista.recuperar_tarefa(tarefa.id) == tarefa
    assert tarefa.nome == "Estudar Pytest"
    assert tarefa.status == "a fazer"

def test_lista_de_tarefas_recuperar_tarefa_nao_existente():
    # Arrange
    lista = ListaDeTarefas()

    # Garante que veio None
    assert lista.recuperar_tarefa(1) is None


def test_lista_de_tarefas_atualizar_tarefa():
    # Arrange
    lista = ListaDeTarefas()
    tarefa = lista.criar_tarefa("Estudar Pytest")

    # Act
    lista.atualiza_tarefa(tarefa.id, status="feito")

    # Assert
    tarefa_obtida = lista.recuperar_tarefa(tarefa.id)
    assert tarefa_obtida.status == "feito"
    # O nome nao foi informado, entao continua o mesmo.
    assert tarefa_obtida.nome == "Estudar Pytest"


def test_lista_de_tarefas_atualizar_so_altera_a_tarefa_do_id():
    # Arrange
    lista = ListaDeTarefas()
    primeira = lista.criar_tarefa("Estudar Pytest")
    segunda = lista.criar_tarefa("Estudar Docker")

    # Act
    lista.atualiza_tarefa(segunda.id, status="feito")

    # Assert
    assert lista.recuperar_tarefa(segunda.id).status == "feito"
    assert lista.recuperar_tarefa(primeira.id).status == "a fazer"


def test_lista_de_tarefas_deletar_tarefa():
    # Arrange
    lista = ListaDeTarefas()
    primeira = lista.criar_tarefa("Estudar Pytest")
    segunda = lista.criar_tarefa("Estudar Docker")

    # Act
    lista.deletar_tarefa(segunda.id)

    # Assert
    assert lista.recuperar_tarefa(segunda.id) is None
    assert lista.recuperar_tarefa(primeira.id) == primeira


def test_lista_de_tarefas_deletar_tarefa_nao_existente_nao_remove_nada():
    # Arrange
    lista = ListaDeTarefas()
    tarefa = lista.criar_tarefa("Estudar Pytest")

    # Act
    lista.deletar_tarefa(99)

    # Assert
    assert lista.recuperar_tarefa(tarefa.id) == tarefa
