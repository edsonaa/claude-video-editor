"""Chamadas ao FFmpeg/ffprobe, num lugar só."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class ErroFFmpeg(RuntimeError):
    pass


def _binario(nome: str) -> str:
    env = os.environ.get(nome.upper())  # FFMPEG=/caminho/ffmpeg, FFPROBE=…
    if env:
        return env
    achado = shutil.which(nome)
    if not achado:
        raise ErroFFmpeg(f"não achei o {nome}. Instale o FFmpeg ou aponte a variável {nome.upper()}.")
    return achado


def ffmpeg() -> str:
    return _binario("ffmpeg")


def ffprobe() -> str:
    return _binario("ffprobe")


def rodar(args: list[str], entrada: bytes | None = None, texto: bool = True):
    proc = subprocess.run(args, input=entrada, capture_output=True, text=texto and entrada is None)
    if proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
        raise ErroFFmpeg(f"{Path(args[0]).name} falhou ({proc.returncode}):\n{err[-2000:]}")
    return proc


def sondar(caminho: str | os.PathLike, contar_frames: bool = False) -> dict:
    """ffprobe em JSON (formato + streams)."""
    args = [ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    if contar_frames:
        args += ["-count_packets"]
    args.append(str(caminho))
    return json.loads(rodar(args).stdout)


def ler_audio(caminho, taxa: int = 16000, inicio: float | None = None,
              duracao: float | None = None, canal: int | None = None):
    """Decodifica para float32 mono (numpy). `canal` escolhe um canal em vez da mistura."""
    import numpy as np  # só quem analisa áudio precisa de numpy

    args = [ffmpeg(), "-v", "error", "-nostdin"]
    if inicio is not None:
        args += ["-ss", f"{inicio:.6f}"]
    args += ["-i", str(caminho)]
    if duracao is not None:
        args += ["-t", f"{duracao:.6f}"]
    args += ["-vn"]
    if canal is not None:
        args += ["-af", f"pan=mono|c0=c{canal}"]
    else:
        args += ["-ac", "1"]
    args += ["-ar", str(taxa), "-f", "f32le", "-"]
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise ErroFFmpeg(proc.stderr.decode("utf-8", "replace")[-2000:])
    return np.frombuffer(proc.stdout, dtype=np.float32)


def extrair_wav(origem, destino, taxa: int = 16000) -> Path:
    """WAV mono 16 kHz para transcrição."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    rodar([ffmpeg(), "-v", "error", "-nostdin", "-y", "-i", str(origem), "-vn",
           "-ac", "1", "-ar", str(taxa), "-c:a", "pcm_s16le", str(destino)])
    return destino
