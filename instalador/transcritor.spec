# Receita do PyInstaller. Use scripts/montar_instalador.py, que a chama e confere o resultado.
#
# Os três executáveis dividem a mesma pasta de bibliotecas. É uma pasta, e não um
# arquivo único: o arquivo único se descompacta inteiro a cada abertura e é mais
# confundido com vírus.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ENTRADAS = Path(SPECPATH) / "entradas"

# nome do executável -> (script, abre terminal)
PROGRAMAS = {
    "Transcritor": ("janela.py", False),
    "transcrever": ("transcrever.py", True),
    "transcritor-drive": ("transcritor_drive.py", True),
}
NOMES_DOS_SCRIPTS = {Path(script).stem for script, _ in PROGRAMAS.values()}

analise = Analysis(
    [str(ENTRADAS / script) for script, _ in PROGRAMAS.values()],
    pathex=[str(Path(SPECPATH).parent / "src")],
    # O modelo que acha os trechos sem fala vem dentro do faster-whisper.
    # O huggingface_hub só usa o hf_xet, que acelera o download, se achar a metadata dele.
    datas=collect_data_files("faster_whisper") + copy_metadata("hf_xet"),
    # nvidia: as bibliotecas da placa somam 2 GB e ficam de fora (PLANO.md).
    excludes=["nvidia", "pytest", "_pytest", "pypdf", "setuptools", "pip"],
)
# O googleapiclient traz a descrição de todas as APIs do Google; só a do Drive é usada.
analise.datas = [
    item
    for item in analise.datas
    if "discovery_cache" not in item[0] or Path(item[0]).name == "drive.v3.json"
]

pyz = PYZ(analise.pure)


def executavel(nome, script, console):
    # Todo executável leva os ajustes de inicialização do PyInstaller e só o seu script.
    scripts = [
        item
        for item in analise.scripts
        if item[0] not in NOMES_DOS_SCRIPTS or item[0] == Path(script).stem
    ]
    return EXE(pyz, scripts, exclude_binaries=True, name=nome, console=console, upx=False)


COLLECT(
    *[executavel(nome, script, console) for nome, (script, console) in PROGRAMAS.items()],
    analise.binaries,
    analise.datas,
    upx=False,
    name="Transcritor",
)
