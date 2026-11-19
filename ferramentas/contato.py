#!/usr/bin/env python3
"""Folha de contato: um quadro a cada N frames, lado a lado, com o tempo e o frame em cada um.

Uso:
  contato.py <video> <saida.png> [--inicio S] [--fim S] [--cada 4] [--colunas 6] [--largura 320] [--maximo 60]

Tempos aceitam segundos (75.2) ou mm:ss (1:15.2). Precisa de numpy e OpenCV.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import contato  # noqa: E402
from edicao.tempo import de_hms  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("saida")
    ap.add_argument("--inicio", default="0")
    ap.add_argument("--fim")
    ap.add_argument("--cada", type=int, default=4, help="um quadro a cada N frames")
    ap.add_argument("--colunas", type=int, default=6)
    ap.add_argument("--largura", type=int, default=320, help="largura de cada quadro, em px")
    ap.add_argument("--maximo", type=int, default=60, help="máximo de quadros na folha")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    r = contato.folha(a.video, a.saida, de_hms(a.inicio), de_hms(a.fim) if a.fim else None,
                      a.cada, a.colunas, a.largura, a.maximo)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
