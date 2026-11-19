"""Tempo: a única conversão de segundos para frames do fluxo.

Todos os scripts convertem por aqui. Erro de taxa de quadros aparece como
descompasso crescente no fim do vídeo, por isso a taxa é sempre uma fração
exata (30000/1001), nunca 29.97.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import re

# Taxas comuns, como aparecem no ffprobe ou digitadas pela pessoa.
_ALIASES = {
    "23.976": Fraction(24000, 1001), "23.98": Fraction(24000, 1001),
    "29.97": Fraction(30000, 1001),
    "47.952": Fraction(48000, 1001), "47.95": Fraction(48000, 1001),
    "59.94": Fraction(60000, 1001),
    "119.88": Fraction(120000, 1001),
}


@dataclass(frozen=True)
class Taxa:
    """Taxa de quadros exata."""

    fps: Fraction

    @classmethod
    def de(cls, valor) -> "Taxa":
        """Aceita '30000/1001', '29.97', 29.97, 30, Fraction ou Taxa."""
        if isinstance(valor, Taxa):
            return valor
        if isinstance(valor, Fraction):
            fps = valor
        elif isinstance(valor, int):
            fps = Fraction(valor)
        else:
            texto = str(valor).strip().replace(",", ".")
            if texto in _ALIASES:
                fps = _ALIASES[texto]
            elif "/" in texto:
                num, den = texto.split("/", 1)
                fps = Fraction(int(num), int(den))
            else:
                f = float(texto)
                # 29.97002997 (ffprobe às vezes) → 30000/1001
                for alvo in _ALIASES.values():
                    if abs(f - float(alvo)) < 0.0015:
                        fps = alvo
                        break
                else:
                    fps = Fraction(texto).limit_denominator(1001)
        if fps <= 0:
            raise ValueError(f"taxa de quadros inválida: {valor!r}")
        return cls(fps)

    # --- propriedades usadas na entrega (xmeml) ---
    @property
    def ntsc(self) -> bool:
        return self.fps.denominator == 1001

    @property
    def timebase(self) -> int:
        """Inteiro usado pelo xmeml: 30 para 29,97, 24 para 23,976."""
        return round(self.fps)

    @property
    def drop_frame_possivel(self) -> bool:
        return self.ntsc and self.timebase in (30, 60)

    def __str__(self) -> str:
        if self.fps.denominator == 1:
            return str(self.fps.numerator)
        return f"{self.fps.numerator}/{self.fps.denominator}"

    def __float__(self) -> float:
        return float(self.fps)

    # --- conversões ---
    def frames(self, segundos: float) -> int:
        """Segundos → frame mais próximo. O lugar único do arredondamento."""
        return int(round(Fraction(segundos).limit_denominator(10**9) * self.fps))

    def frames_piso(self, segundos: float) -> int:
        return math.floor(Fraction(segundos).limit_denominator(10**9) * self.fps)

    def segundos(self, frames: int) -> float:
        return float(Fraction(frames) / self.fps)

    def quantizar(self, segundos: float) -> float:
        """Arredonda um tempo para a borda de frame mais próxima."""
        return self.segundos(self.frames(segundos))

    # --- timecode ---
    def timecode(self, frames: int, drop: bool = False) -> str:
        """Frames → HH:MM:SS:FF (ou HH:MM:SS;FF em drop-frame)."""
        if frames < 0:
            raise ValueError("frames negativos")
        base = self.timebase
        if drop:
            if not self.drop_frame_possivel:
                raise ValueError("drop-frame só existe em 29,97 e 59,94")
            pulo = 2 if base == 30 else 4
            por_10min = base * 60 * 10 - pulo * 9
            por_min = base * 60 - pulo
            d, m = divmod(frames, por_10min)
            if m > pulo:
                frames += pulo * 9 * d + pulo * ((m - pulo) // por_min)
            else:
                frames += pulo * 9 * d
        ff = frames % base
        ss = (frames // base) % 60
        mm = (frames // (base * 60)) % 60
        hh = frames // (base * 3600)
        sep = ";" if drop else ":"
        return f"{hh:02d}:{mm:02d}:{ss:02d}{sep}{ff:02d}"

    def de_timecode(self, tc: str) -> int:
        """HH:MM:SS:FF ou HH:MM:SS;FF → frames. ';' indica drop-frame."""
        m = re.fullmatch(r"(\d+):(\d\d):(\d\d)([:;.])(\d+)", tc.strip())
        if not m:
            raise ValueError(f"timecode inválido: {tc!r}")
        hh, mm, ss, sep, ff = m.groups()
        hh, mm, ss, ff = int(hh), int(mm), int(ss), int(ff)
        base = self.timebase
        total = ((hh * 60 + mm) * 60 + ss) * base + ff
        if sep == ";":
            pulo = 2 if base == 30 else 4
            minutos = hh * 60 + mm
            total -= pulo * (minutos - minutos // 10)
        return total


def hms(segundos: float, casas: int = 2) -> str:
    """Segundos → H:MM:SS.cc legível (para o Claude ler, não para entrega)."""
    neg = segundos < 0
    s = abs(segundos)
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    fmt = f"{{:0{3 + casas}.{casas}f}}" if casas else "{:02.0f}"
    texto = (f"{int(h)}:" if h else "") + f"{int(m):02d}:" + fmt.format(s)
    return ("-" if neg else "") + texto


def de_hms(texto: str) -> float:
    """'1:02.5', '01:02:03.4', '75.2' ou '75' → segundos."""
    partes = texto.strip().replace(",", ".").split(":")
    total = 0.0
    for p in partes:
        total = total * 60 + float(p)
    return total
