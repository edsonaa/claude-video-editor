#!/usr/bin/env python3
"""Legendas do vídeo, a partir da transcrição e dos cortes (tempo da sequência).

Uso (a pasta do vídeo primeiro; os padrões vêm do bloco `legendas` da configuração):
  legendas.py gerar <pasta> [--modo frase|palavra] [--max-caracteres 42] [--linhas 2]
                    [--correcoes correcoes.json] [--manter-hesitacoes] [--quebrar-no-corte]
      divide a fala em blocos (l001, l002…) e grava _CLAUDE/legendas/blocos_vNN.json e revisao.txt
  legendas.py ver <pasta>                      os blocos atuais, com caracteres por segundo e avisos
  legendas.py corrigir <pasta> <id> "<texto>"  troca o texto de um bloco (mantém os tempos), versão nova
  legendas.py exportar <pasta> [--formatos srt,vtt,ass,hyperframes] [--perfil <pasta do perfil>]
                       [--formato 16:9] [--de S --ate S]
      srt/vtt: para o programa de edição, o YouTube e plataformas de curso
      ass: para queimar no render (FFmpeg: -vf "ass=arquivo.ass"); no modo palavra, a palavra
           falada fica na cor de destaque do perfil
      hyperframes: parâmetros do efeito legenda-animada para o trecho [de, ate)

correcoes.json: {"palavra errada": "palavra certa", …} (palavras inteiras, sem diferenciar maiúsculas).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import config as C  # noqa: E402
from edicao import efeitos as EF  # noqa: E402
from edicao import estado as E  # noqa: E402
from edicao import legendas as L  # noqa: E402
from edicao import transcricao as T  # noqa: E402
from edicao.linha import Linha  # noqa: E402

PADRAO = {"modo": "frase", "max_caracteres": 42, "linhas": 2, "remover_hesitacoes": True, "caixa_alta": False,
          "posicao": "baixo", "saidas": ["srt"], "quebrar_no_corte": False}


def _cfg():
    c = C.carregar(obrigatorio=False) or {}
    return {**PADRAO, **(c.get("legendas") or {})}


_pasta_legendas = L.pasta_legendas
_atual = L.ler_atual
_gravar_versao = L.gravar_versao


def cmd_gerar(a):
    cfg = _cfg()
    modo = a.modo or cfg["modo"]
    max_car = a.max_caracteres or cfg["max_caracteres"]
    linhas = a.linhas or cfg["linhas"]
    d = E.ler(a.pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    fps = (d.get("midia") or {}).get("fps")
    if not segs or not fps:
        raise E.ErroEstado("o estado precisa de cortes e de midia.fps")
    base = E.caminho_estado(a.pasta).parent.parent
    transcs = {}
    for vid, c in ((d.get("transcricao") or {}).get("palavras") or {}).items():
        transcs[vid] = T.ler(Path(c) if Path(c).is_absolute() else base / c)
    if not transcs:
        raise E.ErroEstado("o estado não tem transcricao.palavras")
    correcoes = json.loads(Path(a.correcoes).read_text(encoding="utf-8")) if a.correcoes else None
    linha = Linha(segs, fps)
    ws = L.palavras_na_sequencia(transcs, linha, not (a.manter_hesitacoes or not cfg["remover_hesitacoes"]), correcoes)
    bls = L.blocos(ws, fps, max_car, linhas, quebrar_no_corte=a.quebrar_no_corte or cfg["quebrar_no_corte"])
    conteudo = {"base_cortes_versao": d["cortes"]["versao"], "fps": str(linha.taxa),
                "duracao": round(linha.duracao, 3),
                "opcoes": {"modo": modo, "max_caracteres": max_car, "linhas": linhas}, "blocos": bls}
    arq = _gravar_versao(a.pasta, conteudo)
    print(f"{arq}: {len(bls)} blocos de {len(ws)} palavras ({modo}, até {linhas}×{max_car} caracteres)")
    print(f"  para revisar: {arq.parent / 'revisao.txt'}")
    for av in L.avisos(bls, max_car=max_car):
        print(f"  ! {av}")


def cmd_ver(a):
    conteudo, arq = _atual(a.pasta)
    sys.stdout.write(f"# {arq.name}\n" + L.texto_revisao(conteudo["blocos"]))
    for av in L.avisos(conteudo["blocos"], max_car=conteudo["opcoes"]["max_caracteres"]):
        print(f"! {av}")
    d = E.ler(a.pasta)
    if conteudo["base_cortes_versao"] != (d.get("cortes") or {}).get("versao"):
        print("! o corte mudou depois destas legendas: gere de novo")


def cmd_corrigir(a):
    b, arq = L.corrigir_bloco(a.pasta, a.id, a.texto)
    print(f"{a.id} → {' / '.join(b['linhas'])} ({arq.name})")


def cmd_exportar(a):
    cfg = _cfg()
    conteudo, arq = _atual(a.pasta)
    d = E.ler(a.pasta)
    if conteudo["base_cortes_versao"] != (d.get("cortes") or {}).get("versao"):
        print("! o corte mudou depois destas legendas: os tempos vão estar errados (gere de novo)")
    bls = conteudo["blocos"]
    formatos = [f.strip() for f in (a.formatos.split(",") if a.formatos else cfg["saidas"])]
    destino = _pasta_legendas(a.pasta)
    nome = f"{d['projeto']}_legendas_v{conteudo['versao']:02d}"
    caixa = cfg["caixa_alta"]
    feitos = {}
    for f in formatos:
        if f == "srt":
            p = destino / f"{nome}.srt"; p.write_text(L.srt(bls, caixa), encoding="utf-8")
        elif f == "vtt":
            p = destino / f"{nome}.vtt"; p.write_text(L.vtt(bls, caixa), encoding="utf-8")
        elif f == "ass":
            tema = EF.tema_de(perfil_dir=a.perfil) if a.perfil else EF.mesclar_tema()
            w, h = EF.FORMATOS[a.formato or (C.carregar(obrigatorio=False) or {}).get("video", {}).get("formato", "16:9")]
            p = destino / f"{nome}.ass"
            p.write_text(L.ass(bls, tema, w, h, conteudo["opcoes"]["modo"], cfg["posicao"], caixa), encoding="utf-8")
        elif f == "hyperframes":
            de = a.de or 0.0
            ate = a.ate if a.ate is not None else conteudo["duracao"]
            p = destino / f"{nome}_hyperframes_{de:g}-{ate:g}.json"
            p.write_text(json.dumps(L.para_hyperframes(bls, de, ate, conteudo["opcoes"]["modo"], cfg["posicao"]),
                                    ensure_ascii=False), encoding="utf-8")
        else:
            raise E.ErroEstado(f"formato '{f}' desconhecido (srt, vtt, ass, hyperframes)")
        feitos[f] = str(p)
        print(p)
    with E.editar(a.pasta) as e:
        e.setdefault("legendas", {}).setdefault("saidas", {}).update(feitos)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gerar"); p.add_argument("pasta")
    p.add_argument("--modo", choices=["frase", "palavra"]); p.add_argument("--max-caracteres", type=int)
    p.add_argument("--linhas", type=int, choices=[1, 2]); p.add_argument("--correcoes")
    p.add_argument("--manter-hesitacoes", action="store_true"); p.add_argument("--quebrar-no-corte", action="store_true")
    p.set_defaults(f=cmd_gerar)
    p = sub.add_parser("ver"); p.add_argument("pasta"); p.set_defaults(f=cmd_ver)
    p = sub.add_parser("corrigir"); p.add_argument("pasta"); p.add_argument("id"); p.add_argument("texto")
    p.set_defaults(f=cmd_corrigir)
    p = sub.add_parser("exportar"); p.add_argument("pasta"); p.add_argument("--formatos"); p.add_argument("--perfil")
    p.add_argument("--formato", choices=list(EF.FORMATOS)); p.add_argument("--de", type=float); p.add_argument("--ate", type=float)
    p.set_defaults(f=cmd_exportar)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        a.f(a)
    except (E.ErroEstado, EF.ErroEfeito, C.ErroConfig) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
