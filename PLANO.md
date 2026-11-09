# Transcritor de aulas

A pessoa envia o áudio de uma aula, e a aplicação transcreve, gera um PDF e salva os arquivos nas pastas escolhidas do Google Drive.

## Decisões

- **Usuário:** um amigo do Lucas, rodando no próprio PC.
- **Transcrição:** faster-whisper, uma implementação local e gratuita do Whisper. O áudio não sai do PC durante a transcrição.
- **Modelo:** `small` por padrão e `large-v3-turbo` como opção de qualidade, escolhidos na sessão 11 com um áudio real. Os números estão em [docs/comparacao-modelos.md](docs/comparacao-modelos.md). Rever na sessão 14, com a placa de vídeo.
- **Drive:** o usuário conecta a própria conta e escolhe a pasta do áudio e a pasta do PDF.

## Funcionar em outro PC

Funcionar no PC do Lucas não garante que funcione no do amigo. O projeto precisa cuidar destes pontos:

- **Dependências:** o instalador precisa levar ou instalar o ffmpeg e tudo que o Python usa.
- **Hardware:** sem placa de vídeo compatível, a transcrição roda no processador, mais devagar.
- **Modelo:** o download inicial exige internet e espaço em disco.
- **Google:** o acesso ao Drive exige um projeto próprio no Google Cloud, e o modo de teste tem limitações de usuários e de duração da autorização. Confirmar as regras atuais na sessão 18.

Antes de implementar, descobrir qual é o PC do amigo: sistema, memória e placa de vídeo.

## Cuidados

- Nunca publicar credenciais ou tokens do Google no repositório.
- Pedir ao Google apenas as permissões mínimas para o Drive.
- Usar nos testes um áudio próprio ou de licença livre, nunca a gravação de uma aula.
- Avisar no README que é preciso ter permissão para gravar e transcrever a aula.
- Usar Python 3.12 se as dependências ainda não funcionarem no Python 3.14 instalado.
- Manter modelos e ambientes virtuais fora do OneDrive, para evitar sincronização pesada.

## Pronto quando

- Uma aula longa vira um PDF legível sem intervenção manual.
- O áudio e o PDF chegam às pastas escolhidas no Drive.
- A instalação funciona em um PC sem ambiente de desenvolvimento.
