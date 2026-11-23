import json

import pytest

from transcritor import preferencias
from transcritor.preferencias import Preferencias, caminho_das_preferencias, carregar, salvar


def gravar(conteudo: str) -> None:
    caminho = caminho_das_preferencias()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")


def test_sem_nada_salvo_nada_e_enviado():
    assert carregar() == Preferencias()
    assert carregar().enviar_ao_drive is False


def test_o_que_foi_salvo_volta_igual():
    escolhas = Preferencias(True, "Áudios de Física", "Resumos d'água", "C:\\Aulas")

    salvar(escolhas)

    assert carregar() == escolhas
    # Não sobra o arquivo parcial.
    pasta = caminho_das_preferencias().parent
    assert [arquivo.name for arquivo in pasta.iterdir()] == ["preferencias.json"]


@pytest.mark.parametrize("conteudo", ["", "{", "[]", "null", '"texto"', "\x00\x01"])
def test_arquivo_estragado_volta_para_o_padrao(conteudo):
    gravar(conteudo)

    assert carregar() == Preferencias()


def test_bytes_que_nao_sao_texto_voltam_para_o_padrao():
    gravar("")
    caminho_das_preferencias().write_bytes(b"\xff\xfe\x00\xd8")

    assert carregar() == Preferencias()


def test_so_o_campo_errado_e_ignorado():
    gravar(json.dumps({"enviar_ao_drive": "sim", "pasta_audio": "Física", "do_futuro": 1}))

    assert carregar() == Preferencias(pasta_audio="Física")


def test_pasta_em_branco_volta_para_o_padrao():
    gravar(json.dumps({"pasta_audio": "   ", "pasta_pdf": "  Meus   PDFs "}))

    assert carregar() == Preferencias(pasta_pdf="Meus PDFs")


def test_falha_ao_gravar_nao_estraga_o_que_ja_estava_salvo(monkeypatch):
    salvar(Preferencias(pasta_audio="Física"))

    def falhar(*_, **__):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(preferencias.Path, "write_text", falhar)
    with pytest.raises(OSError):
        salvar(Preferencias(pasta_audio="Química"))

    assert carregar().pasta_audio == "Física"
