"""Monta o instalador para Windows: PyInstaller, conferência e Inno Setup.

    python scripts/montar_instalador.py

O resultado fica fora do OneDrive, em %LOCALAPPDATA%\\transcritor-aulas-instalador.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INSTALADOR = RAIZ / "instalador"
EXECUTAVEIS = ("Transcritor.exe", "transcrever.exe", "transcritor-drive.exe")

# O que não pode ir no instalador: segredos, autorizações, áudios e modelos. O
# silero_vad do faster-whisper (.onnx) não está na lista: ele faz parte do programa.
PROIBIDOS = (
    "token.json",
    "client_secret*.json",
    "credentials*.json",
    ".env",
    "*.mp3",
    "*.m4a",
    "*.wav",
    "model.bin",
)
# Bem acima disto, a pasta só pode ter levado as bibliotecas da NVIDIA.
TAMANHO_MAXIMO_MB = 700


class FalhaNaMontagem(RuntimeError):
    """O instalador não pôde ser montado, ou o que foi montado não pode ser entregue."""


def versao() -> str:
    from transcritor import __version__

    return __version__


def achar_inno() -> Path:
    pastas = (
        os.environ.get("LOCALAPPDATA", "") + r"\Programs",
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
    )
    for pasta in pastas:
        compilador = Path(pasta) / "Inno Setup 6" / "ISCC.exe"
        if compilador.is_file():
            return compilador
    no_path = shutil.which("ISCC")
    if no_path:
        return Path(no_path)
    raise FalhaNaMontagem(
        "o Inno Setup 6 não foi encontrado: winget install JRSoftware.InnoSetup --scope user"
    )


def conferir(programa: Path) -> float:
    """Devolve o tamanho da pasta montada em MB, ou levanta FalhaNaMontagem."""
    for nome in EXECUTAVEIS:
        if not (programa / nome).is_file():
            raise FalhaNaMontagem(f"faltou o executável {nome}")
    for padrao in PROIBIDOS:
        achado = next(programa.rglob(padrao), None)
        if achado is not None:
            raise FalhaNaMontagem(f"este arquivo não pode ir no instalador: {achado}")
    tamanho = sum(a.stat().st_size for a in programa.rglob("*") if a.is_file()) / 1024**2
    if tamanho > TAMANHO_MAXIMO_MB:
        raise FalhaNaMontagem(f"a pasta tem {tamanho:.0f} MB; o limite é {TAMANHO_MAXIMO_MB} MB")
    return tamanho


def montar(saida: Path, client_secret: Path | None = None) -> Path:
    # Antes do PyInstaller, que demora: sem o Inno Setup, ele seria em vão.
    inno = achar_inno()
    subprocess.run(
        [
            *(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean"),
            *("--log-level", "WARN"),
            *("--distpath", str(saida), "--workpath", str(saida / "trabalho")),
            str(INSTALADOR / "transcritor.spec"),
        ],
        check=True,
    )
    programa = saida / "Transcritor"
    tamanho = conferir(programa)
    print(f"Programa montado: {tamanho:.0f} MB em {programa}")
    if client_secret is not None:
        # Depois da conferência: só entra quando pedido, nunca por acidente.
        shutil.copyfile(client_secret, programa / "client_secret.json")
        print("O instalador leva o client_secret.json: não o publique no GitHub.")

    numero = versao()
    subprocess.run(
        [
            *(str(inno), "/Qp", f"/DVersao={numero}"),
            *(f"/DOrigem={programa}", f"/DSaida={saida}"),
            str(INSTALADOR / "transcritor.iss"),
        ],
        check=True,
    )
    return saida / f"transcritor-aulas-{numero}-instalador.exe"


def main() -> int:
    padrao = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "transcritor-aulas-instalador"
    parser = argparse.ArgumentParser(description="Monta o instalador para Windows.")
    parser.add_argument("--saida", type=Path, default=padrao, help="pasta do resultado")
    parser.add_argument(
        "--client-secret",
        type=Path,
        help="leva este client_secret.json no instalador, para a pessoa conectar ao Drive sem "
        "criar um projeto no Google Cloud",
    )
    argumentos = parser.parse_args()
    if sys.platform != "win32":
        parser.error("o instalador só pode ser montado no Windows")
    if argumentos.client_secret is not None and not argumentos.client_secret.is_file():
        parser.error(f"arquivo não encontrado: {argumentos.client_secret}")
    try:
        instalador = montar(argumentos.saida.resolve(), argumentos.client_secret)
    except (FalhaNaMontagem, subprocess.CalledProcessError) as erro:
        print(f"montar_instalador: erro: {erro}", file=sys.stderr)
        return 1
    print(f"Instalador: {instalador} ({instalador.stat().st_size / 1024**2:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
