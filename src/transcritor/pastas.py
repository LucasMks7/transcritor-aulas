"""Pastas de destino no Google Drive.

Com o escopo drive.file, a busca do Drive só devolve o que o próprio
transcritor criou. Por isso "listar pastas" quer dizer listar as pastas do
transcritor, nunca o Drive inteiro da pessoa.

O Drive aceita duas pastas com o mesmo nome. Para não criar uma pasta nova a
cada uso, obter_ou_criar reaproveita a que já existe com aquele nome.

As funções recebem o serviço do Drive pronto (drive.servico_do_drive), e os
testes passam um dublê no lugar dele.
"""

from collections.abc import Callable
from typing import NamedTuple

TIPO_PASTA = "application/vnd.google-apps.folder"


class Pasta(NamedTuple):
    id: str
    nome: str


class Destino(NamedTuple):
    """Para onde vai cada arquivo gerado. Um destino novo é só uma linha em DESTINOS."""

    rotulo: str  # como aparece nas mensagens: "Pasta do áudio"
    finalidade: str  # como aparece na pergunta: "para o áudio"
    nome_padrao: str


DESTINOS = {
    "audio": Destino("Pasta do áudio", "o áudio", "Transcritor - Áudios"),
    "pdf": Destino("Pasta do PDF", "o PDF", "Transcritor - PDFs"),
}


class FalhaNoDrive(RuntimeError):
    """O Google Drive recusou o pedido ou não respondeu."""


def _texto_na_busca(texto: str) -> str:
    # Na linguagem de busca do Drive, o texto vai entre aspas simples. Barra
    # invertida e aspas dentro dele precisam de escape: "Aula d'água" é um nome válido.
    return "'" + texto.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _executar(pedido):
    from googleapiclient.errors import HttpError

    try:
        return pedido.execute()
    # HttpError: o Drive recusou (cota, autorização). OSError: sem internet.
    except (HttpError, OSError) as erro:
        raise FalhaNoDrive(f"o Google Drive não respondeu: {erro}") from erro


def _buscar(servico, filtro: str) -> list[Pasta]:
    consulta = f"mimeType = '{TIPO_PASTA}' and trashed = false"
    if filtro:
        consulta += f" and {filtro}"
    pastas = []
    pagina = None
    while True:
        resposta = _executar(
            servico.files().list(
                q=consulta,
                spaces="drive",
                fields="nextPageToken, files(id, name)",
                orderBy="name",
                pageToken=pagina,
            )
        )
        pastas += [Pasta(f["id"], f["name"]) for f in resposta.get("files", [])]
        pagina = resposta.get("nextPageToken")
        if not pagina:
            return pastas


def listar_pastas(servico) -> list[Pasta]:
    """As pastas criadas pelo transcritor que não estão na lixeira, em ordem alfabética."""
    return _buscar(servico, "")


def limpar_nome(nome: str) -> str:
    nome = " ".join(nome.split())
    if not nome:
        raise ValueError("o nome da pasta não pode ficar vazio")
    return nome


def criar_pasta(servico, nome: str) -> Pasta:
    """Cria a pasta na raiz do Meu Drive."""
    nome = limpar_nome(nome)
    criada = _executar(
        servico.files().create(body={"name": nome, "mimeType": TIPO_PASTA}, fields="id, name")
    )
    return Pasta(criada["id"], criada["name"])


def obter_ou_criar(servico, nome: str) -> Pasta:
    """A pasta do transcritor com esse nome, criada agora se ainda não existir."""
    nome = limpar_nome(nome)
    existentes = _buscar(servico, f"name = {_texto_na_busca(nome)}")
    return existentes[0] if existentes else criar_pasta(servico, nome)


def escolher_pasta(
    servico,
    finalidade: str,
    nome_padrao: str,
    perguntar: Callable[[str], str] | None = None,
    mostrar: Callable[[str], None] | None = None,
) -> Pasta:
    """Mostra as pastas numeradas e devolve a escolhida.

    A resposta pode ser o número de uma pasta, o nome de uma pasta nova ou
    vazia, que usa o nome padrão. Um nome que já existe reaproveita a pasta.
    """
    # input e print são buscados agora, não na definição da função: um valor
    # padrão "= input" guardaria a função do momento da importação.
    perguntar = perguntar or input
    mostrar = mostrar or print
    pastas = listar_pastas(servico)
    if pastas:
        mostrar(f"Pastas do transcritor no seu Drive para {finalidade}:")
        for numero, pasta in enumerate(pastas, start=1):
            mostrar(f"  {numero}. {pasta.nome}")
    else:
        mostrar("O transcritor ainda não criou nenhuma pasta no seu Drive.")

    while True:
        resposta = perguntar(
            f"Número da pasta, ou nome de uma pasta nova [{nome_padrao}]: "
        ).strip()
        if not resposta:
            return obter_ou_criar(servico, nome_padrao)
        # Sem pastas na lista, "2026" só pode ser o nome de uma pasta nova.
        if resposta.isdigit() and pastas:
            numero = int(resposta)
            if 1 <= numero <= len(pastas):
                return pastas[numero - 1]
            mostrar(f"Não há pasta número {numero}. Escolha de 1 a {len(pastas)}.")
            continue
        return obter_ou_criar(servico, resposta)
