"""Rastreio de rosto com o YuNet (OpenCV), para a câmera que segue o rosto.

Amostra o vídeo a poucas imagens por segundo, guarda o maior rosto de cada
amostra (centro e tamanho normalizados de 0 a 1) e uma trilha suavizada,
com as falhas preenchidas por interpolação. A etapa de câmera parte disso.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import urllib.request

from . import ff
from .tempo import Taxa

URL_MODELO = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
              "face_detection_yunet/face_detection_yunet_2023mar.onnx")
NOME_MODELO = "face_detection_yunet_2023mar.onnx"


def baixar_modelo(pasta) -> Path:
    destino = Path(pasta) / NOME_MODELO
    if destino.exists() and destino.stat().st_size > 100_000:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".parcial")
    with urllib.request.urlopen(URL_MODELO, timeout=120) as r:
        tmp.write_bytes(r.read())
    if tmp.stat().st_size < 100_000:
        tmp.unlink()
        raise RuntimeError("o download do modelo veio incompleto (o GitHub devolveu um ponteiro LFS?)")
    tmp.replace(destino)
    return destino


def rastrear(video, modelo, amostras_por_s: float = 5.0, inicio: float = 0.0, fim: float | None = None,
             largura_analise: int = 640, confianca: float = 0.7, suavizar_s: float = 0.6) -> dict:
    import cv2
    import numpy as np

    info = ff.sondar(video)
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    taxa = Taxa.de(v.get("r_frame_rate") or v.get("avg_frame_rate"))
    w0, h0 = int(v["width"]), int(v["height"])
    dur = float(info["format"].get("duration") or 0)
    fim = dur if fim is None else min(fim, dur)
    w = min(largura_analise, w0)
    h = int(round(h0 * w / w0 / 2) * 2)

    det = cv2.FaceDetectorYN.create(str(modelo), "", (w, h), confianca, 0.3, 5000)
    args = [ff.ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{inicio:.6f}", "-i", str(video),
            "-t", f"{fim - inicio:.6f}", "-vf", f"fps={amostras_por_s},scale={w}:{h}",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tam = w * h * 3
    amostras = []
    k = 0
    while True:
        buf = proc.stdout.read(tam)
        if len(buf) < tam:
            break
        q = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        _, faces = det.detect(q)
        t = round(inicio + k / amostras_por_s, 3)
        if faces is not None and len(faces):
            f = max(faces, key=lambda r: r[2] * r[3])
            x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14])
            olhos = [(float(f[4]) / w, float(f[5]) / h), (float(f[6]) / w, float(f[7]) / h)]
            amostras.append({"t": t, "cx": round((x + fw / 2) / w, 4), "cy": round((y + fh / 2) / h, 4),
                             "w": round(fw / w, 4), "h": round(fh / h, 4), "conf": round(score, 3),
                             "olhos_y": round(sum(o[1] for o in olhos) / 2, 4), "n": int(len(faces))})
        else:
            amostras.append({"t": t, "cx": None})
        k += 1
    proc.stdout.close()
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise ff.ErroFFmpeg(err[-1500:])

    trilha = suavizar(amostras, janela=max(1, int(round(suavizar_s * amostras_por_s))))
    achadas = sum(1 for a in amostras if a.get("cx") is not None)
    resumo = {"amostras": len(amostras), "com_rosto": achadas,
              "cobertura": round(achadas / len(amostras), 3) if amostras else 0.0}
    if achadas:
        resumo["cx_medio"] = round(sum(a["cx"] for a in amostras if a.get("cx") is not None) / achadas, 3)
        resumo["largura_media"] = round(sum(a["w"] for a in amostras if a.get("cx") is not None) / achadas, 3)
        resumo["varios_rostos"] = sum(1 for a in amostras if (a.get("n") or 0) > 1)
    return {"video": str(Path(video).resolve()), "fps": str(taxa), "resolucao": [w0, h0],
            "amostras_por_s": amostras_por_s, "resumo": resumo, "amostras": amostras, "trilha": trilha}


def suavizar(amostras: list[dict], janela: int = 3) -> list[dict]:
    """Mediana móvel do centro (resiste a um quadro errado) e interpolação nas falhas."""
    import numpy as np

    ts = [a["t"] for a in amostras]
    cols = {}
    for campo in ("cx", "cy", "w"):
        vals = np.array([a.get(campo) if a.get("cx") is not None else np.nan for a in amostras], dtype=float)
        ok = ~np.isnan(vals)
        if not ok.any():
            return [{"t": t, "cx": None, "cy": None, "w": None, "interpolado": True} for t in ts]
        idx = np.arange(len(vals))
        vals = np.interp(idx, idx[ok], vals[ok])  # falhas: interpolação; pontas: valor mais próximo
        if janela > 1:
            meio = janela // 2
            pad = np.pad(vals, meio, mode="edge")
            vals = np.array([np.median(pad[i:i + janela]) for i in range(len(vals))])
        cols[campo] = vals
    tem = [a.get("cx") is not None for a in amostras]
    return [{"t": t, "cx": round(float(cols["cx"][i]), 4), "cy": round(float(cols["cy"][i]), 4),
             "w": round(float(cols["w"][i]), 4), **({} if tem[i] else {"interpolado": True})}
            for i, t in enumerate(ts)]
