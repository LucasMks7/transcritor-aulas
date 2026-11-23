"""Autorização do Drive com dublês no lugar do Google: nada sai do PC."""

import json
from types import SimpleNamespace

import pytest
from google.auth.exceptions import RefreshError, TransportError
from httplib2.error import ServerNotFoundError

from transcritor import drive
from transcritor.drive import (
    ESCOPOS,
    FalhaNaAutorizacao,
    carregar_credenciais,
    conectar,
    desconectar,
)


class CredenciaisFalsas:
    def __init__(self, valid=True, refresh_token="renovacao", nome="nova"):
        self.valid = valid
        self.refresh_token = refresh_token
        self.nome = nome

    def to_json(self):
        return json.dumps({"nome": self.nome, "refresh_token": self.refresh_token})


@pytest.fixture
def token(tmp_path):
    return tmp_path / "config" / "token.json"


@pytest.fixture
def client_secret(tmp_path):
    caminho = tmp_path / "client_secret.json"
    caminho.write_text("{}", encoding="utf-8")
    return caminho


def test_escopo_pedido_e_so_o_dos_arquivos_criados_pelo_programa():
    # Permissão mínima: nada de ler o Drive inteiro da pessoa.
    assert ESCOPOS == ["https://www.googleapis.com/auth/drive.file"]


def test_pasta_de_configuracao_fica_no_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert drive.caminho_do_token() == tmp_path / "transcritor-aulas" / "token.json"
    assert drive.caminho_do_client_secret() == tmp_path / "transcritor-aulas" / "client_secret.json"


def test_client_secret_pode_vir_de_uma_variavel_de_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSCRITOR_CLIENT_SECRET", str(tmp_path / "meu.json"))

    assert drive.caminho_do_client_secret() == tmp_path / "meu.json"


def test_sem_token_salvo_nao_ha_credenciais(token):
    assert carregar_credenciais(token) is None


def test_token_valido_e_usado_sem_renovar(token):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")
    salvo = CredenciaisFalsas()

    credenciais = carregar_credenciais(token, ler=lambda caminho: salvo, renovar=pytest.fail)

    assert credenciais is salvo


def test_token_vencido_e_renovado_e_salvo_de_novo(token):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")
    vencido = CredenciaisFalsas(valid=False, nome="renovada")
    renovadas = []

    credenciais = carregar_credenciais(token, ler=lambda caminho: vencido, renovar=renovadas.append)

    assert credenciais is vencido
    assert renovadas == [vencido]
    assert json.loads(token.read_text(encoding="utf-8"))["nome"] == "renovada"


def test_autorizacao_revogada_e_apagada_para_pedir_outra(token):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")

    def recusar(credenciais):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    credenciais = carregar_credenciais(
        token, ler=lambda caminho: CredenciaisFalsas(valid=False), renovar=recusar
    )

    assert credenciais is None
    assert not token.exists()


def test_token_vencido_sem_renovacao_e_apagado(token):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")

    credenciais = carregar_credenciais(
        token, ler=lambda caminho: CredenciaisFalsas(valid=False, refresh_token=None)
    )

    assert credenciais is None
    assert not token.exists()


def test_token_corrompido_e_apagado(token):
    token.parent.mkdir()
    token.write_text("isto não é json", encoding="utf-8")

    assert carregar_credenciais(token) is None
    assert not token.exists()


def test_conectar_com_token_salvo_nao_abre_o_navegador(token, client_secret):
    salvo = CredenciaisFalsas()

    credenciais = conectar(
        client_secret, token, autorizar=pytest.fail, carregar=lambda caminho: salvo
    )

    assert credenciais is salvo


def test_conectar_sem_token_pede_autorizacao_e_salva(token, client_secret):
    pedidos = []

    def autorizar(caminho):
        pedidos.append(caminho)
        return CredenciaisFalsas()

    conectar(client_secret, token, autorizar=autorizar, ha_internet=lambda: True)

    assert pedidos == [client_secret]
    assert json.loads(token.read_text(encoding="utf-8"))["refresh_token"] == "renovacao"


def test_sem_o_client_secret_explica_onde_ele_falta(token, tmp_path):
    with pytest.raises(FalhaNaAutorizacao, match="falta o arquivo de credenciais.*google-drive.md"):
        conectar(tmp_path / "sumiu.json", token, autorizar=pytest.fail)


def test_client_secret_invalido_vira_mensagem_clara(token, client_secret):
    def autorizar(caminho):
        raise ValueError("Client secrets must be for a web or installed app.")

    with pytest.raises(FalhaNaAutorizacao, match="não é válido"):
        conectar(client_secret, token, autorizar=autorizar, ha_internet=lambda: True)
    assert not token.exists()


def test_autorizacao_negada_vira_mensagem_clara(token, client_secret):
    def autorizar(caminho):
        raise RuntimeError("access_denied")

    with pytest.raises(FalhaNaAutorizacao, match="não foi concluída: access_denied"):
        conectar(client_secret, token, autorizar=autorizar, ha_internet=lambda: True)
    assert not token.exists()


def test_desconectar_apaga_o_token(token):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")

    assert desconectar(token) is True
    assert not token.exists()
    assert desconectar(token) is False


@pytest.mark.parametrize(
    "falha",
    [
        TransportError("sem internet"),
        ConnectionResetError("caiu"),
        RefreshError("o servidor do Google caiu", retryable=True),
    ],
    ids=["sem-internet", "queda", "google-fora-do-ar"],
)
def test_sem_internet_na_renovacao_o_token_e_mantido(token, falha):
    token.parent.mkdir()
    token.write_text("{}", encoding="utf-8")

    def renovar(credenciais):
        raise falha

    with pytest.raises(FalhaNaAutorizacao, match="não respondeu"):
        carregar_credenciais(
            token, ler=lambda caminho: CredenciaisFalsas(valid=False), renovar=renovar
        )
    assert token.exists()


def test_sem_internet_o_navegador_nem_abre(token, client_secret):
    with pytest.raises(FalhaNaAutorizacao, match="Confira a conexão"):
        conectar(client_secret, token, autorizar=pytest.fail, ha_internet=lambda: False)


def test_token_que_nao_pode_ser_salvo_vira_mensagem_clara(tmp_path):
    ocupado = tmp_path / "arquivo-no-lugar-da-pasta"
    ocupado.write_text("", encoding="utf-8")

    with pytest.raises(FalhaNaAutorizacao, match="não foi possível salvar a autorização"):
        drive.salvar_token(CredenciaisFalsas(), ocupado / "token.json")


def servico_que_falha(erro):
    def falhar(**_):
        raise erro

    return SimpleNamespace(about=lambda: SimpleNamespace(get=falhar))


@pytest.mark.parametrize("erro", [ServerNotFoundError("dns"), TransportError("rede")])
def test_conta_sem_internet_vira_mensagem_clara(monkeypatch, erro):
    monkeypatch.setattr(drive, "servico_do_drive", lambda credenciais: servico_que_falha(erro))

    with pytest.raises(FalhaNaAutorizacao, match="Confira a conexão"):
        drive.conta_conectada("credenciais")


def test_conta_com_autorizacao_revogada_esquece_o_token(monkeypatch):
    salvo = drive.caminho_do_token()
    salvo.parent.mkdir(parents=True, exist_ok=True)
    salvo.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        drive,
        "servico_do_drive",
        lambda credenciais: servico_que_falha(RefreshError("invalid_grant")),
    )

    with pytest.raises(FalhaNaAutorizacao, match="expirou ou foi revogada. Conecte de novo"):
        drive.conta_conectada("credenciais")
    assert not salvo.exists()


def test_comando_conectar_mostra_a_conta(monkeypatch, capsys):
    monkeypatch.setattr(drive, "conectar", lambda: "credenciais")
    monkeypatch.setattr(drive, "conta_conectada", lambda credenciais: "aluno@exemplo.com")

    assert drive.main(["conectar"]) == 0

    assert capsys.readouterr().out == "Conectado ao Google Drive de aluno@exemplo.com.\n"


def test_comando_conectar_com_falha_mostra_erro(monkeypatch, capsys):
    def falhar():
        raise FalhaNaAutorizacao("a autorização não foi concluída: access_denied")

    monkeypatch.setattr(drive, "conectar", falhar)

    assert drive.main(["conectar"]) == 1

    assert capsys.readouterr().err.startswith("transcritor-drive: erro: a autorização")


def test_comando_desconectar(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert drive.main(["desconectar"]) == 0

    assert "Não havia autorização" in capsys.readouterr().out
