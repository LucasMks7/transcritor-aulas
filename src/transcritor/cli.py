"""Interface de linha de comando."""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from transcritor import __version__, drive, entrega, preferencias
from transcritor.arquivos import (
    SaidaInvalida,
    TextoParcial,
    conferir_saida,
    gravar_pdf,
)
from transcritor.audio import AudioInvalido, conferir_audio
from transcritor.pastas import AutorizacaoExpirada
from transcritor.pdf import Cabecalho
from transcritor.transcricao import (
    DISPOSITIVO_PADRAO,
    DISPOSITIVOS,
    MODELO_PADRAO,
    MODELOS,
    FalhaNaTranscricao,
    ModeloCarregado,
    Segmento,
    avisos_da_transcricao,
    carregar_modelo,
    formatar_tempo,
    transcrever,
)

LARGURA_DA_LINHA = 70

CODIGO_FALHA_NA_TRANSCRICAO = 1
# O texto foi salvo, mas o PDF não: também é falha, para um script perceber.
CODIGO_FALHA_NO_PDF = 1
# O mesmo vale para os arquivos que não chegaram ao Drive.
CODIGO_FALHA_NO_ENVIO = 1
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


def descrever_modelo(carregado: ModeloCarregado) -> str:
    """Diz qual modelo vai transcrever e onde, e por que a placa ficou de fora."""
    if carregado.dispositivo == "cuda":
        return f"Transcrevendo com o modelo {carregado.nome} na placa de vídeo..."
    texto = f"Transcrevendo com o modelo {carregado.nome} no processador..."
    if carregado.motivo_sem_gpu:
        # Quem tem placa e vê a transcrição lenta precisa saber o porquê.
        texto = f"Placa de vídeo não usada: {carregado.motivo_sem_gpu}.\n" + texto
    return texto


def criar_parser() -> argparse.ArgumentParser:
    parser = ParserEmPortugues(
        prog="transcrever",
        description="Transcreve um arquivo de áudio em português, no próprio PC. "
        "Nada é enviado para a internet, a não ser com --enviar.",
    )
    parser.add_argument("audio", type=Path, help="arquivo de áudio a transcrever")
    parser.add_argument(
        "--saida",
        type=Path,
        help="arquivo de texto a criar; o PDF fica ao lado, com o mesmo nome "
        "(padrão: o nome do áudio, com .txt)",
    )
    parser.add_argument(
        "--modelo",
        choices=MODELOS,
        help="modelo do Whisper; os maiores erram menos e demoram mais "
        f"(padrão: {MODELO_PADRAO['cuda']} na placa de vídeo, "
        f"{MODELO_PADRAO['cpu']} no processador)",
    )
    parser.add_argument(
        "--dispositivo",
        choices=DISPOSITIVOS,
        default=DISPOSITIVO_PADRAO,
        help="onde transcrever: cuda é a placa de vídeo da NVIDIA, cpu é o "
        "processador, e auto usa a placa quando ela funciona (padrão: %(default)s)",
    )
    # No terminal, o envio é sempre pedido na hora. A preferência marcada na janela
    # não vale aqui, para um comando antigo não passar a enviar áudios sem aviso.
    parser.add_argument(
        "--enviar",
        action="store_true",
        help="no fim, envia o PDF e o áudio para as suas pastas do Google Drive",
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
    try:
        conferir_saida(audio, saida)
        texto = TextoParcial(saida)
    except SaidaInvalida as erro:
        print(f"transcrever: erro: {erro}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA
    except OSError as erro:
        print(
            f"transcrever: erro: não foi possível gravar em {saida}: {erro.strerror}",
            file=sys.stderr,
        )
        return CODIGO_ENTRADA_INVALIDA

    def guardar(segmento: Segmento, total: float) -> None:
        texto.guardar(segmento)
        mostrar_progresso(segmento.fim, total)

    servico = None
    if argumentos.enviar:
        # Antes de transcrever: o navegador não pode ficar esperando a pessoa
        # voltar depois de uma hora.
        try:
            servico = drive.servico_do_drive(drive.conectar())
        except drive.FalhaNaAutorizacao as erro:
            print(f"transcrever: erro: {erro}", file=sys.stderr)
            print("Para só transcrever, rode de novo sem --enviar.", file=sys.stderr)
            texto.abandonar()
            return CODIGO_FALHA_NO_ENVIO
        except KeyboardInterrupt:
            texto.abandonar()
            return CODIGO_CANCELADO

    if duracao is not None:
        print(f"Áudio de {formatar_tempo(duracao)}.", file=sys.stderr)

    try:
        print("Carregando o modelo...", file=sys.stderr)
        carregado = carregar_modelo(argumentos.modelo, argumentos.dispositivo)
        print(descrever_modelo(carregado), file=sys.stderr)
        transcricao = transcrever(audio, carregado.modelo, guardar)
    except FalhaNaTranscricao as erro:
        limpar_progresso()
        print(f"transcrever: erro: {erro}", file=sys.stderr)
        avisar_do_parcial(texto)
        return CODIGO_FALHA_NA_TRANSCRICAO
    except KeyboardInterrupt:
        limpar_progresso()
        print("Transcrição cancelada.", file=sys.stderr)
        avisar_do_parcial(texto)
        return CODIGO_CANCELADO

    limpar_progresso()
    texto.concluir()
    print(f"Transcrição salva em: {saida}")
    for aviso in avisos_da_transcricao(transcricao, duracao):
        print(aviso, file=sys.stderr)

    pdf = saida.with_suffix(".pdf")
    cabecalho = Cabecalho(audio.stem, transcricao.duracao, carregado.nome, date.today())
    try:
        gravar_pdf(transcricao.segmentos, cabecalho, pdf)
    except OSError as erro:
        # No Windows, o caso mais comum é o PDF anterior aberto no leitor.
        print(
            f"transcrever: erro: não foi possível gravar o PDF em {pdf}: {erro.strerror}. "
            "Se ele estiver aberto em outro programa, feche-o e rode de novo. "
            "O texto já está salvo.",
            file=sys.stderr,
        )
        return CODIGO_FALHA_NO_PDF
    print(f"PDF salvo em: {pdf}")
    if servico is not None:
        return enviar(servico, pdf, audio)
    return 0


def enviar(servico, pdf: Path, audio: Path) -> int:
    """Envia o PDF primeiro: é pequeno, e é o que a pessoa mais quer."""
    codigo = 0
    nomes = preferencias.carregar().nomes_das_pastas()
    try:
        for entregue in entrega.entregar(
            servico, [pdf, audio], nomes, drive.mostrar_envio, drive.mostrar_repeticao
        ):
            if entregue.erro:
                print(f"transcrever: {entrega.descrever(entregue)}", file=sys.stderr)
                codigo = CODIGO_FALHA_NO_ENVIO
            else:
                print(entrega.descrever(entregue))
    except AutorizacaoExpirada as erro:
        print(f"transcrever: erro: {erro}.", file=sys.stderr)
        codigo = CODIGO_FALHA_NO_ENVIO
    except KeyboardInterrupt:
        print("\nEnvio cancelado.", file=sys.stderr)
        codigo = CODIGO_CANCELADO
    if codigo != 0:
        print(
            "A transcrição está salva no PC. Para tentar o envio de novo: "
            f'transcritor-drive enviar "{pdf}" "{audio}"',
            file=sys.stderr,
        )
    return codigo


def avisar_do_parcial(texto: TextoParcial) -> None:
    """Diz onde ficou o texto já transcrito; um parcial vazio é apagado."""
    parcial = texto.abandonar()
    if parcial is not None:
        print(f"O trecho já transcrito está em: {parcial}", file=sys.stderr)
