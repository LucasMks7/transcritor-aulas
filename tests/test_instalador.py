"""A conferência da pasta que vai no instalador. Montá-lo de verdade fica para o CI."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "montar_instalador.py"


@pytest.fixture
def montador():
    # scripts/ não é um pacote, então o módulo é carregado pelo caminho.
    especificacao = importlib.util.spec_from_file_location("montar_instalador", SCRIPT)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def programa(montador, tmp_path):
    (tmp_path / "_internal").mkdir()
    for nome in montador.EXECUTAVEIS:
        (tmp_path / nome).write_bytes(b"MZ")
    return tmp_path


def test_pasta_completa_e_aceita(montador, programa):
    assert montador.conferir(programa) < 1


def test_executavel_que_faltou_e_recusado(montador, programa):
    (programa / "transcrever.exe").unlink()

    with pytest.raises(montador.FalhaNaMontagem, match="transcrever.exe"):
        montador.conferir(programa)


@pytest.mark.parametrize(
    "nome",
    ["token.json", "client_secret.json", "client_secret_123.json", ".env", "aula.mp3", "model.bin"],
)
def test_segredos_audios_e_modelos_sao_recusados(montador, programa, nome):
    (programa / "_internal" / nome).write_text("segredo", encoding="utf-8")

    with pytest.raises(montador.FalhaNaMontagem, match="não pode ir no instalador"):
        montador.conferir(programa)


def test_pasta_grande_demais_e_recusada(montador, programa, monkeypatch):
    monkeypatch.setattr(montador, "TAMANHO_MAXIMO_MB", 0)

    with pytest.raises(montador.FalhaNaMontagem, match="o limite é 0 MB"):
        montador.conferir(programa)


def test_sem_o_inno_setup_explica_como_instalar(montador, monkeypatch, tmp_path):
    for variavel in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        monkeypatch.setenv(variavel, str(tmp_path))
    monkeypatch.setattr(montador.shutil, "which", lambda nome: None)

    with pytest.raises(montador.FalhaNaMontagem, match="winget install"):
        montador.montar(tmp_path)
