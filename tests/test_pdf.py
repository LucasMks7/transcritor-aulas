from datetime import date

from pypdf import PdfReader

from transcritor.pdf import (
    Cabecalho,
    Paragrafo,
    agrupar_em_paragrafos,
    gerar_pdf,
    para_fonte_do_pdf,
)
from transcritor.transcricao import Segmento

CABECALHO = Cabecalho("Aula 3 - Introdução à Química", 3725.0, "small", date(2026, 11, 10))


def test_segmentos_seguidos_formam_um_paragrafo():
    segmentos = [Segmento(0.0, 2.0, "Bom dia, turma."), Segmento(2.5, 4.0, "Vamos começar.")]

    assert agrupar_em_paragrafos(segmentos) == [
        Paragrafo(0.0, "Bom dia, turma. Vamos começar.")
    ]


def test_pausa_longa_abre_um_paragrafo_novo():
    segmentos = [
        Segmento(0.0, 2.0, "Primeiro assunto."),
        Segmento(5.0, 7.0, "Segundo assunto."),
    ]

    assert agrupar_em_paragrafos(segmentos) == [
        Paragrafo(0.0, "Primeiro assunto."),
        Paragrafo(5.0, "Segundo assunto."),
    ]


def test_fala_sem_pausas_e_quebrada_pelo_tamanho():
    # Dez minutos de fala corrida, um segmento a cada 5 segundos.
    segmentos = [Segmento(i * 5.0, i * 5.0 + 5.0, f"frase {i}.") for i in range(120)]

    paragrafos = agrupar_em_paragrafos(segmentos, duracao_desejada=90.0)

    assert [p.inicio for p in paragrafos][:3] == [0.0, 90.0, 180.0]
    # Nenhuma frase se perde na divisão.
    assert " ".join(p.texto for p in paragrafos) == " ".join(s.texto for s in segmentos)


def test_paragrafo_longo_espera_o_fim_da_frase_para_terminar():
    segmentos = [
        Segmento(0.0, 85.0, "Começo da explicação."),
        Segmento(85.0, 95.0, "O edifício que ia construir,"),
        Segmento(95.0, 100.0, "com cinquenta janelas."),
        Segmento(100.0, 105.0, "Outro assunto."),
    ]

    paragrafos = agrupar_em_paragrafos(segmentos, duracao_desejada=90.0)

    assert [p.texto for p in paragrafos] == [
        "Começo da explicação. O edifício que ia construir, com cinquenta janelas.",
        "Outro assunto.",
    ]


def test_fala_sem_pontuacao_e_quebrada_no_tamanho_maximo():
    segmentos = [Segmento(i * 5.0, i * 5.0 + 5.0, "sem ponto") for i in range(100)]

    paragrafos = agrupar_em_paragrafos(segmentos, duracao_desejada=90.0, duracao_maxima=180.0)

    assert [p.inicio for p in paragrafos][:3] == [0.0, 180.0, 360.0]


def test_segmentos_vazios_sao_ignorados():
    segmentos = [Segmento(0.0, 1.0, ""), Segmento(1.0, 2.0, "Texto.")]

    assert agrupar_em_paragrafos(segmentos) == [Paragrafo(1.0, "Texto.")]


def test_sem_segmentos_nao_ha_paragrafos():
    assert agrupar_em_paragrafos([]) == []


def test_acentos_do_portugues_ficam_como_estao():
    texto = "Ação, coração, à Câmara, pôde, pêssego, órgão, ü"

    assert para_fonte_do_pdf(texto) == texto


def test_pontuacao_tipografica_vira_a_versao_simples():
    assert para_fonte_do_pdf("“Olá” — disse ele… ‘né’") == "\"Olá\" - disse ele... 'né'"


def test_caractere_fora_da_fonte_vira_interrogacao_sem_quebrar():
    assert para_fonte_do_pdf("Łódź 🎓") == "?ód? ?"


def test_pdf_traz_titulo_dados_da_transcricao_e_texto(tmp_path, ler_pdf):
    destino = tmp_path / "aula.pdf"
    segmentos = [
        Segmento(0.0, 2.0, "Bom dia, turma."),
        Segmento(125.0, 128.0, "Agora, a “tabela periódica”."),
    ]

    gerar_pdf(segmentos, CABECALHO, destino)

    texto = ler_pdf(destino)
    assert "Aula 3 - Introdução à Química" in texto
    assert "Duração: 1:02:05" in texto
    assert "10/11/2026" in texto
    assert "modelo small" in texto
    # Cada parágrafo começa com o tempo em que aparece no áudio.
    assert "00:00\nBom dia, turma." in texto
    assert '02:05\nAgora, a "tabela periódica".' in texto


def test_pdf_leva_o_titulo_nos_metadados(tmp_path):
    destino = tmp_path / "aula.pdf"

    gerar_pdf([Segmento(0.0, 1.0, "Oi.")], CABECALHO, destino)

    assert PdfReader(destino).metadata.title == CABECALHO.titulo


def test_aula_longa_ocupa_varias_paginas_numeradas(tmp_path, ler_pdf):
    destino = tmp_path / "aula.pdf"
    frase = "Esta é uma frase de uma aula longa, repetida para encher páginas."
    segmentos = [Segmento(i * 5.0, i * 5.0 + 4.0, frase) for i in range(600)]

    gerar_pdf(segmentos, CABECALHO, destino)

    paginas = PdfReader(destino).pages
    assert len(paginas) > 5
    assert f"Página 1 de {len(paginas)}" in paginas[0].extract_text()
    # Sem os rodapés e com os espaços normalizados, já que as quebras de linha e
    # de página podem partir uma frase, o texto chega inteiro.
    linhas = [linha for linha in ler_pdf(destino).splitlines() if not linha.startswith("Página ")]
    assert " ".join(" ".join(linhas).split()).count(frase) == 600


def test_audio_sem_fala_gera_pdf_que_diz_isso(tmp_path, ler_pdf):
    destino = tmp_path / "aula.pdf"

    gerar_pdf([], CABECALHO, destino)

    assert "Nenhuma fala foi encontrada" in ler_pdf(destino)
