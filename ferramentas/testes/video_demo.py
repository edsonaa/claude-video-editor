#!/usr/bin/env python3
"""Monta um vídeo de demonstração completo (estado + mídias) para o painel de revisão.

  video_demo.py <destino>      monta em <destino>/2026-01-15_Demo e mostra o comando do painel

Tem um pouco de tudo: câmera em H.264 (toca no navegador), gravação de tela em
ProRes com áudio PCM (precisa de prévia), animação com transparência (ProRes 4444)
e em tela cheia, efeitos sonoros, música, legendas, marcações e pedidos.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent))
sys.path.insert(0, str(TESTES))
from edicao import estado as E  # noqa: E402
from edicao import ff  # noqa: E402
from edicao import transcricao as T  # noqa: E402
import gerar_clipe  # noqa: E402

FPS = "30000/1001"
SEGS = [{"id": "s001", "video": "cam01", "inicio": 0.45, "fim": 2.05},
        {"id": "s002", "video": "cam01", "inicio": 2.55, "fim": 4.15},
        {"id": "s003", "video": "tela01", "inicio": 1.0, "fim": 3.0},
        {"id": "s004", "video": "cam01", "inicio": 5.45, "fim": 8.05}]


def _ff(*args):
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", *map(str, args)])


def montar(destino: Path, clipe: Path | None = None, legendas: bool = True) -> Path:
    clipe = clipe or gerar_clipe.gerar(destino / "_clipe")
    v = destino / "2026-01-15_Demo"
    if v.exists():
        shutil.rmtree(v)
    brutos = v / "Brutos"
    renders = v / "Renders"
    for p in (brutos, renders, v / "_CLAUDE"):
        p.mkdir(parents=True, exist_ok=True)
    shutil.copy(clipe / "cam01.mp4", brutos / "cam01.mp4")
    _ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30000/1001:duration=6", "-f", "lavfi",
        "-i", "sine=frequency=330:sample_rate=48000:duration=6", "-c:v", "prores_ks", "-profile:v", "0",
        "-c:a", "pcm_s16le", brutos / "tela01.mov")
    # animação sobreposta com transparência (ProRes 4444) e uma em tela cheia (H.264)
    _ff("-f", "lavfi", "-i", "color=c=0x7C3AED@0.0:size=1280x720:rate=30000/1001:duration=2.5,format=rgba",
        "-vf", "drawbox=x=60:y=520:w=520:h=120:color=0x111827:t=fill,drawbox=x=60:y=520:w=10:h=120:color=0xFACC15:t=fill,"
        "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(between(X,60,579)*between(Y,520,639),235,0)'",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", renders / "mo01.mov")
    _ff("-f", "lavfi", "-i", "color=c=0x0F172A:size=1280x720:rate=30000/1001:duration=1.5",
        "-vf", "drawbox=x=440:y=260:w=400:h=200:color=0xFACC15@1:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        renders / "mo02.mp4")
    _ff("-f", "lavfi", "-i", "aevalsrc='0.15*sin(2*PI*220*t)|0.15*sin(2*PI*277*t)':s=48000:d=10",
        v / "_CLAUDE" / "musica_v01.wav")
    transc = T.normalizar(json.loads((TESTES / "dados" / "whisperx.json").read_text(encoding="utf-8")))
    (v / "_CLAUDE" / "palavras_cam01.json").write_text(json.dumps(transc, ensure_ascii=False), encoding="utf-8")

    E.criar(v, "2026-01-15_Demo", fluxo=["iniciar", "preparar", "cortes", "motion_mapa", "motion_render", "sfx",
                                           "legendas"])
    with E.editar(v) as d:
        d["midia"] = {"fps": FPS, "resolucao": [1280, 720], "principal": "cam01", "arquivos": [
            {"id": "cam01", "caminho": str(brutos / "cam01.mp4"), "tipo": "camera", "duracao": 12.0,
             "resolucao": [1280, 720]},
            {"id": "tela01", "caminho": str(brutos / "tela01.mov"), "tipo": "tela", "duracao": 6.0,
             "resolucao": [1280, 720]}]}
        d["transcricao"] = {"motor": "whisperx", "palavras": {"cam01": "_CLAUDE/palavras_cam01.json"}}
        d["cortes"] = {"versao": 1, "segmentos": [dict(s) for s in SEGS]}
        d["motions"] = {"versao": 1, "base_cortes_versao": 1, "itens": [
            {"id": "mo01", "status": "renderizado", "inicio_seq": 0.6, "fim_seq": 3.1, "formato": "sobreposicao",
             "ideia": "Tarja com o nome e a especialidade", "render": {"arquivo": str(renders / "mo01.mov"), "versao": 1}},
            {"id": "mo02", "status": "renderizado", "inicio_seq": 5.3, "fim_seq": 6.8, "formato": "tela_cheia",
             "ideia": "Card do número: 20 placas", "render": {"arquivo": str(renders / "mo02.mp4"), "versao": 1}},
            {"id": "mo03", "status": "proposto", "inicio_seq": 7.2, "fim_seq": 8.6, "formato": "enfase",
             "ideia": "Ênfase em “problema de alimentação”"}]}
        d["camera"] = {"movimentos": [{"id": "cam01", "inicio_seq": 3.3, "fim_seq": 5.1, "tipo": "aproximação lenta",
                                       "de": 1.0, "ate": 1.12}]}
        d["sfx"] = {"itens": [
            {"id": "sfx01", "arquivo": str(clipe / "sfx" / "whoosh" / "whoosh_01.wav"), "inicio_seq": 5.1,
             "ganho_db": -12, "evento": "entrada do card mo02"},
            {"id": "sfx02", "arquivo": str(clipe / "sfx" / "pop" / "pop_01.wav"), "inicio_seq": 0.65, "ganho_db": -16,
             "evento": "tarja mo01"}],
            "musica": {"arquivo": str(v / "_CLAUDE" / "musica_v01.wav"), "inicio_seq": 0.0, "duracao": 10.0,
                       "ganho_db": -6}}
        d["marcadores"] = [{"id": "m001", "video": "cam01", "tempo": 1.4, "tipo": "hesitacao",
                            "texto": "“ééé” cortado; confira se a respiração ficou natural"},
                           {"id": "m002", "video": "cam01", "tempo": 9.5, "tipo": "duvida_take",
                            "texto": "Este take repete o anterior; deixei de fora"}]
        for e in ("iniciar", "preparar", "cortes", "motion_mapa"):
            d["etapas"][e] = "concluido"
        d["etapas"]["motion_render"] = "aguardando_aprovacao"
        E.nova_pendencia(d, "sfx", "Testar um whoosh mais curto na entrada do card", "sfx01")
    if legendas:
        subprocess.run([sys.executable, str(TESTES.parent / "legendas.py"), "gerar", str(v), "--modo", "palavra",
                        "--max-caracteres", "24"], check=True, capture_output=True)
    return v


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "demo").resolve()
    v = montar(destino)
    print(v)
    print(f"python {TESTES.parent / 'painel.py'} abrir {v} --porta 0")
