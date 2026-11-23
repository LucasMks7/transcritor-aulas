"""Envio de um arquivo para uma pasta do Google Drive.

O envio é retomável: o arquivo vai em blocos e, depois de uma falha, o programa
pergunta ao Drive até onde chegou e continua dali. Em um áudio de 100 MB numa
internet ruim, isso é a diferença entre terminar e recomeçar do zero.

As funções recebem o serviço do Drive pronto (drive.servico_do_drive), e os
testes passam um dublê no lugar dele.
"""

import hashlib
import mimetypes
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from transcritor.pastas import AutorizacaoExpirada, FalhaNoDrive, texto_na_busca
from transcritor.rede import (
    AUTORIZACAO_EXPIRADA,
    autorizacao_expirou,
    erros_de_conexao,
    motivo_do_drive,
    vale_repetir,
)

# O Drive exige múltiplos de 256 KB. Blocos pequenos mostram o progresso e
# obedecem ao cancelamento mais depressa; blocos grandes fazem menos pedidos.
TAMANHO_DO_BLOCO = 2 * 1024 * 1024

# Falhas seguidas, sem nenhum bloco entregue no meio. Com as esperas de 1, 2, 4,
# 8 e 16 segundos, o programa insiste por uns 30 segundos antes de desistir.
TENTATIVAS = 6

CAMPOS = "id, name, webViewLink"


class ArquivoNoDrive(NamedTuple):
    id: str
    nome: str
    link: str
    ja_estava_la: bool = False


class FalhaNoEnvio(FalhaNoDrive):
    """O arquivo não chegou ao Drive. O original continua intacto no PC."""


def enviar_arquivo(
    servico,
    arquivo: Path,
    pasta_id: str,
    ao_progredir: Callable[[int, int], None] = lambda enviado, total: None,
    ao_repetir: Callable[[int, float], None] = lambda tentativa, espera: None,
    esperar: Callable[[float], object] = time.sleep,
) -> ArquivoNoDrive:
    """Envia o arquivo, insistindo quando a falha é passageira.

    ao_progredir recebe os bytes enviados e o total; ao_repetir, o número da
    próxima tentativa e quantos segundos faltam para ela. Uma exceção levantada
    por qualquer um dos dois interrompe o envio: é assim que se cancela.
    """
    try:
        conteudo = arquivo.open("rb")
    except OSError as erro:
        raise FalhaNoEnvio(f"não foi possível ler {arquivo}: {erro.strerror}") from erro

    with conteudo:
        total = arquivo.stat().st_size
        if total == 0:
            raise FalhaNoEnvio(f"o arquivo está vazio: {arquivo}")

        pedido = None
        procurou = False
        falhas = 0
        while True:
            try:
                if not procurou:
                    existente = _procurar_igual(servico, arquivo, pasta_id)
                    if existente is not None:
                        return existente
                    procurou = True
                if pedido is None:
                    pedido = _novo_pedido(servico, conteudo, arquivo, pasta_id)
                situacao, resposta = pedido.next_chunk()
            except Exception as erro:
                if _sessao_expirou(erro, pedido):
                    # O Drive guarda um envio incompleto por alguns dias. Depois
                    # disso, só resta começar outro.
                    pedido = None
                elif not vale_repetir(erro):
                    raise _traduzir(erro, arquivo) from erro
                falhas += 1
                if falhas >= TENTATIVAS:
                    raise _traduzir(erro, arquivo) from erro
                espera = _espera(falhas)
                ao_repetir(falhas + 1, espera)
                esperar(espera)
                continue

            # Um bloco chegou: a próxima queda tem direito a todas as tentativas.
            falhas = 0
            if resposta is not None:
                ao_progredir(total, total)
                return _do_drive(resposta)
            ao_progredir(situacao.resumable_progress, total)


def _novo_pedido(servico, conteudo, arquivo: Path, pasta_id: str):
    from googleapiclient.http import MediaIoBaseUpload

    tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    # O arquivo é aberto e fechado por enviar_arquivo, e não pela biblioteca: no
    # Windows, um arquivo esquecido aberto não pode ser movido nem apagado.
    midia = MediaIoBaseUpload(conteudo, mimetype=tipo, chunksize=TAMANHO_DO_BLOCO, resumable=True)
    return servico.files().create(
        body={"name": arquivo.name, "parents": [pasta_id]}, media_body=midia, fields=CAMPOS
    )


def _do_drive(dados: dict, ja_estava_la: bool = False) -> ArquivoNoDrive:
    return ArquivoNoDrive(dados["id"], dados["name"], dados.get("webViewLink", ""), ja_estava_la)


def _espera(falhas: int) -> float:
    # O sorteio evita que vários computadores voltem todos no mesmo instante.
    return 2 ** (falhas - 1) + random.random()


def _procurar_igual(servico, arquivo: Path, pasta_id: str) -> ArquivoNoDrive | None:
    """O mesmo arquivo, se já estiver na pasta: mesmo nome e mesmo conteúdo.

    Repetir um envio não pode encher o Drive de cópias. Só o nome não basta: o
    gravador do celular chama toda aula de "Nova gravação", e substituir pelo
    nome apagaria a aula anterior.
    """
    consulta = (
        f"name = {texto_na_busca(arquivo.name)} and "
        f"{texto_na_busca(pasta_id)} in parents and trashed = false"
    )
    resposta = (
        servico.files()
        .list(q=consulta, spaces="drive", fields=f"files({CAMPOS}, md5Checksum)")
        .execute()
    )
    candidatos = resposta.get("files", [])
    if candidatos:
        soma = _md5(arquivo)
        for candidato in candidatos:
            if candidato.get("md5Checksum") == soma:
                return _do_drive(candidato, ja_estava_la=True)
    return None


def _md5(arquivo: Path) -> str:
    # MD5 porque é a soma que o Drive informa; serve para comparar, não para segurança.
    soma = hashlib.md5(usedforsecurity=False)
    with arquivo.open("rb") as conteudo:
        while bloco := conteudo.read(1024 * 1024):
            soma.update(bloco)
    return soma.hexdigest()


def _sessao_expirou(erro: Exception, pedido) -> bool:
    from googleapiclient.errors import HttpError

    # Antes de o envio começar, o 404 é da pasta de destino, e repetir não adianta.
    comecou = pedido is not None and pedido.resumable_uri is not None
    return comecou and isinstance(erro, HttpError) and erro.resp.status in (404, 410)


def _traduzir(erro: Exception, arquivo: Path) -> FalhaNoDrive:
    from googleapiclient.errors import HttpError

    if autorizacao_expirou(erro):
        # Não é só deste arquivo: nenhum outro chegaria.
        return AutorizacaoExpirada(AUTORIZACAO_EXPIRADA)
    if isinstance(erro, HttpError):
        motivo = motivo_do_drive(erro)
        if motivo == "storageQuotaExceeded":
            texto = "não há espaço livre no seu Google Drive"
        elif erro.resp.status == 404:
            texto = "a pasta de destino não existe mais no seu Drive"
        else:
            detalhe = f"{erro.resp.status} {motivo}".strip()
            texto = f"o Google Drive recusou o envio ({detalhe})"
    elif isinstance(erro, erros_de_conexao()):
        texto = f"a conexão falhou {TENTATIVAS} vezes seguidas"
    else:
        texto = str(erro)
    return FalhaNoEnvio(f"{arquivo.name} não foi enviado: {texto}")
