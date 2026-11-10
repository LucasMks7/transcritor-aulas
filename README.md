# Transcritor de aulas

Transcreve o áudio de uma aula no próprio PC, com o [faster-whisper](https://github.com/SYSTRAN/faster-whisper). O áudio não é enviado para nenhum serviço: depois do download inicial do modelo, a transcrição funciona sem internet.

> **Status:** em desenvolvimento. O plano completo, com PDF e envio para o Google Drive, está em [PLANO.md](PLANO.md).

> **Antes de gravar:** é preciso ter permissão para gravar e para transcrever uma aula. Combine com quem dá a aula e respeite as regras da instituição.

## Uso

```text
transcrever aula.mp3                           # cria aula.txt ao lado do áudio
transcrever aula.mp3 --saida anotacoes.txt     # escolhe o arquivo de texto
transcrever aula.mp3 --modelo large-v3-turbo   # erra menos e demora mais
```

Na primeira vez, o modelo é baixado da internet. Depois disso, o comando funciona sem conexão.

| Opção | Valores | Padrão |
| --- | --- | --- |
| `--saida` | qualquer caminho de arquivo | o nome do áudio, com `.txt` |
| `--modelo` | `tiny`, `base`, `small`, `medium`, `large-v3-turbo` | `small` |

| Código de saída | Significado |
| --- | --- |
| `0` | Transcrição salva |
| `1` | A transcrição falhou (modelo não carregado, falta de memória etc.) |
| `2` | Entrada inválida (arquivo de áudio, arquivo de saída ou opções) |
| `130` | Cancelado com `Ctrl+C` |

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

O Whisper tem modelos de vários tamanhos: os maiores erram menos e demoram mais. A comparação, feita com um áudio real em português, está em [docs/comparacao-modelos.md](docs/comparacao-modelos.md). Em resumo, em um notebook de 2017, sem usar a placa de vídeo:

| Modelo | Download | Aula de 1 hora | Erro de palavras |
| --- | ---: | ---: | ---: |
| `small` (padrão) | 464 MB | cerca de 34 min | 7,2% |
| `large-v3-turbo` | 1547 MB | mais de 77 min | 1,8% |

O tempo do `small` vem da transcrição de um áudio de 2 horas, que levou 67 minutos. O do `large-v3-turbo` é uma projeção a partir de um áudio de 3 minutos; em uma aula inteira, a transcrição fica mais lenta e o tempo real deve ser maior.

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

Os testes não usam gravações de aulas. A amostra da comparação é um capítulo de *O Alienista* lido para o LibriVox, em domínio público; o áudio não fica no repositório.

## Licença

[MIT](LICENSE)
