"""Transcrição de áudio com o faster-whisper, feita inteira no próprio PC."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

# Escolhidos na comparação da sessão 11; veja docs/comparacao-modelos.md.
MODELOS = ("tiny", "base", "small", "medium", "large-v3-turbo")
MODELO_PADRAO = "small"
IDIOMA = "pt"

# O Whisper trabalha com áudio a 16 kHz, em um canal só.
TAXA_DE_AMOSTRAGEM = 16_000

# O faster-whisper calcula o espectrograma de tudo o que recebe de uma vez, e a
# memória cresce com a duração: medimos 7 GB em um áudio de 2 horas. Entregando
# blocos de 10 minutos, o gasto deixa de depender do tamanho da aula.
SEGUNDOS_POR_BLOCO = 600
# O corte de cada bloco é procurado neste trecho final dele, no ponto mais
# silencioso, para não partir uma palavra ao meio. Em 30 segundos de fala
# sempre há alguma pausa entre frases.
SEGUNDOS_DE_BUSCA_DO_CORTE = 30
# Tamanho da janela usada para medir o volume: mais curta que uma pausa de
# respiração e mais longa que o intervalo entre duas sílabas.
SEGUNDOS_DA_JANELA_DE_VOLUME = 0.2


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

    def transcribe(self, audio: np.ndarray, **opcoes): ...


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


def ler_amostras(audio: Path) -> np.ndarray:
    """Decodifica o arquivo inteiro para amostras a 16 kHz, em um canal."""
    from faster_whisper.audio import decode_audio

    return decode_audio(str(audio), sampling_rate=TAXA_DE_AMOSTRAGEM)


def ponto_mais_silencioso(amostras: np.ndarray, taxa: int = TAXA_DE_AMOSTRAGEM) -> int:
    """Devolve a posição do meio da janela de menor volume do trecho."""
    janela = max(int(SEGUNDOS_DA_JANELA_DE_VOLUME * taxa), 1)
    quantidade = len(amostras) // janela
    if quantidade == 0:
        return len(amostras)

    # Uma linha por janela; o volume de cada uma é a média dos quadrados.
    janelas = amostras[: quantidade * janela].reshape(quantidade, janela)
    volumes = np.mean(np.square(janelas, dtype=np.float64), axis=1)
    return int(np.argmin(volumes)) * janela + janela // 2


def dividir_em_blocos(
    amostras: np.ndarray,
    taxa: int = TAXA_DE_AMOSTRAGEM,
    segundos_por_bloco: float = SEGUNDOS_POR_BLOCO,
    segundos_de_busca: float = SEGUNDOS_DE_BUSCA_DO_CORTE,
) -> list[tuple[int, int]]:
    """Divide o áudio em blocos de até segundos_por_bloco, cortando nas pausas.

    Devolve as posições (início, fim) de cada bloco, sem sobras nem sobreposição.
    """
    tamanho = int(segundos_por_bloco * taxa)
    busca = min(int(segundos_de_busca * taxa), tamanho // 2)

    blocos = []
    inicio = 0
    while len(amostras) - inicio > tamanho:
        limite = inicio + tamanho
        # O corte fica dentro do trecho final do bloco, onde houver menos som.
        fim = limite - busca + ponto_mais_silencioso(amostras[limite - busca : limite], taxa)
        blocos.append((inicio, fim))
        inicio = fim
    if inicio < len(amostras):
        blocos.append((inicio, len(amostras)))
    return blocos


def transcrever(
    audio: Path,
    modelo: Modelo,
    ao_avancar: Callable[[Segmento, float], None] | None = None,
    segundos_por_bloco: float = SEGUNDOS_POR_BLOCO,
) -> Transcricao:
    """Transcreve o áudio inteiro, em português.

    A cada trecho pronto, chama ao_avancar com o segmento e a duração total do
    áudio. Em uma aula longa, é assim que a interface mostra o andamento e
    guarda o texto aos poucos, sem esperar o fim.
    """
    prontos = []
    try:
        amostras = ler_amostras(audio)
        duracao = len(amostras) / TAXA_DE_AMOSTRAGEM

        blocos = dividir_em_blocos(amostras, segundos_por_bloco=segundos_por_bloco)
        for inicio, fim in blocos:
            segmentos, _ = modelo.transcribe(
                amostras[inicio:fim],
                # Informar o idioma evita que o modelo o adivinhe pelos primeiros
                # 30 segundos, que em uma aula podem ser só barulho de sala.
                language=IDIOMA,
                # Pula os trechos sem fala. Além de poupar tempo, evita um defeito
                # conhecido do Whisper: em silêncio longo, ele repete ou inventa
                # frases.
                vad_filter=True,
            )
            # Os tempos vêm contados a partir do começo do bloco.
            deslocamento = inicio / TAXA_DE_AMOSTRAGEM
            # O faster-whisper devolve um gerador: a transcrição acontece neste
            # laço, um trecho por vez.
            for segmento in segmentos:
                pronto = Segmento(
                    segmento.start + deslocamento,
                    segmento.end + deslocamento,
                    segmento.text.strip(),
                )
                prontos.append(pronto)
                if ao_avancar is not None:
                    ao_avancar(pronto, duracao)
    # O CTranslate2 avisa os problemas dele, como falta de memória, com RuntimeError.
    except (RuntimeError, MemoryError) as erro:
        raise FalhaNaTranscricao(
            f"A transcrição parou depois de {len(prontos)} trechos: {erro}"
        ) from erro

    return Transcricao(tuple(prontos), duracao)
