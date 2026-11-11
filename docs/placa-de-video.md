# Placa de vídeo: o que foi medido

Medição feita em 10 de novembro de 2026, no mesmo notebook da [comparação dos modelos](comparacao-modelos.md) e das [aulas longas](aulas-longas.md): Intel Core i7-7700HQ, 16 GB de memória e uma **NVIDIA GeForce GTX 1050 Ti com 4 GB**, de 2017. Programas: faster-whisper 1.2.1, CTranslate2 4.8.5, cuBLAS 12.9 e cuDNN 9.

## Fazer a placa funcionar

O CTranslate2 já vem preparado para placas da NVIDIA, mas depende de duas bibliotecas que não vêm com ele: o cuBLAS e o cuDNN. Três descobertas:

1. **O modelo carrega na placa mesmo sem elas.** A falta só aparece no primeiro cálculo, com `Library cublas64_12.dll is not found`. Por isso o programa transcreve um segundo de silêncio logo depois de carregar: se a placa falhar, a troca para o processador acontece antes de a aula começar, e não com ela pela metade.
2. **A NVIDIA publica as duas como pacotes do pip** (`nvidia-cublas-cu12` e `nvidia-cudnn-cu12`). Não é preciso instalar o CUDA Toolkit, só ter o driver atualizado. Em compensação, os pacotes ocupam **2 GB**, por isso ficam num extra opcional, `pip install ".[gpu]"`.
3. **No Windows, as DLLs só são encontradas pelo `PATH`.** O pip as instala dentro do `site-packages`, onde o Windows não procura. Testamos `os.add_dll_directory`, a forma recomendada desde o Python 3.8, e não funcionou: o CTranslate2 carrega as DLLs com a busca clássica do Windows. O programa acrescenta as pastas ao `PATH` do próprio processo antes de usar a placa.

## Tipo de cálculo

A GTX 1050 Ti é da geração Pascal, que não acelera `float16`. O CTranslate2 oferece nela `int8`, `int8_float32` e `float32`. No capítulo de 3 minutos:

| Modelo | `int8` | `int8_float32` | `float32` |
| --- | ---: | ---: | ---: |
| `small` | 7,42x | 7,35x | 6,49x |
| `large-v3-turbo` | 6,53x | 6,96x | 1,36x |

Ficou `int8`, o mesmo do processador. O `float32` do `large-v3-turbo` ocupa o dobro de memória e não cabe bem nos 4 GB, dos quais a tela já usa perto de 1 GB: fica cinco vezes mais lento. A diferença entre `int8` e `int8_float32` está dentro da variação entre execuções.

## Velocidade e erro, modelo a modelo

O mesmo capítulo de 3 minutos e o mesmo script da comparação, agora com `--dispositivo cuda`:

| Modelo | Carga | Transcrição | Velocidade | No processador | Erro de palavras |
| --- | ---: | ---: | ---: | ---: | ---: |
| `tiny` | 0,4 s | 6,8 s | 26,64x | 11,07x | 18,8% |
| `base` | 0,8 s | 9,3 s | 19,42x | 8,51x | 12,2% |
| `small` | 1,8 s | 17,7 s | 10,14x | 3,55x | 6,6% |
| `medium` | 7,4 s | 46,3 s | 3,89x | 1,3x | 1,8% |
| `large-v3-turbo` | 7,0 s | 19,8 s | 9,09x | 0,78x | 1,5% |

**O `large-v3-turbo` é o que mais ganha:** fica doze vezes mais rápido e praticamente empata com o `small`. O motivo está na arquitetura: ele tem um decodificador de só 4 camadas, contra 32 do `large-v3`, e o codificador, a parte pesada, é justamente a que a placa acelera melhor. O erro de palavras de cada modelo mudou um pouco em relação ao processador; com uma palavra valendo 0,3 ponto percentual, as diferenças estão dentro do ruído.

Memória de vídeo: o pico ficou em cerca de 2 GB acima do que a tela já usava, com o `large-v3-turbo`.

## A aula longa

A sessão 13 mostrou que uma amostra de 3 minutos engana: no processador, a velocidade caiu pela metade em duas horas seguidas. Repetimos o mesmo teste, o audiolivro completo de *O Alienista* (1:58:45), agora pela linha de comando no modo automático, que escolheu a placa e o `large-v3-turbo`:

| Medida | Processador, `small` | Placa de vídeo, `large-v3-turbo` |
| --- | ---: | ---: |
| Tempo | 67 min | **17 min 16 s** |
| Velocidade | 1,77x | 6,88x |
| Palavras transcritas | 16 547 | 16 806 |

A placa também perdeu velocidade em relação à amostra curta (de 9,09x para 6,88x), mas bem menos que o processador, e não por calor: o relógio dela ficou entre 1708 e 1721 MHz o tempo todo, com temperatura máxima de 69 °C. A diferença vem provavelmente do que continua no processador, como a decodificação do áudio e o filtro de silêncio, e de execuções de teste feitas em paralelo durante a medição.

## Um defeito que a métrica não via

Ao gerar o primeiro PDF, o `large-v3-turbo` devolveu o capítulo de teste **inteiro em minúsculas e sem pontuação**. A métrica de erro ignora pontuação e maiúsculas, por isso a comparação não mostrou o problema. No audiolivro completo, o mesmo modelo pontuou normalmente: o defeito depende do áudio. O Whisper imita o estilo do texto que já transcreveu e, quando começa sem pontuação, segue assim.

A correção é entregar ao modelo, como se já tivesse sido dita, uma frase pontuada em português (`initial_prompt`). Com ela, no mesmo capítulo:

| Modelo | Sinais de pontuação, sem e com a frase | Erro de palavras, sem e com a frase |
| --- | ---: | ---: |
| `large-v3-turbo`, placa | 0 → 59 | 1,8% → 2,1% |
| `small`, placa | 61 → 55 | 6,3% → 6,9% |
| `small`, processador | 59 → 62 | 6,9% → 6,6% |

O erro de palavras variou uma ou duas palavras para cima ou para baixo, dentro do ruído. A frase vai no começo de cada bloco de 10 minutos, já que cada bloco começa sem texto anterior.

## Decisão

- **Com placa de vídeo, o padrão é o `large-v3-turbo`.** Erra cerca de quatro vezes menos que o `small` e transcreve uma aula de duas horas em pouco mais de um quarto de hora.
- **Sem placa, continua o `small`**, pelos motivos da [comparação](comparacao-modelos.md).
- **O modo automático testa a placa e volta para o processador** se ela não existir ou falhar, dizendo o motivo. Quem pede `--dispositivo cuda` recebe um erro em vez disso, porque uma transcrição dez vezes mais lenta sem aviso seria pior.

## Limites

- Uma placa só, e antiga. Placas mais novas aceleram `float16` e devem ser bem mais rápidas; uma placa com 2 GB pode não ter memória para o `large-v3-turbo`. Nesse caso, o teste de silêncio falha, e o programa volta para o processador.
- Só placas da NVIDIA. O CTranslate2 não usa placas da AMD nem a placa integrada da Intel.
- O PC do amigo ainda não foi visto. Se ele não tiver uma NVIDIA, nada desta página muda a experiência dele, e o instalador não precisa levar os 2 GB de bibliotecas.
