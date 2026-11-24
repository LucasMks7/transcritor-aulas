"""Janela para escolher o áudio e acompanhar a transcrição, sobre o mesmo núcleo do terminal."""

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

from transcritor import drive, preferencias
from transcritor.arquivos import SaidaInvalida, TextoParcial, conferir_saida, gravar_pdf
from transcritor.audio import AudioInvalido, conferir_audio

# Os textos de andamento são os mesmos do terminal.
from transcritor.cli import descrever_modelo, formatar_progresso
from transcritor.entrega import entregar
from transcritor.pastas import AutorizacaoExpirada
from transcritor.pdf import Cabecalho
from transcritor.transcricao import (
    FalhaNaTranscricao,
    Segmento,
    avisos_da_transcricao,
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
TEXTO_CONECTANDO = (
    "Conectando ao Google Drive... Se o navegador abrir, entre na sua conta e permita o acesso."
)
TEXTO_PRIVACIDADE = "O áudio é transcrito neste computador e não é enviado para a internet."
TEXTO_PRIVACIDADE_COM_DRIVE = (
    "O áudio é transcrito neste computador. Depois, o áudio e o PDF vão só para o seu Drive."
)

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
    # Os nomes das pastas do Drive, ou None para não enviar nada.
    pastas: dict[str, str] | None = None

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
    # O PDF existe, mas algum arquivo não chegou ao Drive: dá para tentar de novo.
    falta_enviar: bool = False


class _Cancelada(Exception):
    """Levantada dentro da transcrição para interrompê-la no próximo trecho."""


def preparar_pedido(campo: str, pastas: dict[str, str] | None = None) -> Pedido:
    """Confere o áudio do campo ou levanta AudioInvalido ou SaidaInvalida."""
    # O "Copiar como caminho" do Windows põe o caminho entre aspas.
    texto = campo.strip().strip('"').strip()
    if not texto:
        raise AudioInvalido("escolha o arquivo de áudio da aula.")
    audio = Path(texto)
    duracao = conferir_audio(audio)
    conferir_saida(audio, audio.with_suffix(".txt"))
    return Pedido(audio, duracao, pastas)


def conectar_ao_drive():
    """Usa a autorização salva ou abre o navegador. Levanta FalhaNaAutorizacao."""
    return drive.servico_do_drive(drive.conectar())


def executar(
    pedido: Pedido,
    avisar: Callable[[Andamento | Resultado], None],
    cancelamento: threading.Event,
) -> None:
    """Transcreve, gera o PDF e o envia ao Drive, se pedido, avisando cada etapa.

    Roda fora da thread da janela.

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

    servico = None
    falha_no_drive = None
    try:
        if pedido.pastas is not None:
            # Antes de transcrever, com a pessoa ainda na frente do PC. Sem acesso
            # ao Drive, a transcrição segue: o PDF vale por si.
            avisar(Andamento(TEXTO_CONECTANDO))
            try:
                servico = conectar_ao_drive()
            except drive.FalhaNaAutorizacao as erro:
                falha_no_drive = str(erro)
            if cancelamento.is_set():
                raise _Cancelada
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
    avisos = avisos_da_transcricao(transcricao, pedido.duracao)
    pronto = " ".join([*avisos, f"Pronto! PDF salvo em: {pdf}"])
    if pedido.pastas is None:
        avisar(Resultado(True, pronto, pdf))
        return
    if servico is not None:
        falha_no_drive = enviar_ao_drive(servico, pedido, pdf, avisar, cancelamento)
    avisar(_resultado_do_envio(pronto, pdf, falha_no_drive))


def reenviar(
    pedido: Pedido,
    pdf: Path,
    avisar: Callable[[Andamento | Resultado], None],
    cancelamento: threading.Event,
) -> None:
    """Tenta só o envio outra vez, sem transcrever de novo. Roda fora da thread da janela.

    O que já chegou ao Drive não é mandado outra vez: o envio reconhece o arquivo.
    """
    avisar(Andamento(TEXTO_CONECTANDO))
    try:
        servico = conectar_ao_drive()
    except drive.FalhaNaAutorizacao as erro:
        falha = str(erro)
    except Exception as erro:
        falha = f"erro inesperado: {erro}"
    else:
        falha = enviar_ao_drive(servico, pedido, pdf, avisar, cancelamento)
    avisar(_resultado_do_envio(f"PDF salvo em: {pdf}", pdf, falha))


def _resultado_do_envio(pronto: str, pdf: Path, falha: str | None) -> Resultado:
    if falha is None:
        return Resultado(True, f"{pronto}. O áudio e o PDF estão no seu Drive.", pdf)
    texto = f"{pronto}. Envio ao Drive incompleto: {falha.rstrip('.')}."
    return Resultado(False, texto, pdf, falta_enviar=True)


def enviar_ao_drive(
    servico,
    pedido: Pedido,
    pdf: Path,
    avisar: Callable[[Andamento | Resultado], None],
    cancelamento: threading.Event,
) -> str | None:
    """Envia o PDF e o áudio. Devolve o que deu errado, ou None."""

    def progredir(arquivo: Path, enviado: int, total: int) -> None:
        if cancelamento.is_set():
            raise _Cancelada
        percentual = enviado / total * 100
        avisar(Andamento(f"Enviando {arquivo.name} ao Drive ({percentual:.0f}%)", percentual))

    def repetir(tentativa: int, espera: float) -> None:
        avisar(Andamento(f"A conexão falhou. Nova tentativa em {espera:.0f} s..."))

    def esperar(segundos: float) -> None:
        # A espera termina na hora em que a pessoa cancela.
        if cancelamento.wait(segundos):
            raise _Cancelada

    avisar(Andamento("Enviando ao Drive..."))
    try:
        entregas = entregar(
            servico, [pdf, pedido.audio], pedido.pastas, progredir, repetir, esperar
        )
        erros = [entrega.erro for entrega in entregas if entrega.erro]
    except _Cancelada:
        return "o envio foi cancelado"
    except AutorizacaoExpirada as erro:
        return f"{erro}. Clique em Enviar de novo para entrar na sua conta"
    except Exception as erro:
        return f"erro inesperado: {erro}"
    return "; ".join(erros) or None


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
        # O último pedido, para o botão Enviar de novo.
        self.pedido: Pedido | None = None
        self.falta_enviar = False

        self.preferencias = preferencias.carregar()

        self.audio = tk.StringVar()
        self.enviar = tk.BooleanVar(value=self.preferencias.enviar_ao_drive)
        self.pasta_audio = tk.StringVar(value=self.preferencias.pasta_audio)
        self.pasta_pdf = tk.StringVar(value=self.preferencias.pasta_pdf)
        self.privacidade = tk.StringVar()
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

        self.caixa_enviar = ttk.Checkbutton(
            quadro,
            text="Enviar o áudio e o PDF para o meu Google Drive",
            variable=self.enviar,
            command=self._mostrar_envio,
        )
        self.caixa_enviar.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.campos_das_pastas = []
        for linha, rotulo, variavel in (
            (2, "Pasta do áudio", self.pasta_audio),
            (3, "Pasta do PDF", self.pasta_pdf),
        ):
            ttk.Label(quadro, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 8))
            campo_da_pasta = ttk.Entry(quadro, textvariable=variavel)
            campo_da_pasta.grid(row=linha, column=1, sticky="ew", pady=2)
            self.campos_das_pastas.append(campo_da_pasta)

        botoes = ttk.Frame(quadro)
        botoes.grid(row=4, column=0, columnspan=3, pady=(8, 4))
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
        self.botao_reenviar = ttk.Button(
            botoes, text="Enviar de novo", command=self.reenviar, state="disabled"
        )
        self.botao_reenviar.grid(row=0, column=3, padx=4)

        self.barra = ttk.Progressbar(quadro, maximum=100)
        self.barra.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)

        ttk.Label(quadro, textvariable=self.situacao, wraplength=480).grid(
            row=6, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(quadro, textvariable=self.privacidade, foreground="gray").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        quadro.columnconfigure(1, weight=1)
        self._mostrar_envio()

    def _mostrar_envio(self) -> None:
        """As pastas só podem ser escolhidas quando o envio está ligado."""
        enviar = self.enviar.get()
        self.privacidade.set(TEXTO_PRIVACIDADE_COM_DRIVE if enviar else TEXTO_PRIVACIDADE)
        for campo in self.campos_das_pastas:
            campo.configure(state="normal" if enviar else "disabled")

    def escolher_audio(self) -> None:
        # Sem áudio escolhido, a caixa abre na pasta da última aula.
        texto = self.audio.get().strip().strip('"')
        pasta = Path(texto).parent if texto else Path(self.preferencias.pasta_local or Path.home())
        escolhido = filedialog.askopenfilename(
            parent=self.raiz,
            title="Áudio da aula",
            filetypes=TIPOS_DE_ARQUIVO,
            initialdir=pasta if pasta.is_dir() else Path.home(),
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

        escolhas = self._escolhas()
        pastas = escolhas.nomes_das_pastas() if escolhas.enviar_ao_drive else None
        try:
            pedido = preparar_pedido(self.audio.get(), pastas)
        except (AudioInvalido, SaidaInvalida) as erro:
            self.situacao.set(f"Erro: {erro}")
            return
        self._lembrar(replace(escolhas, pasta_local=str(pedido.audio.resolve().parent)))

        duracao = "" if pedido.duracao is None else f" de {formatar_tempo(pedido.duracao)}"
        self.situacao.set(f"Áudio{duracao}. Preparando...")
        self.pdf = None
        self.pedido = pedido
        self._trabalhar(executar, pedido)

    def reenviar(self) -> None:
        """Manda para o Drive o que faltou da última transcrição."""
        if self.transcrevendo or not self.falta_enviar:
            return
        # As pastas podem ter sido trocadas na janela depois da falha.
        escolhas = self._escolhas()
        self._lembrar(escolhas)
        self.pedido = replace(self.pedido, pastas=escolhas.nomes_das_pastas())
        self._trabalhar(reenviar, self.pedido, self.pdf)

    def _trabalhar(self, tarefa: Callable, *argumentos) -> None:
        """Roda a tarefa em outra thread e passa a ler as mensagens dela."""
        self.falta_enviar = False
        self._travar(True)
        self._definir_barra(None)
        # Um por tarefa: o pedido de cancelar uma não pode valer para a seguinte.
        self.cancelamento = threading.Event()
        # Em outra thread porque a transcrição leva minutos: na thread da janela,
        # ela pararia de responder. daemon=True não segura o programa ao fechar.
        self.thread = threading.Thread(
            target=tarefa, args=(*argumentos, self.fila.put, self.cancelamento), daemon=True
        )
        self.thread.start()
        self.raiz.after(INTERVALO_DA_FILA_MS, self.ler_fila)

    def _escolhas(self) -> preferencias.Preferencias:
        """O que está na janela agora. Uma pasta em branco volta para o nome padrão."""
        self.pasta_audio.set(preferencias.nome_ou_padrao(self.pasta_audio.get(), "audio"))
        self.pasta_pdf.set(preferencias.nome_ou_padrao(self.pasta_pdf.get(), "pdf"))
        return replace(
            self.preferencias,
            enviar_ao_drive=self.enviar.get(),
            pasta_audio=self.pasta_audio.get(),
            pasta_pdf=self.pasta_pdf.get(),
        )

    def _lembrar(self, escolhas: preferencias.Preferencias) -> None:
        if escolhas == self.preferencias:
            return
        self.preferencias = escolhas
        try:
            preferencias.salvar(escolhas)
        except OSError:
            # Não lembrar da escolha não é motivo para não transcrever a aula.
            pass

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
        pode_reenviar = self.falta_enviar and not trabalhando
        self.botao_reenviar.configure(state="normal" if pode_reenviar else "disabled")
        self.caixa_enviar.configure(state=livre)
        if trabalhando:
            for campo in self.campos_das_pastas:
                campo.configure(state="disabled")
        else:
            self._mostrar_envio()

    def _terminar(self, resultado: Resultado) -> None:
        self.thread = None
        self.pdf = resultado.pdf
        self.falta_enviar = resultado.falta_enviar
        self.situacao.set(resultado.texto)
        # Com o PDF pronto, a barra fica cheia mesmo que o envio tenha falhado.
        self._definir_barra(100 if resultado.sucesso or resultado.pdf else 0)
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
    # Sem terminal, o Windows deixa os dois fluxos como None, e uma biblioteca que
    # tente escrever neles derrubaria o programa.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    raiz = tk.Tk()
    Janela(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
