def romeu_e_julieta(val: int) -> str:
    """
    Param:
        val: int (numero)
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
        
        
# Caso 2 ------------------------------------------------------------------
from dataclasses import dataclass


@dataclass
class Tarefa:
    id: int
    nome: str
    status: str = "a fazer"
    

# Caso 3 DOC ------------------------------------------------------------------

class ListaDeTarefas:

    def __init__(self) -> None:
        self.tarefas: list[Tarefa] = []
        self.contador_id: int = 1

    def criar_tarefa(self, nome: str, status: str = "a fazer") -> Tarefa:
        # Tarefa DOC
        tarefa = Tarefa(self.contador_id, nome, status)
        self.tarefas.append(tarefa)
        
        self.contador_id += 1
        
        return tarefa
    
    def atualiza_tarefa(
        self,
        id: int,
        nome: str | None = None,
        status: str | None = None
    ) -> None:
        # Só o que vier preenchido é alterado; o resto da tarefa fica intacto.
        for tarefa in self.tarefas:
            if tarefa.id == id:
                if nome:
                    tarefa.nome = nome
                if status:
                    tarefa.status = status
                break

    def deletar_tarefa(self, id: int) -> None:
        for tarefa in self.tarefas:
            if tarefa.id == id:
                self.tarefas.remove(tarefa)
                break


    def recuperar_tarefa(self, id: int) -> Tarefa | None:
        for tarefa in self.tarefas:
            if tarefa.id == id:
                return tarefa
        return None
