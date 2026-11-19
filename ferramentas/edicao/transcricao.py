"""Transcrição num formato só, venha do WhisperX, do ElevenLabs Scribe ou de outro motor.

Formato normalizado ("palavras/1"):
{
  "formato": "palavras/1", "motor": "whisperx", "idioma": "pt",
  "origem": "<arquivo transcrito>", "offset": 0.0,
  "palavras": [
    {"texto": "Olá", "inicio": 0.12, "fim": 0.40, "tipo": "palavra", "conf": 0.93},
    {"texto": "ééé", "inicio": 0.9, "fim": 1.3, "tipo": "hesitacao"},
    {"texto": "(risos)", "inicio": 2.0, "fim": 2.6, "tipo": "evento"},
    {"texto": "vinte", "inicio": 3.1, "fim": 3.4, "tipo": "palavra", "estimado": true}
  ]
}
- Tempos já no tempo da câmera (o `offset` do áudio externo já foi somado).
- `estimado`: o motor não deu tempo para a palavra (números, no WhisperX);
  o tempo foi interpolado entre as vizinhas. Não use como borda de corte.

Os scripts leem as palavras; o Claude lê as frases (texto_frases).
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import re
import unicodedata

from .tempo import hms

FORMATO = "palavras/1"

# Muletas em português. Só formas que quase nunca são conteúdo: "é" (verbo),
# "e" e "um" (artigo) são palavras, e "tipo", "né", "então" ficam de fora de
# propósito (quem julga é a pessoa).
_HESITACOES = re.compile(
    r"^(?:[eéê]{2,}h*|[eéê]h+|a{2,}h*|ah+|ã+h*|hu+m+|hm+|m{2,}|uh+m*|ahn+|anh+|hã+)[.,!?…]*$",
    re.IGNORECASE)


def eh_hesitacao(texto: str) -> bool:
    t = texto.strip().strip("[]()").strip()
    return bool(t) and bool(_HESITACOES.match(t))


def _limpo(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


# --------------------------------------------------------------- normalizar
def detectar_motor(dados: dict) -> str:
    if dados.get("formato") == FORMATO:
        return "normalizado"
    if "segments" in dados:
        return "whisperx"
    if isinstance(dados.get("words"), list) and dados["words"] and "type" in dados["words"][0]:
        return "scribe"
    if "word_segments" in dados:
        return "whisperx"
    raise ValueError("formato de transcrição desconhecido (esperado WhisperX, Scribe ou palavras/1)")


def _interpolar(palavras: list[dict]) -> None:
    """Preenche palavras sem tempo entre as vizinhas que têm."""
    n = len(palavras)
    i = 0
    while i < n:
        if palavras[i].get("inicio") is not None and palavras[i].get("fim") is not None:
            i += 1
            continue
        j = i
        while j < n and (palavras[j].get("inicio") is None or palavras[j].get("fim") is None):
            j += 1
        antes = palavras[i - 1]["fim"] if i > 0 else (palavras[j]["inicio"] if j < n else 0.0)
        depois = palavras[j]["inicio"] if j < n else antes + 0.3 * (j - i)
        if depois < antes:
            depois = antes
        passo = (depois - antes) / (j - i)
        for k in range(i, j):
            palavras[k]["inicio"] = round(antes + passo * (k - i), 3)
            palavras[k]["fim"] = round(antes + passo * (k - i + 1), 3)
            palavras[k]["estimado"] = True
        i = j


def de_whisperx(dados: dict) -> list[dict]:
    palavras = []
    fonte = []
    if dados.get("segments"):
        for seg in dados["segments"]:
            ws = seg.get("words")
            if ws:
                for w in ws:
                    fonte.append((w, seg))
            else:  # segmento sem alinhamento: uma "palavra" por segmento, estimada
                fonte.append(({"word": seg.get("text", ""), "start": seg.get("start"), "end": seg.get("end")}, seg))
    else:
        fonte = [(w, None) for w in dados.get("word_segments", [])]
    for w, seg in fonte:
        texto = _limpo(w.get("word") or w.get("text"))
        if not texto:
            continue
        p = {"texto": texto, "inicio": w.get("start"), "fim": w.get("end"),
             "tipo": "hesitacao" if eh_hesitacao(texto) else "palavra"}
        if w.get("score") is not None:
            p["conf"] = round(float(w["score"]), 3)
        falante = w.get("speaker") or (seg or {}).get("speaker")
        if falante:
            p["falante"] = falante
        palavras.append(p)
    _interpolar(palavras)
    return palavras


def de_scribe(dados: dict) -> list[dict]:
    palavras = []
    for w in dados.get("words", []):
        tipo = w.get("type", "word")
        if tipo == "spacing":
            continue
        texto = _limpo(w.get("text"))
        if not texto:
            continue
        if tipo == "audio_event":
            t = "evento"
        else:
            t = "hesitacao" if eh_hesitacao(texto) else "palavra"
        p = {"texto": texto, "inicio": w.get("start"), "fim": w.get("end"), "tipo": t}
        if w.get("logprob") is not None:
            import math
            p["conf"] = round(math.exp(float(w["logprob"])), 3)
        if w.get("speaker_id"):
            p["falante"] = w["speaker_id"]
        palavras.append(p)
    _interpolar(palavras)
    return palavras


def normalizar(dados: dict, origem: str = "", offset: float = 0.0, idioma: str | None = None) -> dict:
    motor = detectar_motor(dados)
    if motor == "normalizado":
        out = dict(dados)
        if offset:
            out = aplicar_offset(out, offset)
        return out
    palavras = de_whisperx(dados) if motor == "whisperx" else de_scribe(dados)
    palavras.sort(key=lambda p: (p["inicio"], p["fim"]))
    for p in palavras:
        p["inicio"] = round(float(p["inicio"]) + offset, 3)
        p["fim"] = round(float(p["fim"]) + offset, 3)
        if p["fim"] < p["inicio"]:
            p["fim"] = p["inicio"]
    return {"formato": FORMATO, "motor": motor,
            "idioma": idioma or dados.get("language") or dados.get("language_code"),
            "origem": origem, "offset": offset, "palavras": palavras}


def aplicar_offset(transc: dict, offset: float) -> dict:
    out = dict(transc)
    out["offset"] = round(transc.get("offset", 0.0) + offset, 6)
    out["palavras"] = [dict(p, inicio=round(p["inicio"] + offset, 3), fim=round(p["fim"] + offset, 3))
                       for p in transc["palavras"]]
    return out


def ler(caminho) -> dict:
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("formato") != FORMATO:
        dados = normalizar(dados, origem=str(caminho))
    return dados


# --------------------------------------------------------------- frases
_FIM_FRASE = re.compile(r"[.!?…]$")


def frases(palavras: list[dict], pausa: float = 0.6, max_dur: float = 15.0) -> list[dict]:
    """Agrupa palavras em frases: quebra em pontuação final, em pausa ≥ `pausa` s ou ao passar de `max_dur`."""
    out: list[dict] = []
    atual: list[int] = []

    def fechar():
        if not atual:
            return
        ps = [palavras[i] for i in atual]
        anterior = out[-1]["fim"] if out else None
        out.append({
            "inicio": ps[0]["inicio"], "fim": ps[-1]["fim"],
            "pausa_antes": round(ps[0]["inicio"] - anterior, 3) if anterior is not None else None,
            "texto": " ".join(_texto_marcado(p) for p in ps),
            "palavras": [atual[0], atual[-1]],
            "hesitacoes": sum(1 for p in ps if p["tipo"] == "hesitacao"),
            "estimado": any(p.get("estimado") for p in ps),
        })
        atual.clear()

    for i, p in enumerate(palavras):
        if atual:
            ant = palavras[atual[-1]]
            if p["inicio"] - ant["fim"] >= pausa or p["fim"] - palavras[atual[0]]["inicio"] > max_dur:
                fechar()
        atual.append(i)
        if _FIM_FRASE.search(p["texto"]) and p["tipo"] == "palavra":
            fechar()
    fechar()
    return out


def _texto_marcado(p: dict) -> str:
    if p["tipo"] == "hesitacao":
        return f"({p['texto'].strip('()[]')})"
    if p["tipo"] == "evento":
        return f"[{p['texto'].strip('()[]')}]"
    return p["texto"]


# --------------------------------------------------------------- lacunas
def lacunas(palavras: list[dict], som: list[list[float]], minimo: float = 0.6, folga: float = 0.15) -> list[list[float]]:
    """Trechos com som (silencedetect) que nenhuma palavra cobre: takes que o motor pode ter engolido."""
    cobertos = sorted([max(0.0, p["inicio"] - folga), p["fim"] + folga] for p in palavras if p["tipo"] != "evento")
    fundidos: list[list[float]] = []
    for a, b in cobertos:
        if fundidos and a <= fundidos[-1][1]:
            fundidos[-1][1] = max(fundidos[-1][1], b)
        else:
            fundidos.append([a, b])
    out = []
    for a, b in som:
        cursor = a
        for x, y in fundidos:
            if y <= cursor or x >= b:
                continue
            if x > cursor and x - cursor >= minimo:
                out.append([round(cursor, 3), round(x, 3)])
            cursor = max(cursor, y)
        if b - cursor >= minimo:
            out.append([round(cursor, 3), round(b, 3)])
    return out


def texto_frases(transc: dict, video: str = "", lacs: list[list[float]] | None = None,
                 pausa: float = 0.6, pausa_marcar: float = 0.3) -> str:
    """O texto que o Claude lê: uma frase por linha, com tempo, pausa e lacunas no meio."""
    fs = frases(transc["palavras"], pausa=pausa)
    eventos = [("frase", f["inicio"], f) for f in fs] + [("lacuna", a, (a, b)) for a, b in (lacs or [])]
    eventos.sort(key=lambda e: e[1])
    linhas = [f"# {video or transc.get('origem', '')} · {len(fs)} frases · motor {transc.get('motor')}"
              f" · (ééé) = hesitação, [x] = evento, ~ = tempo estimado, ⟨som sem palavra⟩ = possível take engolido"]
    for tipo, _, obj in eventos:
        if tipo == "lacuna":
            a, b = obj
            linhas.append(f"{hms(a)}–{hms(b)}  ⟨som sem palavra {b - a:.1f}s⟩")
            continue
        f = obj
        pausa_txt = f"  +{f['pausa_antes']:.1f}s" if f["pausa_antes"] and f["pausa_antes"] >= pausa_marcar else ""
        est = " ~" if f["estimado"] else ""
        linhas.append(f"{hms(f['inicio'])}–{hms(f['fim'])}{pausa_txt}{est}  {f['texto']}")
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------- fala na sequência
def fala_na_sequencia(transcricoes: dict, linha, pausa: float = 0.6) -> str:
    """A fala no tempo da sequência, para planejar animações.

    `transcricoes`: id do vídeo → transcrição normalizada. `linha`: edicao.linha.Linha.
    Uma frase por linha com o timecode da sequência e o segmento; no fim de
    cada segmento, o tempo exato do corte (use-o como borda de animação que
    começa ou termina junto com o corte, não o tempo da palavra).
    """
    taxa = linha.taxa
    linhas = ["# fala no tempo da sequência · tempos da sequência · ┄ corte = tempo exato da junção"]
    for n, p in enumerate(linha.pedacos):
        transc = transcricoes.get(p.video)
        dentro = []
        if transc:
            ini, fim = taxa.segundos(p.in_f), taxa.segundos(p.out_f)
            dentro = [w for w in transc["palavras"] if ini <= w["inicio"] < fim]
        desloc = taxa.segundos(p.seq_ini) - taxa.segundos(p.in_f)
        if not dentro:
            linhas.append(f"{hms(taxa.segundos(p.seq_ini))}  {p.id}  ⟨sem fala transcrita⟩")
        for f in frases(dentro, pausa=pausa):
            est = " ~" if f["estimado"] else ""
            linhas.append(f"{hms(f['inicio'] + desloc)}  {p.id}{est}  {f['texto']}")
        if n < len(linha.pedacos) - 1:
            prox = linha.pedacos[n + 1]
            linhas.append(f"  ┄ corte {hms(taxa.segundos(p.seq_fim), 3)} (frame {p.seq_fim})  {p.id} → {prox.id}")
    linhas.append(f"  ┄ fim {hms(linha.duracao, 3)} (frame {linha.duracao_frames})")
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------- notas faladas
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", t)


def _achar(palavras: list[dict], expressao: str, a_partir: int = 0, corte: float = 0.8) -> list[tuple[int, int, float]]:
    """Ocorrências aproximadas de uma expressão (tolera erros de transcrição)."""
    alvo = _norm(expressao).split()
    n = len(alvo)
    toks = [_norm(p["texto"]) for p in palavras]
    achados = []
    i = a_partir
    while i <= len(toks) - n:
        trecho = " ".join(toks[i:i + n])
        r = difflib.SequenceMatcher(None, trecho, " ".join(alvo)).ratio()
        if r >= corte:
            achados.append((i, i + n - 1, round(r, 2)))
            i += n
        else:
            i += 1
    return achados


def notas_faladas(palavras: list[dict], abertura: str = "nota de edição",
                  fechamento: str = "fim da nota", pausa_longa: float = 1.0) -> list[dict]:
    """Acha "nota de edição … fim da nota". Sem fechamento, a nota termina na próxima pausa longa."""
    notas = []
    fechamentos = _achar(palavras, fechamento)
    usados = set()
    for ai, af, r in _achar(palavras, abertura):
        if any(ai <= u <= af for u in usados):
            continue
        fecho = next(((fi, ff, rf) for fi, ff, rf in fechamentos if fi > af and fi not in usados), None)
        prox_abertura = next((x for x, _, _ in _achar(palavras, abertura, af + 1)), None)
        if fecho and (prox_abertura is None or fecho[0] < prox_abertura):
            fim_idx, conf = fecho[1], "alta" if min(r, fecho[2]) >= 0.9 else "media"
            usados.add(fecho[0])
            texto_idx = range(af + 1, fecho[0])
        else:
            fim_idx = af
            for k in range(af + 1, len(palavras)):
                fim_idx = k
                if k + 1 < len(palavras) and palavras[k + 1]["inicio"] - palavras[k]["fim"] >= pausa_longa:
                    break
            conf = "baixa"
            texto_idx = range(af + 1, fim_idx + 1)
        notas.append({
            "inicio": palavras[ai]["inicio"], "fim": palavras[fim_idx]["fim"],
            "texto": " ".join(palavras[k]["texto"] for k in texto_idx),
            "confianca": conf, "palavras": [ai, fim_idx],
        })
    return notas


# --------------------------------------------------------------- motores
def rodar_whisperx(wav, pasta_saida, idioma: str = "pt", modelo: str = "large-v3",
                   termos: str | None = None, dispositivo: str | None = None, extra: list[str] | None = None) -> Path:
    """Chama o WhisperX pela linha de comando. Opções mudam entre versões: confira `whisperx --help`."""
    import shutil
    import subprocess

    exe = os.environ.get("WHISPERX") or shutil.which("whisperx")
    if not exe:
        raise RuntimeError("whisperx não encontrado no PATH (ou na variável WHISPERX)")
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    args = [exe, str(wav), "--model", modelo, "--language", idioma, "--output_format", "json",
            "--output_dir", str(pasta_saida)]
    if termos:
        args += ["--initial_prompt", termos]
    if dispositivo:
        args += ["--device", dispositivo]
    args += extra or []
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"whisperx falhou:\n{proc.stderr[-2000:]}")
    saida = pasta_saida / (Path(wav).stem + ".json")
    if not saida.exists():
        raise RuntimeError(f"whisperx terminou mas não achei {saida}")
    return saida


def rodar_scribe(audio, saida, idioma: str = "pt", modelo: str = "scribe_v2",
                 chave: str | None = None, eventos: bool = True, timeout: int = 900) -> Path:
    """Envia ao ElevenLabs Scribe (POST /v1/speech-to-text). Cobra por hora de áudio."""
    import urllib.request
    import uuid

    chave = chave or os.environ.get("ELEVENLABS_API_KEY")
    if not chave:
        raise RuntimeError("defina ELEVENLABS_API_KEY")
    fronteira = uuid.uuid4().hex
    campos = {"model_id": modelo, "timestamps_granularity": "word",
              "tag_audio_events": "true" if eventos else "false", "diarize": "false"}
    if idioma:
        campos["language_code"] = idioma
    corpo = bytearray()
    for k, v in campos.items():
        corpo += f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    nome = Path(audio).name.replace('"', "")
    corpo += (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}\"\r\n"
              f"Content-Type: application/octet-stream\r\n\r\n").encode()
    corpo += Path(audio).read_bytes() + f"\r\n--{fronteira}--\r\n".encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=bytes(corpo), method="POST",
                                 headers={"xi-api-key": chave,
                                          "Content-Type": f"multipart/form-data; boundary={fronteira}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dados = r.read()
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_bytes(dados)
    return saida
