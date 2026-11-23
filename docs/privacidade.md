# Política de privacidade do Transcritor de aulas

Atualizada em 23 de novembro de 2026.

O Transcritor de aulas é um programa gratuito e de código aberto que roda no computador de quem o usa. Ele não tem servidor próprio, não exibe anúncios e não coleta estatísticas de uso.

## O que fica no computador

- O áudio da aula, o texto e o PDF. A transcrição é feita no próprio computador, e o áudio não é enviado a nenhum serviço de transcrição.
- As preferências e, se a pessoa conectar o Google Drive, a autorização de acesso. Ficam em `%APPDATA%\transcritor-aulas`.

## O que sai do computador

- **Só se a pessoa pedir:** o áudio e o PDF são enviados para o Google Drive dela, diretamente do computador para o Google. O desenvolvedor não recebe nem vê esses arquivos.
- Na primeira transcrição, o programa baixa o modelo de reconhecimento de fala do Hugging Face. Nenhum áudio vai nesse pedido.

## Acesso à conta do Google

O programa pede só a permissão `drive.file`. Com ela, ele enxerga apenas os arquivos e as pastas que ele mesmo criou no Drive, e nunca o resto. Ele a usa para:

- criar e encontrar as pastas de destino;
- enviar o áudio e o PDF, e reconhecer o que já foi enviado;
- mostrar o e-mail da conta conectada, para a pessoa confirmar que é a certa.

Os dados da conta do Google não são guardados fora do computador, vendidos, compartilhados nem usados para anúncios ou para treinar modelos.

## Como apagar

- `transcritor-drive desconectar` apaga a autorização deste computador.
- Em [myaccount.google.com/permissions](https://myaccount.google.com/permissions), a pessoa revoga o acesso do programa.
- Os arquivos enviados ficam no Drive da pessoa, que pode apagá-los quando quiser.

## Contato

Dúvidas: [abra uma issue no repositório](https://github.com/LucasMks7/transcritor-aulas/issues).
