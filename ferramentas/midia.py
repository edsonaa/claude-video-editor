#!/usr/bin/env python3
"""Inventário da mídia (ffprobe): duração, fps exato, resolução, áudio, data de gravação e alertas.

Uso:
  midia.py <arquivos ou pastas…> [--json] [--saida inventario.json] [--contar-frames]
  midia.py <arquivos ou pastas…> --estado <pasta do vídeo>
      grava o bloco `midia` do estado (ids pelo nome do arquivo; mantém ids,
      tipos e proxies já decididos). Confira o tipo de cada um (camera, tela, audio).

Ordem: data de gravação (metadado); sem data, nome em ordem natural.
Alertas: arquivo ilegível, vídeo sem áudio, fps diferente entre vídeos, taxa variável (VFR).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import estado as E, midia  # noqa: E402
from edicao.tempo import hms  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("alvos", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--saida")
    ap.add_argument("--contar-frames", action="store_true", help="conta os pacotes (lento em arquivos grandes)")
    ap.add_argument("--estado", help="pasta do vídeo: grava o inventário no estado")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    inv = midia.inventario(a.alvos, a.contar_frames)
    if a.saida:
        Path(a.saida).write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.json:
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return 0
    if not inv["arquivos"]:
        print("nenhum arquivo de vídeo ou áudio encontrado")
        return 1
    for i in inv["arquivos"]:
        partes = [i["nome"], i.get("tipo", "?")]
        if i.get("duracao"):
            partes.append(hms(i["duracao"], 2))
        if i.get("fps"):
            partes.append(f"{i['fps']} fps" + (" VFR" if i.get("vfr") else ""))
        if i.get("resolucao"):
            partes.append("x".join(str(x) for x in i["resolucao"]))
        partes.append(f"{i.get('canais_audio', 0)} canais")
        if i.get("gravado_em"):
            partes.append(i["gravado_em"][:19])
        print("  ".join(partes))
    if inv["alertas"]:
        print("alertas:")
        for al in inv["alertas"]:
            print(f"  ! {al}")
    if a.saida:
        print(f"inventário gravado em {a.saida}")
    if a.estado:
        with E.editar(a.estado) as d:
            d["midia"] = midia.para_estado(inv, d.get("midia"))
        m = E.ler(a.estado)["midia"]
        print(f"estado: {len(m['arquivos'])} arquivos; principal {m.get('principal')} "
              f"({m.get('fps')} fps, {'x'.join(str(x) for x in m.get('resolucao') or [])})")
        print("  ids: " + ", ".join(f"{x['id']} ({x['tipo']})" for x in m["arquivos"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
