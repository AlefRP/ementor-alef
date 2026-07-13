
from docs.exemplos.codigo import romeu_e_julieta, Tarefa


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
    
    