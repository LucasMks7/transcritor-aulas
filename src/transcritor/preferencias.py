"""Preferências da pessoa, lembradas entre um uso e outro.

Ficam em preferencias.json, na mesma pasta de configuração da autorização. As
pastas do Drive são guardadas pelo nome, e não pelo ID: se alguém apagar a
pasta, o próximo envio cria outra com o mesmo nome em vez de falhar.
"""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from transcritor.arquivos import caminho_parcial
from transcritor.drive import pasta_de_configuracao
from transcritor.pastas import DESTINOS, limpar_nome


@dataclass(frozen=True)
class Preferencias:
    # Desligado até a pessoa pedir: sem isso, nada sai do computador.
    enviar_ao_drive: bool = False
    pasta_audio: str = DESTINOS["audio"].nome_padrao
    pasta_pdf: str = DESTINOS["pdf"].nome_padrao
    # Onde a caixa de escolha do áudio abre.
    pasta_local: str = ""

    def nomes_das_pastas(self) -> dict[str, str]:
        """Nas mesmas chaves de pastas.DESTINOS."""
        return {"audio": self.pasta_audio, "pdf": self.pasta_pdf}


def caminho_das_preferencias() -> Path:
    return pasta_de_configuracao() / "preferencias.json"


def carregar(caminho: Path | None = None) -> Preferencias:
    """As preferências salvas. O que faltar ou não fizer sentido fica com o padrão.

    Nunca levanta erro: um arquivo de preferências estragado não pode impedir
    alguém de transcrever uma aula.
    """
    caminho = caminho or caminho_das_preferencias()
    try:
        salvas = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferencias()
    if not isinstance(salvas, dict):
        return Preferencias()

    valores = {}
    for campo in fields(Preferencias):
        valor = salvas.get(campo.name)
        # Um campo de outro tipo, ou de uma versão futura, é ignorado.
        if type(valor) is type(campo.default):
            valores[campo.name] = valor
    for nome, destino in (("pasta_audio", "audio"), ("pasta_pdf", "pdf")):
        if nome in valores:
            valores[nome] = nome_ou_padrao(valores[nome], destino)
    return Preferencias(**valores)


def salvar(preferencias: Preferencias, caminho: Path | None = None) -> None:
    """Levanta OSError se não for possível gravar."""
    caminho = caminho or caminho_das_preferencias()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # Um desligamento no meio da gravação não deixa o arquivo pela metade.
    parcial = caminho_parcial(caminho)
    parcial.write_text(
        json.dumps(asdict(preferencias), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    parcial.replace(caminho)


def nome_ou_padrao(nome: str, destino: str) -> str:
    """O nome da pasta sem espaços sobrando, ou o padrão se ficar vazio."""
    try:
        return limpar_nome(nome)
    except ValueError:
        return DESTINOS[destino].nome_padrao
