"""Autorização de acesso ao Google Drive da pessoa que usa o programa.

O escopo é o drive.file: o programa só enxerga os arquivos e pastas que ele
mesmo criou, nunca o resto do Drive. É o escopo que o Google recomenda e não
exige verificação do app. Veja docs/google-drive.md.

Dois arquivos ficam na pasta de configuração do usuário, fora do repositório:

- client_secret.json: identifica o programa para o Google. Vem do projeto no
  Google Cloud.
- token.json: a autorização dada pela pessoa. Permite enviar arquivos sem
  pedir login de novo a cada vez.
"""

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

ESCOPOS = ["https://www.googleapis.com/auth/drive.file"]
NOME_DA_PASTA = "transcritor-aulas"


class FalhaNaAutorizacao(RuntimeError):
    """Não foi possível obter ou usar a autorização do Google."""


def pasta_de_configuracao() -> Path:
    """%APPDATA%\\transcritor-aulas no Windows, ~/.config/transcritor-aulas nos outros."""
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / NOME_DA_PASTA


def caminho_do_client_secret() -> Path:
    # A variável de ambiente serve para testes e para quem guarda o arquivo em outro lugar.
    escolhido = os.environ.get("TRANSCRITOR_CLIENT_SECRET")
    return Path(escolhido) if escolhido else pasta_de_configuracao() / "client_secret.json"


def caminho_do_token() -> Path:
    return pasta_de_configuracao() / "token.json"


def _autorizar_no_navegador(client_secret: Path):
    """Abre o navegador para a pessoa entrar na conta e permitir o acesso."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    fluxo = InstalledAppFlow.from_client_secrets_file(str(client_secret), ESCOPOS)
    # O Google devolve a autorização para um servidor temporário neste PC, numa
    # porta livre escolhida na hora. Nada passa por servidor nosso.
    return fluxo.run_local_server(
        port=0,
        authorization_prompt_message="Abrindo o navegador para você entrar na conta do Google...",
        success_message="Pronto! Pode fechar esta aba e voltar ao transcritor.",
    )


def _ler_token(token: Path):
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(str(token), ESCOPOS)


def _renovar(credenciais) -> None:
    from google.auth.transport.requests import Request

    credenciais.refresh(Request())


def carregar_credenciais(
    token: Path | None = None,
    ler: Callable = _ler_token,
    renovar: Callable = _renovar,
):
    """Devolve a autorização salva, renovada se preciso, ou None se não houver uma válida.

    Uma autorização revogada pela pessoa, ou vencida, é apagada: o próximo
    passo é pedir uma nova no navegador.
    """
    from google.auth.exceptions import RefreshError

    token = token or caminho_do_token()
    if not token.is_file():
        return None
    try:
        credenciais = ler(token)
    except ValueError:
        # Arquivo corrompido ou de outra versão: melhor pedir de novo.
        token.unlink()
        return None

    if credenciais.valid:
        return credenciais
    if credenciais.refresh_token:
        try:
            renovar(credenciais)
        except RefreshError:
            token.unlink()
            return None
        salvar_token(credenciais, token)
        return credenciais
    token.unlink()
    return None


def salvar_token(credenciais, token: Path | None = None) -> None:
    token = token or caminho_do_token()
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(credenciais.to_json(), encoding="utf-8")


def conectar(
    client_secret: Path | None = None,
    token: Path | None = None,
    autorizar: Callable = _autorizar_no_navegador,
    carregar: Callable = carregar_credenciais,
):
    """Usa a autorização salva ou pede uma nova no navegador.

    autorizar e carregar existem para os testes trocarem o Google por dublês.
    """
    token = token or caminho_do_token()
    credenciais = carregar(token)
    if credenciais is not None:
        return credenciais

    client_secret = client_secret or caminho_do_client_secret()
    if not client_secret.is_file():
        raise FalhaNaAutorizacao(
            f"falta o arquivo de credenciais do programa em {client_secret}. "
            "Veja como criá-lo em docs/google-drive.md."
        )
    try:
        credenciais = autorizar(client_secret)
    except ValueError as erro:
        # A biblioteca levanta ValueError para um client_secret.json inválido.
        raise FalhaNaAutorizacao(f"o arquivo {client_secret} não é válido: {erro}") from erro
    except Exception as erro:
        # Navegador fechado, acesso negado, sem internet: a orientação é a mesma.
        raise FalhaNaAutorizacao(f"a autorização não foi concluída: {erro}") from erro
    salvar_token(credenciais, token)
    return credenciais


def desconectar(token: Path | None = None) -> bool:
    """Esquece a autorização salva neste PC. Devolve se havia uma."""
    token = token or caminho_do_token()
    if token.is_file():
        token.unlink()
        return True
    return False


def conta_conectada(credenciais) -> str:
    """O e-mail da conta autorizada, para a pessoa confirmar que é a certa."""
    from googleapiclient.discovery import build

    from googleapiclient.errors import HttpError

    try:
        servico = build("drive", "v3", credentials=credenciais, cache_discovery=False)
        sobre = servico.about().get(fields="user(emailAddress)").execute()
    # HttpError: a API do Drive desativada no projeto, por exemplo. OSError: sem internet.
    except (HttpError, OSError) as erro:
        raise FalhaNaAutorizacao(f"o Google Drive não respondeu: {erro}") from erro
    return sobre["user"]["emailAddress"]


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="transcritor-drive", description="Conecta o transcritor ao seu Google Drive."
    )
    parser.add_argument(
        "acao",
        choices=("conectar", "desconectar"),
        help="conectar pede a autorização no navegador; desconectar a esquece neste PC",
    )
    argumentos = parser.parse_args(argv)

    if argumentos.acao == "desconectar":
        if desconectar():
            print("Autorização apagada deste PC. Para revogá-la também no Google, use "
                  "https://myaccount.google.com/permissions")
        else:
            print("Não havia autorização salva neste PC.")
        return 0

    try:
        credenciais = conectar()
        email = conta_conectada(credenciais)
    except FalhaNaAutorizacao as erro:
        print(f"transcritor-drive: erro: {erro}", file=sys.stderr)
        return 1
    print(f"Conectado ao Google Drive de {email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
