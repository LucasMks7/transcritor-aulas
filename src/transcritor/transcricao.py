"""Transcrição de áudio com o faster-whisper, feita inteira no próprio PC."""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

MODELOS = ("tiny", "base", "small", "medium", "large-v3-turbo")
IDIOMA = "pt"
# Frase pontuada que o modelo recebe como se já tivesse sido dita antes do áudio.
EXEMPLO_DE_ESTILO = "Bom dia, turma. Hoje, vamos continuar a aula de onde paramos."

# "auto" usa a placa de vídeo quando ela funciona e o processador quando não.
DISPOSITIVOS = ("auto", "cuda", "cpu")
DISPOSITIVO_PADRAO = "auto"
# Na placa de vídeo, o large-v3-turbo é quase tão rápido quanto o small e erra
# bem menos. No processador, ele fica mais lento que o tempo real, e o small
# continua o melhor equilíbrio. Veja docs/comparacao-modelos.md.
MODELO_PADRAO = {"cuda": "large-v3-turbo", "cpu": "small"}
# int8 foi o mais rápido nos dois. Na GTX 1050 Ti, o float32 do large-v3-turbo
# não cabe bem nos 4 GB e fica cinco vezes mais lento.
TIPOS_DE_CALCULO = {"cpu": "int8", "cuda": "int8"}

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


def formatar_tempo(segundos: float) -> str:
    """Escreve 3725 como "1:02:05" e 125 como "02:05"."""
    minutos, segundos = divmod(int(segundos), 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas}:{minutos:02}:{segundos:02}"
    return f"{minutos:02}:{segundos:02}"


class Modelo(Protocol):
    """O que este módulo usa do WhisperModel. Nos testes, um dublê ocupa o lugar."""

    def transcribe(self, audio: np.ndarray, **opcoes): ...


@dataclass(frozen=True)
class ModeloCarregado:
    modelo: Modelo
    nome: str
    # "cuda" (placa de vídeo da NVIDIA) ou "cpu" (processador).
    dispositivo: str
    # Por que a placa de vídeo não foi usada, quando o modo automático desistiu dela.
    motivo_sem_gpu: str | None = None


def _criar_whisper(nome: str, dispositivo: str) -> Modelo:
    # Importado aqui porque é pesado: o --help e os testes não precisam esperar por ele.
    from faster_whisper import WhisperModel

    return WhisperModel(nome, device=dispositivo, compute_type=TIPOS_DE_CALCULO[dispositivo])


def _contar_gpus() -> int:
    """Quantas placas da NVIDIA o CTranslate2 enxerga; zero se não houver driver."""
    preparar_bibliotecas_cuda()
    import ctranslate2

    return ctranslate2.get_cuda_device_count()


def preparar_bibliotecas_cuda() -> None:
    """Mostra ao Windows onde estão o cuBLAS e o cuDNN instalados pelo pip.

    O CTranslate2 só procura essas bibliotecas na hora de calcular, e o Windows
    não olha dentro do site-packages sozinho. Sem o extra [gpu], não há o que
    preparar, e a transcrição segue no processador.
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    for raiz in nvidia.__path__:
        for biblioteca in ("cublas", "cudnn"):
            pasta = str(Path(raiz) / biblioteca / "bin")
            # Tem de ser o PATH: o CTranslate2 carrega as DLLs com a busca
            # clássica do Windows, e os.add_dll_directory não funcionou nos testes.
            if Path(pasta).is_dir() and pasta not in os.environ["PATH"].split(os.pathsep):
                os.environ["PATH"] = pasta + os.pathsep + os.environ["PATH"]


def testar_modelo(modelo: Modelo) -> None:
    """Transcreve um segundo de silêncio para exercitar todas as bibliotecas.

    Na GPU, o modelo carrega mesmo sem o cuBLAS e o cuDNN, e a falta deles só
    aparece no primeiro cálculo. Descobrir isso agora permite voltar para o
    processador antes de começar a aula, e não com ela pela metade.
    """
    silencio = np.zeros(TAXA_DE_AMOSTRAGEM, dtype=np.float32)
    segmentos, _ = modelo.transcribe(silencio, language=IDIOMA)
    # O gerador precisa ser percorrido para o cálculo acontecer.
    list(segmentos)


def carregar_modelo(
    nome: str | None = None,
    dispositivo: str = DISPOSITIVO_PADRAO,
    criar: Callable[[str, str], Modelo] = _criar_whisper,
    contar_gpus: Callable[[], int] = _contar_gpus,
) -> ModeloCarregado:
    """Carrega o modelo no dispositivo pedido, ou levanta FalhaNaTranscricao.

    No modo "auto", usa a placa de vídeo se ela existir e passar no teste, e o
    processador nos outros casos. Pedindo "cuda" explicitamente, uma falha na
    placa vira erro, em vez de virar sem aviso uma transcrição dez vezes mais
    lenta. Sem nome, o modelo é o padrão do dispositivo que for usado.

    criar e contar_gpus existem para os testes trocarem a biblioteca por dublês.
    """
    motivo_sem_gpu = None
    if dispositivo != "cpu":
        nome_na_gpu = nome or MODELO_PADRAO["cuda"]
        try:
            modelo = _carregar_na_gpu(nome_na_gpu, criar, contar_gpus)
            return ModeloCarregado(modelo, nome_na_gpu, "cuda")
        except _SemGpu as erro:
            if dispositivo == "cuda":
                raise FalhaNaTranscricao(
                    f"Não foi possível usar a placa de vídeo: {erro}."
                ) from erro
            motivo_sem_gpu = str(erro)

    nome_na_cpu = nome or MODELO_PADRAO["cpu"]
    modelo = _carregar(nome_na_cpu, "cpu", criar)
    return ModeloCarregado(modelo, nome_na_cpu, "cpu", motivo_sem_gpu)


class _SemGpu(Exception):
    """A placa de vídeo não existe ou não conseguiu transcrever."""


def _carregar_na_gpu(
    nome: str, criar: Callable[[str, str], Modelo], contar_gpus: Callable[[], int]
) -> Modelo:
    try:
        quantidade = contar_gpus()
    except Exception as erro:
        raise _SemGpu(f"o CTranslate2 não conseguiu procurar a placa ({erro})") from erro
    if quantidade == 0:
        raise _SemGpu("nenhuma placa de vídeo da NVIDIA foi encontrada")

    try:
        modelo = criar(nome, "cuda")
        testar_modelo(modelo)
    # O CTranslate2 avisa driver antigo, DLL ausente e falta de memória da placa
    # com RuntimeError. Falta de internet ou de disco chega como OSError e segue
    # adiante: no processador, o mesmo download falharia de novo.
    except RuntimeError as erro:
        motivo = f"a placa foi encontrada, mas não conseguiu transcrever ({erro})"
        if "cublas" in str(erro).lower() or "cudnn" in str(erro).lower():
            motivo += '. Faltam as bibliotecas da NVIDIA: instale com pip install ".[gpu]"'
        raise _SemGpu(motivo) from erro
    except Exception as erro:
        raise _erro_ao_carregar(nome, erro) from erro
    return modelo


def _carregar(nome: str, dispositivo: str, criar: Callable[[str, str], Modelo]) -> Modelo:
    try:
        return criar(nome, dispositivo)
    except Exception as erro:
        raise _erro_ao_carregar(nome, erro) from erro


def _erro_ao_carregar(nome: str, erro: Exception) -> FalhaNaTranscricao:
    # A biblioteca levanta tipos diferentes para falta de internet, disco cheio
    # e arquivo corrompido; para quem usa, a orientação é a mesma.
    return FalhaNaTranscricao(
        f"Não foi possível carregar o modelo {nome}. Na primeira vez, ele é "
        f"baixado da internet e precisa de espaço em disco. Detalhe: {erro}"
    )


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
                # O Whisper imita o estilo do texto anterior. Sem um exemplo, o
                # large-v3-turbo às vezes começa sem pontuação nem maiúsculas e
                # segue assim até o fim, o que deixa o PDF ilegível. Vale para
                # cada bloco, que começa sem texto anterior.
                initial_prompt=EXEMPLO_DE_ESTILO,
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
