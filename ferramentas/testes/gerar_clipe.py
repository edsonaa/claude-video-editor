#!/usr/bin/env python3
"""Gera o clipe de teste sintético (sempre igual) para os testes de regressão.

  cam01.mp4   1280x720, 29,97 fps (30000/1001), 12 s, com "falas" (tons) em
              trechos conhecidos e o número do frame desenhado na imagem
  cam02.mp4   igual, mas 25 fps e SEM áudio (para os alertas do inventário)
  rosto.mp4   4 s, 30 fps, uma forma de rosto desenhada andando (para o rastreio)
  sfx/        três "efeitos" curtos com pico em tempos conhecidos

Os trechos com som ficam em FALAS (segundos). Não precisa de internet.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from edicao import ff  # noqa: E402

FALAS = [(0.5, 2.0), (2.6, 4.1), (5.5, 8.0), (9.0, 11.0)]
DURACAO = 12.0
SFX = {  # nome: (duração, tempo do pico)
    "whoosh/whoosh_01.wav": (1.2, 0.8),
    "impacto/impacto_01.wav": (0.6, 0.05),
    "pop/pop_01.wav": (0.25, 0.1),
}


def _expr_falas() -> str:
    janelas = "+".join(f"between(t,{a},{b})" for a, b in FALAS)
    # Tom com leve vibrato, cara de voz para o silencedetect (não para transcrever).
    return f"0.35*sin(2*PI*(180+20*sin(2*PI*3*t))*t)*({janelas})"


def gerar(destino: Path, forcar: bool = False) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    f = ff.ffmpeg()
    cam01 = destino / "cam01.mp4"
    if forcar or not cam01.exists():
        ff.rodar([f, "-v", "error", "-y", "-nostdin",
                  "-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=30000/1001:duration={DURACAO}",
                  "-f", "lavfi", "-i", f"aevalsrc='{_expr_falas()}':s=48000:d={DURACAO}",
                  "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                  "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ac", "2",
                  "-metadata", "creation_time=2026-01-15T10:00:00Z", "-shortest", str(cam01)])
    cam02 = destino / "cam02.mp4"
    if forcar or not cam02.exists():
        ff.rodar([f, "-v", "error", "-y", "-nostdin",
                  "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=3",
                  "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-pix_fmt", "yuv420p",
                  "-metadata", "creation_time=2026-01-15T10:05:00Z", str(cam02)])
    rosto = destino / "rosto.mp4"
    if forcar or not rosto.exists():
        _gerar_rosto(rosto)
    for nome, (dur, pico) in SFX.items():
        arq = destino / "sfx" / nome
        if forcar or not arq.exists():
            arq.parent.mkdir(parents=True, exist_ok=True)
            # Ruído com envelope que sobe até o pico e cai.
            env = f"if(lt(t,{pico}),t/{pico},max(0,1-(t-{pico})/{dur - pico}))"
            ff.rodar([f, "-v", "error", "-y", "-nostdin", "-f", "lavfi",
                      "-i", f"aevalsrc='0.8*{env}*sin(2*PI*600*t)':s=48000:d={dur}",
                      "-c:a", "pcm_s16le", str(arq)])
    return destino


def _gerar_rosto(arq: Path) -> None:
    """Um 'rosto' de desenho atravessando o quadro, para testar o rastreio sem foto de ninguém."""
    import cv2
    import numpy as np

    larg, alt, fps, n = 960, 540, 30, 120
    proc = subprocess.Popen([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-f", "rawvideo",
                             "-pix_fmt", "bgr24", "-s", f"{larg}x{alt}", "-r", str(fps), "-i", "-",
                             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                             "-pix_fmt", "yuv420p", str(arq)], stdin=subprocess.PIPE)
    for i in range(n):
        q = np.full((alt, larg, 3), (70, 90, 110), np.uint8)
        cx = int(250 + 460 * i / (n - 1))
        cy = 270
        cv2.ellipse(q, (cx, cy), (95, 125), 0, 0, 360, (150, 180, 225), -1)   # rosto
        for dx in (-38, 38):
            cv2.ellipse(q, (cx + dx, cy - 25), (18, 10), 0, 0, 360, (250, 250, 250), -1)
            cv2.circle(q, (cx + dx, cy - 25), 7, (40, 30, 20), -1)
            cv2.line(q, (cx + dx - 22, cy - 52), (cx + dx + 22, cy - 55), (40, 50, 70), 5)
        cv2.line(q, (cx, cy - 15), (cx - 8, cy + 25), (110, 130, 180), 4)       # nariz
        cv2.ellipse(q, (cx, cy + 55), (35, 14), 0, 0, 180, (60, 60, 160), 5)     # boca
        cv2.ellipse(q, (cx, cy - 105), (100, 50), 0, 180, 360, (30, 40, 60), -1)  # cabelo
        proc.stdin.write(q.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise ff.ErroFFmpeg("falha ao gerar rosto.mp4")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("destino", nargs="?", default=str(Path(__file__).parent / "clipe"))
    ap.add_argument("--forcar", action="store_true", help="gerar de novo mesmo se já existir")
    a = ap.parse_args()
    print(gerar(Path(a.destino), a.forcar))
