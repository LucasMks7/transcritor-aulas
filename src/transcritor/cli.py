"""Interface de linha de comando."""

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from transcritor import __version__
from transcritor.transcricao import (
    MODELO_PADRAO,
    MODELOS,
    FalhaNaTranscricao,
    carregar_modelo,
    transcrever,
)

CODIGO_FALHA_NA_TRANSCRICAO = 1
# Mesmo código que o argparse usa para erros de uso.
CODIGO_ENTRADA_INVALIDA = 2
# Convenção dos terminais para programa interrompido com Ctrl+C.
CODIGO_CANCELADO = 130

# O argparse só escreve em inglês. Mensagens fora desta lista seguem como estão.
TRADUCOES_DO_ARGPARSE = (
    (r"the following arguments are required: (.+)", r"falta informar: \1"),
    (
        r"argument (.+): invalid choice: (.+) \(choose from (.+)\)",
        r"valor inválido para \1: \2. Opções: \3",
    ),
    (r"argument (.+): expected one argument", r"a opção \1 precisa de um valor"),
    (r"unrecognized arguments: (.+)", r"opção desconhecida: \1"),
)


class ParserEmPortugues(argparse.ArgumentParser):
    """Escreve os erros de uso no mesmo formato e idioma dos demais erros."""

    def error(self, message: str):
        for padrao, traducao in TRADUCOES_DO_ARGPARSE:
            message = re.sub(padrao, traducao, message)
        self.exit(
            CODIGO_ENTRADA_INVALIDA,
            f"{self.prog}: erro: {message}\nUse {self.prog} --help para ver as opções.\n",
        )


def usar_utf8_na_saida() -> None:
    """Mantém os acentos corretos quando a saída é redirecionada no Windows."""
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8")


def criar_parser() -> argparse.ArgumentParser:
    parser = ParserEmPortugues(
        prog="transcrever",
        description="Transcreve um arquivo de áudio em português, sem enviá-lo "
        "para fora do PC.",
    )
    parser.add_argument("audio", type=Path, help="arquivo de áudio a transcrever")
    parser.add_argument(
        "--saida",
        type=Path,
        help="arquivo de texto a criar (padrão: o nome do áudio, com .txt)",
    )
    parser.add_argument(
        "--modelo",
        choices=MODELOS,
        default=MODELO_PADRAO,
        help="modelo do Whisper; os maiores erram menos e demoram mais "
        "(padrão: %(default)s)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    usar_utf8_na_saida()
    argumentos = criar_parser().parse_args(argv)

    audio = argumentos.audio
    if not audio.is_file():
        print(f"transcrever: erro: arquivo não encontrado: {audio}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA
    saida = argumentos.saida or audio.with_suffix(".txt")

    try:
        print(f"Carregando o modelo {argumentos.modelo}...", file=sys.stderr)
        modelo = carregar_modelo(argumentos.modelo)
        print("Transcrevendo... Isso pode levar vários minutos.", file=sys.stderr)
        transcricao = transcrever(audio, modelo)
    except FalhaNaTranscricao as erro:
        print(f"transcrever: erro: {erro}", file=sys.stderr)
        return CODIGO_FALHA_NA_TRANSCRICAO
    except KeyboardInterrupt:
        print("Transcrição cancelada.", file=sys.stderr)
        return CODIGO_CANCELADO

    try:
        saida.write_text(transcricao.texto + "\n", encoding="utf-8")
    except OSError as erro:
        print(
            f"transcrever: erro: não foi possível gravar {saida}: {erro.strerror}",
            file=sys.stderr,
        )
        return CODIGO_FALHA_NA_TRANSCRICAO

    print(f"Transcrição salva em: {saida}")
    return 0
