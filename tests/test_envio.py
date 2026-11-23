"""Envio retomável com um servidor falso no lugar da rede: nada sai do PC.

O dublê entra embaixo da biblioteca do Google, no lugar do httplib2. Assim os
testes exercitam a retomada de verdade, com os mesmos pedidos que iriam ao Drive.
"""

import hashlib
import json
import re
from types import SimpleNamespace

import pytest
from google.auth.exceptions import RefreshError
from httplib2 import Response
from httplib2.error import ServerNotFoundError

from transcritor import drive, entrega, envio, pastas, preferencias
from transcritor.envio import TAMANHO_DO_BLOCO, TENTATIVAS, FalhaNoEnvio, enviar_arquivo
from transcritor.pastas import AutorizacaoExpirada


def erro_http(codigo, motivo=""):
    corpo = {"error": {"code": codigo, "errors": [{"reason": motivo}]}}
    return (codigo, {}, json.dumps(corpo).encode())


class ServidorFalso:
    """Imita o Drive: busca, abertura do envio, blocos e a pergunta "até onde chegou?".

    falhas diz o que dá errado, na ordem dos pedidos de cada tipo: None é um
    pedido normal, uma exceção é uma queda de conexão, e uma tupla é uma
    resposta de erro. "depois" grava o bloco e só então derruba a conexão.
    """

    def __init__(self, existentes=(), **falhas):
        self.existentes = list(existentes)
        self.falhas = {tipo: list(lista) for tipo, lista in falhas.items()}
        self.pedidos = []
        self.sessoes = 0
        self.recebido = b""
        self.metadados = None

    def request(self, uri, method="GET", body=None, headers=None, **_):
        headers = headers or {}
        if method == "GET":
            tipo = "busca"
        elif method == "POST":
            tipo = "abertura"
        elif headers.get("Content-Range", "").startswith("bytes */"):
            tipo = "pergunta"
        else:
            tipo = "bloco"
        self.pedidos.append(tipo)

        fila = self.falhas.get(tipo, [])
        falha = fila.pop(0) if fila else None
        if isinstance(falha, Exception):
            raise falha
        if isinstance(falha, tuple):
            return self._resposta(*falha)
        resposta = getattr(self, f"_{tipo}")(uri, body, headers)
        if falha == "depois":
            raise ConnectionResetError("caiu depois de gravar")
        return resposta

    @staticmethod
    def _resposta(codigo, cabecalhos=None, corpo=b""):
        return Response({"status": codigo, **(cabecalhos or {})}), corpo

    def _busca(self, uri, body, headers):
        return self._resposta(200, {}, json.dumps({"files": self.existentes}).encode())

    def _abertura(self, uri, body, headers):
        self.sessoes += 1
        self.recebido = b""
        self.metadados = json.loads(body)
        return self._resposta(200, {"location": f"https://envio/{self.sessoes}"})

    def _bloco(self, uri, body, headers):
        inicio, _, total = re.match(
            r"bytes (\d+)-(\d+)/(\d+)", headers["Content-Range"]
        ).groups()
        # O Drive de verdade recusa um bloco fora do lugar.
        assert int(inicio) == len(self.recebido)
        self.recebido += body.read() if hasattr(body, "read") else body
        return self._situacao(int(total))

    def _pergunta(self, uri, body, headers):
        return self._situacao(int(headers["Content-Range"].split("/")[1]))

    def _situacao(self, total):
        if len(self.recebido) == total:
            corpo = {"id": "novo", "name": self.metadados["name"], "webViewLink": "https://drive/novo"}
            return self._resposta(200, {}, json.dumps(corpo).encode())
        cabecalhos = {"range": f"bytes=0-{len(self.recebido) - 1}"} if self.recebido else {}
        return self._resposta(308, cabecalhos)


@pytest.fixture
def arquivo(tmp_path):
    """Dois blocos inteiros e um pedaço, com conteúdo que denuncia bloco trocado."""
    caminho = tmp_path / "aula.mp3"
    caminho.write_bytes(b"a" * TAMANHO_DO_BLOCO + b"b" * TAMANHO_DO_BLOCO + b"fim")
    return caminho


@pytest.fixture
def enviar(arquivo):
    """Envia para o servidor dado sem esperar de verdade, anotando as esperas."""
    from googleapiclient.discovery import build

    def chamar(servidor, caminho=arquivo, **opcoes):
        # O documento da API vem com a biblioteca; só a rede é trocada.
        servico = build("drive", "v3", http=servidor, cache_discovery=False)
        chamar.esperas = []
        opcoes.setdefault("esperar", chamar.esperas.append)
        return enviar_arquivo(servico, caminho, "pasta-1", **opcoes)

    return chamar


def test_envia_em_blocos_para_a_pasta_com_o_nome_do_arquivo(enviar, arquivo):
    servidor = ServidorFalso()
    progresso = []

    enviado = enviar(servidor, ao_progredir=lambda feito, total: progresso.append((feito, total)))

    assert enviado == ("novo", "aula.mp3", "https://drive/novo", False)
    assert servidor.metadados == {"name": "aula.mp3", "parents": ["pasta-1"]}
    assert servidor.recebido == arquivo.read_bytes()
    total = arquivo.stat().st_size
    assert progresso == [
        (TAMANHO_DO_BLOCO, total),
        (2 * TAMANHO_DO_BLOCO, total),
        (total, total),
    ]
    assert enviar.esperas == []


@pytest.mark.parametrize(
    "falha",
    [
        ConnectionResetError("caiu"),
        TimeoutError("demorou"),
        ServerNotFoundError("sem internet"),
        erro_http(503),
        erro_http(429),
        erro_http(403, "userRateLimitExceeded"),
    ],
    ids=["queda", "demora", "sem-internet", "503", "429", "ritmo"],
)
def test_falha_passageira_no_meio_retoma_de_onde_parou(enviar, arquivo, falha):
    servidor = ServidorFalso(bloco=[None, falha])

    enviar(servidor)

    assert servidor.recebido == arquivo.read_bytes()
    # Um envio só: o primeiro bloco não foi mandado de novo.
    assert servidor.sessoes == 1
    assert servidor.pedidos.count("pergunta") == 1


def test_queda_depois_do_ultimo_bloco_nao_envia_de_novo(enviar, arquivo):
    # O Drive recebeu tudo, mas a resposta se perdeu no caminho.
    servidor = ServidorFalso(bloco=[None, None, "depois"])

    assert enviar(servidor).id == "novo"
    assert servidor.sessoes == 1
    assert servidor.pedidos.count("bloco") == 3


@pytest.mark.parametrize("etapa", ["busca", "abertura"])
def test_falha_antes_do_primeiro_bloco_tambem_e_repetida(enviar, arquivo, etapa):
    servidor = ServidorFalso(**{etapa: [ConnectionResetError("caiu")]})

    enviar(servidor)

    assert servidor.recebido == arquivo.read_bytes()


def test_a_espera_dobra_a_cada_falha_e_desiste_no_fim(enviar, arquivo):
    servidor = ServidorFalso(abertura=[ConnectionResetError("caiu")] * 20)
    avisos = []

    with pytest.raises(FalhaNoEnvio, match=f"a conexão falhou {TENTATIVAS} vezes"):
        enviar(servidor, ao_repetir=lambda tentativa, espera: avisos.append(tentativa))

    assert servidor.pedidos.count("abertura") == TENTATIVAS
    assert [int(espera) for espera in enviar.esperas] == [1, 2, 4, 8, 16]
    assert avisos == [2, 3, 4, 5, 6]
    assert arquivo.exists()


def test_um_bloco_entregue_renova_as_tentativas(enviar, arquivo):
    queda = ConnectionResetError("caiu")
    quase = [queda] * (TENTATIVAS - 1)
    servidor = ServidorFalso(bloco=[*quase, None, *quase])

    enviar(servidor)

    assert servidor.recebido == arquivo.read_bytes()


def test_envio_vencido_no_drive_comeca_outro(enviar, arquivo):
    servidor = ServidorFalso(bloco=[None, erro_http(404)])

    enviar(servidor)

    assert servidor.sessoes == 2
    assert servidor.recebido == arquivo.read_bytes()


@pytest.mark.parametrize(
    ("falha", "mensagem"),
    [
        (erro_http(403, "storageQuotaExceeded"), "não há espaço livre"),
        (erro_http(404, "notFound"), "a pasta de destino não existe mais"),
        (erro_http(400, "invalid"), r"recusou o envio \(400 invalid\)"),
    ],
)
def test_falha_definitiva_nao_e_repetida(enviar, falha, mensagem):
    servidor = ServidorFalso(abertura=[falha])

    with pytest.raises(FalhaNoEnvio, match=mensagem):
        enviar(servidor)

    assert servidor.pedidos.count("abertura") == 1
    assert enviar.esperas == []


@pytest.mark.parametrize("etapa", ["busca", "abertura", "bloco"])
def test_autorizacao_expirada_em_qualquer_etapa_para_na_hora(enviar, etapa):
    servidor = ServidorFalso(**{etapa: [RefreshError("invalid_grant")]})

    with pytest.raises(AutorizacaoExpirada, match="expirou"):
        enviar(servidor)
    assert enviar.esperas == []


def test_renovacao_com_o_google_fora_do_ar_e_repetida(enviar, arquivo):
    servidor = ServidorFalso(bloco=[None, RefreshError("500", retryable=True)])

    enviar(servidor)

    assert servidor.recebido == arquivo.read_bytes()


def test_entrega_com_autorizacao_expirada_esquece_o_token_e_para(arquivo, monkeypatch):
    salvo = drive.caminho_do_token()
    salvo.parent.mkdir(parents=True, exist_ok=True)
    salvo.write_text("{}", encoding="utf-8")
    tentados = []

    def expirar(servico, arquivo, *_):
        tentados.append(arquivo)
        raise AutorizacaoExpirada("a autorização expirou")

    monkeypatch.setattr(pastas, "obter_ou_criar", lambda _s, nome: pastas.Pasta(nome, nome))
    monkeypatch.setattr(envio, "enviar_arquivo", expirar)

    with pytest.raises(AutorizacaoExpirada):
        list(entrega.entregar("serviço", [arquivo, arquivo], {"audio": "A", "pdf": "B"}))

    assert len(tentados) == 1
    assert not salvo.exists()


def test_arquivo_igual_ja_no_drive_nao_e_enviado_de_novo(enviar, arquivo):
    soma = hashlib.md5(arquivo.read_bytes()).hexdigest()
    servidor = ServidorFalso([{"id": "velho", "name": "aula.mp3", "md5Checksum": soma}])

    enviado = enviar(servidor)

    assert enviado.id == "velho"
    assert enviado.ja_estava_la
    assert servidor.pedidos == ["busca"]


def test_mesmo_nome_com_outro_conteudo_vira_outro_arquivo(enviar):
    servidor = ServidorFalso([{"id": "velho", "name": "aula.mp3", "md5Checksum": "outra"}])

    assert enviar(servidor).id == "novo"


def test_cancelar_pelo_progresso_interrompe_e_libera_o_arquivo(enviar, arquivo):
    servidor = ServidorFalso()

    def cancelar(enviado, total):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        enviar(servidor, ao_progredir=cancelar)

    assert servidor.pedidos.count("bloco") == 1
    arquivo.unlink()  # No Windows, falharia se o arquivo tivesse ficado aberto.


def test_arquivo_vazio_ou_inexistente_nem_chega_a_rede(enviar, tmp_path):
    vazio = tmp_path / "vazio.mp3"
    vazio.touch()
    servidor = ServidorFalso()

    with pytest.raises(FalhaNoEnvio, match="vazio"):
        enviar(servidor, vazio)
    with pytest.raises(FalhaNoEnvio, match="não foi possível ler"):
        enviar(servidor, tmp_path / "sumiu.mp3")
    assert servidor.pedidos == []


# --- O comando transcritor-drive enviar ---


@pytest.fixture
def comando(monkeypatch):
    """Troca o Drive por dublês e anota para qual pasta foi cada arquivo."""
    enviados = []

    def enviar(servico, arquivo, pasta_id, *_):
        if not arquivo.exists():
            raise FalhaNoEnvio(f"não foi possível ler {arquivo}")
        enviados.append((arquivo.name, pasta_id))
        return envio.ArquivoNoDrive("id", arquivo.name, "https://drive/id")

    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: SimpleNamespace())
    monkeypatch.setattr(pastas, "obter_ou_criar", lambda _s, nome: pastas.Pasta(nome, nome))
    monkeypatch.setattr(envio, "enviar_arquivo", enviar)
    return enviados


def test_comando_enviar_separa_o_audio_do_pdf(comando, arquivo, capsys):
    pdf = arquivo.with_suffix(".PDF")
    pdf.write_bytes(b"%PDF")

    assert drive.main(["enviar", str(arquivo), str(pdf)]) == 0

    assert comando == [("aula.mp3", "Transcritor - Áudios"), ("aula.PDF", "Transcritor - PDFs")]
    assert "aula.mp3 enviado para Transcritor - Áudios: https://drive/id" in capsys.readouterr().out


def test_comando_enviar_usa_as_pastas_das_preferencias(comando, arquivo):
    preferencias.salvar(preferencias.Preferencias(pasta_audio="Física"))

    assert drive.main(["enviar", str(arquivo)]) == 0

    assert comando == [("aula.mp3", "Física")]


def test_falha_em_um_arquivo_nao_impede_os_outros(comando, arquivo, capsys):
    assert drive.main(["enviar", str(arquivo.with_name("sumiu.mp3")), str(arquivo)]) == 1

    assert comando == [("aula.mp3", "Transcritor - Áudios")]
    assert "erro: não foi possível ler" in capsys.readouterr().err


def test_enviar_sem_arquivos_e_arquivos_sem_enviar_sao_erros_de_uso(capsys):
    for argumentos in (["enviar"], ["pastas", "aula.mp3"]):
        with pytest.raises(SystemExit) as saida:
            drive.main(argumentos)
        assert saida.value.code == 2
