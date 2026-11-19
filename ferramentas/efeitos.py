#!/usr/bin/env python3
"""Biblioteca de efeitos (HyperFrames) e de estilos.

Uso:
  efeitos.py listar [--formato tela_cheia|sobreposicao|...] [--json]
  efeitos.py mostrar <efeito>                 parâmetros, duração, eventos de som, quando usar
  efeitos.py estilos                          os estilos prontos (perfis completos)
  efeitos.py criar <efeito> <destino> [--perfil <pasta do perfil> | --estilo <nome> | --tema tema.json]
                   [--param chave=valor …] [--params arquivo.json] [--duracao S] [--fps 30000/1001]
                   [--formato 16:9|9:16|1:1|4:5] [--gsap gsap.min.js]
      copia o efeito para <destino> (ex.: _CLAUDE/motion/mo04) com o tema e o conteúdo nas variáveis
      da composição, a duração exata em frames e o tamanho do formato. Depois: `npx hyperframes check`,
      `snapshot` e `render` (sobreposição: --format mov). Os eventos de som ficam em eventos.json.
  efeitos.py vitrine <saida.png> [--estilo E | --perfil P] [--efeitos a,b,c] [--formato 16:9]
      uma imagem com vários efeitos no mesmo estilo, para ver como o estilo fica
  efeitos.py previa <efeito> <saida.gif> [--estilo E | --perfil P] [--formato 16:9] [--quadros 36]
      GIF de prévia pelos snapshots do HyperFrames (precisa do HyperFrames; HYPERFRAMES_CMD muda o comando).

Valores de --param são JSON quando possível (listas: --param itens='["a","b"]').
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import efeitos as EF  # noqa: E402


def _params(a):
    p = {}
    if a.params:
        p.update(json.loads(Path(a.params).read_text(encoding="utf-8")))
    for kv in a.param or []:
        if "=" not in kv:
            raise EF.ErroEfeito(f"--param precisa de chave=valor (veio {kv!r})")
        k, val = kv.split("=", 1)
        p[k] = EF.interpretar_param(val)
    return p


def _tema(a):
    return EF.tema_de(perfil_dir=getattr(a, "perfil", None), estilo=getattr(a, "estilo", None),
                      arquivo=getattr(a, "tema", None))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("listar"); p.add_argument("--formato"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("mostrar"); p.add_argument("efeito")
    sub.add_parser("estilos")
    for nome in ("criar", "previa"):
        p = sub.add_parser(nome)
        p.add_argument("efeito"); p.add_argument("destino" if nome == "criar" else "saida")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--perfil"); g.add_argument("--estilo"); g.add_argument("--tema")
        p.add_argument("--param", action="append"); p.add_argument("--params")
        p.add_argument("--formato", default="16:9"); p.add_argument("--gsap")
        if nome == "criar":
            p.add_argument("--duracao", type=float); p.add_argument("--fps", default="30")
        else:
            p.add_argument("--quadros", type=int, default=36); p.add_argument("--largura", type=int, default=480)
    p = sub.add_parser("vitrine"); p.add_argument("saida")
    g = p.add_mutually_exclusive_group(); g.add_argument("--perfil"); g.add_argument("--estilo"); g.add_argument("--tema")
    p.add_argument("--efeitos"); p.add_argument("--formato", default="16:9"); p.add_argument("--gsap")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.cmd == "listar":
            todos = {k: v for k, v in EF.listar().items() if not a.formato or v["formato"] == a.formato}
            if a.json:
                print(json.dumps(todos, ensure_ascii=False, indent=1))
                return 0
            for k, m in todos.items():
                d = m["duracao"]
                print(f"{k:<20} {m['formato']:<22} {d['min']}–{d['max']}s  {m['titulo']}: {m['bom_para']}")
        elif a.cmd == "mostrar":
            m = EF.carregar(a.efeito)
            d = m["duracao"]
            print(f"{a.efeito} — {m['titulo']} ({m['formato']}, {d['padrao']}s, {d['min']}–{d['max']}s)")
            print(m["descricao"])
            print(f"bom para: {m['bom_para']}\nevitar: {m['evitar']}")
            print("parâmetros:")
            for prm in m["parametros"]:
                extra = f" opções: {prm['opcoes']}" if prm.get("opcoes") else ""
                ob = " (obrigatório)" if prm.get("obrigatorio") else ""
                print(f"  {prm['id']:<14} {prm['tipo']:<8} {prm['rotulo']}{ob}; padrão {json.dumps(prm.get('padrao'), ensure_ascii=False)}{extra}")
                if prm.get("descricao"):
                    print(f"  {'':<14} {prm['descricao']}")
            print("eventos de som: " + "; ".join(f"{e['t']} {e['tipo']} ({e['forca']})" for e in m.get("eventos_som", [])))
            print(f"exemplo: --params com {json.dumps(m.get('exemplo', {}), ensure_ascii=False)}")
        elif a.cmd == "estilos":
            for k, t in EF.listar_estilos().items():
                c = t["cores"]
                print(f"{k:<14} {t.get('titulo', '')}: {t.get('descricao', '')}")
                print(f"{'':<14} fundo {c['fundo']} · texto {c['texto']} · destaque {c['destaque']} · "
                      f"{t['fontes']['titulo']}/{t['fontes']['texto']} · {t['material']}")
        elif a.cmd == "criar":
            r = EF.criar(a.efeito, a.destino, _tema(a), _params(a), a.duracao, a.fps, a.formato, a.gsap)
            print(f"{a.destino}: {r['efeito']} · {r['formato']} {r['tamanho'][0]}x{r['tamanho'][1]} · "
                  f"{r['frames']} frames a {r['fps']} fps · render em {r['saida'].upper()}")
            print(f"  eventos de som: {len(r['eventos_som'])} (eventos.json, em segundos a partir do início do item)")
        elif a.cmd == "vitrine":
            ef = [x.strip() for x in a.efeitos.split(",")] if a.efeitos else None
            titulo = f"estilo {a.estilo}" if a.estilo else (f"perfil {Path(a.perfil).name}" if a.perfil else "")
            print(EF.vitrine(a.saida, _tema(a), ef, a.formato, gsap=a.gsap, titulo=titulo))
        elif a.cmd == "previa":
            out = EF.previa(a.efeito, a.saida, _tema(a), a.formato, a.quadros, a.largura, _params(a) or None, a.gsap)
            print(out)
    except EF.ErroEfeito as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
