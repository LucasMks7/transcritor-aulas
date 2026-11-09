import pytest

from transcritor.avaliacao import contar_erros, normalizar, taxa_de_erro


def test_normalizar_tira_maiusculas_e_pontuacao():
    assert normalizar("— Todos? É impossível; alguns sim...") == [
        "todos",
        "é",
        "impossível",
        "alguns",
        "sim",
    ]


def test_normalizar_separa_no_hifen():
    assert normalizar("prepare-se") == normalizar("prepare se") == ["prepare", "se"]


@pytest.mark.parametrize("escrito", ["4º", "4°", "4 º", "4ª"])
def test_normalizar_escreve_os_ordinais_por_extenso(escrito):
    assert normalizar(f"{escrito} que à vista disso") == [
        "quarto",
        "que",
        "à",
        "vista",
        "disso",
    ]


def test_normalizar_le_o_sinal_de_paragrafo():
    assert normalizar("do § 4º,") == ["do", "parágrafo", "quarto"]


def test_normalizar_mantem_os_numeros_comuns():
    assert normalizar("em 1882, 40 loucos") == ["em", "1882", "40", "loucos"]


@pytest.mark.parametrize(
    ("hipotese", "erros"),
    [
        ("a casa verde de itaguaí", 0),
        ("a casa verdi de itaguaí", 1),  # troca
        ("a casa de itaguaí", 1),  # falta
        ("a casa muito verde de itaguaí", 1),  # sobra no meio
        ("", 5),
    ],
)
def test_conta_trocas_faltas_e_sobras(hipotese, erros):
    referencia = "a casa verde de itaguaí".split()

    assert contar_erros(referencia, hipotese.split()) == erros


def test_o_que_vem_antes_e_depois_do_trecho_nao_conta():
    referencia = "a casa verde de itaguaí".split()
    hipotese = "capítulo onze a casa verde de itaguaí fim do capítulo".split()

    assert contar_erros(referencia, hipotese) == 0


def test_taxa_de_erro_divide_pelas_palavras_da_referencia():
    assert taxa_de_erro("A Casa Verde de Itaguaí.", "a casa verdi de itaguaí") == 0.2


def test_taxa_de_erro_recusa_referencia_vazia():
    with pytest.raises(ValueError):
        taxa_de_erro(" ... ", "qualquer coisa")
