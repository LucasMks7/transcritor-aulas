import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

from transcritor import arquivos, preferencias
from transcritor import janela as modulo
from transcritor.arquivos import SaidaInvalida, caminho_parcial
from transcritor.audio import AudioInvalido
from transcritor.drive import FalhaNaAutorizacao
from transcritor.entrega import Entrega
from transcritor.envio import ArquivoNoDrive
from transcritor.janela import (
    TEXTO_CANCELADO,
    TEXTO_CANCELANDO,
    TEXTO_CARREGANDO,
    TEXTO_CONECTANDO,
    TEXTO_GERANDO_PDF,
    TEXTO_INICIAL,
    TEXTO_PRIVACIDADE,
    TEXTO_PRIVACIDADE_COM_DRIVE,
    Andamento,
    Janela,
    Pedido,
    Resultado,
    executar,
    preparar_pedido,
    reenviar,
)
from transcritor.pastas import AutorizacaoExpirada
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


PASTAS = {"audio": "Física", "pdf": "Resumos"}


@pytest.fixture
def drive_falso(monkeypatch):
    """Troca a conexão e o envio por dublês. Anota o que seria enviado."""
    falso = SimpleNamespace(enviados=[], erros={}, conexoes=0)

    def conectar():
        falso.conexoes += 1
        return "serviço"

    def entregar(servico, lista, nomes, ao_progredir, ao_repetir, esperar):
        assert servico == "serviço"
        for arquivo in lista:
            ao_progredir(arquivo, 50, 100)
            pasta = nomes["pdf" if arquivo.suffix == ".pdf" else "audio"]
            if arquivo.suffix in falso.erros:
                yield Entrega(arquivo, pasta, erro=falso.erros[arquivo.suffix])
                continue
            falso.enviados.append((arquivo.name, pasta))
            yield Entrega(arquivo, pasta, ArquivoNoDrive("id", arquivo.name, "link"))

    monkeypatch.setattr(modulo, "conectar_ao_drive", conectar)
    monkeypatch.setattr(modulo, "entregar", entregar)
    return falso


def test_sem_pedir_o_envio_nada_fala_com_o_drive(audio, modelo_que_funciona, drive_falso):
    executar(Pedido(audio, 1.0), lambda aviso: None, threading.Event())

    assert drive_falso.conexoes == 0
    assert drive_falso.enviados == []


def test_envia_o_pdf_e_o_audio_para_as_pastas_pedidas(audio, modelo_que_funciona, drive_falso):
    avisos = []

    executar(Pedido(audio, 1.0, PASTAS), avisos.append, threading.Event())

    assert avisos[0] == Andamento(TEXTO_CONECTANDO)
    assert Andamento("Enviando aula.mp3 ao Drive (50%)", 50) in avisos
    assert drive_falso.enviados == [("aula.pdf", "Resumos"), ("aula.mp3", "Física")]
    assert avisos[-1].sucesso
    assert "estão no seu Drive" in avisos[-1].texto


def test_sem_acesso_ao_drive_a_aula_e_transcrita_mesmo_assim(
    audio, modelo_que_funciona, drive_falso, monkeypatch
):
    def falhar():
        raise FalhaNaAutorizacao("sem conexão com a internet")

    monkeypatch.setattr(modulo, "conectar_ao_drive", falhar)
    avisos = []

    executar(Pedido(audio, 1.0, PASTAS), avisos.append, threading.Event())

    resultado = avisos[-1]
    assert not resultado.sucesso
    assert resultado.pdf.is_file()
    assert "sem conexão com a internet" in resultado.texto


def test_falha_no_envio_de_um_arquivo_aparece_no_resultado(
    audio, modelo_que_funciona, drive_falso
):
    drive_falso.erros[".mp3"] = "não há espaço livre no seu Google Drive"
    avisos = []

    executar(Pedido(audio, 1.0, PASTAS), avisos.append, threading.Event())

    assert drive_falso.enviados == [("aula.pdf", "Resumos")]
    assert not avisos[-1].sucesso
    assert avisos[-1].pdf.is_file()
    assert "não há espaço livre" in avisos[-1].texto


def test_autorizacao_expirada_no_envio_orienta_a_entrar_de_novo(
    audio, modelo_que_funciona, drive_falso, monkeypatch
):
    def expirar(*_):
        raise AutorizacaoExpirada("a autorização do Google expirou")

    monkeypatch.setattr(modulo, "entregar", expirar)
    avisos = []

    executar(Pedido(audio, 1.0, PASTAS), avisos.append, threading.Event())

    assert "Clique em Enviar de novo" in avisos[-1].texto
    assert avisos[-1].falta_enviar


def test_reenviar_manda_os_arquivos_sem_transcrever(audio, drive_falso, monkeypatch):
    monkeypatch.setattr(modulo, "carregar_modelo", pytest.fail)
    pdf = audio.with_suffix(".pdf")
    avisos = []

    reenviar(Pedido(audio, 1.0, PASTAS), pdf, avisos.append, threading.Event())

    assert drive_falso.enviados == [("aula.pdf", "Resumos"), ("aula.mp3", "Física")]
    assert avisos[-1] == Resultado(
        True, f"PDF salvo em: {pdf}. O áudio e o PDF estão no seu Drive.", pdf
    )


@pytest.mark.parametrize(
    "erro", [FalhaNaAutorizacao("o Google Drive não respondeu"), ValueError("imprevisto")]
)
def test_reenviar_sem_conexao_continua_podendo_tentar(audio, drive_falso, monkeypatch, erro):
    def falhar():
        raise erro

    monkeypatch.setattr(modulo, "conectar_ao_drive", falhar)
    avisos = []

    reenviar(Pedido(audio, 1.0, PASTAS), audio, avisos.append, threading.Event())

    assert avisos[-1].falta_enviar
    assert str(erro) in avisos[-1].texto


def test_audio_incompleto_avisa_junto_com_o_resultado(audio, modelo_que_funciona):
    avisos = []

    executar(Pedido(audio, 60.0), avisos.append, threading.Event())

    assert avisos[-1].sucesso
    assert "o arquivo diz ter 01:00, mas só 00:01 puderam ser lidos" in avisos[-1].texto


def test_cancelar_durante_o_envio_mantem_o_pdf(audio, modelo_que_funciona, drive_falso):
    cancelamento = threading.Event()
    avisos = []

    def avisar(mensagem):
        avisos.append(mensagem)
        if mensagem.texto.startswith("Enviando ao Drive"):
            cancelamento.set()

    executar(Pedido(audio, 1.0, PASTAS), avisar, cancelamento)

    assert drive_falso.enviados == []
    assert "o envio foi cancelado" in avisos[-1].texto
    assert avisos[-1].pdf.is_file()


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


def test_as_pastas_so_podem_ser_editadas_com_o_envio_ligado(janela):
    assert [estado(campo) for campo in janela.campos_das_pastas] == ["disabled"] * 2
    assert janela.privacidade.get() == TEXTO_PRIVACIDADE

    janela.caixa_enviar.invoke()

    assert [estado(campo) for campo in janela.campos_das_pastas] == ["normal"] * 2
    assert janela.privacidade.get() == TEXTO_PRIVACIDADE_COM_DRIVE


def test_transcrever_lembra_das_escolhas(janela, audio, modelo_que_funciona, drive_falso):
    janela.audio.set(str(audio))
    janela.caixa_enviar.invoke()
    janela.pasta_audio.set("  Física   I ")
    janela.pasta_pdf.set("")

    janela.iniciar()
    esperar_o_fim(janela)

    # A pasta em branco volta para o padrão, e isso aparece no campo.
    assert janela.pasta_pdf.get() == "Transcritor - PDFs"
    assert drive_falso.enviados == [
        ("aula.pdf", "Transcritor - PDFs"),
        ("aula.mp3", "Física I"),
    ]
    assert preferencias.carregar() == preferencias.Preferencias(
        True, "Física I", "Transcritor - PDFs", str(audio.resolve().parent)
    )


def test_enviar_de_novo_so_fica_disponivel_depois_de_uma_falha(
    janela, audio, modelo_que_funciona, drive_falso
):
    drive_falso.erros[".mp3"] = "a conexão falhou"
    janela.audio.set(str(audio))
    janela.caixa_enviar.invoke()
    assert estado(janela.botao_reenviar) == "disabled"

    janela.iniciar()
    assert estado(janela.botao_reenviar) == "disabled"
    esperar_o_fim(janela)

    assert estado(janela.botao_reenviar) == "normal"
    assert estado(janela.botao_abrir) == "normal"

    # A pessoa troca a pasta, a internet volta, e só o envio é refeito.
    drive_falso.erros.clear()
    drive_falso.enviados.clear()
    janela.pasta_audio.set("Outra")
    janela.reenviar()
    esperar_o_fim(janela)

    assert drive_falso.enviados == [("aula.pdf", "Transcritor - PDFs"), ("aula.mp3", "Outra")]
    assert estado(janela.botao_reenviar) == "disabled"
    assert estado(janela.botao_abrir) == "normal"


def test_a_janela_abre_com_o_que_foi_lembrado(tk_da_sessao, monkeypatch, tmp_path):
    preferencias.salvar(preferencias.Preferencias(True, "Física", "Resumos", str(tmp_path)))
    topo = tk.Toplevel(tk_da_sessao)
    topo.withdraw()
    janela = Janela(topo)
    pedidos = []
    monkeypatch.setattr(
        modulo.filedialog, "askopenfilename", lambda **opcoes: pedidos.append(opcoes) or ""
    )

    janela.escolher_audio()

    assert janela.enviar.get()
    assert (janela.pasta_audio.get(), janela.pasta_pdf.get()) == ("Física", "Resumos")
    assert pedidos[0]["initialdir"] == tmp_path
    topo.destroy()


def test_nao_conseguir_lembrar_nao_impede_a_transcricao(
    janela, audio, modelo_que_funciona, monkeypatch
):
    def falhar(escolhas):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(preferencias, "salvar", falhar)
    janela.audio.set(str(audio))

    janela.iniciar()
    esperar_o_fim(janela)

    assert janela.situacao.get().startswith("Pronto!")


def test_durante_o_trabalho_as_opcoes_de_envio_ficam_travadas(
    janela, audio, modelo_que_funciona, drive_falso
):
    janela.audio.set(str(audio))
    janela.caixa_enviar.invoke()

    janela.iniciar()

    assert estado(janela.caixa_enviar) == "disabled"
    assert [estado(campo) for campo in janela.campos_das_pastas] == ["disabled"] * 2
    esperar_o_fim(janela)
    assert estado(janela.caixa_enviar) == "normal"
    assert [estado(campo) for campo in janela.campos_das_pastas] == ["normal"] * 2


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
