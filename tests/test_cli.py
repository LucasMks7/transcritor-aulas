import os
import subprocess
import sys

import pytest

from transcritor import __version__, cli
from transcritor.cli import caminho_parcial, formatar_progresso, formatar_tempo, main
from transcritor.transcricao import MODELO_PADRAO, FalhaNaTranscricao


@pytest.fixture
def audio(criar_audio):
    """Um MP3 de verdade, porque o comando confere o arquivo antes de transcrever."""
    return criar_audio("aula.mp3")


@pytest.fixture
def modelos_pedidos(monkeypatch, criar_modelo):
    """Troca o carregamento do modelo por um dublê e devolve os nomes pedidos."""
    pedidos = []

    def carregar(nome):
        pedidos.append(nome)
        return criar_modelo(" Bom dia, turma.", " Vamos começar.", duracao=1.0)

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
    assert "Áudio de 00:01." in capturado.err
    # O arquivo parcial vira o definitivo; não sobra nada para trás.
    assert not caminho_parcial(saida).exists()


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
    # Nada foi transcrito, então o parcial vazio não fica para trás.
    assert not caminho_parcial(audio.with_suffix(".txt")).exists()


def test_saida_que_nao_pode_ser_gravada_mostra_erro(capsys, audio, modelos_pedidos, tmp_path):
    saida = tmp_path / "pasta-que-nao-existe" / "aula.txt"

    assert main([str(audio), "--saida", str(saida)]) == 2

    assert "não foi possível gravar" in capsys.readouterr().err
    # A pasta é conferida antes de gastar tempo com o modelo.
    assert modelos_pedidos == []


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


@pytest.mark.parametrize("conteudo", [b"", b"isto nao e um audio"])
def test_arquivo_que_nao_e_audio_mostra_erro_sem_carregar_o_modelo(
    capsys, modelos_pedidos, tmp_path, conteudo
):
    falso = tmp_path / "falso.mp3"
    falso.write_bytes(conteudo)

    assert main([str(falso)]) == 2

    erro = capsys.readouterr().err
    assert erro.startswith("transcrever: erro: o arquivo não é um áudio ou vídeo")
    assert "Traceback" not in erro
    assert modelos_pedidos == []
    assert list(tmp_path.iterdir()) == [falso]


def test_saida_igual_ao_audio_e_recusada_para_nao_apagar_a_gravacao(
    capsys, audio, modelos_pedidos
):
    tamanho = audio.stat().st_size

    assert main([str(audio), "--saida", str(audio)]) == 2

    assert "não pode ser o próprio áudio" in capsys.readouterr().err
    assert audio.stat().st_size == tamanho
    assert modelos_pedidos == []


def test_falha_no_meio_de_uma_aula_guarda_o_que_ja_foi_transcrito(
    capsys, audio, monkeypatch, criar_modelo
):
    modelo = criar_modelo(
        " Bom dia, turma.", " Vamos começar.", falha=RuntimeError("faltou memória")
    )
    monkeypatch.setattr(cli, "carregar_modelo", lambda nome: modelo)
    saida = audio.with_suffix(".txt")

    assert main([str(audio)]) == 1

    parcial = caminho_parcial(saida)
    assert parcial.read_text(encoding="utf-8") == "Bom dia, turma.\nVamos começar.\n"
    # O nome definitivo só aparece quando a transcrição está completa.
    assert not saida.exists()
    erro = capsys.readouterr().err
    assert "faltou memória" in erro
    assert f"O trecho já transcrito está em: {parcial}" in erro


def test_ctrl_c_no_meio_de_uma_aula_guarda_o_que_ja_foi_transcrito(
    capsys, audio, monkeypatch, criar_modelo
):
    modelo = criar_modelo(" Bom dia, turma.", falha=KeyboardInterrupt())
    monkeypatch.setattr(cli, "carregar_modelo", lambda nome: modelo)

    assert main([str(audio)]) == 130

    parcial = caminho_parcial(audio.with_suffix(".txt"))
    assert parcial.read_text(encoding="utf-8") == "Bom dia, turma.\n"
    assert f"O trecho já transcrito está em: {parcial}" in capsys.readouterr().err


def test_transcricao_nova_substitui_a_anterior(audio, modelos_pedidos):
    saida = audio.with_suffix(".txt")
    saida.write_text("texto antigo", encoding="utf-8")

    assert main([str(audio)]) == 0

    assert saida.read_text(encoding="utf-8").startswith("Bom dia, turma.")


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(0, "00:00"), (65.9, "01:05"), (3599, "59:59"), (3725, "1:02:05"), (7125, "1:58:45")],
)
def test_formata_o_tempo(segundos, esperado):
    assert formatar_tempo(segundos) == esperado


@pytest.mark.parametrize(
    ("transcrito", "total", "esperado"),
    [
        (750, 6300, "Transcrevendo 12:30 de 1:45:00 (12%)"),
        # O fim do último trecho pode passar da duração informada.
        (181, 180, "Transcrevendo 03:01 de 03:00 (100%)"),
        (5, 0, "Transcrevendo 00:05 de 00:00"),
    ],
)
def test_formata_o_progresso(transcrito, total, esperado):
    assert formatar_progresso(transcrito, total) == esperado


def test_progresso_aparece_no_terminal_na_mesma_linha(
    capsys, audio, modelos_pedidos, monkeypatch
):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    assert main([str(audio)]) == 0

    assert "\rTranscrevendo 00:00 de 00:01 (50%)" in capsys.readouterr().err


def test_progresso_nao_aparece_na_saida_redirecionada(capsys, audio, modelos_pedidos):
    assert main([str(audio)]) == 0

    assert "\rTranscrevendo" not in capsys.readouterr().err
