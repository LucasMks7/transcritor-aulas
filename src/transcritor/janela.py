"""Janela para escolher o áudio e acompanhar a transcrição, sobre o mesmo núcleo do terminal."""

import os
import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

from transcritor.arquivos import SaidaInvalida, TextoParcial, conferir_saida, gravar_pdf
from transcritor.audio import AudioInvalido, conferir_audio

# Os textos de andamento são os mesmos do terminal.
from transcritor.cli import descrever_modelo, formatar_progresso
from transcritor.pdf import Cabecalho
from transcritor.transcricao import (
    FalhaNaTranscricao,
    Segmento,
    carregar_modelo,
    formatar_tempo,
    transcrever,
)

# De quanto em quanto tempo a janela olha a fila de mensagens da thread de trabalho.
INTERVALO_DA_FILA_MS = 100

TEXTO_INICIAL = "Escolha o áudio da aula e clique em Transcrever."
TEXTO_CARREGANDO = (
    "Carregando o modelo... Na primeira vez, ele é baixado da internet, "
    "o que pode levar alguns minutos."
)
TEXTO_GERANDO_PDF = "Gerando o PDF..."
TEXTO_CANCELANDO = "Cancelando..."
TEXTO_CANCELADO = "Transcrição cancelada."
TEXTO_PRIVACIDADE = "O áudio é transcrito neste computador e não é enviado para a internet."

# Só filtra a caixa de escolha. O programa confere o conteúdo, não a extensão.
TIPOS_DE_ARQUIVO = [
    ("Áudio e vídeo", "*.mp3 *.m4a *.ogg *.opus *.wav *.flac *.aac *.wma *.mp4 *.mkv *.webm *.mov"),
    ("Todos os arquivos", "*.*"),
]


@dataclass(frozen=True)
class Pedido:
    """O áudio escolhido, já conferido, e onde ficam o texto e o PDF."""

    audio: Path
    duracao: float | None

    @property
    def saida(self) -> Path:
        # Como no terminal sem --saida: o texto e o PDF ficam ao lado do áudio.
        return self.audio.with_suffix(".txt")


@dataclass(frozen=True)
class Andamento:
    """Uma etapa do trabalho. Sem percentual, a barra fica em vaivém."""

    texto: str
    percentual: float | None = None


@dataclass(frozen=True)
class Resultado:
    """Como a transcrição terminou, com o texto que a janela mostra."""

    sucesso: bool
    texto: str
    pdf: Path | None = None


class _Cancelada(Exception):
    """Levantada dentro da transcrição para interrompê-la no próximo trecho."""


def preparar_pedido(campo: str) -> Pedido:
    """Confere o áudio do campo ou levanta AudioInvalido ou SaidaInvalida."""
    # O "Copiar como caminho" do Windows põe o caminho entre aspas.
    texto = campo.strip().strip('"').strip()
    if not texto:
        raise AudioInvalido("escolha o arquivo de áudio da aula.")
    audio = Path(texto)
    duracao = conferir_audio(audio)
    conferir_saida(audio, audio.with_suffix(".txt"))
    return Pedido(audio, duracao)


def executar(
    pedido: Pedido,
    avisar: Callable[[Andamento | Resultado], None],
    cancelamento: threading.Event,
) -> None:
    """Transcreve e gera o PDF, avisando cada etapa. Roda fora da thread da janela.

    Sempre termina com exatamente um Resultado, inclusive em erros imprevistos:
    sem isso, a janela ficaria esperando para sempre.
    """
    try:
        texto = TextoParcial(pedido.saida)
    except OSError as erro:
        avisar(Resultado(False, f"Erro: não foi possível gravar em {pedido.saida.parent}: "
                                f"{erro.strerror}"))
        return

    def guardar(segmento: Segmento, total: float) -> None:
        # A transcrição só para entre um trecho e outro. Levantar aqui faz o
        # erro atravessar o laço do faster-whisper e encerrar o trabalho.
        if cancelamento.is_set():
            raise _Cancelada
        texto.guardar(segmento)
        percentual = min(segmento.fim / total, 1) * 100 if total > 0 else None
        avisar(Andamento(formatar_progresso(segmento.fim, total), percentual))

    try:
        avisar(Andamento(TEXTO_CARREGANDO))
        carregado = carregar_modelo()
        if cancelamento.is_set():
            raise _Cancelada
        avisar(Andamento(descrever_modelo(carregado), 0))
        transcricao = transcrever(pedido.audio, carregado.modelo, guardar)
    except _Cancelada:
        avisar(Resultado(False, _com_parcial(TEXTO_CANCELADO, texto.abandonar())))
        return
    except FalhaNaTranscricao as erro:
        avisar(Resultado(False, _com_parcial(f"Erro: {erro}", texto.abandonar())))
        return
    except Exception as erro:
        avisar(Resultado(False, _com_parcial(f"Erro inesperado: {erro}", texto.abandonar())))
        return

    texto.concluir()
    avisar(Andamento(TEXTO_GERANDO_PDF))
    cabecalho = Cabecalho(pedido.audio.stem, transcricao.duracao, carregado.nome, date.today())
    try:
        pdf = gravar_pdf(transcricao.segmentos, cabecalho, pedido.saida.with_suffix(".pdf"))
    except OSError as erro:
        avisar(Resultado(False, f"O texto foi salvo em {pedido.saida}, mas o PDF não: "
                                f"{erro.strerror}. Se ele estiver aberto em outro "
                                "programa, feche-o e transcreva de novo."))
        return
    avisar(Resultado(True, f"Pronto! PDF salvo em: {pdf}", pdf))


def _com_parcial(texto: str, parcial: Path | None) -> str:
    if parcial is None:
        return texto
    return f"{texto} O trecho já transcrito está em: {parcial}"


def abrir_arquivo(caminho: Path) -> None:
    """Abre o arquivo no programa padrão do sistema, como um clique duplo."""
    if hasattr(os, "startfile"):
        os.startfile(caminho)  # Só existe no Windows.
    else:
        webbrowser.open(caminho.resolve().as_uri())


class Janela:
    """Monta os campos e mantém a janela respondendo enquanto a transcrição roda."""

    def __init__(self, raiz: tk.Tk | tk.Toplevel):
        self.raiz = raiz
        # O Tkinter só pode ser usado pela thread que o criou. A thread de trabalho
        # deixa as mensagens nesta fila, e a janela as lê de tempos em tempos.
        self.fila: queue.Queue[Andamento | Resultado] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.cancelamento = threading.Event()
        self.barra_em_vaivem = False
        self.pdf: Path | None = None

        self.audio = tk.StringVar()
        self.situacao = tk.StringVar(value=TEXTO_INICIAL)

        raiz.title("Transcritor de aulas")
        raiz.resizable(False, False)
        raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        self._montar()

    def _montar(self) -> None:
        quadro = ttk.Frame(self.raiz, padding=12)
        quadro.grid()

        ttk.Label(quadro, text="Áudio").grid(row=0, column=0, sticky="w")
        campo = ttk.Entry(quadro, textvariable=self.audio, width=56)
        campo.grid(row=0, column=1, sticky="ew", pady=4)
        campo.bind("<Return>", lambda evento: self.iniciar())
        campo.focus()
        self.botao_escolher = ttk.Button(quadro, text="Escolher...", command=self.escolher_audio)
        self.botao_escolher.grid(row=0, column=2, padx=(8, 0))

        botoes = ttk.Frame(quadro)
        botoes.grid(row=1, column=0, columnspan=3, pady=(8, 4))
        self.botao_transcrever = ttk.Button(botoes, text="Transcrever", command=self.iniciar)
        self.botao_transcrever.grid(row=0, column=0, padx=4)
        self.botao_cancelar = ttk.Button(
            botoes, text="Cancelar", command=self.cancelar, state="disabled"
        )
        self.botao_cancelar.grid(row=0, column=1, padx=4)
        self.botao_abrir = ttk.Button(
            botoes, text="Abrir PDF", command=self.abrir_pdf, state="disabled"
        )
        self.botao_abrir.grid(row=0, column=2, padx=4)

        self.barra = ttk.Progressbar(quadro, maximum=100)
        self.barra.grid(row=2, column=0, columnspan=3, sticky="ew", pady=4)

        ttk.Label(quadro, textvariable=self.situacao, wraplength=480).grid(
            row=3, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(quadro, text=TEXTO_PRIVACIDADE, foreground="gray").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        quadro.columnconfigure(1, weight=1)

    def escolher_audio(self) -> None:
        atual = Path(self.audio.get().strip().strip('"'))
        escolhido = filedialog.askopenfilename(
            parent=self.raiz,
            title="Áudio da aula",
            filetypes=TIPOS_DE_ARQUIVO,
            initialdir=atual.parent if atual.parent.is_dir() else Path.home(),
        )
        # Cancelar a caixa devolve um texto vazio; nesse caso, vale o de antes.
        if escolhido:
            self.audio.set(str(Path(escolhido)))

    @property
    def transcrevendo(self) -> bool:
        return self.thread is not None

    def iniciar(self) -> None:
        """Confere o áudio e começa a transcrição em outra thread."""
        if self.transcrevendo:
            return

        try:
            pedido = preparar_pedido(self.audio.get())
        except (AudioInvalido, SaidaInvalida) as erro:
            self.situacao.set(f"Erro: {erro}")
            return

        duracao = "" if pedido.duracao is None else f" de {formatar_tempo(pedido.duracao)}"
        self.situacao.set(f"Áudio{duracao}. Preparando...")
        self.pdf = None
        self._travar(True)
        self._definir_barra(None)
        # Um por transcrição: o pedido de cancelar uma não pode valer para a seguinte.
        self.cancelamento = threading.Event()
        # Em outra thread porque a transcrição leva minutos: na thread da janela,
        # ela pararia de responder. daemon=True não segura o programa ao fechar.
        self.thread = threading.Thread(
            target=executar, args=(pedido, self.fila.put, self.cancelamento), daemon=True
        )
        self.thread.start()
        self.raiz.after(INTERVALO_DA_FILA_MS, self.ler_fila)

    def ler_fila(self) -> None:
        """Aplica na janela as mensagens deixadas pela thread de trabalho."""
        try:
            while True:
                mensagem = self.fila.get_nowait()
                if isinstance(mensagem, Resultado):
                    self._terminar(mensagem)
                elif not self.cancelamento.is_set():
                    # Depois do pedido de cancelar, o andamento que ainda estava
                    # na fila apagaria o aviso "Cancelando...".
                    self.situacao.set(mensagem.texto)
                    self._definir_barra(mensagem.percentual)
        except queue.Empty:
            pass

        if self.transcrevendo:
            self.raiz.after(INTERVALO_DA_FILA_MS, self.ler_fila)

    def _definir_barra(self, percentual: float | None) -> None:
        """Sem percentual, a barra fica em vaivém: há trabalho, mas não se sabe quanto."""
        em_vaivem = percentual is None
        if em_vaivem != self.barra_em_vaivem:
            self.barra_em_vaivem = em_vaivem
            if em_vaivem:
                self.barra.configure(mode="indeterminate")
                self.barra.start()
            else:
                self.barra.stop()
                self.barra.configure(mode="determinate")
        if not em_vaivem:
            self.barra.configure(value=percentual)

    def _travar(self, trabalhando: bool) -> None:
        """Durante a transcrição, só o Cancelar fica disponível."""
        livre = "disabled" if trabalhando else "normal"
        self.botao_transcrever.configure(state=livre)
        self.botao_escolher.configure(state=livre)
        self.botao_cancelar.configure(state="normal" if trabalhando else "disabled")
        self.botao_abrir.configure(state="normal" if self.pdf else "disabled")

    def _terminar(self, resultado: Resultado) -> None:
        self.thread = None
        self.pdf = resultado.pdf
        self.situacao.set(resultado.texto)
        self._definir_barra(100 if resultado.sucesso else 0)
        self._travar(False)

    def cancelar(self) -> None:
        """Pede o cancelamento; o resultado chega pela fila, como qualquer outro."""
        if not self.transcrevendo:
            return
        self.botao_cancelar.configure(state="disabled")
        self.situacao.set(TEXTO_CANCELANDO)
        self._definir_barra(None)
        self.cancelamento.set()

    def abrir_pdf(self) -> None:
        if self.pdf is not None:
            abrir_arquivo(self.pdf)

    def fechar(self) -> None:
        # A thread é daemon e morre com o programa; o .parcial guarda o que já
        # estava pronto.
        self.cancelamento.set()
        self.raiz.destroy()


def main() -> None:
    raiz = tk.Tk()
    Janela(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
