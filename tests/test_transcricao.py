from pathlib import Path

import pytest

from transcritor.transcricao import (
    FalhaNaTranscricao,
    Segmento,
    Transcricao,
    carregar_modelo,
    transcrever,
)

AUDIO = Path("aula.mp3")


def test_transcrever_devolve_os_segmentos_sem_espacos_nas_pontas(criar_modelo):
    modelo = criar_modelo(" Bom dia, turma.", " Hoje o assunto é outro.", duracao=8.0)

    transcricao = transcrever(AUDIO, modelo)

    assert transcricao == Transcricao(
        (
            Segmento(0.0, 4.0, "Bom dia, turma."),
            Segmento(4.0, 8.0, "Hoje o assunto é outro."),
        ),
        duracao=8.0,
    )


def test_transcrever_pede_portugues_para_o_modelo(criar_modelo):
    modelo = criar_modelo("Bom dia.")

    transcrever(AUDIO, modelo)

    audio, opcoes = modelo.chamadas[0]
    assert audio == "aula.mp3"
    assert opcoes["language"] == "pt"


def test_texto_traz_um_segmento_por_linha(criar_modelo):
    transcricao = transcrever(AUDIO, criar_modelo("Bom dia, turma.", "Vamos começar."))

    assert transcricao.texto == "Bom dia, turma.\nVamos começar."


def test_audio_sem_fala_vira_transcricao_vazia(criar_modelo):
    transcricao = transcrever(AUDIO, criar_modelo(duracao=3.0))

    assert transcricao.segmentos == ()
    assert transcricao.texto == ""


def test_carregar_modelo_usa_o_processador_com_int8(monkeypatch):
    import faster_whisper

    pedidos = []

    def criar(nome, **opcoes):
        pedidos.append((nome, opcoes))
        return "modelo carregado"

    monkeypatch.setattr(faster_whisper, "WhisperModel", criar)

    assert carregar_modelo("small") == "modelo carregado"
    assert pedidos == [("small", {"device": "cpu", "compute_type": "int8"})]


def test_falha_ao_carregar_o_modelo_vira_mensagem_clara(monkeypatch):
    import faster_whisper

    def falhar(nome, **opcoes):
        raise OSError("sem conexão")

    monkeypatch.setattr(faster_whisper, "WhisperModel", falhar)

    with pytest.raises(FalhaNaTranscricao, match="modelo small.*sem conexão"):
        carregar_modelo("small")
