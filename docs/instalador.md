# Instalador para Windows

Para quem vai só usar o programa: não precisa ter Python, ffmpeg nem senha de administrador.

## Montar

```bash
pip install -e ".[instalador]"
winget install JRSoftware.InnoSetup --scope user
python scripts/montar_instalador.py
```

O resultado fica em `%LOCALAPPDATA%\transcritor-aulas-instalador`, fora do OneDrive. Leva uns cinco minutos em um notebook de 2017.

Com `--client-secret CAMINHO`, o instalador leva o `client_secret.json`, e quem instala conecta ao Drive sem criar um projeto no Google Cloud. **Esse instalador não pode ser publicado no GitHub**: ele deve ir direto para a pessoa. Se a pessoa tiver o próprio `client_secret.json` em `%APPDATA%\transcritor-aulas`, o dela vem antes.

## O que vai dentro

| | Tamanho |
| --- | ---: |
| Instalador | 106 MB |
| Programa instalado | 306 MB |
| Modelo `small`, baixado na primeira transcrição | 464 MB |

São três executáveis que dividem as mesmas bibliotecas: `Transcritor.exe` (a janela, com atalho no menu Iniciar), `transcrever.exe` e `transcritor-drive.exe` (os comandos do terminal, na pasta do programa).

## Decisões

- **PyInstaller e Inno Setup.** O PyInstaller junta o Python e as bibliotecas em uma pasta; o Inno Setup transforma a pasta em um instalador com atalhos e desinstalação.
- **Pasta, e não arquivo único.** O executável único do PyInstaller se descompacta inteiro em uma pasta temporária a cada abertura e é mais confundido com vírus.
- **Instala só para a pessoa,** em `%LOCALAPPDATA%\Programs`. Não pede senha de administrador.
- **Sem as bibliotecas da NVIDIA.** Elas somam 2 GB, quase sete vezes o programa todo. No instalado, a transcrição roda no processador, e o programa diz por quê. Antes, um PC com placa e sem as bibliotecas baixava 1,5 GB do `large-v3-turbo` para só então descobrir que não podia usá-lo; agora isso é conferido antes do download.
- **Sem o modelo.** Ele é baixado na primeira transcrição e fica no cache do Hugging Face.
- **Só a API do Drive.** A biblioteca do Google traz a descrição de todas as APIs; a receita mantém só a do Drive.
- **Conferência antes de empacotar.** A montagem falha se a pasta tiver um token, um `client_secret.json` que não foi pedido, um áudio ou um modelo, ou se passar de 700 MB.
- **Atualização limpa.** Instalar uma versão nova apaga as bibliotecas da anterior, para não misturar as duas.
- **Desinstalar pergunta antes de apagar** as preferências e a autorização do Google, e o padrão é manter. Transcrições, áudios e arquivos no Drive nunca são apagados. O modelo continua em `%USERPROFILE%\.cache\huggingface` e pode ser apagado à mão.

## Aviso do Windows

O instalador não tem assinatura digital, que é paga. Por isso, o SmartScreen pode mostrar "O Windows protegeu o computador". Para seguir, clique em **Mais informações** e em **Executar assim mesmo**, e só se o arquivo veio direto de quem o montou.

## O que foi conferido

Em 23 de novembro de 2026, no Windows 10, com o `PATH` só do Windows, `APPDATA` vazio e sem modelo em cache, em uma pasta com espaço e acento no nome:

- instalação silenciosa, `transcrever.exe` do download do modelo ao PDF e mensagens de erro de áudio inexistente e de `client_secret.json` ausente;
- o código da janela, em um executável sem terminal, do download do `small` ao PDF;
- reinstalação por cima da anterior e desinstalação silenciosa, que manteve as preferências e a autorização.

O GitHub Actions repete a montagem, a instalação, a transcrição, a abertura da janela e a desinstalação quando o código muda.

Ainda falta testar em um PC de outra pessoa, sem nada de desenvolvimento, e o login no Google a partir do programa instalado (sessão 25).
