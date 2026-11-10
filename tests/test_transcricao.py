import numpy as np
import pytest

from transcritor.transcricao import (
    FalhaNaTranscricao,
    Segmento,
    carregar_modelo,
    dividir_em_blocos,
    ponto_mais_silencioso,
    transcrever,
)

TAXA = 16_000


@pytest.fixture
def audio(criar_audio):
    """Dois segundos de áudio de verdade, lidos pelo mesmo caminho do programa."""
    return criar_audio("aula.wav", segundos=2.0)


def test_transcrever_devolve_os_segmentos_sem_espacos_nas_pontas(audio, criar_modelo):
    modelo = criar_modelo(" Bom dia, turma.", " Hoje o assunto é outro.", duracao=2.0)

    transcricao = transcrever(audio, modelo)

    assert transcricao.segmentos == (
        Segmento(0.0, 1.0, "Bom dia, turma."),
        Segmento(1.0, 2.0, "Hoje o assunto é outro."),
    )
    assert transcricao.duracao == pytest.approx(2.0, abs=0.01)


def test_transcrever_entrega_as_amostras_e_pede_portugues(audio, criar_modelo):
    modelo = criar_modelo("Bom dia.")

    transcrever(audio, modelo)

    amostras, opcoes = modelo.chamadas[0]
    assert len(amostras) == pytest.approx(2.0 * TAXA, abs=160)
    assert opcoes["language"] == "pt"
    # Sem o filtro de silêncio, o Whisper inventa texto nos trechos sem fala.
    assert opcoes["vad_filter"] is True


def test_texto_traz_um_segmento_por_linha(audio, criar_modelo):
    transcricao = transcrever(audio, criar_modelo("Bom dia, turma.", "Vamos começar."))

    assert transcricao.texto == "Bom dia, turma.\nVamos começar."


def test_audio_sem_fala_vira_transcricao_vazia(audio, criar_modelo):
    transcricao = transcrever(audio, criar_modelo())

    assert transcricao.segmentos == ()
    assert transcricao.texto == ""


def test_cada_trecho_pronto_e_avisado_com_a_duracao_total(audio, criar_modelo):
    modelo = criar_modelo(" Bom dia.", " Vamos começar.", duracao=2.0)
    avisos = []

    transcrever(audio, modelo, lambda segmento, total: avisos.append((segmento, total)))

    assert [segmento for segmento, _ in avisos] == [
        Segmento(0.0, 1.0, "Bom dia."),
        Segmento(1.0, 2.0, "Vamos começar."),
    ]
    assert [total for _, total in avisos] == [pytest.approx(2.0, abs=0.01)] * 2


def test_os_trechos_sao_avisados_um_a_um_e_nao_so_no_fim(audio, criar_modelo):
    """Em uma aula longa, o aviso precisa sair enquanto a transcrição acontece."""
    modelo = criar_modelo(" Bom dia.", falha=RuntimeError("faltou memória"))
    avisos = []

    with pytest.raises(FalhaNaTranscricao):
        transcrever(audio, modelo, lambda segmento, total: avisos.append(segmento.texto))

    assert avisos == ["Bom dia."]


@pytest.mark.parametrize("falha", [RuntimeError("faltou memória"), MemoryError()])
def test_falha_no_meio_vira_mensagem_que_diz_ate_onde_foi(audio, criar_modelo, falha):
    modelo = criar_modelo(" Bom dia.", " Vamos começar.", falha=falha)

    with pytest.raises(FalhaNaTranscricao, match="depois de 2 trechos"):
        transcrever(audio, modelo)


def test_audio_longo_vai_para_o_modelo_em_blocos(audio, criar_modelo):
    """O modelo nunca recebe a aula inteira de uma vez, o que estouraria a memória."""
    # O dublê devolve um segmento que ocupa o primeiro meio segundo de cada bloco.
    modelo = criar_modelo(" Trecho.", duracao=0.5)

    transcrever(audio, modelo, segundos_por_bloco=0.5)

    tamanhos = [len(amostras) for amostras, _ in modelo.chamadas]
    assert len(tamanhos) >= 4
    assert max(tamanhos) <= 0.5 * TAXA
    # Nenhuma amostra fica de fora nem é transcrita duas vezes.
    assert sum(tamanhos) == pytest.approx(2.0 * TAXA, abs=160)


def test_os_tempos_de_cada_bloco_sao_contados_desde_o_comeco_do_audio(audio, criar_modelo):
    modelo = criar_modelo(" Trecho.", duracao=0.5)

    transcricao = transcrever(audio, modelo, segundos_por_bloco=0.5)

    inicios = [segmento.inicio for segmento in transcricao.segmentos]
    assert inicios[0] == 0.0
    assert inicios == sorted(inicios)
    # O último bloco começa perto do fim, e não em zero.
    assert inicios[-1] > 1.0
    for segmento in transcricao.segmentos:
        assert segmento.fim == pytest.approx(segmento.inicio + 0.5)


def ruido(segundos: float) -> np.ndarray:
    gerador = np.random.default_rng(0)
    return gerador.uniform(-0.5, 0.5, int(segundos * TAXA)).astype(np.float32)


def test_ponto_mais_silencioso_fica_dentro_da_pausa():
    amostras = ruido(3.0)
    amostras[int(1.6 * TAXA) : int(2.2 * TAXA)] = 0.0

    ponto = ponto_mais_silencioso(amostras)

    assert 1.6 * TAXA <= ponto <= 2.2 * TAXA


def test_blocos_cortam_na_pausa_e_nao_no_meio_da_fala():
    amostras = ruido(25.0)
    # Uma pausa de meio segundo pouco antes da marca dos 10 segundos.
    amostras[int(8.0 * TAXA) : int(8.5 * TAXA)] = 0.0

    blocos = dividir_em_blocos(amostras, segundos_por_bloco=10, segundos_de_busca=3)

    primeiro_corte = blocos[0][1]
    assert 8.0 * TAXA <= primeiro_corte <= 8.5 * TAXA


def test_blocos_cobrem_o_audio_inteiro_sem_sobras_nem_sobreposicao():
    amostras = ruido(25.0)

    blocos = dividir_em_blocos(amostras, segundos_por_bloco=10, segundos_de_busca=3)

    assert blocos[0][0] == 0
    assert blocos[-1][1] == len(amostras)
    for (_, fim), (inicio, _) in zip(blocos, blocos[1:]):
        assert fim == inicio
    assert all(0 < fim - inicio <= 10 * TAXA for inicio, fim in blocos)


def test_audio_menor_que_um_bloco_fica_inteiro():
    amostras = ruido(4.0)

    assert dividir_em_blocos(amostras, segundos_por_bloco=10) == [(0, len(amostras))]


def test_audio_vazio_nao_tem_blocos():
    assert dividir_em_blocos(np.zeros(0, dtype=np.float32)) == []


def test_carregar_modelo_usa_o_processador_com_int8(monkeypatch):
    import faster_whisper

    pedidos = []

    def criar(nome, **opcoes):
        pedidos.append((nome, opcoes))
        return "modelo carregado"

    monkeypatch.setattr(faster_whisper, "WhisperModel", criar)

    assert carregar_modelo("small") == "modelo carregado"
    assert pedidos == [("small", {"device": "cpu", "compute_type": "int8"})]


def test_falha_ao_carregar_o_modelo_vira_mensagem_clara(monkeypatch):
    import faster_whisper

    def falhar(nome, **opcoes):
        raise OSError("sem conexão")

    monkeypatch.setattr(faster_whisper, "WhisperModel", falhar)

    with pytest.raises(FalhaNaTranscricao, match="modelo small.*sem conexão"):
        carregar_modelo("small")
