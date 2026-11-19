#!/usr/bin/env python3
"""Mapa de silêncios e de trechos com som de um arquivo (silencedetect do FFmpeg).

Uso:
  silencios.py <arquivo> [--limiar -35] [--minimo 0.3] [--inicio S] [--duracao S] [--saida silencios.json]

Esta ferramenta só mapeia: quem decide o corte é a etapa de cortes.
O limiar depende do ambiente da gravação; confira num trecho antes de confiar.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import silencios  # noqa: E402
from edicao.tempo import hms  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arquivo")
    ap.add_argument("--limiar", type=float, default=-35.0, help="dBFS (padrão -35)")
    ap.add_argument("--minimo", type=float, default=0.3, help="duração mínima do silêncio, em s")
    ap.add_argument("--inicio", type=float)
    ap.add_argument("--duracao", type=float)
    ap.add_argument("--saida")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    r = silencios.detectar(a.arquivo, a.limiar, a.minimo, a.inicio, a.duracao)
    r["arquivo"] = str(Path(a.arquivo).resolve())
    if a.saida:
        Path(a.saida).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"gravado em {a.saida}")
    total_sil = sum(b - a_ for a_, b in r["silencios"])
    print(f"{len(r['silencios'])} silêncios ≥ {a.minimo}s somando {hms(total_sil, 1)} "
          f"de {hms(r['duracao'], 1)}; {len(r['som'])} trechos com som")
    if not a.saida:
        for x, y in r["silencios"]:
            print(f"  {hms(x, 2)} – {hms(y, 2)}  ({y - x:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
