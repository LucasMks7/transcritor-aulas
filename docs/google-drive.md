# Acesso ao Google Drive

Regras conferidas em 11 de novembro de 2026, na documentação do Google.

## Decisões

- **Escopo `drive.file`.** O programa só enxerga os arquivos e pastas que ele mesmo criou. Não lê, não lista e não apaga nada do resto do Drive. O Google classifica esse escopo como [recomendado e não sensível](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), e por isso ele não exige aprovação do app. A consequência: as pastas de destino (sessões 19 e 20) são pastas criadas pelo transcritor. Uma pasta que já existia no Drive não aparece na lista.
- **Publicar o app em vez de deixá-lo em teste.** Em teste, só entram até 100 usuários cadastrados, e [a autorização expira 7 dias depois do consentimento](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview). O amigo teria de reconectar toda semana. Como o único escopo é não sensível, o app pode ser publicado sem passar pela verificação do Google. Ao publicar, é preciso **conectar de novo**, porque um token emitido durante o teste continua expirando em 7 dias.
- **Aplicativo para computador (OAuth "Desktop app").** A autorização abre o navegador, e o Google devolve a resposta para um servidor temporário no próprio PC, numa porta livre escolhida na hora.
- **Onde ficam os arquivos.** O `client_secret.json` identifica o programa, e o `token.json` guarda a autorização da pessoa. Os dois ficam em `%APPDATA%\transcritor-aulas`, fora do repositório, e o `.gitignore` bloqueia os dois nomes. O Google avisa que o segredo de um app de computador não fica realmente secreto, porque vai junto com o programa. Mesmo assim, ele não é publicado no GitHub, para ninguém usar a cota do projeto em nome dele.

## Criar o projeto no Google Cloud

1. Em [console.cloud.google.com](https://console.cloud.google.com/), crie um projeto chamado `transcritor-aulas`.
2. Em **APIs e serviços > Biblioteca**, ative a **Google Drive API**.
3. Em **Google Auth Platform > Branding**, preencha o nome do app (`Transcritor de aulas`) e o seu e-mail de suporte. O público é **Externo**.
4. Em **Google Auth Platform > Acesso a dados**, adicione o escopo `https://www.googleapis.com/auth/drive.file`. Ele deve aparecer na lista de escopos não sensíveis.
5. Em **Google Auth Platform > Clientes**, crie um cliente do tipo **App para computador**. Baixe o JSON e salve-o como `%APPDATA%\transcritor-aulas\client_secret.json`.
6. Em **Google Auth Platform > Público**, clique em **Publicar app**.

## Conectar

```text
transcritor-drive conectar      # abre o navegador e mostra a conta conectada
transcritor-drive desconectar   # esquece a autorização neste PC
```

Como o app não é verificado, o Google mostra o aviso "O Google não verificou este app". Para seguir, clique em **Avançado** e depois em **Acessar transcritor-aulas**. A tela seguinte diz exatamente o que o app pode fazer: ver, editar, criar e excluir **apenas os arquivos do Drive que você usar com este app**.

Para revogar o acesso também no Google, use [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Quando a autorização deixa de valer

O programa renova o acesso sozinho. Se a pessoa revogar a autorização ou se ela vencer, o token salvo é apagado, e o próximo `conectar` pede a autorização de novo no navegador.
