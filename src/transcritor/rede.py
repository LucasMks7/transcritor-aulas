"""O que pode dar errado ao falar com o Google, e o que vale a pena repetir.

As bibliotecas do Google deixam passar erros de várias famílias, e nem todas
são OSError: sem internet, o httplib2 levanta ServerNotFoundError e o
google-auth levanta TransportError. Este módulo reúne a lista em um lugar só.
"""

import json
from http.client import HTTPException

SEM_RESPOSTA = "o Google Drive não respondeu. Confira a conexão com a internet"
AUTORIZACAO_EXPIRADA = "a autorização do Google expirou ou foi revogada"

# Motivos que o Drive usa no 403 para "devagar": estes passam, os outros não.
LIMITES_DE_RITMO = {"rateLimitExceeded", "userRateLimitExceeded"}


def erros_de_conexao() -> tuple[type[Exception], ...]:
    """As exceções de quando o pedido nem chegou a ter resposta."""
    # Importadas aqui para quem só transcreve não carregar as bibliotecas do Google.
    from google.auth.exceptions import TransportError
    from httplib2.error import HttpLib2Error

    return (OSError, HttpLib2Error, TransportError, HTTPException)


def motivo_do_drive(erro) -> str:
    """O código curto do erro no corpo da resposta, como storageQuotaExceeded."""
    try:
        return json.loads(erro.content)["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


def autorizacao_expirou(erro: Exception) -> bool:
    """Se só um novo login resolve."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(erro, HttpError):
        return erro.resp.status == 401
    # A renovação também falha quando o servidor do Google está fora do ar. Nesse
    # caso a autorização continua boa, e jogá-la fora pediria um login à toa.
    return isinstance(erro, RefreshError) and not erro.retryable


def vale_repetir(erro: Exception) -> bool:
    """Se o mesmo pedido, daqui a pouco, pode dar certo."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(erro, RefreshError):
        return erro.retryable
    if isinstance(erro, HttpError):
        codigo = erro.resp.status
        if codigo == 403:
            return motivo_do_drive(erro) in LIMITES_DE_RITMO
        return codigo in (408, 429) or codigo >= 500
    return isinstance(erro, erros_de_conexao())
