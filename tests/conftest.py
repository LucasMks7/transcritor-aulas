import math
from types import SimpleNamespace

import av
import pytest

# Formato do arquivo -> codificador de áudio. São os formatos em que uma aula
# costuma chegar: gravador do celular (M4A), WhatsApp (OGG/Opus), MP3, WAV e FLAC.
CODIFICADORES = {
    ".wav": "pcm_s16le",
    ".mp3": "libmp3lame",
    ".m4a": "aac",
    ".ogg": "libopus",
    ".flac": "flac",
}
TAXA_DE_AMOSTRAGEM = 48_000


class ModeloFalso:
    """Imita o WhisperModel: devolve segmentos prontos, sem carregar modelo algum."""

    def __init__(self, textos, duracao, falha=None):
        self.textos = textos
        self.duracao = duracao
        self.falha = falha
        self.chamadas = []

    def transcribe(self, audio, **opcoes):
        self.chamadas.append((audio, opcoes))
        return self._segmentos(), SimpleNamespace(duration=self.duracao)

    def _segmentos(self):
        """Um gerador, como o do faster-whisper: nada acontece até ser percorrido."""
        fatia = self.duracao / max(len(self.textos), 1)
        for i, texto in enumerate(self.textos):
            yield SimpleNamespace(start=i * fatia, end=(i + 1) * fatia, text=texto)
        # Imita a transcrição que quebra no meio, depois de entregar alguns trechos.
        if self.falha is not None:
            raise self.falha


@pytest.fixture
def criar_modelo():
    def criar(*textos, duracao=10.0, falha=None):
        return ModeloFalso(textos, duracao, falha)

    return criar


def _tom(segundos: float) -> av.AudioFrame:
    """Um tom de 440 Hz, mono, em amostras de 16 bits."""
    quantidade = int(segundos * TAXA_DE_AMOSTRAGEM)
    amostras = bytearray()
    for i in range(quantidade):
        valor = int(12_000 * math.sin(2 * math.pi * 440 * i / TAXA_DE_AMOSTRAGEM))
        amostras += valor.to_bytes(2, "little", signed=True)

    quadro = av.AudioFrame(format="s16", layout="mono", samples=quantidade)
    quadro.sample_rate = TAXA_DE_AMOSTRAGEM
    quadro.planes[0].update(bytes(amostras))
    return quadro


@pytest.fixture
def criar_audio(tmp_path):
    """Gera um áudio de verdade no formato da extensão pedida.

    O repositório não guarda áudios, então cada teste cria o seu com o mesmo
    PyAV que o programa usa para ler.
    """

    def criar(nome: str, segundos: float = 1.0):
        caminho = tmp_path / nome
        with av.open(str(caminho), "w") as conteudo:
            faixa = conteudo.add_stream(
                CODIFICADORES[caminho.suffix], rate=TAXA_DE_AMOSTRAGEM, layout="mono"
            )
            # Cada codificador quer as amostras em um formato e em blocos de um
            # tamanho; o reamostrador entrega os dois do jeito pedido.
            reamostrador = av.AudioResampler(
                format=faixa.format,
                layout="mono",
                rate=TAXA_DE_AMOSTRAGEM,
                frame_size=faixa.codec_context.frame_size or None,
            )
            for quadro in reamostrador.resample(_tom(segundos)):
                conteudo.mux(faixa.encode(quadro))
            for quadro in reamostrador.resample(None):
                conteudo.mux(faixa.encode(quadro))
            conteudo.mux(faixa.encode(None))
        return caminho

    return criar
