import time

def skip_time(time):
    print("To te enganando...")

def calculo_idade(dado):
    return dado

def verifica_idade():
    if calculo_idade(20) >= 18:
        return "Maior de idade"
    return "Menor de idade"

def executa_uma_tarefa():
    print("Iniciando uma tarefa...")
    time.sleep(30)  # Simula um atraso na execução
    print("Tarefa concluída!")

time.sleep = skip_time

calculo_idade = lambda x: 12 # Stub para simular a função de cálculo de idade

# breakpoint()

executa_uma_tarefa()
verifica_idade()
