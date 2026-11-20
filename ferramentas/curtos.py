#!/usr/bin/env python3
"""Cortes curtos (Shorts, Reels, TikTok) a partir do vídeo longo já cortado.

Uso (a pasta do vídeo longo primeiro):
  curtos.py frases <pasta>
      a fala do corte final em frases com id (f001…) e tempo da sequência:
      _CLAUDE/curtos/frases.txt (para ler) e frases.json
  curtos.py sugerir <pasta> [--min 20] [--max 60] [-n 8]
      janelas de frases na duração pedida, com nota e motivos (pontos de partida, não decisão)
  curtos.py criar <pasta> <nome> --de f012 --ate f019 [--formato 9:16] [--titulo "…"]
      cria <pasta>/Curtos/<nome>/ como um projeto próprio: os cortes do trecho (os mesmos
      quadros do longo), o enquadramento vertical de cada segmento (centrado no rosto se
      houver _CLAUDE/rosto_<id>.json; tela encaixada) e o fluxo cortes → legendas → render.
      --de/--ate também aceitam segundos da sequência.
  curtos.py listar <pasta>
      os curtos criados e em que pé está cada um

Depois de criar: revisar no painel (painel.py abrir <pasta do curto>), legendas e render no
projeto do curto, como em qualquer vídeo.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import curtos as K  # noqa: E402
from edicao import estado as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("frases"); p.add_argument("pasta")
    p = sub.add_parser("sugerir"); p.add_argument("pasta"); p.add_argument("--min", type=float, default=20)
    p.add_argument("--max", type=float, default=60); p.add_argument("-n", type=int, default=8)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("criar"); p.add_argument("pasta"); p.add_argument("nome")
    p.add_argument("--de", required=True); p.add_argument("--ate", required=True)
    p.add_argument("--formato", default="9:16", choices=["9:16", "1:1", "4:5", "16:9"]); p.add_argument("--titulo")
    p = sub.add_parser("listar"); p.add_argument("pasta")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.cmd == "frases":
            c = K.frases(a.pasta)
            pasta = E.caminho_estado(a.pasta).parent / "curtos"
            print(f"{len(c['frases'])} frases ({c['duracao']:.1f} s de vídeo, corte v{c['cortes_versao']}): "
                  f"{pasta / 'frases.txt'}")
        elif a.cmd == "sugerir":
            r = K.sugerir(a.pasta, a.min, a.max, a.n)
            if a.json:
                print(json.dumps(r, ensure_ascii=False, indent=1))
            for k, s in enumerate(r, 1) if not a.json else []:
                print(f"{k}. {s['de']}–{s['ate']} ({s['duracao']:.0f} s, nota {s['nota']}): {s['texto'][:110]}…")
                print(f"   {'; '.join(s['motivos'])}")
            if not r:
                print("nenhuma janela nessa faixa de duração")
        elif a.cmd == "criar":
            r = K.criar(a.pasta, a.nome, a.de, a.ate, a.formato, a.titulo)
            print(f"{r['pasta']} ({r['id']}): {r['duracao']:.1f} s, {r['segmentos']} segmentos, {r['formato']}"
                  f" · {r['pelo_rosto']} centrados no rosto · {r['encaixados']} encaixados")
        elif a.cmd == "listar":
            for c in K.listar(a.pasta):
                et = c.get("etapas") or {}
                fin = c.get("entregas") or []
                print(f"{c['id']} {c['nome']} ({c['ate'] - c['de']:.0f} s, {c['formato']}): "
                      f"{', '.join(f'{e}={s}' for e, s in et.items())}"
                      + (f" · final: {fin[-1]['arquivo']}" if fin else ""))
    except E.ErroEstado as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
