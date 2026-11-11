import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

from transcritor import arquivos
from transcritor import janela as modulo
from transcritor.arquivos import SaidaInvalida, caminho_parcial
from transcritor.audio import AudioInvalido
from transcritor.janela import (
    TEXTO_CANCELADO,
    TEXTO_CANCELANDO,
    TEXTO_CARREGANDO,
    TEXTO_GERANDO_PDF,
    TEXTO_INICIAL,
    Andamento,
    Janela,
    Pedido,
    Resultado,
    executar,
    preparar_pedido,
)
from transcritor.transcricao import FalhaNaTranscricao, ModeloCarregado


@pytest.fixture
def audio(criar_audio):
    return criar_audio("aula.mp3")


@pytest.fixture
def usar_modelo(monkeypatch):
    """Troca o carregamento do modelo pelo dublê dado."""

    def usar(modelo):
        monkeypatch.setattr(
            modulo, "carregar_modelo", lambda: ModeloCarregado(modelo, "small", "cpu")
        )

    return usar


@pytest.fixture
def modelo_que_funciona(usar_modelo, criar_modelo):
    usar_modelo(criar_modelo(" Bom dia, turma.", " Vamos começar.", duracao=1.0))


class ModeloSemFim:
    """Transcreve para sempre, como uma aula muito longa, até ser cancelado."""

    def __init__(self):
        self.comecou = threading.Event()

    def transcribe(self, audio, **opcoes):
        return self._segmentos(), None

    def _segmentos(self):
        inicio = 0.0
        while True:
            self.comecou.set()
            yield SimpleNamespace(start=inicio, end=inicio + 0.01, text=" Trecho.")
            inicio += 0.01
            time.sleep(0.005)


# --- Lógica sem Tkinter: roda em qualquer máquina, inclusive no CI sem tela. ---


def test_pedido_valido_traz_o_audio_a_duracao_e_a_saida_ao_lado(audio):
    pedido = preparar_pedido(str(audio))

    assert pedido.audio == audio
    assert pedido.duracao == pytest.approx(1.0, abs=0.15)
    assert pedido.saida == audio.with_suffix(".txt")


def test_pedido_aceita_o_caminho_entre_aspas_do_windows(audio):
    assert preparar_pedido(f'  "{audio}"\n').audio == audio


@pytest.mark.parametrize("campo", ["", "   ", '""'])
def test_pedido_sem_audio_pede_para_escolher(campo):
    with pytest.raises(AudioInvalido, match="escolha o arquivo"):
        preparar_pedido(campo)


def test_pedido_com_arquivo_que_nao_e_audio_e_recusado(tmp_path):
    falso = tmp_path / "falso.mp3"
    falso.write_bytes(b"isto nao e um audio")

    with pytest.raises(AudioInvalido):
        preparar_pedido(str(falso))


def test_pedido_que_apagaria_o_proprio_audio_e_recusado(audio):
    # Um vídeo chamado aula.pdf seria substituído pelo PDF da transcrição.
    video = audio.rename(audio.with_suffix(".pdf"))

    with pytest.raises(SaidaInvalida):
        preparar_pedido(str(video))


def test_executar_avisa_cada_etapa_e_termina_com_o_pdf(audio, modelo_que_funciona, ler_pdf):
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    pdf = audio.with_suffix(".pdf")
    assert avisos[0] == Andamento(TEXTO_CARREGANDO)
    assert avisos[1] == Andamento("Transcrevendo com o modelo small no processador...", 0)
    assert avisos[2] == Andamento("Transcrevendo 00:00 de 00:01 (50%)", pytest.approx(50, abs=1))
    assert avisos[-2] == Andamento(TEXTO_GERANDO_PDF)
    assert avisos[-1] == Resultado(True, f"Pronto! PDF salvo em: {pdf}", pdf)
    assert audio.with_suffix(".txt").read_text(encoding="utf-8") == (
        "Bom dia, turma.\nVamos começar.\n"
    )
    assert "Bom dia, turma. Vamos começar." in ler_pdf(pdf)


def test_falha_no_meio_avisa_o_erro_e_onde_ficou_o_texto(audio, usar_modelo, criar_modelo):
    usar_modelo(criar_modelo(" Bom dia, turma.", falha=RuntimeError("faltou memória")))
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    resultado = avisos[-1]
    parcial = caminho_parcial(audio.with_suffix(".txt"))
    assert not resultado.sucesso
    assert "faltou memória" in resultado.texto
    assert str(parcial) in resultado.texto
    assert parcial.read_text(encoding="utf-8") == "Bom dia, turma.\n"
    assert not audio.with_suffix(".txt").exists()


def test_modelo_que_nao_carrega_avisa_o_erro_sem_deixar_arquivos(audio, monkeypatch):
    def falhar():
        raise FalhaNaTranscricao("Não foi possível carregar o modelo small.")

    monkeypatch.setattr(modulo, "carregar_modelo", falhar)
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    assert avisos[-1] == Resultado(False, "Erro: Não foi possível carregar o modelo small.")
    assert sorted(p.name for p in audio.parent.iterdir()) == ["aula.mp3"]


def test_erro_imprevisto_tambem_termina_com_um_resultado(audio, monkeypatch):
    def falhar():
        raise ValueError("algo estranho")

    monkeypatch.setattr(modulo, "carregar_modelo", falhar)
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    assert avisos[-1] == Resultado(False, "Erro inesperado: algo estranho")


def test_cancelar_durante_a_transcricao_guarda_o_que_ja_foi_feito(audio, usar_modelo):
    usar_modelo(ModeloSemFim())
    cancelamento = threading.Event()
    avisos = []

    def avisar(mensagem):
        avisos.append(mensagem)
        # Cancela assim que o primeiro trecho é avisado.
        if isinstance(mensagem, Andamento) and mensagem.texto.startswith("Transcrevendo 00"):
            cancelamento.set()

    executar(Pedido(audio, 1.0), avisar, cancelamento)

    parcial = caminho_parcial(audio.with_suffix(".txt"))
    assert avisos[-1] == Resultado(
        False, f"{TEXTO_CANCELADO} O trecho já transcrito está em: {parcial}"
    )
    assert parcial.read_text(encoding="utf-8") == "Trecho.\n"


def test_cancelar_enquanto_o_modelo_carrega_nem_comeca_a_transcrever(audio, usar_modelo):
    modelo = ModeloSemFim()
    usar_modelo(modelo)
    cancelamento = threading.Event()
    cancelamento.set()
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, cancelamento)

    assert avisos[-1] == Resultado(False, TEXTO_CANCELADO)
    assert not modelo.comecou.is_set()
    assert not caminho_parcial(audio.with_suffix(".txt")).exists()


def test_pasta_sem_permissao_avisa_antes_de_carregar_o_modelo(audio, monkeypatch):
    def recusar(saida):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(modulo, "TextoParcial", recusar)
    monkeypatch.setattr(modulo, "carregar_modelo", pytest.fail)
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    assert avisos == [
        Resultado(False, f"Erro: não foi possível gravar em {audio.parent}: Permission denied")
    ]


def test_pdf_que_nao_pode_ser_gravado_avisa_que_o_texto_ficou_salvo(
    audio, modelo_que_funciona, monkeypatch
):
    def falhar(segmentos, cabecalho, destino):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(arquivos, "gerar_pdf", falhar)
    avisos = []

    executar(Pedido(audio, 1.0), avisos.append, threading.Event())

    resultado = avisos[-1]
    assert not resultado.sucesso
    assert resultado.pdf is None
    assert f"O texto foi salvo em {audio.with_suffix('.txt')}, mas o PDF não" in resultado.texto
    assert audio.with_suffix(".txt").is_file()


# --- Janela de verdade: precisa de uma tela, então é pulada no Linux do CI. ---


@pytest.fixture(scope="session")
def tk_da_sessao():
    """Um único Tk para todos os testes.

    Criar e destruir vários em seguida falha de vez em quando no Windows, e o
    teste seria pulado como se não houvesse tela.
    """
    try:
        raiz = tk.Tk()
    except tk.TclError:
        pytest.skip("não há tela para abrir a janela")
    raiz.withdraw()
    yield raiz
    raiz.destroy()


@pytest.fixture
def janela(tk_da_sessao):
    # Cada teste recebe uma janela filha nova, que pode ser fechada à vontade.
    topo = tk.Toplevel(tk_da_sessao)
    topo.withdraw()
    yield Janela(topo)
    if topo.winfo_exists():
        topo.destroy()


def esperar_o_fim(janela):
    """Espera a thread de trabalho e lê a fila, como o laço da janela faria."""
    janela.thread.join(timeout=10)
    janela.ler_fila()


def estado(botao) -> str:
    return str(botao.cget("state"))


def test_janela_abre_pronta_para_escolher_o_audio(janela):
    assert janela.situacao.get() == TEXTO_INICIAL
    assert not janela.transcrevendo
    assert estado(janela.botao_transcrever) == "normal"
    assert estado(janela.botao_cancelar) == "disabled"
    assert estado(janela.botao_abrir) == "disabled"


def test_audio_invalido_mostra_o_erro_e_nao_comeca(janela, tmp_path, monkeypatch):
    monkeypatch.setattr(modulo, "carregar_modelo", pytest.fail)
    janela.audio.set(str(tmp_path / "sumiu.mp3"))

    janela.iniciar()

    assert janela.situacao.get().startswith("Erro: arquivo não encontrado")
    assert not janela.transcrevendo


def test_transcricao_trava_os_botoes_e_libera_o_pdf_no_fim(janela, audio, modelo_que_funciona):
    janela.audio.set(str(audio))

    janela.iniciar()

    assert janela.transcrevendo
    assert janela.situacao.get() == "Áudio de 00:01. Preparando..."
    assert estado(janela.botao_transcrever) == "disabled"
    assert estado(janela.botao_escolher) == "disabled"
    assert estado(janela.botao_cancelar) == "normal"

    esperar_o_fim(janela)

    assert not janela.transcrevendo
    assert janela.situacao.get() == f"Pronto! PDF salvo em: {audio.with_suffix('.pdf')}"
    assert janela.barra.cget("value") == 100
    assert estado(janela.botao_transcrever) == "normal"
    assert estado(janela.botao_cancelar) == "disabled"
    assert estado(janela.botao_abrir) == "normal"


def test_abrir_pdf_abre_o_arquivo_gerado(janela, audio, modelo_que_funciona, monkeypatch):
    abertos = []
    monkeypatch.setattr(modulo, "abrir_arquivo", abertos.append)
    janela.audio.set(str(audio))
    janela.iniciar()
    esperar_o_fim(janela)

    janela.abrir_pdf()

    assert abertos == [audio.with_suffix(".pdf")]


def test_segundo_clique_durante_a_transcricao_e_ignorado(janela, audio, modelo_que_funciona):
    janela.audio.set(str(audio))

    janela.iniciar()
    thread = janela.thread
    janela.iniciar()

    assert janela.thread is thread
    esperar_o_fim(janela)


def test_andamento_move_a_barra_e_atualiza_o_texto(janela):
    janela.fila.put(Andamento("Transcrevendo 12:30 de 1:45:00 (12%)", 11.9))

    janela.ler_fila()

    assert janela.situacao.get() == "Transcrevendo 12:30 de 1:45:00 (12%)"
    assert str(janela.barra.cget("mode")) == "determinate"
    assert janela.barra.cget("value") == pytest.approx(11.9)


def test_sem_percentual_a_barra_fica_em_vaivem(janela):
    janela.fila.put(Andamento("Transcrevendo", 50))
    janela.fila.put(Andamento(TEXTO_CARREGANDO))

    janela.ler_fila()

    assert str(janela.barra.cget("mode")) == "indeterminate"


def test_cancelar_interrompe_e_libera_a_janela(janela, audio, usar_modelo):
    modelo = ModeloSemFim()
    usar_modelo(modelo)
    janela.audio.set(str(audio))
    janela.iniciar()
    assert modelo.comecou.wait(timeout=10)

    janela.cancelar()

    assert janela.situacao.get() == TEXTO_CANCELANDO
    assert estado(janela.botao_cancelar) == "disabled"

    esperar_o_fim(janela)

    # O andamento que ficou na fila não pode apagar o aviso de cancelamento.
    assert janela.situacao.get().startswith(TEXTO_CANCELADO)
    assert not janela.transcrevendo
    assert janela.barra.cget("value") == 0
    assert estado(janela.botao_transcrever) == "normal"
    assert estado(janela.botao_abrir) == "disabled"


def test_fechar_a_janela_pede_o_cancelamento(janela, audio, usar_modelo):
    modelo = ModeloSemFim()
    usar_modelo(modelo)
    janela.audio.set(str(audio))
    janela.iniciar()
    assert modelo.comecou.wait(timeout=10)
    thread = janela.thread

    janela.fechar()

    thread.join(timeout=10)
    assert not thread.is_alive()


def test_escolher_audio_preenche_o_campo(janela, monkeypatch, tmp_path):
    escolhido = tmp_path / "aula 3.m4a"
    monkeypatch.setattr(
        modulo.filedialog, "askopenfilename", lambda **opcoes: escolhido.as_posix()
    )

    janela.escolher_audio()

    assert janela.audio.get() == str(escolhido)


def test_cancelar_a_escolha_mantem_o_audio_anterior(janela, monkeypatch):
    janela.audio.set("aula.mp3")
    monkeypatch.setattr(modulo.filedialog, "askopenfilename", lambda **opcoes: "")

    janela.escolher_audio()

    assert janela.audio.get() == "aula.mp3"
