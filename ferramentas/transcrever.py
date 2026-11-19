#!/usr/bin/env python3
"""Transcrição: roda o motor, normaliza, e gera o que o Claude lê.

Uso:
  transcrever.py rodar <video|audio> <saida.json> [--motor whisperx|scribe] [--idioma pt]
                 [--termos "Nome, Termo"] [--offset S] [--modelo M]
      extrai o WAV 16 kHz mono, transcreve e grava já normalizado (palavras/1).
      --offset: soma S segundos (áudio externo → tempo da câmera).

  transcrever.py normalizar <bruto.json> <saida.json> [--offset S] [--origem arquivo]
      converte uma transcrição do WhisperX ou do Scribe para o formato único.

  transcrever.py frases <palavras.json> [--silencios silencios.json] [--video cam01] [--saida frases.txt]
      uma frase por linha, com tempo, pausas e ⟨som sem palavra⟩ (lacunas).

  transcrever.py lacunas <palavras.json> <silencios.json> [--minimo 0.6] [--json]
      trechos com som e sem palavra: retranscreva SEM termos/contexto.

  transcrever.py notas <palavras.json> [--abertura "nota de edição"] [--fechamento "fim da nota"]
      acha as notas faladas para o editor.

  transcrever.py fala <pasta do vídeo> [--saida fala_seq.txt]
      a fala no tempo da sequência (pelos cortes do estado), com o tempo exato de cada corte.

Sempre confira trechos com som e sem palavra: com contexto inicial o motor às
vezes inventa frases ou engole takes repetidos.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import ff, transcricao as T  # noqa: E402
from edicao import estado as E  # noqa: E402
from edicao.linha import Linha  # noqa: E402
from edicao.tempo import hms  # noqa: E402


def _gravar(obj, caminho):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _resumo(t: dict) -> str:
    ps = t["palavras"]
    hes = sum(1 for p in ps if p["tipo"] == "hesitacao")
    est = sum(1 for p in ps if p.get("estimado"))
    ev = sum(1 for p in ps if p["tipo"] == "evento")
    return f"{len(ps)} palavras · {hes} hesitações · {ev} eventos · {est} com tempo estimado"


def cmd_rodar(a):
    with tempfile.TemporaryDirectory() as tmp:
        wav = ff.extrair_wav(a.entrada, Path(tmp) / (Path(a.entrada).stem + ".wav"))
        bruto = Path(a.saida).with_suffix(".bruto.json")
        if a.motor == "whisperx":
            saida = T.rodar_whisperx(wav, Path(tmp) / "wx", a.idioma, a.modelo or "large-v3", a.termos)
            bruto.write_bytes(Path(saida).read_bytes())
        else:
            T.rodar_scribe(wav, bruto, a.idioma, a.modelo or "scribe_v2")
    dados = json.loads(bruto.read_text(encoding="utf-8"))
    t = T.normalizar(dados, origem=str(Path(a.entrada).resolve()), offset=a.offset, idioma=a.idioma)
    _gravar(t, a.saida)
    print(f"{a.saida}: {_resumo(t)} (bruto em {bruto})")


def cmd_normalizar(a):
    dados = json.loads(Path(a.bruto).read_text(encoding="utf-8"))
    t = T.normalizar(dados, origem=a.origem or "", offset=a.offset)
    _gravar(t, a.saida)
    print(f"{a.saida}: {_resumo(t)} (motor {t['motor']})")


def _lacunas_de(t, silencios_json, minimo):
    sil = json.loads(Path(silencios_json).read_text(encoding="utf-8"))
    return T.lacunas(t["palavras"], sil["som"], minimo)


def cmd_frases(a):
    t = T.ler(a.palavras)
    lacs = _lacunas_de(t, a.silencios, a.minimo) if a.silencios else None
    texto = T.texto_frases(t, a.video or Path(a.palavras).stem, lacs, pausa=a.pausa)
    if a.saida:
        Path(a.saida).write_text(texto, encoding="utf-8")
        n = texto.count("\n") - 1
        print(f"{a.saida}: {n} linhas" + (f", {len(lacs)} lacunas" if lacs else ""))
    else:
        sys.stdout.write(texto)


def cmd_lacunas(a):
    t = T.ler(a.palavras)
    lacs = _lacunas_de(t, a.silencios, a.minimo)
    if a.json:
        print(json.dumps(lacs))
        return
    print(f"{len(lacs)} trechos com som e sem palavra (≥ {a.minimo}s):")
    for x, y in lacs:
        print(f"  {hms(x)} – {hms(y)}  ({y - x:.1f}s)")


def cmd_notas(a):
    t = T.ler(a.palavras)
    notas = T.notas_faladas(t["palavras"], a.abertura, a.fechamento)
    if a.json:
        print(json.dumps(notas, ensure_ascii=False, indent=1))
        return
    print(f"{len(notas)} notas:")
    for n in notas:
        print(f"  {hms(n['inicio'])}–{hms(n['fim'])}  [{n['confianca']}]  {n['texto']}")


def cmd_fala(a):
    d = E.ler(a.pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise SystemExit("o estado ainda não tem cortes")
    fps = (d.get("midia") or {}).get("fps")
    if not fps:
        raise SystemExit("o estado não tem midia.fps")
    pasta = E.caminho_estado(a.pasta).parent.parent
    transcs = {}
    for vid, caminho in ((d.get("transcricao") or {}).get("palavras") or {}).items():
        c = Path(caminho)
        transcs[vid] = T.ler(c if c.is_absolute() else pasta / c)
    texto = T.fala_na_sequencia(transcs, Linha(segs, fps))
    if a.saida:
        Path(a.saida).write_text(texto, encoding="utf-8")
        print(f"{a.saida}: {texto.count(chr(10))} linhas")
    else:
        sys.stdout.write(texto)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("rodar")
    p.add_argument("entrada"); p.add_argument("saida")
    p.add_argument("--motor", choices=["whisperx", "scribe"], default="whisperx")
    p.add_argument("--idioma", default="pt"); p.add_argument("--termos"); p.add_argument("--modelo")
    p.add_argument("--offset", type=float, default=0.0)
    p.set_defaults(f=cmd_rodar)
    p = sub.add_parser("normalizar")
    p.add_argument("bruto"); p.add_argument("saida")
    p.add_argument("--offset", type=float, default=0.0); p.add_argument("--origem")
    p.set_defaults(f=cmd_normalizar)
    p = sub.add_parser("frases")
    p.add_argument("palavras"); p.add_argument("--silencios"); p.add_argument("--video")
    p.add_argument("--saida"); p.add_argument("--pausa", type=float, default=0.6)
    p.add_argument("--minimo", type=float, default=0.6)
    p.set_defaults(f=cmd_frases)
    p = sub.add_parser("lacunas")
    p.add_argument("palavras"); p.add_argument("silencios")
    p.add_argument("--minimo", type=float, default=0.6); p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_lacunas)
    p = sub.add_parser("notas")
    p.add_argument("palavras"); p.add_argument("--abertura", default="nota de edição")
    p.add_argument("--fechamento", default="fim da nota"); p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_notas)
    p = sub.add_parser("fala")
    p.add_argument("pasta"); p.add_argument("--saida")
    p.set_defaults(f=cmd_fala)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a.f(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
