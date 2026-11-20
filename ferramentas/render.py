#!/usr/bin/env python3
"""Render do vídeo pelo FFmpeg, a partir do estado: para quem não revisa num programa de edição.

Uso (a pasta do vídeo primeiro):
  render.py plano <pasta> [--formato 9:16] [--de S --ate S]
      o que vai entrar (pedaços com quadros exatos, enquadramento, animações, som), sem renderizar
  render.py rascunho <pasta> [--de S --ate S] [--legenda auto|ass|animada|nao]
      resolução baixa e rápido, para revisar (_CLAUDE/rascunhos/<projeto>_rascunho_vNN.mp4)
  render.py final <pasta> [--de S --ate S] [--formato F] [--legenda …] [--perfil <pasta do perfil>]
      na resolução do formato (16:9 1920x1080, 9:16 1080x1920, 1:1, 4:5), em <pastas.renders>/<projeto>_final_vNN.mp4

O que entra: os cortes (frames exatos, a mesma conversão da entrega em XML), a voz (a tratada,
quando houver) com fades curtos nas junções, as animações renderizadas por cima (tela cheia e com
transparência), a legenda queimada (ASS das legendas atuais, ou a legenda animada), a música e os
efeitos sonoros com o ganho de cada um, e a loudness no alvo do config (audio.alvo_lufs, pico_dbtp).

Enquadramento por segmento (cortes.segmentos[].quadro): {"modo": "inteiro"}, {"modo": "cortar",
"x": 0.42, "y": 0.5, "zoom": 1.0} (x/y: o centro, de 0 a 1) ou {"modo": "encaixar"} (o quadro inteiro
sobre um fundo desfocado). Sem quadro: inteiro se a proporção bate; câmera recortada no centro; tela encaixada.
Movimentos de câmera não são aplicados (o render avisa). Cada render é uma versão nova; o original nunca muda.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import config as C  # noqa: E402
from edicao import estado as E  # noqa: E402
from edicao import render as R  # noqa: E402
from edicao.tempo import de_hms  # noqa: E402


def _t(x):
    return de_hms(x) if x is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("plano", "rascunho", "final"):
        p = sub.add_parser(nome)
        p.add_argument("pasta")
        p.add_argument("--de"); p.add_argument("--ate")
        p.add_argument("--formato", choices=["16:9", "9:16", "1:1", "4:5"])
        p.add_argument("--json", action="store_true")
        if nome != "plano":
            p.add_argument("--legenda", choices=["auto", "ass", "animada", "nao"], default="auto")
            p.add_argument("--perfil", help="pasta do perfil (cores e fontes da legenda queimada)")
            p.add_argument("--saida")
            p.add_argument("--alvo", type=float); p.add_argument("--pico", type=float)
            p.add_argument("--manter", action="store_true", help="mantém os arquivos intermediários")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.cmd == "plano":
            pl = R.plano(a.pasta, False, _t(a.de), _t(a.ate), a.formato)
            print(json.dumps(pl, ensure_ascii=False, indent=1) if a.json else R.resumo_plano(pl))
            return 0
        cfg = C.carregar(obrigatorio=False) or {}
        au = cfg.get("audio") or {}
        perfil = a.perfil
        if not perfil and cfg.get("perfil_padrao"):
            cand = C.pasta() / "perfis" / (E.ler(a.pasta).get("perfil") or cfg["perfil_padrao"])
            perfil = str(cand) if cand.exists() else None
        r = R.renderizar(a.pasta, a.cmd == "rascunho", _t(a.de), _t(a.ate), a.formato, a.legenda, perfil,
                         Path(a.saida) if a.saida else None, a.alvo if a.alvo is not None else au.get("alvo_lufs", -14.0),
                         a.pico if a.pico is not None else au.get("pico_dbtp", -1.0),
                         progresso=(lambda m: None) if a.json else (lambda m: print(f"  {m}", flush=True)),
                         manter=a.manter)
    except (E.ErroEstado, C.ErroConfig) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"{r['arquivo']}")
        print(f"  {r['formato']} {r['tamanho'][0]}x{r['tamanho'][1]} · {r['duracao']:.2f} s (sequência {r['duracao_sequencia']:.2f} s)"
              f" · {r['lufs']:.1f} LUFS · pico {r['pico_dbtp']:.1f} dBTP · legenda: {r['legenda']}")
        for av in r["avisos"]:
            print(f"  ! {av}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
