import os
import subprocess
import sys

import pytest

from transcritor import __version__, cli
from transcritor.cli import main
from transcritor.transcricao import MODELO_PADRAO, FalhaNaTranscricao


@pytest.fixture
def audio(tmp_path):
    """Um arquivo que existe; o conteúdo não importa, porque o modelo é um dublê."""
    arquivo = tmp_path / "aula.mp3"
    arquivo.touch()
    return arquivo


@pytest.fixture
def modelos_pedidos(monkeypatch, criar_modelo):
    """Troca o carregamento do modelo por um dublê e devolve os nomes pedidos."""
    pedidos = []

    def carregar(nome):
        pedidos.append(nome)
        return criar_modelo(" Bom dia, turma.", " Vamos começar.")

    monkeypatch.setattr(cli, "carregar_modelo", carregar)
    return pedidos


def test_version_mostra_a_versao_do_pacote(capsys):
    with pytest.raises(SystemExit) as saida:
        main(["--version"])

    assert saida.value.code == 0
    assert capsys.readouterr().out.strip() == f"transcrever {__version__}"


def test_transcreve_para_um_txt_ao_lado_do_audio(capsys, audio, modelos_pedidos):
    assert main([str(audio)]) == 0

    saida = audio.with_suffix(".txt")
    assert saida.read_text(encoding="utf-8") == "Bom dia, turma.\nVamos começar.\n"
    assert modelos_pedidos == [MODELO_PADRAO]
    capturado = capsys.readouterr()
    assert capturado.out == f"Transcrição salva em: {saida}\n"
    assert "erro" not in capturado.err


def test_saida_escolhida_recebe_o_texto(audio, modelos_pedidos, tmp_path):
    saida = tmp_path / "anotações.txt"

    assert main([str(audio), "--saida", str(saida)]) == 0

    assert saida.read_text(encoding="utf-8").startswith("Bom dia, turma.")
    assert not audio.with_suffix(".txt").exists()


def test_modelo_escolhido_e_o_carregado(audio, modelos_pedidos):
    assert main([str(audio), "--modelo", "tiny"]) == 0

    assert modelos_pedidos == ["tiny"]


def test_audio_inexistente_mostra_erro_sem_carregar_o_modelo(
    capsys, modelos_pedidos, tmp_path
):
    assert main([str(tmp_path / "sumiu.mp3")]) == 2

    capturado = capsys.readouterr()
    assert capturado.err.startswith("transcrever: erro: arquivo não encontrado")
    assert capturado.out == ""
    assert modelos_pedidos == []


def test_pasta_no_lugar_do_audio_e_recusada(capsys, modelos_pedidos, tmp_path):
    assert main([str(tmp_path)]) == 2

    assert "arquivo não encontrado" in capsys.readouterr().err
    assert modelos_pedidos == []


def test_falha_na_transcricao_mostra_erro_e_termina_com_codigo_1(
    capsys, audio, monkeypatch
):
    def falhar(nome):
        raise FalhaNaTranscricao("Não foi possível carregar o modelo small.")

    monkeypatch.setattr(cli, "carregar_modelo", falhar)

    assert main([str(audio)]) == 1

    capturado = capsys.readouterr()
    assert capturado.err.endswith(
        "transcrever: erro: Não foi possível carregar o modelo small.\n"
    )
    assert not audio.with_suffix(".txt").exists()


def test_saida_que_nao_pode_ser_gravada_mostra_erro(capsys, audio, modelos_pedidos, tmp_path):
    saida = tmp_path / "pasta-que-nao-existe" / "aula.txt"

    assert main([str(audio), "--saida", str(saida)]) == 1

    assert "não foi possível gravar" in capsys.readouterr().err


def test_ctrl_c_mostra_cancelamento_e_termina_com_codigo_130(capsys, audio, monkeypatch):
    def interromper(nome):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "carregar_modelo", interromper)

    assert main([str(audio)]) == 130

    assert "cancelada" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argumentos", "esperado"),
    [
        ([], "falta informar: audio"),
        (["aula.mp3", "--modelo", "enorme"], "valor inválido para --modelo"),
        (["aula.mp3", "--saida"], "a opção --saida precisa de um valor"),
        (["aula.mp3", "--xyz"], "opção desconhecida: --xyz"),
    ],
)
def test_erros_de_uso_saem_em_portugues(capsys, argumentos, esperado):
    with pytest.raises(SystemExit) as saida:
        main(argumentos)

    assert saida.value.code == 2
    erro = capsys.readouterr().err
    assert erro.startswith(f"transcrever: erro: {esperado}")
    assert "--help" in erro


def test_saida_redirecionada_usa_utf8():
    ambiente = {**os.environ, "PYTHONUTF8": "0"}
    ambiente.pop("PYTHONIOENCODING", None)

    resultado = subprocess.run(
        [sys.executable, "-c", "from transcritor.cli import main; main(['--help'])"],
        capture_output=True,
        env=ambiente,
    )

    assert resultado.returncode == 0
    assert "Transcreve um arquivo de áudio".encode("utf-8") in resultado.stdout
