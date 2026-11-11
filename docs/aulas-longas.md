# Aulas longas: o que foi medido

Medição feita em 9 de novembro de 2026, na mesma máquina da [comparação dos modelos](comparacao-modelos.md): Intel Core i7-7700HQ, 16 GB de memória, só no processador, com o modelo `small`.

O áudio de teste é o audiolivro completo de *O Alienista* do [LibriVox](https://archive.org/details/o_alienista_0904_librivox), em domínio público: os nove arquivos juntos somam 1 hora, 58 minutos e 45 segundos.

## O problema encontrado

Na primeira versão, o comando entregava o arquivo inteiro ao faster-whisper. A transcrição terminou sem erros, mas com dois números ruins:

| Medida | Resultado |
| --- | ---: |
| Tempo | 67 min (1,77x o tempo real) |
| Pico de memória | 7089 MB |
| Palavras transcritas | 16 547 |

**Memória.** Sete gigabytes travariam um PC com 8 GB. A causa não é o modelo nem o filtro de silêncio: decodificar as duas horas e filtrar o silêncio chega a 1,6 GB. O restante vem do espectrograma, que o faster-whisper calcula para o áudio inteiro de uma vez antes de transcrever. O gasto cresce com a duração, cerca de 3,5 GB por hora de aula.

**Tempo.** Na amostra de 3 minutos, o `small` rodou a 3,55x o tempo real. Em duas horas seguidas, caiu para 1,77x. A causa não foi medida; a mais provável é o processador do notebook, que esquenta em carga contínua e reduz a velocidade. De qualquer forma, projetar o tempo de uma aula a partir de uma amostra curta dá um número otimista demais.

## A correção

O áudio agora vai para o modelo em blocos de 10 minutos. Para não partir uma palavra ao meio, cada corte é procurado nos 30 segundos finais do bloco, no ponto de menor volume, que costuma ser uma pausa entre frases. Os tempos de cada bloco são somados ao início dele, então continuam contados desde o começo da aula.

| Medida | Antes | Com blocos |
| --- | ---: | ---: |
| Pico de memória no áudio de 2 horas | 7089 MB | 1470 MB |
| Pico de memória em 17 minutos de áudio (modelo `tiny`) | não medido | 793 MB |
| Erro de palavras no capítulo de teste | 7,2% | 6,9% |

O pico de 1470 MB foi lido aos 22 minutos de áudio, depois de dois cortes de bloco, e estava parado desde o primeiro minuto. A execução foi encerrada ali, porque o tempo total já era conhecido.

**Os cortes não pioraram o texto.** Comparando os primeiros 22 minutos das duas execuções, as diferenças aparecem espalhadas pelo texto, e não concentradas nos minutos 10 e 20. Em vários pontos, a versão em blocos trouxe frases que a primeira tinha pulado. As duas execuções diferem em cerca de 11% das palavras, o que mostra o quanto o Whisper varia quando o mesmo áudio é dividido de outro jeito.

## O que ainda pesa

- O arquivo é decodificado inteiro para a memória antes da transcrição: são cerca de 220 MB por hora de áudio, com um pico passageiro de mais que o dobro disso. É o que sobra do pico de 1470 MB. Decodificar aos poucos resolveria, e fica para quando houver necessidade.
- Uma aula de duas horas leva mais de uma hora no processador. Com a placa de vídeo, o mesmo áudio levou 17 minutos, com um modelo que erra menos; veja [placa-de-video.md](placa-de-video.md).
