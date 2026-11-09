"""Compara modelos do Whisper na mesma máquina e com o mesmo áudio.

Para cada modelo, mede o tempo de transcrição e a taxa de erro de palavras em
relação a um texto de referência. Uso:

    python scripts/comparar_modelos.py audio.mp3 referencia.txt --saida resultados
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel, download_model

from transcritor.avaliacao import taxa_de_erro

MODELOS_PADRAO = ("tiny", "base", "small", "medium", "large-v3-turbo")
# Tipo de cálculo indicado para cada dispositivo: int8 é o mais rápido no
# processador, e a GTX 1050 Ti não tem float16 eficiente.
TIPOS_DE_CALCULO = {"cpu": "int8", "cuda": "int8"}


def tamanho_em_mb(pasta: Path) -> float:
    return sum(a.stat().st_size for a in pasta.rglob("*") if a.is_file()) / 1024**2


def medir(nome: str, audio: Path, referencia: str, dispositivo: str) -> dict:
    # O download fica fora das medidas: ele só acontece na primeira vez.
    pasta = Path(download_model(nome))

    inicio = time.perf_counter()
    modelo = WhisperModel(
        str(pasta), device=dispositivo, compute_type=TIPOS_DE_CALCULO[dispositivo]
    )
    carga = time.perf_counter() - inicio

    inicio = time.perf_counter()
    segmentos, informacoes = modelo.transcribe(str(audio), language="pt")
    # A transcrição só acontece de fato quando os segmentos são percorridos.
    texto = " ".join(segmento.text.strip() for segmento in segmentos)
    transcricao = time.perf_counter() - inicio

    return {
        "modelo": nome,
        "tamanho_mb": round(tamanho_em_mb(pasta)),
        "carga_s": round(carga, 1),
        "transcricao_s": round(transcricao, 1),
        "duracao_do_audio_s": round(informacoes.duration, 1),
        # Quantas vezes mais rápido que o tempo real: 2 significa que uma aula
        # de uma hora leva meia hora.
        "velocidade": round(informacoes.duration / transcricao, 2),
        "erro_de_palavras": round(taxa_de_erro(referencia, texto), 4),
        "texto": texto,
    }


def tabela(resultados: list[dict]) -> str:
    linhas = [
        "| Modelo | Tamanho | Carga | Transcrição | Velocidade | Erro de palavras |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in resultados:
        numeros = (
            f"| {r['tamanho_mb']} MB | {r['carga_s']} s | {r['transcricao_s']} s "
            f"| {r['velocidade']}x | {r['erro_de_palavras'] * 100:.1f}% |"
        )
        # Vírgula decimal, como se escreve em português.
        linhas.append(f"| `{r['modelo']}` " + numeros.replace(".", ","))
    return "\n".join(linhas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path)
    parser.add_argument("referencia", type=Path)
    parser.add_argument("--modelos", nargs="+", default=MODELOS_PADRAO)
    parser.add_argument("--dispositivo", choices=TIPOS_DE_CALCULO, default="cpu")
    parser.add_argument("--saida", type=Path, help="pasta para o JSON e os textos")
    argumentos = parser.parse_args()

    referencia = argumentos.referencia.read_text(encoding="utf-8")
    resultados = []
    for nome in argumentos.modelos:
        print(f"Medindo {nome}...", file=sys.stderr, flush=True)
        resultados.append(medir(nome, argumentos.audio, referencia, argumentos.dispositivo))

    print(f"Máquina: {platform.processor()} | dispositivo: {argumentos.dispositivo}")
    print(tabela(resultados))

    if argumentos.saida is not None:
        argumentos.saida.mkdir(parents=True, exist_ok=True)
        sufixo = argumentos.dispositivo
        for r in resultados:
            texto = r.pop("texto")
            (argumentos.saida / f"{r['modelo']}-{sufixo}.txt").write_text(
                texto + "\n", encoding="utf-8"
            )
        (argumentos.saida / f"resultados-{sufixo}.json").write_text(
            json.dumps(resultados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
