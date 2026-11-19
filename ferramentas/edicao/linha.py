"""Linha do tempo: converte entre o tempo do arquivo de origem e o da sequência.

Os cortes ficam guardados no tempo da origem (sobrevivem a novas versões do
corte). A sequência é o encadeamento dos segmentos, em frames inteiros.
Toda conversão passa por aqui, com a mesma quantização da entrega.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tempo import Taxa


@dataclass(frozen=True)
class Pedaco:
    id: str
    video: str
    in_f: int        # frame de entrada no arquivo de origem
    out_f: int       # frame de saída (exclusivo) no arquivo de origem
    seq_ini: int     # frame de início na sequência
    texto: str = ""

    @property
    def dur(self) -> int:
        return self.out_f - self.in_f

    @property
    def seq_fim(self) -> int:
        return self.seq_ini + self.dur


class Linha:
    def __init__(self, segmentos: list[dict], taxa) -> None:
        self.taxa = Taxa.de(taxa)
        self.pedacos: list[Pedaco] = []
        cursor = 0
        for s in segmentos:
            in_f = self.taxa.frames(s["inicio"])
            out_f = self.taxa.frames(s["fim"])
            if out_f <= in_f:
                continue  # segmento menor que 1 frame some na quantização
            p = Pedaco(s["id"], s["video"], in_f, out_f, cursor, s.get("texto", ""))
            self.pedacos.append(p)
            cursor = p.seq_fim

    @property
    def duracao_frames(self) -> int:
        return self.pedacos[-1].seq_fim if self.pedacos else 0

    @property
    def duracao(self) -> float:
        return self.taxa.segundos(self.duracao_frames)

    def origem_para_seq(self, video: str, t: float) -> tuple[float | None, Pedaco | None]:
        """Tempo na origem → tempo na sequência (None se o trecho saiu do corte)."""
        f = self.taxa.frames(t)
        for p in self.pedacos:
            if p.video == video and p.in_f <= f < p.out_f:
                return self.taxa.segundos(p.seq_ini + f - p.in_f), p
        return None, None

    def origem_para_seq_proximo(self, video: str, t: float) -> tuple[float, Pedaco | None, bool]:
        """Como origem_para_seq, mas um trecho cortado cai na junção onde estaria.

        Devolve (tempo_seq, pedaço, dentro_do_corte).
        """
        seq, p = self.origem_para_seq(video, t)
        if seq is not None:
            return seq, p, True
        f = self.taxa.frames(t)
        candidatos = [p for p in self.pedacos if p.video == video and p.in_f >= f]
        if candidatos:
            p = min(candidatos, key=lambda x: x.in_f)
            return self.taxa.segundos(p.seq_ini), p, False
        anteriores = [p for p in self.pedacos if p.video == video and p.out_f <= f]
        if anteriores:
            p = max(anteriores, key=lambda x: x.out_f)
            return self.taxa.segundos(p.seq_fim), p, False
        return self.duracao, None, False

    def seq_para_origem(self, t_seq: float) -> tuple[str, float, Pedaco] | None:
        """Tempo na sequência → (vídeo, tempo na origem, pedaço). Para revisões pelo chat."""
        f = self.taxa.frames(t_seq)
        for p in self.pedacos:
            if p.seq_ini <= f < p.seq_fim:
                return p.video, self.taxa.segundos(p.in_f + f - p.seq_ini), p
        if self.pedacos and f == self.duracao_frames:
            p = self.pedacos[-1]
            return p.video, self.taxa.segundos(p.out_f), p
        return None

    def cortes_seq(self) -> list[float]:
        """Tempo exato de cada junção na sequência (o 'tempo do corte')."""
        return [self.taxa.segundos(p.seq_fim) for p in self.pedacos[:-1]]
