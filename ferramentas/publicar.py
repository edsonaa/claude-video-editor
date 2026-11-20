#!/usr/bin/env python3
"""Publicação: capítulos, capa, textos por plataforma (validados) e a pasta pronta para subir.

Uso (a pasta do vídeo primeiro):
  publicar.py limites
      os limites de cada plataforma que o script confere (e quando foram conferidos)
  publicar.py capitulos <pasta> [<arquivo.txt>|-] [--das-animacoes] [--gravar]
      cada linha: "<onde> <título>", onde = 1:23 (tempo do vídeo), f012 (frase do curtos.py frases),
      s003 (segmento) ou mo04 (animação). --das-animacoes usa os marcadores de capítulo do plano.
      Confere as regras do YouTube (0:00, pelo menos 3, 10 s cada) e mostra a lista pronta.
  publicar.py capa <pasta> [-n 6]
      candidatas a capa do corte final (nítidas, bem expostas, com rosto): _CLAUDE/publicar/capas/
  publicar.py capa <pasta> --escolher 3
  publicar.py definir <pasta> <textos.json>
      {"youtube": {"titulo", "descricao", "tags": [], "hashtags": []},
       "instagram": {"legenda", "hashtags": []}, "tiktok": {"legenda", "hashtags": []}}
      (Shorts usam os textos de "youtube", ou "shorts" se existir)
  publicar.py conferir <pasta> [--plataformas youtube,shorts,instagram,tiktok]
  publicar.py pacote <pasta> [--plataformas …] [--forcar]
      Publicar/<plataforma>/: o vídeo final (link, sem duplicar quando dá), texto.txt, legendas
      SRT/VTT, a capa e conferencia.md. Recusa se a conferência tiver erro (sem --forcar).

O envio para as plataformas é da pessoa: o pacote deixa tudo pronto para colar e subir.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import estado as E  # noqa: E402
from edicao import publicar as PB  # noqa: E402


def _plataformas(txt):
    return [p.strip() for p in txt.split(",")] if txt else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("limites")
    p = sub.add_parser("capitulos"); p.add_argument("pasta"); p.add_argument("arquivo", nargs="?")
    p.add_argument("--das-animacoes", action="store_true"); p.add_argument("--gravar", action="store_true")
    p = sub.add_parser("capa"); p.add_argument("pasta"); p.add_argument("-n", type=int, default=6)
    p.add_argument("--escolher", type=int)
    p = sub.add_parser("definir"); p.add_argument("pasta"); p.add_argument("arquivo")
    p = sub.add_parser("conferir"); p.add_argument("pasta"); p.add_argument("--plataformas")
    p = sub.add_parser("pacote"); p.add_argument("pasta"); p.add_argument("--plataformas")
    p.add_argument("--forcar", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.cmd == "limites":
            print(f"conferidos em {PB.CONFERIDO} (mudam: confira de novo antes de confiar num número antigo)")
            for pl, lim in PB.LIMITES.items():
                print(f"  {pl}: " + ", ".join(f"{k}={v}" for k, v in lim.items()))
            return 0
        if a.cmd == "capitulos":
            d = E.ler(a.pasta)
            dur = PB._duracao(d)
            if a.das_animacoes:
                caps = PB.capitulos_das_animacoes(a.pasta)
            else:
                texto = sys.stdin.read() if a.arquivo in (None, "-") else Path(a.arquivo).read_text(encoding="utf-8")
                caps = PB.ler_capitulos(a.pasta, texto)
            if caps and caps[0]["tempo"] > 0:
                caps = PB.ajustar_inicio(caps)
                print("(o primeiro capítulo foi para 0:00, como o YouTube exige)")
            erros, avisos = PB.validar_capitulos(caps, dur)
            print(PB.formatar_capitulos(caps, dur))
            for x in erros:
                print(f"✗ {x}")
            for x in avisos:
                print(f"! {x}")
            if a.gravar:
                if erros:
                    print("nada gravado: corrija os erros", file=sys.stderr)
                    return 2
                PB.definir(a.pasta, {"capitulos": caps})
                print("gravado em publicacao.capitulos")
            return 2 if erros else 0
        if a.cmd == "capa":
            if a.escolher:
                print(PB.escolher_capa(a.pasta, a.escolher))
                return 0
            cs = PB.capa_candidatas(a.pasta, a.n)
            for c in cs:
                print(f"{c['n']}. {PB.tc(c['t_seq'])} ({c['video']}, nota {c['nota']}: {', '.join(c['motivos'])}) {c['arquivo']}")
            if cs:
                print(f"folha: {Path(cs[0]['arquivo']).parent / 'candidatas.png'}")
            return 0
        if a.cmd == "definir":
            pub = PB.definir(a.pasta, json.loads(Path(a.arquivo).read_text(encoding="utf-8")))
            print("gravado em publicacao:", ", ".join(pub))
            a.plataformas = None
            a.cmd = "conferir"
        if a.cmd == "conferir":
            r = PB.conferir(a.pasta, _plataformas(a.plataformas))
            ok = True
            for pl, c in r["plataformas"].items():
                print(f"{pl}: " + ("✓" if not c["erros"] else "✗"))
                for x in c["erros"]:
                    print(f"  ✗ {x}")
                    ok = False
                for x in c["avisos"]:
                    print(f"  ! {x}")
            return 0 if ok else 2
        if a.cmd == "pacote":
            r = PB.pacote(a.pasta, _plataformas(a.plataformas), a.forcar)
            for pl, pasta in r["pastas"].items():
                print(f"{pl}: {pasta}")
            return 0
    except E.ErroEstado as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
