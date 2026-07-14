from contextlib import contextmanager
import httpx

# Fake é um duble de teste.
class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def fetch_data(url):
    response = httpx.get(url)

    if response.status_code == 200:
        return response.json()

    return {}


@contextmanager
def patch_get(resposta_falsa):
    get_original = httpx.get
    httpx.get = lambda url: resposta_falsa

    yield resposta_falsa

    httpx.get = get_original


# O fake responde no lugar da API: sem rede, sem servidor, sem flakiness.
with patch_get(FakeResponse(200, {"nome": "Olist"})):
    assert fetch_data("https://exemplo.test/dados") == {"nome": "Olist"}

# O mesmo fake exercita o caminho triste, que na API real seria dificil de forcar.
with patch_get(FakeResponse(404, {"erro": "nao encontrado"})):
    assert fetch_data("https://exemplo.test/dados") == {}

print("Fake ok: os dois caminhos exercitados sem sair da maquina.")
