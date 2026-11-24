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
import socket
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

COMO_RECONECTAR = "Para entrar de novo na conta: transcritor-drive conectar"

ESCOPOS = ["https://www.googleapis.com/auth/drive.file"]
NOME_DA_PASTA = "transcritor-aulas"


# Tempo para a pessoa entrar na conta. Sem limite, fechar a aba do navegador
# deixaria o programa esperando para sempre.
SEGUNDOS_PARA_AUTORIZAR = 300


class FalhaNaAutorizacao(RuntimeError):
    """Não foi possível obter ou usar a autorização do Google."""


def pasta_de_configuracao() -> Path:
    """%APPDATA%\\transcritor-aulas no Windows, ~/.config/transcritor-aulas nos outros."""
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / NOME_DA_PASTA


def caminho_do_client_secret() -> Path:
    # A variável de ambiente serve para testes e para quem guarda o arquivo em outro lugar.
    escolhido = os.environ.get("TRANSCRITOR_CLIENT_SECRET")
    if escolhido:
        return Path(escolhido)
    da_pessoa = pasta_de_configuracao() / "client_secret.json"
    # O instalador pode trazer o arquivo ao lado do executável. O da pessoa vem
    # antes, para quem preferir usar o próprio projeto do Google Cloud.
    if getattr(sys, "frozen", False) and not da_pessoa.is_file():
        do_instalador = Path(sys.executable).parent / "client_secret.json"
        if do_instalador.is_file():
            return do_instalador
    return da_pessoa


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
        timeout_seconds=SEGUNDOS_PARA_AUTORIZAR,
        authorization_prompt_message="Abrindo o navegador para você entrar na conta do Google...",
        success_message="Pronto! Pode fechar esta aba e voltar ao transcritor.",
    )


def _ha_internet() -> bool:
    """Se dá para chegar ao servidor de login do Google."""
    if urllib.request.getproxies():
        # Atrás de um proxy, a conexão direta falha mesmo com a internet funcionando.
        return True
    try:
        socket.create_connection(("oauth2.googleapis.com", 443), timeout=5).close()
    except OSError:
        return False
    return True


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
    passo é pedir uma nova no navegador. Sem internet, ela é mantida, e a função
    levanta FalhaNaAutorizacao.
    """
    from google.auth.exceptions import GoogleAuthError

    from transcritor.rede import SEM_RESPOSTA, autorizacao_expirou

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
        except (GoogleAuthError, OSError) as erro:
            if not autorizacao_expirou(erro):
                raise FalhaNaAutorizacao(SEM_RESPOSTA) from erro
            token.unlink()
            return None
        salvar_token(credenciais, token)
        return credenciais
    token.unlink()
    return None


def salvar_token(credenciais, token: Path | None = None) -> None:
    token = token or caminho_do_token()
    try:
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(credenciais.to_json(), encoding="utf-8")
    except OSError as erro:
        raise FalhaNaAutorizacao(
            f"não foi possível salvar a autorização em {token}: {erro.strerror}"
        ) from erro


def conectar(
    client_secret: Path | None = None,
    token: Path | None = None,
    autorizar: Callable = _autorizar_no_navegador,
    carregar: Callable = carregar_credenciais,
    ha_internet: Callable[[], bool] | None = None,
):
    """Usa a autorização salva ou pede uma nova no navegador.

    autorizar, carregar e ha_internet existem para os testes trocarem o Google
    por dublês.
    """
    from transcritor.rede import SEM_RESPOSTA

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
    # Sem internet, o navegador abriria uma página de erro, e o programa ficaria
    # esperando por um login impossível.
    if not (ha_internet or _ha_internet)():
        raise FalhaNaAutorizacao(SEM_RESPOSTA)
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


def servico_do_drive(credenciais):
    """O cliente da API do Drive v3 que as outras funções recebem."""
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=credenciais, cache_discovery=False)


def conta_conectada(credenciais) -> str:
    """O e-mail da conta autorizada, para a pessoa confirmar que é a certa."""
    from transcritor.pastas import AutorizacaoExpirada, FalhaNoDrive, traduzir

    try:
        sobre = servico_do_drive(credenciais).about().get(fields="user(emailAddress)").execute()
    except Exception as erro:
        traduzido = traduzir(erro)
        if isinstance(traduzido, AutorizacaoExpirada):
            desconectar()
            raise FalhaNaAutorizacao(f"{traduzido}. Conecte de novo") from erro
        if isinstance(traduzido, FalhaNoDrive):
            raise FalhaNaAutorizacao(str(traduzido)) from erro
        raise
    return sobre["user"]["emailAddress"]


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="transcritor-drive", description="Conecta o transcritor ao seu Google Drive."
    )
    parser.add_argument(
        "acao",
        choices=("conectar", "desconectar", "pastas", "pasta-audio", "pasta-pdf", "enviar"),
        help="conectar pede a autorização no navegador; desconectar a esquece neste PC; "
        "pastas lista as pastas do transcritor; pasta-audio e pasta-pdf escolhem ou criam "
        "a pasta de destino de cada arquivo; enviar manda os arquivos para essas pastas",
    )
    parser.add_argument(
        "arquivos",
        nargs="*",
        type=Path,
        help="com enviar: os arquivos; um .pdf vai para a pasta do PDF, e os outros, "
        "para a do áudio",
    )
    parser.add_argument(
        "--nome",
        help="com pasta-audio ou pasta-pdf: usa a pasta com esse nome, criando-a se preciso, "
        "sem perguntar. A escolha vale para os próximos envios",
    )
    argumentos = parser.parse_args(argv)

    if argumentos.acao == "enviar":
        if not argumentos.arquivos:
            parser.error("informe os arquivos a enviar")
        return _comando_enviar(argumentos.arquivos)
    if argumentos.arquivos:
        parser.error("só a ação enviar recebe arquivos")

    if argumentos.acao in ("pastas", "pasta-audio", "pasta-pdf"):
        return _comando_de_pastas(argumentos)

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


def _comando_de_pastas(argumentos) -> int:
    from transcritor import pastas, preferencias

    try:
        servico = servico_do_drive(conectar())
        if argumentos.acao == "pastas":
            encontradas = pastas.listar_pastas(servico)
            if not encontradas:
                print("O transcritor ainda não criou nenhuma pasta no seu Drive.")
            for pasta in encontradas:
                print(pasta.nome)
            return 0
        # "pasta-audio" -> DESTINOS["audio"], "pasta-pdf" -> DESTINOS["pdf"]
        tipo = argumentos.acao.removeprefix("pasta-")
        destino = pastas.DESTINOS[tipo]
        salvas = preferencias.carregar()
        if argumentos.nome:
            escolhida = pastas.obter_ou_criar(servico, argumentos.nome)
        else:
            # Enter mantém a pasta em uso, e não a padrão de fábrica.
            em_uso = salvas.nomes_das_pastas()[tipo]
            escolhida = pastas.escolher_pasta(servico, destino.finalidade, em_uso)
        # "audio" -> o campo pasta_audio das preferências
        preferencias.salvar(replace(salvas, **{f"pasta_{tipo}": escolhida.nome}))
    except pastas.AutorizacaoExpirada as erro:
        desconectar()
        print(f"transcritor-drive: erro: {erro}. {COMO_RECONECTAR}", file=sys.stderr)
        return 1
    except (FalhaNaAutorizacao, pastas.FalhaNoDrive, ValueError) as erro:
        print(f"transcritor-drive: erro: {erro}", file=sys.stderr)
        return 1
    except OSError as erro:
        print(
            f"transcritor-drive: erro: não foi possível salvar a escolha: {erro.strerror}",
            file=sys.stderr,
        )
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nNenhuma pasta escolhida.", file=sys.stderr)
        return 1
    print(f"{destino.rotulo}: {escolhida.nome} (id {escolhida.id})")
    return 0


def mostrar_envio(arquivo: Path, enviado: int, total: int) -> None:
    """Reescreve a mesma linha do terminal; redirecionada, a saída fica sem progresso."""
    if sys.stderr.isatty():
        fim = "\n" if enviado == total else ""
        texto = f"\rEnviando {arquivo.name} ({enviado / total:.0%})"
        print(texto, end=fim, file=sys.stderr, flush=True)


def mostrar_repeticao(tentativa: int, espera: float) -> None:
    from transcritor.envio import TENTATIVAS

    print(
        f"A conexão falhou. Tentativa {tentativa} de {TENTATIVAS} em {espera:.0f} s...",
        file=sys.stderr,
    )


def _comando_enviar(arquivos: list[Path]) -> int:
    from transcritor import preferencias
    from transcritor.entrega import descrever, entregar
    from transcritor.pastas import AutorizacaoExpirada

    falhou = False
    try:
        servico = servico_do_drive(conectar())
        nomes = preferencias.carregar().nomes_das_pastas()
        for entrega in entregar(servico, arquivos, nomes, mostrar_envio, mostrar_repeticao):
            if entrega.erro:
                print(f"transcritor-drive: {descrever(entrega)}", file=sys.stderr)
                falhou = True
            else:
                print(descrever(entrega))
    except AutorizacaoExpirada as erro:
        print(f"transcritor-drive: erro: {erro}. {COMO_RECONECTAR}", file=sys.stderr)
        return 1
    except FalhaNaAutorizacao as erro:
        print(f"transcritor-drive: erro: {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nEnvio cancelado.", file=sys.stderr)
        return 130
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
