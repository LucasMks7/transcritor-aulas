"""Geração do PDF da transcrição."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fpdf import FPDF

from transcritor.transcricao import Segmento, formatar_tempo

# Um parágrafo novo começa depois de uma pausa desta duração: na fala, é o que
# mais se parece com a troca de assunto.
SEGUNDOS_DE_PAUSA_ENTRE_PARAGRAFOS = 2.0
# Sem pausas longas, o parágrafo é encerrado no primeiro fim de frase depois
# deste tamanho, para o texto não virar um bloco único de várias páginas.
SEGUNDOS_POR_PARAGRAFO = 90.0
# Se a fala não tiver pontuação, o parágrafo é encerrado aqui de qualquer jeito.
SEGUNDOS_MAXIMOS_POR_PARAGRAFO = 180.0
FINS_DE_FRASE = (".", "?", "!")

# As fontes que já vêm no PDF cobrem todas as letras do português, mas não a
# pontuação tipográfica que o Whisper às vezes produz. Trocá-la pela versão
# simples evita embutir um arquivo de fonte no programa.
TROCAS_TIPOGRAFICAS = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
        " ": " ",
    }
)

FONTE = "Helvetica"
MARGEM_MM = 20
CORPO_PT = 11
ALTURA_DA_LINHA_MM = 6
CINZA = (110, 110, 110)


@dataclass(frozen=True)
class Paragrafo:
    inicio: float
    texto: str


@dataclass(frozen=True)
class Cabecalho:
    """O que o PDF informa sobre a transcrição, antes do texto."""

    titulo: str
    duracao: float
    modelo: str
    dia: date


def agrupar_em_paragrafos(
    segmentos: tuple[Segmento, ...] | list[Segmento],
    pausa: float = SEGUNDOS_DE_PAUSA_ENTRE_PARAGRAFOS,
    duracao_desejada: float = SEGUNDOS_POR_PARAGRAFO,
    duracao_maxima: float = SEGUNDOS_MAXIMOS_POR_PARAGRAFO,
) -> list[Paragrafo]:
    """Junta os segmentos em parágrafos, quebrando nas pausas longas da fala.

    Sem pausas, um parágrafo que passou de duracao_desejada termina no próximo
    fim de frase, para não partir uma frase entre dois parágrafos.
    """
    paragrafos = []
    atual: list[Segmento] = []
    for segmento in segmentos:
        if not segmento.texto:
            continue
        if atual:
            duracao = segmento.inicio - atual[0].inicio
            fim_de_frase = atual[-1].texto.endswith(FINS_DE_FRASE)
            if (
                segmento.inicio - atual[-1].fim >= pausa
                or (duracao >= duracao_desejada and fim_de_frase)
                or duracao >= duracao_maxima
            ):
                paragrafos.append(_paragrafo(atual))
                atual = []
        atual.append(segmento)
    if atual:
        paragrafos.append(_paragrafo(atual))
    return paragrafos


def _paragrafo(segmentos: list[Segmento]) -> Paragrafo:
    return Paragrafo(segmentos[0].inicio, " ".join(s.texto for s in segmentos))


def para_fonte_do_pdf(texto: str) -> str:
    """Deixa o texto só com caracteres que a fonte do PDF consegue desenhar."""
    texto = texto.translate(TROCAS_TIPOGRAFICAS)
    # O que ainda sobrar (um nome estrangeiro raro, um emoji) vira "?", em vez
    # de impedir o PDF inteiro de ser gerado.
    return texto.encode("latin-1", errors="replace").decode("latin-1")


class _Documento(FPDF):
    def footer(self):
        # Chamado pelo fpdf2 no fim de cada página. {nb} vira o total de páginas.
        self.set_y(-15)
        self.set_font(FONTE, size=9)
        self.set_text_color(*CINZA)
        self.cell(0, 10, f"Página {self.page_no()} de {{nb}}", align="C")


def gerar_pdf(segmentos, cabecalho: Cabecalho, destino: Path) -> None:
    """Grava o PDF em destino, com o cabeçalho e um parágrafo por trecho de fala.

    Cada parágrafo começa com o tempo em que aparece no áudio, para quem
    estuda poder voltar à gravação naquele ponto.
    """
    pdf = _Documento(format="A4")
    pdf.set_margins(MARGEM_MM, MARGEM_MM, MARGEM_MM)
    pdf.set_auto_page_break(auto=True, margin=MARGEM_MM)
    pdf.set_title(para_fonte_do_pdf(cabecalho.titulo))
    pdf.set_creator("transcritor-aulas")
    pdf.add_page()

    pdf.set_font(FONTE, style="B", size=16)
    pdf.multi_cell(0, 8, para_fonte_do_pdf(cabecalho.titulo))
    pdf.ln(1)
    pdf.set_font(FONTE, size=9)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(
        0,
        5,
        f"Duração: {formatar_tempo(cabecalho.duracao)}  |  "
        f"Transcrito em {cabecalho.dia:%d/%m/%Y} com o modelo {cabecalho.modelo} "
        "do Whisper. A transcrição automática pode conter erros.",
    )
    pdf.ln(6)

    paragrafos = agrupar_em_paragrafos(segmentos)
    if not paragrafos:
        pdf.set_font(FONTE, style="I", size=CORPO_PT)
        pdf.multi_cell(0, ALTURA_DA_LINHA_MM, "Nenhuma fala foi encontrada no áudio.")

    for paragrafo in paragrafos:
        pdf.set_font(FONTE, size=8)
        pdf.set_text_color(*CINZA)
        pdf.cell(0, 4, formatar_tempo(paragrafo.inicio), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(FONTE, size=CORPO_PT)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, ALTURA_DA_LINHA_MM, para_fonte_do_pdf(paragrafo.texto))
        pdf.ln(3)

    pdf.output(str(destino))
