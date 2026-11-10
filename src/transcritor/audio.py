"""Conferência do arquivo de áudio antes da transcrição."""

from pathlib import Path

import av


class AudioInvalido(ValueError):
    """O arquivo recebido não pode ser usado como áudio de uma aula."""


def conferir_audio(caminho: Path) -> float | None:
    """Confere que o arquivo tem áudio legível e devolve a duração em segundos.

    A conferência olha o conteúdo, não a extensão: o PyAV traz o ffmpeg embutido
    e lê MP3, M4A, WAV, OGG, FLAC e também vídeos, como a gravação de uma aula
    em MP4. A duração vem vazia quando o arquivo não a informa.

    Fazer isto antes de carregar o modelo dá o erro em um instante, e não depois
    de um download de centenas de MB.
    """
    if not caminho.is_file():
        raise AudioInvalido(f"arquivo não encontrado: {caminho}")

    try:
        with av.open(str(caminho)) as conteudo:
            tem_audio = bool(conteudo.streams.audio)
            duracao = conteudo.duration
    except av.error.FFmpegError as erro:
        raise AudioInvalido(
            f"o arquivo não é um áudio ou vídeo que o programa consiga ler: {caminho}"
        ) from erro

    if not tem_audio:
        raise AudioInvalido(f"o arquivo não tem áudio: {caminho}")

    # O PyAV informa a duração em microssegundos.
    return None if duracao is None else duracao / av.time_base
