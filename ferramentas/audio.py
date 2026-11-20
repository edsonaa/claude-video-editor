#!/usr/bin/env python3
"""Áudio do vídeo: medir, tratar a voz e montar a música de fundo com ducking.

Uso (os padrões vêm do bloco `audio` da configuração):
  audio.py medir <arquivo> [--inicio S --duracao S] [--canal N] [--json]
      loudness (LUFS), pico real (dBTP), piso de ruído, fala/ruído, clipping, com recomendações
  audio.py tratar <arquivo> [<saida.wav>] [--estado <pasta> --id cam01] [--alvo -14] [--pico -1]
                  [--ruido auto|nenhuma|leve|media|forte] [--passa-alta 80] [--compressao nenhuma|leve|media]
                  [--canal N] [--inicio S --duracao S]
      passa-alta → redução de ruído (pelo piso medido) → compressão → loudness em duas passadas.
      A saída tem a mesma duração e o mesmo início do original (o atraso dos filtros é medido e
      compensado). Com --estado/--id, grava em _CLAUDE/audio/<id>_voz_vNN.wav e anota no estado
      (midia.arquivos[].audio_tratado): o XML passa a usar a voz tratada. Para ouvir antes de tratar
      o arquivo inteiro: --inicio/--duracao num trecho de 20–30 s.
  audio.py musica <pasta> <musica> [--nivel-livre -20] [--nivel-fala -32] [--ataque 0.3] [--liberacao 0.8]
                  [--fade-in 1] [--fade-out 2.5] [--inicio-musica S]
      a música do tamanho do vídeo, abaixando sob a fala (pelos cortes e pela transcrição);
      grava _CLAUDE/audio/musica_vNN.wav e anota em sfx.musica (o XML a põe numa trilha própria)
  audio.py final <arquivo> [--alvo -14] [--pico -1]
      confere a mixagem final contra o alvo (para o render e para o que a pessoa exporta do programa)
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import audio as A  # noqa: E402
from edicao import config as C  # noqa: E402
from edicao import estado as E  # noqa: E402
from edicao import legendas as L  # noqa: E402
from edicao import transcricao as T  # noqa: E402
from edicao.linha import Linha  # noqa: E402

PADRAO = {"tratar": True, "alvo_lufs": -14.0, "pico_dbtp": -1.0, "reducao_ruido": "auto", "passa_alta_hz": 80,
          "compressao": "leve", "musica_nivel_livre": -20.0, "musica_nivel_fala": -32.0}


def _cfg():
    c = C.carregar(obrigatorio=False) or {}
    return {**PADRAO, **(c.get("audio") or {})}


def _versao(pasta: Path, prefixo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    ns = [int(m.group(1)) for f in pasta.glob(f"{prefixo}_v*.wav") if (m := re.fullmatch(rf"{re.escape(prefixo)}_v(\d+)\.wav", f.name))]
    return pasta / f"{prefixo}_v{max(ns, default=0) + 1:02d}.wav"


def _mostrar(m: dict):
    print(f"  loudness {m['lufs']} LUFS · faixa {m['lra']} LU · pico real {m['pico_dbtp']} dBTP · "
          f"ruído {m['ruido_db']} dBFS · fala {m['fala_db']} dBFS · fala/ruído {m['snr_db']} dB · "
          f"clipping {m['clipping_pct']}%")


def cmd_medir(a):
    cfg = _cfg()
    m = A.medir(a.arquivo, a.inicio, a.duracao, a.canal)
    if a.json:
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return
    print(a.arquivo)
    _mostrar(m)
    rec = A.recomendacoes(m, cfg["alvo_lufs"], cfg["pico_dbtp"])
    print(f"  redução de ruído sugerida: {A.ruido_auto(m)}")
    for r in rec:
        print(f"  ! {r}")


def cmd_tratar(a):
    cfg = _cfg()
    if a.estado:
        if not a.id:
            raise E.ErroEstado("com --estado, diga qual arquivo (--id cam01)")
        d = E.ler(a.estado)
        arq = next((x for x in (d.get("midia") or {}).get("arquivos", []) if x["id"] == a.id), None)
        if not arq:
            raise E.ErroEstado(f"'{a.id}' não está em midia.arquivos")
        saida = Path(a.saida) if a.saida else _versao(E.caminho_estado(a.estado).parent / "audio", f"{a.id}_voz")
    else:
        if not a.saida:
            raise E.ErroEstado("diga o arquivo de saída (ou use --estado/--id)")
        saida = Path(a.saida)
    trecho = a.inicio is not None or a.duracao is not None
    r = A.tratar(a.arquivo, saida, a.alvo if a.alvo is not None else cfg["alvo_lufs"],
                 a.pico if a.pico is not None else cfg["pico_dbtp"], a.ruido or cfg["reducao_ruido"],
                 cfg["passa_alta_hz"] if a.passa_alta is None else (a.passa_alta or None),
                 a.compressao or cfg["compressao"], a.canal, a.inicio, a.duracao)
    print(f"{saida}  ({'trecho para ouvir' if trecho else 'arquivo inteiro'})")
    print(f"  escolhas: redução de ruído {r['escolhas']['ruido']}, compressão {r['escolhas']['compressao']}, "
          f"passa-alta {r['escolhas']['passa_alta']} Hz · normalização {r['normalizacao']}")
    print("  antes:"); _mostrar(r["antes"])
    print("  depois:"); _mostrar(r["depois"])
    print(f"  duração igual (diferença {r['diferenca_duracao_ms']} ms); atraso dos filtros compensado: "
          f"{r['atraso_compensado_amostras']} amostras")
    for av in r["avisos"]:
        print(f"  ! {av}")
    if a.estado and not trecho:
        with E.editar(a.estado) as d:
            for x in d["midia"]["arquivos"]:
                if x["id"] == a.id:
                    x["audio_tratado"] = str(saida.resolve())
        print(f"  anotado no estado: {a.id} usa a voz tratada nas próximas entregas")


def cmd_musica(a):
    cfg = _cfg()
    d = E.ler(a.pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    fps = (d.get("midia") or {}).get("fps")
    if not segs or not fps:
        raise E.ErroEstado("o estado precisa de cortes e de midia.fps")
    base = E.caminho_estado(a.pasta).parent.parent
    transcs = {vid: T.ler(Path(c) if Path(c).is_absolute() else base / c)
               for vid, c in ((d.get("transcricao") or {}).get("palavras") or {}).items()}
    linha = Linha(segs, fps)
    fala = A.intervalos_de_fala(L.palavras_na_sequencia(transcs, linha, remover_hesitacoes=False))
    saida = _versao(E.caminho_estado(a.pasta).parent / "audio", "musica")
    r = A.musica(a.musica, saida, linha.duracao, fala,
                 a.nivel_livre if a.nivel_livre is not None else cfg["musica_nivel_livre"],
                 a.nivel_fala if a.nivel_fala is not None else cfg["musica_nivel_fala"],
                 a.ataque, a.liberacao, a.fade_in, a.fade_out, a.inicio_musica)
    with E.editar(a.pasta) as e:
        e.setdefault("sfx", {})["musica"] = {"arquivo": str(saida.resolve()), "inicio_seq": 0.0, "duracao": r["duracao"]}
    print(f"{saida}: {r['duracao']} s, {r['trechos_de_fala']} trechos de fala")
    print(f"  música medida em {r['lufs_musica']} LUFS → ganho {r['ganho_livre_db']} dB sem fala, "
          f"{r['ganho_fala_db']} dB sob a fala" + (f"; repetida {r['repeticoes']}× para cobrir o vídeo" if r["repeticoes"] else ""))
    print("  anotado em sfx.musica: entra numa trilha própria na próxima entrega")


def cmd_final(a):
    cfg = _cfg()
    alvo = a.alvo if a.alvo is not None else cfg["alvo_lufs"]
    pico = a.pico if a.pico is not None else cfg["pico_dbtp"]
    m = A.loudness(a.arquivo)
    ok_l = abs(m["lufs"] - alvo) <= 1.0
    ok_p = m["pico_dbtp"] <= pico + 0.1
    print(f"{a.arquivo}: {m['lufs']} LUFS (alvo {alvo}: {'ok' if ok_l else 'FORA'}) · pico real {m['pico_dbtp']} dBTP "
          f"(teto {pico}: {'ok' if ok_p else 'ACIMA'})")
    return 0 if ok_l and ok_p else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("medir"); p.add_argument("arquivo"); p.add_argument("--inicio", type=float)
    p.add_argument("--duracao", type=float); p.add_argument("--canal", type=int); p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_medir)
    p = sub.add_parser("tratar"); p.add_argument("arquivo"); p.add_argument("saida", nargs="?")
    p.add_argument("--estado"); p.add_argument("--id"); p.add_argument("--alvo", type=float); p.add_argument("--pico", type=float)
    p.add_argument("--ruido", choices=["auto", "nenhuma", "leve", "media", "forte"])
    p.add_argument("--passa-alta", type=int); p.add_argument("--compressao", choices=["nenhuma", "leve", "media"])
    p.add_argument("--canal", type=int); p.add_argument("--inicio", type=float); p.add_argument("--duracao", type=float)
    p.set_defaults(f=cmd_tratar)
    p = sub.add_parser("musica"); p.add_argument("pasta"); p.add_argument("musica")
    p.add_argument("--nivel-livre", type=float); p.add_argument("--nivel-fala", type=float)
    p.add_argument("--ataque", type=float, default=0.3); p.add_argument("--liberacao", type=float, default=0.8)
    p.add_argument("--fade-in", type=float, default=1.0); p.add_argument("--fade-out", type=float, default=2.5)
    p.add_argument("--inicio-musica", type=float, default=0.0)
    p.set_defaults(f=cmd_musica)
    p = sub.add_parser("final"); p.add_argument("arquivo"); p.add_argument("--alvo", type=float); p.add_argument("--pico", type=float)
    p.set_defaults(f=cmd_final)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return a.f(a) or 0
    except (A.ErroAudio, E.ErroEstado, C.ErroConfig) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
