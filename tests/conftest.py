from types import SimpleNamespace

import pytest


class ModeloFalso:
    """Imita o WhisperModel: devolve segmentos prontos, sem carregar modelo algum."""

    def __init__(self, textos, duracao):
        self.textos = textos
        self.duracao = duracao
        self.chamadas = []

    def transcribe(self, audio, **opcoes):
        self.chamadas.append((audio, opcoes))
        fatia = self.duracao / max(len(self.textos), 1)
        # Um gerador, como o do faster-whisper: nada acontece até ser percorrido.
        segmentos = (
            SimpleNamespace(start=i * fatia, end=(i + 1) * fatia, text=texto)
            for i, texto in enumerate(self.textos)
        )
        return segmentos, SimpleNamespace(duration=self.duracao)


@pytest.fixture
def criar_modelo():
    def criar(*textos, duracao=10.0):
        return ModeloFalso(textos, duracao)

    return criar
