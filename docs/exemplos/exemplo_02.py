from contextlib import contextmanager
import httpx

# Fake é um duble de teste.
class FakeResponse:
    def __init__(self, url, status_code, json_data=None):
        self.url = url
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def fetch_data(url):
    try:
        response = httpx.get(url)
    except httpx.RequestError:
        return {}

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
with patch_get(FakeResponse("https://exemplo.test/dados", 200, {"nome": "Olist"})):
    assert fetch_data("https://exemplo.test/dados") == {"nome": "Olist"}

# O mesmo fake exercita o caminho triste, que na API real seria dificil de forcar.
with patch_get(FakeResponse("https://exemplo.test/dados", 404, {"erro": "nao encontrado"})):
    assert fetch_data("https://exemplo.test/dados") == {}

print("Fake ok: os dois caminhos exercitados sem sair da maquina.")


def test_fetch_data_deve_retornar_200(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url: FakeResponse(url, 200, {"nome": "Olist"}),
    )
    resposta = fetch_data("https://exemplo.test/dados")
    assert resposta == {"nome": "Olist"}


def test_fetch_data_deve_retornar_500(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url: FakeResponse(url, 500, {"erro": "erro interno"}),
    )
    resposta = fetch_data("https://exemplo.test/dados")
    assert resposta == {}


def test_fetch_data_deve_retornar_erro(monkeypatch):
    def patch_error(url):
        raise httpx.RequestError("Erro de rede simulado")

    monkeypatch.setattr(httpx, "get", patch_error)

    resposta = fetch_data("https://exemplo.test/dados")
    assert resposta == {}
