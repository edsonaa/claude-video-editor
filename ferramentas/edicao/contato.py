"""Folhas de contato: quadros lado a lado com o tempo em cada um.

É o que o Claude olha para entender como um elemento entra, assenta e sai,
sem abrir o vídeo quadro a quadro. Precisa de numpy e OpenCV.
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess

from . import ff
from .tempo import Taxa, hms


def folha(video, saida, inicio: float = 0.0, fim: float | None = None,
          cada: int = 4, colunas: int = 6, largura: int = 320, maximo: int = 60) -> dict:
    """Um quadro a cada `cada` frames entre `inicio` e `fim`, em grade.

    Se o intervalo der mais que `maximo` quadros, o passo aumenta e isso é avisado.
    """
    import cv2
    import numpy as np

    info = ff.sondar(video)
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    taxa = Taxa.de(v.get("r_frame_rate") or v.get("avg_frame_rate"))
    w0, h0 = int(v["width"]), int(v["height"])
    dur = float(info["format"].get("duration") or 0)
    fim = dur if fim is None else min(fim, dur)
    if fim <= inicio:
        raise ValueError("o fim precisa ser depois do início")

    f_ini, f_fim = taxa.frames(inicio), taxa.frames_piso(fim)
    total = max(1, f_fim - f_ini)
    aviso = None
    if math.ceil(total / cada) > maximo:
        novo = math.ceil(total / maximo)
        aviso = f"passo aumentado de {cada} para {novo} frames (limite de {maximo} quadros)"
        cada = novo

    altura = int(round(h0 * largura / w0 / 2) * 2)
    filtro = f"select='not(mod(n\\,{cada}))',scale={largura}:{altura}"
    args = [ff.ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{taxa.segundos(f_ini):.6f}", "-i", str(video),
            "-t", f"{taxa.segundos(total):.6f}", "-vf", filtro, "-fps_mode", "passthrough",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise ff.ErroFFmpeg(proc.stderr.decode("utf-8", "replace")[-1500:])
    tam = largura * altura * 3
    n = len(proc.stdout) // tam
    if n == 0:
        raise ff.ErroFFmpeg("nenhum quadro extraído")
    quadros = np.frombuffer(proc.stdout[: n * tam], dtype=np.uint8).reshape(n, altura, largura, 3)

    linhas = math.ceil(n / colunas)
    faixa = 22
    grade = np.full((linhas * (altura + faixa), colunas * largura, 3), 24, dtype=np.uint8)
    tempos = []
    for i, q in enumerate(quadros):
        lin, col = divmod(i, colunas)
        y, x = lin * (altura + faixa), col * largura
        grade[y + faixa: y + faixa + altura, x: x + largura] = q
        frame = f_ini + i * cada
        t = taxa.segundos(frame)
        tempos.append(round(t, 3))
        rotulo = f"{hms(t, 2)}  f{frame}"
        cv2.putText(grade, rotulo, (x + 6, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1, cv2.LINE_AA)
        cv2.rectangle(grade, (x, y + faixa), (x + largura - 1, y + faixa + altura - 1), (60, 60, 60), 1)
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(saida), grade):
        raise OSError(f"não consegui gravar {saida}")
    return {"arquivo": str(saida), "quadros": n, "cada": cada, "tempos": tempos,
            "fps": str(taxa), "aviso": aviso}
