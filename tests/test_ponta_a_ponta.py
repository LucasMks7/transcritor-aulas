"""O programa inteiro, com o modelo de verdade e um áudio de verdade.

Os outros testes trocam o Whisper por um dublê e por isso não percebem, por
exemplo, uma atualização do faster-whisper que mude o formato dos segmentos.
Este roda o comando como quem usa, com o menor modelo (tiny, 75 MB) e uma
leitura de 3 minutos em domínio público.

Fica fora do pytest comum, por baixar o modelo e levar uns 20 segundos:

    python scripts/baixar_amostra.py
    pytest -m ponta_a_ponta
"""

import os
from pathlib import Path

import pytest

from transcritor.avaliacao import taxa_de_erro
from transcritor.cli import main

pytestmark = pytest.mark.ponta_a_ponta

AMOSTRAS = Path(__file__).resolve().parent.parent / "amostras"
AUDIO = AMOSTRAS / "alienista-cap11.mp3"
REFERENCIA = AMOSTRAS / "alienista-cap11.txt"

# O tiny errou 14,6% nesta amostra (docs/comparacao-modelos.md). A margem cobre
# pequenas diferenças entre máquinas e versões; passar disso indica defeito.
ERRO_MAXIMO = 0.25


@pytest.fixture(scope="module")
def audio():
    if not AUDIO.is_file():
        mensagem = "amostra ausente: rode python scripts/baixar_amostra.py"
        # No CI, um teste pulado passaria despercebido como se tivesse dado certo.
        if os.environ.get("EXIGIR_AMOSTRA"):
            pytest.fail(mensagem)
        pytest.skip(mensagem)
    return AUDIO


@pytest.fixture(scope="module")
def transcrito(audio, tmp_path_factory):
    """Transcreve uma vez só e compartilha o resultado com os testes do módulo."""
    saida = tmp_path_factory.mktemp("ponta_a_ponta") / "alienista.txt"
    codigo = main([str(audio), "--saida", str(saida), "--modelo", "tiny", "--dispositivo", "cpu"])
    return codigo, saida


def test_o_comando_termina_com_sucesso(transcrito):
    codigo, saida = transcrito

    assert codigo == 0
    assert saida.is_file()
    assert saida.with_suffix(".pdf").is_file()


def test_a_transcricao_fica_perto_do_texto_do_livro(transcrito):
    _, saida = transcrito

    erro = taxa_de_erro(REFERENCIA.read_text(encoding="utf-8"), saida.read_text(encoding="utf-8"))

    assert erro < ERRO_MAXIMO


def test_o_pdf_traz_o_texto_e_os_tempos_em_ordem(transcrito, ler_pdf):
    _, saida = transcrito

    texto = ler_pdf(saida.with_suffix(".pdf"))

    assert "Duração: 02:59" in texto
    # Maiúsculas variam de modelo para modelo; a expressão em si não deveria.
    assert "casa verde" in texto.lower()
    # Os parágrafos começam com o tempo em que aparecem no áudio, em ordem.
    tempos = [linha for linha in texto.splitlines() if len(linha) == 5 and linha[2] == ":"]
    assert tempos[0] == "00:00"
    assert tempos == sorted(tempos)
    assert len(tempos) > 1
