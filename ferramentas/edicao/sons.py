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


# ------------------------------------------------------------------ pacote inicial
PACOTE = {
    "whoosh/whoosh-curto": "passagem rápida de ar, da esquerda para a direita",
    "whoosh/whoosh-longo": "passagem mais lenta e cheia",
    "impacto/impacto-grave": "pancada grave e funda, para revelação",
    "impacto/batida": "batida seca e curta",
    "pop/pop": "pop de elemento que aparece",
    "pop/bolha": "bolha que sobe",
    "clique/clique": "clique de mouse (aperta e solta)",
    "clique/tecla": "toque de tecla",
    "ding/ding": "sino limpo",
    "ding/notificacao": "duas notas de aviso",
    "riser/subida": "subida de tensão que termina seca",
    "glitch/glitch": "falha digital curta",
}
LICENCA_PACOTE = "livre (gerado pelo motor, sem direitos de terceiros)"


def _sintetizar(nome: str, taxa: int = 48000):
    """Um som do pacote como array estéreo (n, 2), determinístico."""
    import numpy as np

    rng = np.random.default_rng(sum(map(ord, nome)))  # mesma semente, mesmo som
    sr = taxa

    def t_(dur):
        return np.arange(int(dur * sr)) / sr

    def passa_baixa(x, corte):
        """Um polo, com corte (Hz) que pode variar no tempo."""
        corte = np.broadcast_to(np.asarray(corte, dtype=float), x.shape)
        a = np.exp(-2 * np.pi * corte / sr)
        y = np.empty_like(x)
        acc = 0.0
        for i in range(x.size):
            acc = (1 - a[i]) * x[i] + a[i] * acc
            y[i] = acc
        return y

    def env(t, ataque, queda):
        return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-np.maximum(0, t - ataque) / queda)

    def seno_glide(t, f0, f1, curva=4.0):
        f = f1 + (f0 - f1) * np.exp(-curva * t / t[-1])
        return np.sin(2 * np.pi * np.cumsum(f) / sr)

    mono, pan = None, None
    if nome.startswith("whoosh"):
        dur = 0.45 if "curto" in nome else 1.0
        t = t_(dur)
        ruido = rng.standard_normal(t.size)
        u = t / dur
        forma = np.sin(np.pi * u ** 0.8) ** 2                     # sobe e desce, pico depois do meio
        corte = 300 + 4200 * forma
        x = passa_baixa(ruido, corte) - passa_baixa(ruido, corte * 0.18)
        mono = x * forma
        pan = u                                                  # da esquerda para a direita
    elif nome == "impacto/impacto-grave":
        t = t_(1.4)
        corpo = seno_glide(t, 120, 42, 6) * env(t, 0.004, 0.45)
        ataque = passa_baixa(rng.standard_normal(t.size), 1800) * env(t, 0.001, 0.03) * 3
        mono = np.tanh(1.8 * (corpo + ataque))
    elif nome == "impacto/batida":
        t = t_(0.35)
        mono = np.tanh(2.2 * seno_glide(t, 160, 52, 9) * env(t, 0.002, 0.09)) + \
            passa_baixa(rng.standard_normal(t.size), 4000) * env(t, 0.0005, 0.008) * 0.8
    elif nome == "pop/pop":
        t = t_(0.12)
        mono = seno_glide(t, 950, 280, 7) * env(t, 0.001, 0.035)
    elif nome == "pop/bolha":
        t = t_(0.14)
        f = 380 + 1100 * (t / t[-1]) ** 1.5
        mono = np.sin(2 * np.pi * np.cumsum(f) / sr) * env(t, 0.006, 0.05)
    elif nome == "clique/clique":
        t = t_(0.12)
        r = rng.standard_normal(t.size)
        clique = r - passa_baixa(r, 2500)
        mono = clique * (env(t, 0.0003, 0.003) + 0.55 * env(np.maximum(0, t - 0.055), 0.0003, 0.0025) * (t > 0.055))
    elif nome == "clique/tecla":
        t = t_(0.08)
        r = rng.standard_normal(t.size)
        mono = (passa_baixa(r, 5000) - passa_baixa(r, 900)) * env(t, 0.0004, 0.012)
    elif nome == "ding/ding":
        t = t_(1.6)
        mono = sum(a * np.sin(2 * np.pi * 1320 * p * t) * env(t, 0.002, q)
                   for p, a, q in ((1, 1, 0.6), (2.76, 0.45, 0.25), (5.4, 0.25, 0.12), (8.93, 0.12, 0.06)))
    elif nome == "ding/notificacao":
        t = t_(0.9)
        def nota(f, ini):
            tt = np.maximum(0, t - ini)
            return (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * env(tt, 0.003, 0.18) * (t >= ini)
        mono = nota(660, 0) + nota(990, 0.14)
    elif nome == "riser/subida":
        t = t_(2.0)
        u = t / t[-1]
        r = passa_baixa(rng.standard_normal(t.size), 200 + 7000 * u ** 2)
        tom = np.sin(2 * np.pi * np.cumsum(180 + 1100 * u ** 2) / sr)
        mono = (r * 1.5 + 0.35 * tom) * u ** 2.2 * np.minimum(1, (1 - u) * 60)
    elif nome == "glitch/glitch":
        t = t_(0.42)
        mono = np.zeros(t.size)
        i = 0
        while i < t.size:
            n = int(rng.integers(int(0.012 * sr), int(0.05 * sr)))
            f = float(rng.choice([180, 420, 900, 1600, 2400]))
            seg = np.sign(np.sin(2 * np.pi * f * np.arange(n) / sr)) * (rng.random() * 0.7 + 0.3)
            if rng.random() < 0.3:
                seg = rng.standard_normal(n) * 0.6
            mono[i:i + n] = seg[: max(0, min(n, t.size - i))]
            i += n + int(rng.integers(0, int(0.02 * sr)))
        mono = np.round(mono * 6) / 6 * env(t, 0.001, 0.25)
    else:
        raise ValueError(f"som '{nome}' não está no pacote")
    mono = mono - mono.mean()
    if pan is None:
        pan = np.full(mono.size, 0.5)
    est = np.stack([mono * np.cos(pan * np.pi / 2), mono * np.sin(pan * np.pi / 2)], axis=1) * np.sqrt(2)
    fade = min(est.shape[0] // 4, int(0.004 * sr))
    if fade:
        est[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pico = np.abs(est).max() or 1
    return est * (10 ** (-3 / 20) / pico)


def pacote_inicial(destino, taxa: int = 48000, sobrescrever: bool = False) -> dict:
    """Grava o pacote inicial (12 sons em pastas por categoria) e o índice da biblioteca."""
    import json
    import wave

    import numpy as np

    destino = Path(destino)
    feitos, pulados = [], []
    for nome in PACOTE:
        arq = destino / f"{nome}.wav"
        if arq.exists() and not sobrescrever:
            pulados.append(nome)
            continue
        arq.parent.mkdir(parents=True, exist_ok=True)
        x = (np.clip(_sintetizar(nome, taxa), -1, 1) * 32767).astype("<i2")
        with wave.open(str(arq), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(x.tobytes())
        feitos.append(nome)
    arq_ind = destino / "indice.json"
    velho = json.loads(arq_ind.read_text(encoding="utf-8")) if arq_ind.exists() else None
    ind = indexar(destino, velho)
    for s in ind["sons"]:
        nome = s["arquivo"].rsplit(".", 1)[0]
        if nome in PACOTE:
            s.setdefault("licenca", LICENCA_PACOTE)
            s.setdefault("nota", PACOTE[nome])
    ind.pop("reaproveitados", None)
    erros = ind.pop("erros")
    arq_ind.write_text(json.dumps(ind, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"pasta": str(destino), "feitos": feitos, "pulados": pulados, "indice": str(arq_ind),
            "sons": len(ind["sons"]), "erros": erros}
