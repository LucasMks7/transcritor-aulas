"""Pastas de destino no Drive com um Drive falso em memória: nada sai do PC."""

import pytest

from transcritor import drive, pastas, preferencias
from transcritor.pastas import (
    FalhaNoDrive,
    Pasta,
    criar_pasta,
    escolher_pasta,
    listar_pastas,
    obter_ou_criar,
)


class Pedido:
    def __init__(self, resposta=None, erro=None):
        self.resposta = resposta
        self.erro = erro

    def execute(self):
        if self.erro:
            raise self.erro
        return self.resposta


class DriveFalso:
    """Imita servico.files().list(...).execute() e .create(...).execute().

    Guarda as consultas recebidas para os testes conferirem o filtro enviado
    ao Google, e entrega as pastas em páginas do tamanho escolhido.
    """

    def __init__(self, nomes=(), por_pagina=100, erro=None):
        self.pastas = [Pasta(f"id-{i}", nome) for i, nome in enumerate(nomes)]
        self.por_pagina = por_pagina
        self.erro = erro
        self.consultas = []
        self.criadas = []

    def files(self):
        return self

    def list(self, q, pageToken=None, **_):
        self.consultas.append(q)
        if self.erro:
            return Pedido(erro=self.erro)
        encontradas = sorted(self.pastas, key=lambda p: p.nome)
        if " and name = " in q:
            nome = q.split(" and name = ", 1)[1][1:-1].replace("\\'", "'").replace("\\\\", "\\")
            encontradas = [p for p in encontradas if p.nome == nome]
        inicio = int(pageToken or 0)
        pagina = encontradas[inicio : inicio + self.por_pagina]
        resposta = {"files": [{"id": p.id, "name": p.nome} for p in pagina]}
        if inicio + self.por_pagina < len(encontradas):
            resposta["nextPageToken"] = str(inicio + self.por_pagina)
        return Pedido(resposta)

    def create(self, body, **_):
        if self.erro:
            return Pedido(erro=self.erro)
        assert body["mimeType"] == pastas.TIPO_PASTA
        pasta = Pasta(f"novo-{len(self.criadas)}", body["name"])
        self.criadas.append(pasta)
        self.pastas.append(pasta)
        return Pedido({"id": pasta.id, "name": pasta.nome})


def respostas(*textos):
    fila = list(textos)
    return lambda _pergunta: fila.pop(0)


def test_lista_so_pastas_fora_da_lixeira_em_ordem_alfabetica():
    servico = DriveFalso(["Química", "Física"])

    assert [p.nome for p in listar_pastas(servico)] == ["Física", "Química"]
    assert "mimeType = 'application/vnd.google-apps.folder'" in servico.consultas[0]
    assert "trashed = false" in servico.consultas[0]


def test_lista_junta_todas_as_paginas():
    servico = DriveFalso([f"Aula {n:02}" for n in range(5)], por_pagina=2)

    assert len(listar_pastas(servico)) == 5
    assert len(servico.consultas) == 3


def test_sem_pastas_a_lista_vem_vazia():
    assert listar_pastas(DriveFalso()) == []


def test_cria_pasta_com_espacos_arrumados():
    servico = DriveFalso()

    pasta = criar_pasta(servico, "  Aulas   de Cálculo ")

    assert pasta == Pasta("novo-0", "Aulas de Cálculo")


def test_nome_vazio_nao_cria_pasta():
    servico = DriveFalso()

    with pytest.raises(ValueError, match="vazio"):
        criar_pasta(servico, "   ")
    assert servico.criadas == []


def test_obter_ou_criar_reaproveita_a_pasta_com_o_mesmo_nome():
    servico = DriveFalso(["Áudios"])

    assert obter_ou_criar(servico, "Áudios") == Pasta("id-0", "Áudios")
    assert servico.criadas == []


def test_obter_ou_criar_cria_quando_nao_existe():
    servico = DriveFalso(["Outra"])

    assert obter_ou_criar(servico, "Áudios").nome == "Áudios"
    assert len(servico.criadas) == 1


def test_aspas_no_nome_nao_quebram_a_busca():
    servico = DriveFalso(["Aula d'água"])

    assert obter_ou_criar(servico, "Aula d'água").id == "id-0"
    assert "name = 'Aula d\\'água'" in servico.consultas[0]


def test_falha_do_drive_vira_mensagem_clara():
    servico = DriveFalso(erro=OSError("sem internet"))

    with pytest.raises(FalhaNoDrive, match="não respondeu"):
        listar_pastas(servico)


def test_escolher_pelo_numero():
    servico = DriveFalso(["A", "B"])

    escolhida = escolher_pasta(servico, "o áudio", "Padrão", respostas("2"), lambda _: None)

    assert escolhida.nome == "B"
    assert servico.criadas == []


def test_escolher_numero_fora_da_lista_pergunta_de_novo():
    servico = DriveFalso(["A"])
    mensagens = []

    escolhida = escolher_pasta(servico, "o áudio", "Padrão", respostas("7", "1"), mensagens.append)

    assert escolhida.nome == "A"
    assert any("Não há pasta número 7" in m for m in mensagens)


def test_resposta_vazia_usa_o_nome_padrao():
    servico = DriveFalso()

    escolhida = escolher_pasta(servico, "o áudio", "Transcritor - Áudios", respostas(""), print)

    assert escolhida.nome == "Transcritor - Áudios"


def test_digitar_um_nome_cria_a_pasta_nova():
    servico = DriveFalso(["A"])

    escolhida = escolher_pasta(servico, "o áudio", "Padrão", respostas("Cálculo II"), print)

    assert escolhida.nome == "Cálculo II"
    assert len(servico.criadas) == 1


def test_sem_pastas_um_numero_vira_nome_de_pasta():
    servico = DriveFalso()

    assert escolher_pasta(servico, "o áudio", "Padrão", respostas("2026"), print).nome == "2026"


def test_comando_pastas_lista_os_nomes(monkeypatch, capsys):
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: DriveFalso(["Física"]))

    assert drive.main(["pastas"]) == 0
    assert capsys.readouterr().out.strip() == "Física"


def test_comando_pasta_audio_com_nome_nao_pergunta(monkeypatch, capsys):
    servico = DriveFalso()
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: servico)
    monkeypatch.setattr("builtins.input", lambda _p: pytest.fail("não devia perguntar"))

    assert drive.main(["pasta-audio", "--nome", "Áudios"]) == 0
    assert "Pasta do áudio: Áudios (id novo-0)" in capsys.readouterr().out


def test_comando_pasta_audio_com_drive_fora_do_ar(monkeypatch, capsys):
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: DriveFalso(erro=OSError("rede")))

    assert drive.main(["pasta-audio", "--nome", "Áudios"]) == 1
    assert "erro: o Google Drive não respondeu" in capsys.readouterr().err


def test_audio_e_pdf_tem_nomes_padrao_diferentes():
    # Pastas padrão separadas: o PDF não se perde no meio de horas de áudio.
    assert pastas.DESTINOS["audio"].nome_padrao != pastas.DESTINOS["pdf"].nome_padrao


def test_comando_pasta_pdf_com_nome(monkeypatch, capsys):
    servico = DriveFalso()
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: servico)

    assert drive.main(["pasta-pdf", "--nome", "PDFs de Física"]) == 0
    assert "Pasta do PDF: PDFs de Física (id novo-0)" in capsys.readouterr().out


def test_comando_pasta_pdf_sem_resposta_cria_a_pasta_padrao_do_pdf(monkeypatch, capsys):
    servico = DriveFalso(["Transcritor - Áudios"])
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: servico)
    monkeypatch.setattr("builtins.input", lambda _p: "")

    assert drive.main(["pasta-pdf"]) == 0
    saida = capsys.readouterr().out
    assert "para o PDF" in saida
    assert "Pasta do PDF: Transcritor - PDFs" in saida


def test_a_pasta_escolhida_vale_para_os_proximos_usos(monkeypatch, capsys):
    servico = DriveFalso()
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: servico)
    assert drive.main(["pasta-audio", "--nome", "Física"]) == 0
    assert drive.main(["pasta-pdf", "--nome", "Resumos"]) == 0

    assert preferencias.carregar().nomes_das_pastas() == {"audio": "Física", "pdf": "Resumos"}

    # Enter mantém a pasta em uso.
    monkeypatch.setattr("builtins.input", lambda _p: "")
    assert drive.main(["pasta-audio"]) == 0
    assert preferencias.carregar().pasta_audio == "Física"


def test_pdf_pode_ir_para_a_mesma_pasta_do_audio(monkeypatch, capsys):
    servico = DriveFalso(["Transcritor - Áudios"])
    monkeypatch.setattr(drive, "conectar", lambda: object())
    monkeypatch.setattr(drive, "servico_do_drive", lambda _c: servico)
    monkeypatch.setattr("builtins.input", lambda _p: "1")

    assert drive.main(["pasta-pdf"]) == 0
    assert "Pasta do PDF: Transcritor - Áudios (id id-0)" in capsys.readouterr().out
    assert servico.criadas == []
