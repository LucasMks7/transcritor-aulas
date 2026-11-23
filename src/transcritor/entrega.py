"""Entrega dos arquivos nas pastas escolhidas do Drive.

É a mesma para transcritor-drive enviar, transcrever --enviar e a janela: cada
um só decide como mostrar o andamento e o resultado.
"""

import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

from transcritor import envio, pastas


class Entrega(NamedTuple):
    """O que aconteceu com um arquivo. Exatamente um entre enviado e erro é preenchido."""

    arquivo: Path
    pasta: str
    enviado: envio.ArquivoNoDrive | None = None
    erro: str | None = None


def tipo_do_arquivo(arquivo: Path) -> str:
    """A chave de pastas.DESTINOS: o PDF tem a própria pasta, e o resto é áudio."""
    return "pdf" if arquivo.suffix.lower() == ".pdf" else "audio"


def entregar(
    servico,
    arquivos: Iterable[Path],
    nomes_das_pastas: dict[str, str],
    ao_progredir: Callable[[Path, int, int], None] = lambda arquivo, enviado, total: None,
    ao_repetir: Callable[[int, float], None] = lambda tentativa, espera: None,
    esperar: Callable[[float], object] = time.sleep,
) -> Iterator[Entrega]:
    """Envia um arquivo por vez; a falha de um não impede o envio dos outros."""
    destinos: dict[str, pastas.Pasta] = {}
    for arquivo in arquivos:
        tipo = tipo_do_arquivo(arquivo)
        nome = nomes_das_pastas[tipo]
        try:
            if tipo not in destinos:
                destinos[tipo] = pastas.obter_ou_criar(servico, nome)
            enviado = envio.enviar_arquivo(
                servico,
                arquivo,
                destinos[tipo].id,
                # arquivo=arquivo prende o valor desta volta do laço.
                lambda feito, total, arquivo=arquivo: ao_progredir(arquivo, feito, total),
                ao_repetir,
                esperar,
            )
        except pastas.FalhaNoDrive as erro:
            yield Entrega(arquivo, nome, erro=str(erro))
        else:
            yield Entrega(arquivo, nome, enviado=enviado)


def descrever(entrega: Entrega) -> str:
    if entrega.enviado is None:
        return f"erro: {entrega.erro}"
    situacao = "já estava em" if entrega.enviado.ja_estava_la else "enviado para"
    return f"{entrega.arquivo.name} {situacao} {entrega.pasta}: {entrega.enviado.link}"
