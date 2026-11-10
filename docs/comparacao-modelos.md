# Comparação dos modelos do Whisper

Medição feita em 9 de novembro de 2026 para escolher o modelo padrão do transcritor.

## Como foi medido

- **Máquina:** notebook com Intel Core i7-7700HQ (4 núcleos, 2017) e Windows 10. A transcrição rodou só no processador, com o tipo de cálculo `int8`.
- **Programas:** faster-whisper 1.2.1, CTranslate2 4.8.5, Python 3.14.
- **Áudio:** o capítulo XI de *O Alienista*, de Machado de Assis, lido em português para o [LibriVox](https://archive.org/details/o_alienista_0904_librivox). São 3 minutos, em domínio público.
- **Referência:** o texto do mesmo capítulo no [Wikisource](https://pt.wikisource.org/wiki/O_Alienista/XI), em [`amostras/alienista-cap11.txt`](../amostras/alienista-cap11.txt).
- **Erro de palavras (WER):** trocas, faltas e sobras de palavras, divididas pelo número de palavras da referência (334). Maiúsculas e pontuação não contam; acentos contam. A abertura e o encerramento da gravação, que não estão no livro, ficam fora da conta.
- **Velocidade:** duração do áudio dividida pelo tempo de transcrição. Com 2x, uma aula de uma hora leva meia hora.

Para repetir a medição:

```text
python scripts/comparar_modelos.py alienista-cap11.mp3 amostras/alienista-cap11.txt --saida resultados
```

O áudio não está no repositório. Ele é o arquivo `oalienista_7_machadodeassis_64kb.mp3` da página do LibriVox acima.

## Resultados

| Modelo | Tamanho | Carga | Transcrição | Velocidade | Erro de palavras |
| --- | ---: | ---: | ---: | ---: | ---: |
| `tiny` | 75 MB | 0,5 s | 16,2 s | 11,07x | 14,6% |
| `base` | 141 MB | 0,5 s | 21,1 s | 8,51x | 11,0% |
| `small` | 464 MB | 1,4 s | 50,7 s | 3,55x | 7,2% |
| `medium` | 1460 MB | 4,1 s | 138,8 s | 1,3x | 8,1% |
| `large-v3-turbo` | 1547 MB | 4,5 s | 230,1 s | 0,78x | 1,8% |

**Estas velocidades valem para um áudio curto.** Em uma aula inteira, a transcrição fica mais lenta, provavelmente porque o processador esquenta: o `small` transcreveu um áudio de 2 horas em 67 minutos, a 1,77x o tempo real, metade da velocidade desta tabela. A medição está em [aulas-longas.md](aulas-longas.md). Para os outros modelos, a velocidade em uma aula longa não foi medida, e é de esperar uma queda parecida.

## O que os erros mostram

Comparando cada transcrição com a referência, palavra por palavra:

- **`small`:** erra principalmente a crase ("a Câmara" no lugar de "à Câmara", quatro vezes) e palavras raras: "estipêndio" virou "estipém de o", "fausto" virou "falso", "houve" virou "ouve". O texto continua compreensível.
- **`medium`:** acertou quase tudo, mas **pulou uma frase inteira**, de 20 palavras. É por isso que ficou atrás do `small` nesta amostra. Sem essa frase, o erro seria de cerca de 2%.
- **`large-v3-turbo`:** três diferenças de verdade em 334 palavras.
- **Piso da medida:** a pessoa que lê diz "do domínio" a mais e pula a palavra "terceiro". Isso soma cerca de 1% de erro para todos os modelos, sem culpa deles.

## Decisão

- **Padrão: `small`.** No processador, é o maior modelo que ainda transcreve mais rápido que o tempo real mesmo em uma aula longa, e o PC do amigo pode não ter placa de vídeo. Uma aula de uma hora fica pronta em cerca de 34 minutos, pela medição do áudio de 2 horas, com 464 MB de download.
- **Opção de qualidade: `large-v3-turbo`**, com `--modelo large-v3-turbo`, para quem aceita esperar bem mais que a duração da aula.
- **`medium` não compensa:** custa quase três vezes o tempo do `small` e, nesta amostra, não foi melhor. Em uma aula longa, deve ficar mais lento que o tempo real.

## Limites desta comparação

- É uma amostra só, de 3 minutos. Uma palavra errada vale 0,3 ponto percentual, então diferenças pequenas, como a entre `small` e `medium`, estão dentro do ruído.
- O áudio é uma leitura limpa, perto do microfone. Uma aula gravada na sala, com eco, ruído e fala espontânea, terá mais erros em todos os modelos.
- O vocabulário é literário, do século XIX, o que prejudica os modelos menores mais do que uma aula comum prejudicaria.
- A placa de vídeo ficou de fora. A sessão 14 mede os mesmos modelos nela e pode mudar o padrão para quem tiver uma.
