"""Gravação do texto e do PDF sem nunca deixar um arquivo pela metade.

O terminal e a janela usam as mesmas regras: enquanto o trabalho não termina,
tudo fica em um arquivo .parcial, e o nome definitivo só aparece completo.
"""

from pathlib import Path

from transcritor.pdf import Cabecalho, gerar_pdf
from transcritor.transcricao import Segmento


class SaidaInvalida(ValueError):
    """O arquivo de saída pedido não pode ser usado."""


def caminho_parcial(saida: Path) -> Path:
    """Onde o arquivo é gravado enquanto não está completo."""
    return saida.with_name(saida.name + ".parcial")


def conferir_saida(audio: Path, saida: Path) -> None:
    """Recusa uma saída que apagaria o próprio áudio ou que confunde texto e PDF."""
    if saida.suffix.lower() == ".pdf":
        raise SaidaInvalida(
            "--saida é o arquivo de texto; o PDF é criado ao lado dele, com o mesmo nome."
        )
    if audio.resolve() in (saida.resolve(), saida.with_suffix(".pdf").resolve()):
        raise SaidaInvalida(
            "a saída não pode ser o próprio áudio, que seria apagado pela transcrição."
        )


class TextoParcial:
    """Grava cada trecho no disco assim que fica pronto.

    Se a transcrição de uma aula longa for interrompida, o que já foi feito não
    se perde: fica no .parcial. O .txt só existe com a transcrição completa.
    """

    def __init__(self, saida: Path):
        self.saida = saida
        self.parcial = caminho_parcial(saida)
        # Aberto já no começo: uma pasta sem permissão de gravação aparece
        # agora, e não no fim de uma hora de transcrição. Levanta OSError.
        self._arquivo = self.parcial.open("w", encoding="utf-8")

    def guardar(self, segmento: Segmento) -> None:
        self._arquivo.write(segmento.texto + "\n")
        self._arquivo.flush()

    def concluir(self) -> Path:
        """Dá ao texto o nome definitivo, substituindo uma transcrição anterior."""
        self._arquivo.close()
        self.parcial.replace(self.saida)
        return self.saida

    def abandonar(self) -> Path | None:
        """Devolve onde ficou o que já foi transcrito, ou apaga o parcial vazio."""
        self._arquivo.close()
        if self.parcial.stat().st_size > 0:
            return self.parcial
        self.parcial.unlink()
        return None


def gravar_pdf(segmentos, cabecalho: Cabecalho, pdf: Path) -> Path:
    """Gera o PDF e só então lhe dá o nome definitivo. Levanta OSError."""
    parcial = caminho_parcial(pdf)
    try:
        gerar_pdf(segmentos, cabecalho, parcial)
        parcial.replace(pdf)
    except OSError:
        parcial.unlink(missing_ok=True)
        raise
    return pdf
