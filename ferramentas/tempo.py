#!/usr/bin/env python3
"""Converte entre segundos, frames e timecode, com a taxa exata.

Uso:
  tempo.py --fps 29.97 12.5            segundos → frame e timecode
  tempo.py --fps 29.97 --frame 375     frame → segundos e timecode
  tempo.py --fps 29.97 00:00:12;15     timecode → frame e segundos (';' = drop-frame)

--df mostra o timecode em drop-frame (só 29,97 e 59,94).
"""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao.tempo import Taxa, de_hms  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fps", required=True)
    ap.add_argument("--frame", type=int)
    ap.add_argument("--df", action="store_true")
    ap.add_argument("valor", nargs="?")
    a = ap.parse_args(argv)
    t = Taxa.de(a.fps)
    if a.frame is not None:
        f = a.frame
    elif a.valor and re.fullmatch(r"\d+:\d\d:\d\d[:;.]\d+", a.valor):
        f = t.de_timecode(a.valor)
    elif a.valor:
        f = t.frames(de_hms(a.valor))
    else:
        ap.error("informe segundos, timecode ou --frame")
    drop = a.df or (a.valor or "").count(";") > 0
    print(f"fps {t} ({float(t):.4f})  frame {f}  {t.segundos(f):.6f}s  tc {t.timecode(f, drop)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
