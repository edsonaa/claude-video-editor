#!/usr/bin/env python3
"""Biblioteca de sons: índice e busca.

Uso:
  sons.py indexar <pasta da biblioteca> [--indice indice.json]
      Mede cada som (duração, tempo até o pico, nível) e grava o índice
      (padrão: <biblioteca>/indice.json). Incremental; mantém licenca/tags/nota.
  sons.py buscar <indice.json> [--categoria whoosh] [--texto "vidro"] [--dur-max 1.5] [--json]
  sons.py categorias <indice.json>

Para alinhar: um som com pico em P segundos entra em (tempo do evento − P).
Confira sempre a licença de uso de cada som (campo "licenca", escrito à mão).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import sons  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("indexar"); p.add_argument("biblioteca"); p.add_argument("--indice")
    p = sub.add_parser("buscar"); p.add_argument("indice"); p.add_argument("--categoria"); p.add_argument("--texto")
    p.add_argument("--dur-min", type=float); p.add_argument("--dur-max", type=float)
    p.add_argument("--limite", type=int, default=30); p.add_argument("--json", action="store_true")
    p = sub.add_parser("categorias"); p.add_argument("indice")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if a.cmd == "indexar":
        destino = Path(a.indice) if a.indice else Path(a.biblioteca) / "indice.json"
        velho = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else None
        ind = sons.indexar(a.biblioteca, velho)
        erros = ind.pop("erros")
        reap = ind.pop("reaproveitados")
        destino.write_text(json.dumps(ind, ensure_ascii=False, indent=1), encoding="utf-8")
        cats = {}
        for s in ind["sons"]:
            cats[s["categoria"]] = cats.get(s["categoria"], 0) + 1
        print(f"{destino}: {len(ind['sons'])} sons ({reap} sem mudança) em {len(cats)} categorias")
        print("  " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items())))
        for e in erros:
            print(f"  ! {e}")
        return 0

    ind = json.loads(Path(a.indice).read_text(encoding="utf-8"))
    if a.cmd == "categorias":
        cats = {}
        for s in ind["sons"]:
            cats.setdefault(s["categoria"], []).append(s["duracao"])
        for k, ds in sorted(cats.items()):
            print(f"{k:<16} {len(ds):>4} sons  {min(ds):.2f}–{max(ds):.2f}s")
        return 0
    achados = sons.buscar(ind, a.categoria, a.texto, a.dur_min, a.dur_max, a.limite)
    if a.json:
        print(json.dumps(achados, ensure_ascii=False, indent=1))
        return 0
    for s in achados:
        lic = f"  [{s['licenca']}]" if s.get("licenca") else ""
        print(f"{s['id']:<28} {s['categoria']:<12} {s['duracao']:5.2f}s  pico {s['pico']:.2f}s  "
              f"{s['rms_db']:6.1f} dB rms{lic}")
    if not achados:
        print("nada encontrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
