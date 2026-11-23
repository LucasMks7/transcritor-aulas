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

## Pastas de destino

```text
transcritor-drive pastas                          # lista as pastas que o transcritor criou
transcritor-drive pasta-audio                     # escolhe pelo número ou cria uma pasta nova
transcritor-drive pasta-audio --nome "Cálculo II" # usa essa pasta, criando-a se preciso
transcritor-drive pasta-pdf                       # o mesmo para a pasta do PDF
```

- Por causa do `drive.file`, a lista mostra só as pastas criadas pelo transcritor, nunca o resto do Drive.
- O Drive aceita duas pastas com o mesmo nome. Por isso o transcritor procura a pasta pelo nome antes de criar e reaproveita a que já existe.
- Uma pasta que foi para a lixeira some da lista.
- Os nomes padrão são `Transcritor - Áudios` e `Transcritor - PDFs`. O PDF também pode ir para a mesma pasta do áudio: basta escolher o número dela.
- Enquanto as preferências não forem salvas (sessão 22), o comando só mostra a pasta escolhida e o ID dela.

## Enviar

```text
transcritor-drive enviar aula.mp3 aula.pdf   # o .pdf vai para a pasta do PDF, o resto para a do áudio
```

- **Retomada.** O arquivo vai em blocos de 2 MB. Se a conexão cair, o programa pergunta ao Drive até onde chegou e continua dali.
- **Nova tentativa.** Quedas de conexão, erros 5xx e pedidos de "mais devagar" (429 e limites de ritmo do 403) são repetidos até 6 vezes, com esperas que dobram: 1, 2, 4, 8 e 16 segundos. Cada bloco entregue zera a contagem. Pasta apagada, falta de espaço e recusas do Drive param na hora, porque repetir não resolve.
- **Sem cópias.** Um arquivo com o mesmo nome e o mesmo conteúdo (MD5) que já está na pasta não é enviado de novo. O mesmo nome com outro conteúdo vira um arquivo novo: o gravador do celular dá o mesmo nome a aulas diferentes, e substituir apagaria uma delas.
- A falha em um arquivo não impede o envio dos outros, e o original nunca é apagado do PC.

Conferido no Drive de verdade em 23 de novembro de 2026: 5 MB com uma queda forçada no segundo bloco, retomados sem reenviar o que já tinha chegado.

Para revogar o acesso também no Google, use [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Quando a autorização deixa de valer

O programa renova o acesso sozinho. Se a pessoa revogar a autorização ou se ela vencer, o token salvo é apagado, e o próximo `conectar` pede a autorização de novo no navegador.
