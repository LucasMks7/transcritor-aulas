import pytest
from faster_whisper.audio import decode_audio

from transcritor.audio import AudioInvalido, conferir_audio

FORMATOS = ["aula.wav", "aula.mp3", "aula.m4a", "aula.ogg", "aula.flac"]


@pytest.mark.parametrize("nome", FORMATOS)
def test_aceita_os_formatos_comuns_e_informa_a_duracao(criar_audio, nome):
    audio = criar_audio(nome, segundos=2.0)

    # Os formatos com compressão acrescentam alguns milissegundos nas pontas.
    assert conferir_audio(audio) == pytest.approx(2.0, abs=0.15)


@pytest.mark.parametrize("nome", FORMATOS)
def test_o_faster_whisper_le_os_mesmos_formatos(criar_audio, nome):
    """Cobre o caminho de verdade: o áudio vira amostras a 16 kHz para o modelo."""
    audio = criar_audio(nome, segundos=2.0)

    amostras = decode_audio(str(audio), sampling_rate=16_000)

    assert len(amostras) == pytest.approx(2.0 * 16_000, rel=0.08)


def test_a_extensao_nao_importa_e_sim_o_conteudo(criar_audio, tmp_path):
    audio = criar_audio("aula.mp3")
    renomeado = audio.rename(tmp_path / "gravacao-da-aula.dat")

    assert conferir_audio(renomeado) == pytest.approx(1.0, abs=0.15)


def test_arquivo_inexistente_e_recusado(tmp_path):
    with pytest.raises(AudioInvalido, match="arquivo não encontrado"):
        conferir_audio(tmp_path / "sumiu.mp3")


def test_pasta_e_recusada(tmp_path):
    with pytest.raises(AudioInvalido, match="arquivo não encontrado"):
        conferir_audio(tmp_path)


@pytest.mark.parametrize("conteudo", [b"", b"isto nao e um audio"])
def test_arquivo_que_nao_e_audio_e_recusado(tmp_path, conteudo):
    falso = tmp_path / "falso.mp3"
    falso.write_bytes(conteudo)

    with pytest.raises(AudioInvalido, match="não é um áudio ou vídeo"):
        conferir_audio(falso)


def test_imagem_e_recusada_por_nao_ter_audio(tmp_path):
    # O menor PNG válido: um ponto transparente. O PyAV abre, mas não acha som.
    imagem = tmp_path / "quadro.png"
    imagem.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
        )
    )

    with pytest.raises(AudioInvalido, match="não tem áudio"):
        conferir_audio(imagem)
