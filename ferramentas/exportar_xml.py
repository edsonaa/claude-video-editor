#!/usr/bin/env python3
"""Entrega em FCP 7 XML (Premiere, Resolve) e leitura da volta.

Uso:
  exportar_xml.py exportar <pasta do vídeo> [--etapa cortes] [--teste] [--cores cores.json]
                  [--fade 1] [--menos-um] [--saida arquivo.xml]
      Gera _CLAUDE/entregas/<projeto>_<etapa>_vNN.xml, sempre numa versão nova,
      e anota a entrega no estado. --teste: 3–4 clipes, para conferir o formato
      no programa ANTES de usar de verdade.

  exportar_xml.py volta <pasta do vídeo> <exportado.xml> [--aplicar]
      Lê a sequência que a pessoa exportou do programa e reconstrói os cortes de V1.
      Sem --aplicar só mostra a diferença; com --aplicar grava os cortes no estado
      (os ajustes da pessoa valem mais). Avisa o que estiver fora do modelo.

cores.json: {"duvida_take": 4294741314, …} com os valores de <pproColor>
copiados de um XML exportado pelo Premiere com marcadores daquela cor.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import estado as E, midia, xmeml  # noqa: E402
from edicao.tempo import hms  # noqa: E402


def _proxima_versao(pasta_entregas: Path, base: str) -> Path:
    maior = 0
    for f in pasta_entregas.glob(f"{base}_v*.xml"):
        m = re.fullmatch(rf"{re.escape(base)}_v(\d+)\.xml", f.name)
        if m:
            maior = max(maior, int(m.group(1)))
    return pasta_entregas / f"{base}_v{maior + 1:02d}.xml"


def cmd_exportar(a):
    d = E.ler(a.pasta)
    cores = json.loads(Path(a.cores).read_text(encoding="utf-8")) if a.cores else None
    seq = xmeml.montar(d, nome=f"{d['projeto']}_{a.etapa}" + ("_TESTE" if a.teste else ""), teste=a.teste,
                       sondar=midia.analisar, cores=cores, fade_frames=a.fade, menos_um=a.menos_um)
    texto = seq.xml()
    pasta_claude = E.caminho_estado(a.pasta).parent
    if a.saida:
        destino = Path(a.saida)
        if destino.exists():
            raise SystemExit(f"{destino} já existe: nunca sobrescrever uma entrega")
    else:
        base = f"{d['projeto']}_{a.etapa}" + ("_teste" if a.teste else "")
        destino = _proxima_versao(pasta_claude / "entregas", base)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    versao = int(re.search(r"_v(\d+)\.xml$", destino.name).group(1)) if re.search(r"_v(\d+)\.xml$", destino.name) else None
    if not a.teste:
        with E.editar(a.pasta) as e:
            e.setdefault("entregas", []).append({"etapa": E.nome_etapa(a.etapa), "arquivo": str(destino.resolve()),
                                                  **({"versao": versao} if versao else {}),
                                                  "data": E.agora()})
    clipes_v1 = sum(1 for c in seq.clipes if c.tipo == "video" and c.trilha == 1)
    dur = max([c.end for c in seq.clipes] + [0])
    print(f"{destino}")
    print(f"  {clipes_v1} clipes em V1 · {len(seq.marcadores)} marcadores · {hms(seq.taxa.segundos(dur), 2)} · {seq.taxa} fps")
    outros = {}
    for c in seq.clipes:
        if not (c.tipo == "video" and c.trilha == 1) and not (c.tipo == "audio" and c.trilha == 1):
            k = f"{'V' if c.tipo == 'video' else 'A'}{c.trilha}"
            outros[k] = outros.get(k, 0) + 1
    if outros:
        print("  outras trilhas: " + ", ".join(f"{k}: {v}" for k, v in sorted(outros.items())))
    for av in seq.avisos:
        print(f"  ! {av}")
    if a.teste:
        print("  arquivo de TESTE: abra no programa (Arquivo → Importar) e confira clipes, áudio, marcadores e tempos")


def cmd_volta(a):
    d = E.ler(a.pasta)
    arquivos = (d.get("midia") or {}).get("arquivos") or []
    r = xmeml.ler_volta(Path(a.xml).read_text(encoding="utf-8"), arquivos)
    velhos = (d.get("cortes") or {}).get("segmentos") or []
    novos = r["segmentos"]
    # Mantém o texto dos segmentos que ainda batem com um antigo (mesmo vídeo e sobreposição).
    for s in novos:
        for v in velhos:
            if v["video"] == s["video"] and v["inicio"] < s["fim"] and s["inicio"] < v["fim"] and v.get("texto"):
                s.setdefault("texto", v["texto"])
                break
    print(f"volta: {len(novos)} segmentos em V1 ({r['fps']} fps); antes: {len(velhos)}")
    dur_velha = sum(s["fim"] - s["inicio"] for s in velhos)
    dur_nova = sum(s["fim"] - s["inicio"] for s in novos)
    print(f"  duração {hms(dur_velha, 2)} → {hms(dur_nova, 2)}")
    for av in r["avisos"]:
        print(f"  ! {av}")
    if r["marcadores"]:
        print(f"  {len(r['marcadores'])} marcadores na sequência exportada (os que não são do Claude viram instrução):")
        for m in r["marcadores"]:
            print(f"    {hms(m['tempo_seq'], 2)}  {m['nome']}  {m['comentario']}")
    if a.aplicar:
        with E.editar(a.pasta) as e:
            e.setdefault("cortes", {})["segmentos"] = novos
        print(f"  cortes gravados no estado (versão {E.ler(a.pasta)['cortes']['versao']})")
        for al in E.alertas(E.ler(a.pasta)):
            print(f"  ! {al}")
    else:
        print("  (nada gravado; use --aplicar para gravar os cortes no estado)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("exportar")
    p.add_argument("pasta"); p.add_argument("--etapa", default="cortes")
    p.add_argument("--teste", action="store_true"); p.add_argument("--cores")
    p.add_argument("--fade", type=int, default=1, help="frames de fade de áudio (0 = sem fades)")
    p.add_argument("--menos-um", action="store_true", help="bordas em transição como -1 (forma da especificação)")
    p.add_argument("--saida")
    p.set_defaults(f=cmd_exportar)
    p = sub.add_parser("volta")
    p.add_argument("pasta"); p.add_argument("xml"); p.add_argument("--aplicar", action="store_true")
    p.set_defaults(f=cmd_volta)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        a.f(a)
    except (E.ErroEstado, xmeml.ErroXML) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
