# Transcritor de aulas

Transcreve o áudio de uma aula no próprio PC, com o [faster-whisper](https://github.com/SYSTRAN/faster-whisper). O áudio não é enviado para nenhum serviço: depois do download inicial do modelo, a transcrição funciona sem internet.

> **Status:** em desenvolvimento. O plano completo, com PDF e envio para o Google Drive, está em [PLANO.md](PLANO.md).

> **Antes de gravar:** é preciso ter permissão para gravar e para transcrever uma aula. Combine com quem dá a aula e respeite as regras da instituição.

## Escolha do modelo

O Whisper tem modelos de vários tamanhos: os maiores erram menos e demoram mais. A comparação, feita com um áudio real em português, está em [docs/comparacao-modelos.md](docs/comparacao-modelos.md). Em resumo, em um notebook de 2017, sem usar a placa de vídeo:

| Modelo | Download | Aula de 1 hora | Erro de palavras |
| --- | ---: | ---: | ---: |
| `small` (padrão) | 464 MB | cerca de 17 min | 7,2% |
| `large-v3-turbo` | 1547 MB | cerca de 77 min | 1,8% |

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
