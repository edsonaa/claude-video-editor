"""Mapa de silêncios e de trechos com som (silencedetect do FFmpeg)."""
from __future__ import annotations

import re

from . import ff

_RE_INI = re.compile(r"silence_start:\s*(-?[\d.]+)")
_RE_FIM = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detectar(caminho, limiar_db: float = -35.0, minimo: float = 0.3,
             inicio: float | None = None, duracao: float | None = None) -> dict:
    """Silêncios ≥ `minimo` segundos abaixo de `limiar_db` dBFS.

    Devolve {"duracao", "silencios": [[ini, fim], …], "som": [[ini, fim], …]}
    no tempo do arquivo (já somado o `inicio`, se houver).
    """
    args = [ff.ffmpeg(), "-v", "info", "-nostdin", "-hide_banner"]
    if inicio is not None:
        args += ["-ss", f"{inicio:.6f}"]
    args += ["-i", str(caminho)]
    if duracao is not None:
        args += ["-t", f"{duracao:.6f}"]
    args += ["-vn", "-ac", "1", "-af", f"silencedetect=noise={limiar_db}dB:d={minimo}", "-f", "null", "-"]
    proc = ff.rodar(args)
    log = proc.stderr

    # Duração pelo contêiner: o log do FFmpeg passa do fim por causa do padding do AAC.
    total = float(ff.sondar(caminho)["format"].get("duration") or 0) or (_duracao_do_log(log) or 0.0)
    if inicio:
        total = max(0.0, total - inicio)
    if duracao is not None:
        total = min(total, duracao)

    silencios: list[list[float]] = []
    aberto = None
    for linha in log.splitlines():
        m = _RE_INI.search(linha)
        if m:
            aberto = max(0.0, float(m.group(1)))
            continue
        m = _RE_FIM.search(linha)
        if m and aberto is not None:
            silencios.append([aberto, min(float(m.group(1)), total)])
            aberto = None
    if aberto is not None:  # silêncio até o fim do arquivo
        silencios.append([aberto, total])

    desloc = inicio or 0.0
    silencios = [[round(a + desloc, 3), round(b + desloc, 3)] for a, b in silencios if b > a]
    return {"duracao": round(total + desloc, 3), "limiar_db": limiar_db, "minimo": minimo,
            "silencios": silencios, "som": complemento(silencios, desloc, total + desloc)}


def _duracao_do_log(log: str) -> float | None:
    # Última linha de progresso "time=00:00:12.34" é a duração processada.
    tempos = re.findall(r"time=(\d+):(\d+):([\d.]+)", log)
    if not tempos:
        return None
    h, m, s = tempos[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def complemento(trechos: list[list[float]], inicio: float, fim: float) -> list[list[float]]:
    """Os intervalos entre `trechos` dentro de [inicio, fim]."""
    out, cursor = [], inicio
    for a, b in sorted(trechos):
        if a > cursor + 1e-6:
            out.append([round(cursor, 3), round(a, 3)])
        cursor = max(cursor, b)
    if fim > cursor + 1e-6:
        out.append([round(cursor, 3), round(fim, 3)])
    return out
