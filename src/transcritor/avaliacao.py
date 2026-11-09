"""Medida da qualidade de uma transcrição, comparada com um texto de referência."""

import re

# O texto escrito traz "4º" onde a pessoa lê "quarto", e cada modelo escolhe uma
# das duas formas. Sem igualar as duas, a diferença contaria como erro.
ORDINAIS = {
    "1": "primeiro",
    "2": "segundo",
    "3": "terceiro",
    "4": "quarto",
    "5": "quinto",
    "6": "sexto",
    "7": "sétimo",
    "8": "oitavo",
    "9": "nono",
    "10": "décimo",
}


def normalizar(texto: str) -> list[str]:
    """Devolve as palavras em minúsculas, sem pontuação e com os ordinais por extenso.

    Maiúsculas e pontuação ficam de fora porque a medida é sobre as palavras
    reconhecidas, não sobre o estilo de escrita de cada modelo.
    """
    texto = texto.lower().replace("§", " parágrafo ")
    texto = re.sub(
        r"\b(\d+)\s?[ºª°]", lambda achado: ORDINAIS.get(achado[1], achado[1]), texto
    )
    # Separa também no hífen, para "prepare-se" e "prepare se" contarem igual.
    return re.findall(r"\w+", texto)


def contar_erros(referencia: list[str], hipotese: list[str]) -> int:
    """Menor número de trocas, faltas e sobras de palavras entre os dois textos.

    É a distância de edição de sempre, com uma diferença: o que a hipótese tem
    antes e depois do trecho da referência não conta. Assim, a abertura e o
    encerramento da gravação, que não estão no texto, não viram erro.
    """
    # anterior[j]: custo de alinhar a referência lida até aqui com um trecho da
    # hipótese que termina na palavra j. A primeira linha é toda zero porque
    # começar a hipótese mais adiante é de graça.
    anterior = [0] * (len(hipotese) + 1)
    for linha, palavra_certa in enumerate(referencia, start=1):
        atual = [linha]
        for coluna, palavra in enumerate(hipotese, start=1):
            atual.append(
                min(
                    anterior[coluna] + 1,  # faltou uma palavra da referência
                    atual[coluna - 1] + 1,  # sobrou uma palavra na hipótese
                    anterior[coluna - 1] + (palavra != palavra_certa),  # troca
                )
            )
        anterior = atual

    # O mínimo da última linha deixa de graça o que sobra no fim da hipótese.
    return min(anterior)


def taxa_de_erro(referencia: str, hipotese: str) -> float:
    """Taxa de erro de palavras (WER): erros divididos pelas palavras da referência."""
    palavras = normalizar(referencia)
    if not palavras:
        raise ValueError("O texto de referência não tem palavras.")
    return contar_erros(palavras, normalizar(hipotese)) / len(palavras)
