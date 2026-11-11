# Transcritor de aulas

[![Testes](https://github.com/LucasMks7/transcritor-aulas/actions/workflows/testes.yml/badge.svg)](https://github.com/LucasMks7/transcritor-aulas/actions/workflows/testes.yml)

Transcreve o áudio de uma aula no próprio PC, com o [faster-whisper](https://github.com/SYSTRAN/faster-whisper). O áudio não é enviado para nenhum serviço: depois do download inicial do modelo, a transcrição funciona sem internet.

> **Status:** em desenvolvimento. O plano completo, com envio para o Google Drive, está em [PLANO.md](PLANO.md).

> **Antes de gravar:** é preciso ter permissão para gravar e para transcrever uma aula. Combine com quem dá a aula e respeite as regras da instituição.

## Uso

```text
transcrever aula.mp3                           # cria aula.txt e aula.pdf ao lado do áudio
transcrever aula.mp3 --saida anotacoes.txt     # cria anotacoes.txt e anotacoes.pdf
transcrever aula.mp3 --modelo large-v3-turbo   # erra menos e demora mais
transcrever aula.mp3 --dispositivo cpu         # não usa a placa de vídeo
```

Na primeira vez, o modelo é baixado da internet. Depois disso, o comando funciona sem conexão.

| Opção | Valores | Padrão |
| --- | --- | --- |
| `--saida` | caminho do arquivo de texto; o PDF fica ao lado | o nome do áudio, com `.txt` |
| `--modelo` | `tiny`, `base`, `small`, `medium`, `large-v3-turbo` | `large-v3-turbo` na placa de vídeo, `small` no processador |
| `--dispositivo` | `auto`, `cuda` (placa de vídeo da NVIDIA), `cpu` | `auto` |

| Código de saída | Significado |
| --- | --- |
| `0` | Transcrição salva |
| `1` | A transcrição falhou (modelo não carregado, falta de memória etc.) ou o PDF não pôde ser gravado |
| `2` | Entrada inválida (arquivo de áudio, arquivo de saída ou opções) |
| `130` | Cancelado com `Ctrl+C` |

### Janela

Para quem prefere não usar o terminal:

```text
transcrever-janela
```

Basta escolher o áudio e clicar em **Transcrever**. A janela mostra quanto do áudio já foi transcrito e, no fim, o botão **Abrir PDF** abre o resultado. O texto e o PDF ficam na mesma pasta do áudio, com o mesmo nome. O modelo e o dispositivo são escolhidos sozinhos, como no modo `auto` do terminal.

**Cancelar** para a transcrição no próximo trecho, e o que já estava pronto fica no arquivo `.parcial`. Enquanto o modelo é baixado, na primeira vez, o cancelamento só acontece quando o download termina.

A janela e o terminal usam o mesmo código para conferir o áudio, transcrever e gravar os arquivos. A transcrição roda em outra thread, para a janela continuar respondendo, e manda o andamento para ela por uma fila, porque o Tkinter só aceita ser usado pela thread que o criou.

### PDF

Junto com o texto, o comando gera um PDF pronto para ler e imprimir: o nome do áudio como título, a duração, a data e o modelo usado, e o texto dividido em parágrafos nas pausas da fala. Cada parágrafo começa com o tempo em que aparece na gravação, como `12:30`, para quem estuda voltar ao áudio naquele ponto.

O PDF usa as fontes que já vêm em todo leitor de PDF, então não depende de nenhum arquivo de fonte. Todas as letras do português aparecem normalmente; aspas curvas e travessões viram aspas retas e hífens.

### Placa de vídeo

Com uma placa de vídeo da NVIDIA, a transcrição fica muitas vezes mais rápida, e o modelo padrão passa a ser o `large-v3-turbo`, o que menos erra. No modo `auto`, o comando testa a placa antes de começar: se ela não existir ou não funcionar, a transcrição segue no processador, e o terminal diz por quê. Com `--dispositivo cuda`, uma placa que não funciona vira erro, em vez de uma transcrição lenta sem aviso.

A placa precisa de duas bibliotecas da NVIDIA, o cuBLAS e o cuDNN, que ocupam cerca de 2 GB e por isso não vêm na instalação padrão:

```bash
pip install -e ".[gpu]"
```

Basta ter o driver da NVIDIA atualizado; não é preciso instalar o CUDA Toolkit. As medições estão em [docs/placa-de-video.md](docs/placa-de-video.md).

### Formatos aceitos

O comando confere o conteúdo do arquivo, não a extensão. Ele lê os formatos comuns de áudio, como MP3, M4A (gravador do celular), OGG/Opus (áudio do WhatsApp), WAV e FLAC, e também vídeos com som, como a gravação de uma aula em MP4. Não é preciso instalar o ffmpeg: a biblioteca que lê o áudio já o traz embutido.

Um arquivo que não é áudio, ou um vídeo sem som, é recusado na hora, antes de o modelo ser carregado.

### Aulas longas

- **Progresso:** o terminal mostra quanto do áudio já foi transcrito, como em `Transcrevendo 12:30 de 1:45:00 (12%)`.
- **Nada se perde no meio:** cada trecho transcrito é gravado na hora em um arquivo `.parcial`, ao lado do arquivo de saída. Se a transcrição for cancelada ou falhar, o comando informa onde ficou o que já estava pronto. O `.txt` só aparece com a transcrição completa.
- **Silêncio:** os trechos sem fala são pulados. Isso poupa tempo e evita um defeito conhecido do Whisper, que em silêncio longo repete ou inventa frases.
- **Memória:** o áudio vai para o modelo em blocos de 10 minutos, cortados nas pausas da fala. Sem isso, um áudio de 2 horas chegou a ocupar 7 GB de memória; com os blocos, o pico ficou em 1,5 GB.

As medições estão em [docs/aulas-longas.md](docs/aulas-longas.md).

## Escolha do modelo

O Whisper tem modelos de vários tamanhos: os maiores erram menos e demoram mais. A comparação, feita com um áudio real em português, está em [docs/comparacao-modelos.md](docs/comparacao-modelos.md), e a medição na placa de vídeo, em [docs/placa-de-video.md](docs/placa-de-video.md). Em resumo, em um notebook de 2017 com uma GTX 1050 Ti:

| Modelo | Download | Aula de 1 hora no processador | Aula de 1 hora na placa de vídeo | Erro de palavras |
| --- | ---: | ---: | ---: | ---: |
| `small` | 464 MB | cerca de 34 min (padrão) | cerca de 6 min | 7,2% |
| `large-v3-turbo` | 1547 MB | mais de 77 min | cerca de 9 min (padrão) | 1,8% |

Os tempos do `small` no processador e do `large-v3-turbo` na placa vêm de um áudio de 2 horas, transcrito em 67 e em 17 minutos. Os outros dois são projeções a partir de um áudio de 3 minutos, e numa aula inteira devem ser maiores.

## Desenvolvimento

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows com Git Bash
# .venv\Scripts\Activate.ps1    # Windows com PowerShell
pip install -e ".[dev]"
pytest
```

Se o projeto estiver em uma pasta sincronizada, como o OneDrive, crie o ambiente virtual fora dela. Os modelos ficam no cache do Hugging Face, na pasta do usuário, também fora do projeto.

Os testes comuns trocam o Whisper por um dublê e geram os próprios áudios, então rodam em segundos e sem internet.

O teste de ponta a ponta roda o comando de verdade, com o modelo `tiny`, sobre o capítulo XI de *O Alienista* lido para o LibriVox, em domínio público. O áudio não fica no repositório: o script baixa e confere o arquivo. O teste exige que a transcrição erre menos de 25% das palavras do livro (o `tiny` erra cerca de 15%).

```bash
python scripts/baixar_amostra.py
pytest -m ponta_a_ponta
```

O GitHub Actions roda os testes comuns no Windows e no Ubuntu, com Python 3.10 e 3.14, e o de ponta a ponta no Windows, a cada push. Os testes nunca usam gravações de aulas.

## Licença

[MIT](LICENSE)
