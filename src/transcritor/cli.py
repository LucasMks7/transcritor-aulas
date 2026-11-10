"""Interface de linha de comando."""

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from transcritor import __version__
from transcritor.audio import AudioInvalido, conferir_audio
from transcritor.transcricao import (
    MODELO_PADRAO,
    MODELOS,
    FalhaNaTranscricao,
    Segmento,
    carregar_modelo,
    transcrever,
)

LARGURA_DA_LINHA = 70

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


def formatar_tempo(segundos: float) -> str:
    """Escreve 3725 como "1:02:05" e 125 como "02:05"."""
    minutos, segundos = divmod(int(segundos), 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas}:{minutos:02}:{segundos:02}"
    return f"{minutos:02}:{segundos:02}"


def formatar_progresso(transcrito: float, total: float) -> str:
    texto = f"Transcrevendo {formatar_tempo(transcrito)} de {formatar_tempo(total)}"
    if total > 0:
        # O fim do último trecho pode passar um pouco da duração informada.
        texto += f" ({min(transcrito / total, 1):.0%})"
    return texto


def mostrar_progresso(transcrito: float, total: float) -> None:
    """Reescreve a mesma linha do terminal; redirecionada, a saída fica sem progresso."""
    # Vai para o stderr para não misturar com o resultado, escrito no stdout.
    if sys.stderr.isatty():
        texto = formatar_progresso(transcrito, total).ljust(LARGURA_DA_LINHA)
        print(f"\r{texto}", end="", file=sys.stderr, flush=True)


def limpar_progresso() -> None:
    if sys.stderr.isatty():
        print("\r" + " " * LARGURA_DA_LINHA + "\r", end="", file=sys.stderr, flush=True)


def caminho_parcial(saida: Path) -> Path:
    """Onde o texto é gravado enquanto a transcrição não termina."""
    return saida.with_name(saida.name + ".parcial")


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
    try:
        duracao = conferir_audio(audio)
    except AudioInvalido as erro:
        print(f"transcrever: erro: {erro}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA

    saida = argumentos.saida or audio.with_suffix(".txt")
    if saida.resolve() == audio.resolve():
        print(
            "transcrever: erro: a saída não pode ser o próprio áudio, "
            "que seria apagado pelo texto.",
            file=sys.stderr,
        )
        return CODIGO_ENTRADA_INVALIDA
    parcial = caminho_parcial(saida)
    # Aberto antes de carregar o modelo: uma pasta sem permissão de gravação
    # aparece agora, e não no fim de uma hora de transcrição.
    try:
        arquivo = parcial.open("w", encoding="utf-8")
    except OSError as erro:
        print(
            f"transcrever: erro: não foi possível gravar em {saida}: {erro.strerror}",
            file=sys.stderr,
        )
        return CODIGO_ENTRADA_INVALIDA

    def guardar(segmento: Segmento, total: float) -> None:
        # Cada trecho vai para o disco na hora. Se a transcrição de uma aula
        # longa for interrompida, o que já foi feito não se perde.
        arquivo.write(segmento.texto + "\n")
        arquivo.flush()
        mostrar_progresso(segmento.fim, total)

    if duracao is not None:
        print(f"Áudio de {formatar_tempo(duracao)}.", file=sys.stderr)

    try:
        with arquivo:
            print(f"Carregando o modelo {argumentos.modelo}...", file=sys.stderr)
            modelo = carregar_modelo(argumentos.modelo)
            print("Transcrevendo...", file=sys.stderr)
            transcrever(audio, modelo, guardar)
    except FalhaNaTranscricao as erro:
        limpar_progresso()
        print(f"transcrever: erro: {erro}", file=sys.stderr)
        avisar_do_parcial(parcial)
        return CODIGO_FALHA_NA_TRANSCRICAO
    except KeyboardInterrupt:
        limpar_progresso()
        print("Transcrição cancelada.", file=sys.stderr)
        avisar_do_parcial(parcial)
        return CODIGO_CANCELADO

    limpar_progresso()
    # Só agora o texto ganha o nome definitivo: um .txt nunca está pela metade.
    parcial.replace(saida)
    print(f"Transcrição salva em: {saida}")
    return 0


def avisar_do_parcial(parcial: Path) -> None:
    """Diz onde ficou o texto já transcrito ou, se não houver nenhum, apaga o arquivo."""
    if parcial.stat().st_size > 0:
        print(f"O trecho já transcrito está em: {parcial}", file=sys.stderr)
    else:
        parcial.unlink()
