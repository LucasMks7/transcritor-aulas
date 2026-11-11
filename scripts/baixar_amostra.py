"""Baixa o áudio de exemplo usado no teste de ponta a ponta.

É o capítulo XI de O Alienista, lido para o LibriVox, em domínio público. O
repositório não guarda áudios, então o arquivo é baixado na primeira vez e
conferido pelo SHA-256: um download pela metade ou trocado vira erro aqui, e
não uma taxa de erro estranha no teste. Uso:

    python scripts/baixar_amostra.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://archive.org/download/o_alienista_0904_librivox/"
    "oalienista_7_machadodeassis_64kb.mp3"
)
SHA256 = "d4251ab4764fd64efc100097655b57bb164ede1477d26b45a5566302f2cc3bb6"
DESTINO = Path(__file__).resolve().parent.parent / "amostras" / "alienista-cap11.mp3"


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def baixar(destino: Path = DESTINO) -> Path:
    if destino.is_file() and sha256(destino) == SHA256:
        print(f"A amostra já está em {destino}.")
        return destino

    print(f"Baixando {URL}...")
    temporario = destino.with_name(destino.name + ".parcial")
    with urllib.request.urlopen(URL, timeout=60) as resposta:
        temporario.write_bytes(resposta.read())

    if sha256(temporario) != SHA256:
        temporario.unlink()
        raise SystemExit("O arquivo baixado não é o esperado (SHA-256 diferente).")
    temporario.replace(destino)
    print(f"Amostra salva em {destino}.")
    return destino


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    baixar()
