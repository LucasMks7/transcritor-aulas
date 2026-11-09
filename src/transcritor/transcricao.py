"""Transcrição de áudio com o faster-whisper, feita inteira no próprio PC."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Escolhidos na comparação da sessão 11; veja docs/comparacao-modelos.md.
MODELOS = ("tiny", "base", "small", "medium", "large-v3-turbo")
MODELO_PADRAO = "small"
IDIOMA = "pt"


class FalhaNaTranscricao(RuntimeError):
    """O modelo não pôde ser carregado ou o áudio não pôde ser transcrito."""


@dataclass(frozen=True)
class Segmento:
    """Um trecho de fala, com o início e o fim em segundos."""

    inicio: float
    fim: float
    texto: str


@dataclass(frozen=True)
class Transcricao:
    segmentos: tuple[Segmento, ...]
    duracao: float

    @property
    def texto(self) -> str:
        """Um segmento por linha: o Whisper costuma cortar no fim das frases."""
        return "\n".join(segmento.texto for segmento in self.segmentos)


class Modelo(Protocol):
    """O que este módulo usa do WhisperModel. Nos testes, um dublê ocupa o lugar."""

    def transcribe(self, audio: str, **opcoes): ...


def carregar_modelo(nome: str = MODELO_PADRAO) -> Modelo:
    """Carrega o modelo, baixando-o na primeira vez, ou levanta FalhaNaTranscricao."""
    # Importado aqui porque é pesado: o --help e os testes não precisam esperar por ele.
    from faster_whisper import WhisperModel

    try:
        # int8 é o tipo de cálculo mais rápido no processador.
        return WhisperModel(nome, device="cpu", compute_type="int8")
    except Exception as erro:
        # A biblioteca levanta tipos diferentes para falta de internet, disco
        # cheio e arquivo corrompido; para quem usa, a orientação é a mesma.
        raise FalhaNaTranscricao(
            f"Não foi possível carregar o modelo {nome}. Na primeira vez, ele é "
            f"baixado da internet e precisa de espaço em disco. Detalhe: {erro}"
        ) from erro


def transcrever(audio: Path, modelo: Modelo) -> Transcricao:
    """Transcreve o áudio inteiro, em português."""
    # Informar o idioma evita que o modelo o adivinhe pelos primeiros 30 segundos,
    # que em uma aula podem ser só barulho de sala.
    segmentos, informacoes = modelo.transcribe(str(audio), language=IDIOMA)
    return Transcricao(
        # O faster-whisper devolve um gerador: a transcrição acontece aqui.
        tuple(
            Segmento(segmento.start, segmento.end, segmento.text.strip())
            for segmento in segmentos
        ),
        informacoes.duration,
    )
