from contextlib import contextmanager
import builtins

def spy_print(message):
    spy_print.message = f'Spy diz: {message}'
    

@contextmanager
def patch_print():
    print_original = builtins.print
    builtins.print = spy_print

    yield spy_print

    builtins.print = print_original

def batata():           
    print("Estou frita!")

# spy é um duble de teste.
with patch_print() as spy:
    batata()

print(spy.message)

assert spy.message == "Spy diz: Estou frita!"

"""assert spy.message == 'Spy diz: Estou frita!'"""