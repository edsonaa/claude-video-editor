#!/usr/bin/env python3
"""Rastreio de rosto (YuNet, OpenCV): onde está o rosto ao longo do vídeo.

Uso:
  rosto.py baixar [--pasta modelos/]
      baixa o modelo YuNet (licença MIT, ~230 KB) para a pasta de ferramentas.
  rosto.py rastrear <video> <saida.json> [--modelo caminho.onnx] [--amostras 5]
                    [--inicio S] [--fim S] [--confianca 0.7]

Saída: amostras (centro cx/cy e largura w do maior rosto, de 0 a 1, ou null) e
uma trilha suavizada, sem buracos. Roda local e leve; não precisa de GPU.
"""
import argparse
import json
from pathlib import Path
import sys

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from edicao import rosto  # noqa: E402
from edicao.tempo import de_hms  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("baixar"); p.add_argument("--pasta", default=str(AQUI / "modelos"))
    p = sub.add_parser("rastrear"); p.add_argument("video"); p.add_argument("saida")
    p.add_argument("--modelo", default=str(AQUI / "modelos" / rosto.NOME_MODELO))
    p.add_argument("--amostras", type=float, default=5.0, help="amostras por segundo")
    p.add_argument("--inicio", default="0"); p.add_argument("--fim")
    p.add_argument("--confianca", type=float, default=0.7)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "baixar":
        print(rosto.baixar_modelo(a.pasta))
        return 0
    if not Path(a.modelo).exists():
        print(f"modelo não encontrado em {a.modelo}: rode 'rosto.py baixar' antes", file=sys.stderr)
        return 2
    r = rosto.rastrear(a.video, a.modelo, a.amostras, de_hms(a.inicio), de_hms(a.fim) if a.fim else None,
                       confianca=a.confianca)
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    res = r["resumo"]
    print(f"{a.saida}: rosto em {res['com_rosto']}/{res['amostras']} amostras ({res['cobertura']:.0%})"
          + (f", centro médio x={res['cx_medio']}, largura média {res['largura_media']}" if res.get("com_rosto") else "")
          + (f", {res['varios_rostos']} amostras com mais de um rosto" if res.get("varios_rostos") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
