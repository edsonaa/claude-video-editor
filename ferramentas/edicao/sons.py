"""Índice da biblioteca de sons: duração, tempo até o pico, nível e categoria.

O tempo até o pico é o que alinha um efeito ao que se vê: um impacto entra
`pico` segundos ANTES do quadro do impacto. A categoria é a primeira pasta
dentro da biblioteca (whoosh/, impacto/, pop/…).

Reindexar é incremental: só reanalisa o que mudou (tamanho ou data) e mantém
os campos escritos à mão (licenca, tags, nota).
"""
from __future__ import annotations

import math
from pathlib import Path

from . import ff

EXT = {".wav", ".mp3", ".flac", ".ogg", ".aif", ".aiff", ".m4a", ".opus"}
MANUAIS = ("licenca", "tags", "nota", "favorito")


def analisar(caminho, taxa: int = 48000) -> dict:
    import numpy as np

    info = ff.sondar(caminho)
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    if a is None:
        raise ValueError("sem áudio")
    x = ff.ler_audio(caminho, taxa=taxa)
    if x.size == 0:
        raise ValueError("áudio vazio")
    absx = np.abs(x)
    pico_i = int(absx.argmax())
    pico = float(absx[pico_i])
    # Envelope RMS em janelas de 10 ms: o "pico percebido", menos sensível a um estalo.
    jan = max(1, taxa // 100)
    n = absx.size // jan
    env = np.sqrt((x[: n * jan].reshape(n, jan) ** 2).mean(axis=1)) if n else np.array([pico])
    env_i = int(env.argmax())
    limiar = env.max() * 10 ** (-20 / 20)  # começo: primeira janela a -20 dB do máximo
    inicio_i = int(np.argmax(env >= limiar)) if env.size else 0
    rms = float(np.sqrt((x ** 2).mean()))

    def db(v):
        return round(20 * math.log10(v), 1) if v > 0 else -120.0

    return {
        "duracao": round(x.size / taxa, 3),
        "canais": int(a.get("channels") or 1),
        "taxa": int(a.get("sample_rate") or 0),
        "pico": round((env_i + 0.5) * jan / taxa, 3),          # tempo até o pico do envelope
        "pico_amostra": round(pico_i / taxa, 3),               # tempo da maior amostra
        "inicio_som": round(inicio_i * jan / taxa, 3),         # silêncio no começo do arquivo
        "pico_db": db(pico),
        "rms_db": db(rms),
    }


def indexar(biblioteca, indice_existente: dict | None = None) -> dict:
    bib = Path(biblioteca).resolve()
    antigos = {s["arquivo"]: s for s in (indice_existente or {}).get("sons", [])}
    sons, erros, reaproveitados = [], [], 0
    for f in sorted(bib.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in EXT or f.name.startswith("."):
            continue
        rel = f.relative_to(bib).as_posix()
        st = f.stat()
        velho = antigos.get(rel)
        if velho and velho.get("_tam") == st.st_size and velho.get("_mod") == int(st.st_mtime):
            sons.append(velho)
            reaproveitados += 1
            continue
        try:
            dados = analisar(f)
        except Exception as e:  # um arquivo ruim não para o índice
            erros.append(f"{rel}: {e}")
            continue
        partes = rel.split("/")
        item = {"id": f.stem, "arquivo": rel, "categoria": partes[0] if len(partes) > 1 else "sem_categoria",
                **dados, "_tam": st.st_size, "_mod": int(st.st_mtime)}
        for k in MANUAIS:
            if velho and k in velho:
                item[k] = velho[k]
        sons.append(item)
    # ids únicos (o mesmo nome em pastas diferentes)
    vistos: dict[str, int] = {}
    for s in sons:
        base = s["id"]
        if base in vistos:
            vistos[base] += 1
            s["id"] = f"{s['categoria']}/{base}"
        else:
            vistos[base] = 1
    return {"biblioteca": str(bib), "sons": sons, "erros": erros, "reaproveitados": reaproveitados}


def buscar(indice: dict, categoria: str | None = None, texto: str | None = None,
           dur_min: float | None = None, dur_max: float | None = None, limite: int = 30) -> list[dict]:
    out = []
    for s in indice["sons"]:
        if categoria and s["categoria"].lower() != categoria.lower():
            continue
        if dur_min is not None and s["duracao"] < dur_min:
            continue
        if dur_max is not None and s["duracao"] > dur_max:
            continue
        if texto:
            alvo = " ".join([s["arquivo"], " ".join(s.get("tags") or []), s.get("nota") or ""]).lower()
            if not all(t in alvo for t in texto.lower().split()):
                continue
        out.append(s)
    out.sort(key=lambda s: (not s.get("favorito"), s["categoria"], s["arquivo"]))
    return out[:limite]
