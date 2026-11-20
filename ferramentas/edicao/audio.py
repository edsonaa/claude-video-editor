"""Áudio: medir, tratar a voz e montar a música de fundo com ducking.

Tratar a voz (nesta ordem, cada passo opcional):
  1. passa-alta (tira o grave de ar-condicionado, mesa, vento)
  2. redução de ruído (afftdn), com o piso de ruído MEDIDO no próprio arquivo
  3. compressão leve (a voz oscila menos entre frases)
  4. loudness em duas passadas (loudnorm linear): mede, depois aplica o ganho exato
     até o alvo, com o teto de pico real
A saída tem a mesma duração e o mesmo início do original, para entrar na sequência
no lugar do áudio da câmera. Nunca sobrescreve: sempre um arquivo novo.

Música: a faixa é estendida (repetida) até o fim do vídeo e ganha um envelope de
volume que abaixa sob a fala (com antecipação e liberação suaves), mais fades de
entrada e saída. O resultado é um WAV pronto para a trilha de música; o nível geral
ainda pode ser ajustado no programa.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess

from . import ff

PERFIS_RUIDO = {"nenhuma": None, "leve": 6, "media": 12, "forte": 20}
PERFIS_COMPRESSAO = {
    "nenhuma": None,
    "leve": "acompressor=threshold=-20dB:ratio=2.2:attack=15:release=220:makeup=1.5:knee=6",
    "media": "acompressor=threshold=-24dB:ratio=3.2:attack=10:release=180:makeup=2.5:knee=6",
}


class ErroAudio(Exception):
    pass


def _db(v: float) -> float:
    return round(20 * math.log10(v), 1) if v > 1e-9 else -120.0


# --------------------------------------------------------------- medir
def _loudnorm_json(texto: str) -> dict:
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", texto, re.S)
    if not m:
        raise ErroAudio("o loudnorm não devolveu a medição:\n" + texto[-1500:])
    return {k: (float(v) if re.fullmatch(r"-?[\d.]+|-?inf", str(v)) else v) for k, v in json.loads(m[-1]).items()}


def _entrada(caminho, inicio, duracao) -> list[str]:
    a = []
    if inicio is not None:
        a += ["-ss", f"{inicio:.6f}"]
    a += ["-i", str(caminho)]
    if duracao is not None:
        a += ["-t", f"{duracao:.6f}"]
    return a


def loudness(caminho, inicio=None, duracao=None, filtro_antes: str | None = None) -> dict:
    """Loudness integrada (LUFS), faixa (LU), pico real (dBTP) e limiar, pelo loudnorm (EBU R128)."""
    af = (filtro_antes + "," if filtro_antes else "") + "loudnorm=I=-16:TP=-1:LRA=11:print_format=json"
    p = subprocess.run([ff.ffmpeg(), "-hide_banner", "-nostdin", *_entrada(caminho, inicio, duracao), "-vn",
                        "-af", af, "-f", "null", "-"], capture_output=True, text=True)
    if p.returncode != 0:
        raise ErroAudio(p.stderr[-1500:])
    j = _loudnorm_json(p.stderr)
    return {"lufs": j["input_i"], "lra": j["input_lra"], "pico_dbtp": j["input_tp"], "limiar": j["input_thresh"],
            "_bruto": j}


def medir(caminho, inicio=None, duracao=None, canal: int | None = None) -> dict:
    """Loudness, pico real, piso de ruído, nível da fala, relação fala/ruído, clipping e DC."""
    import numpy as np

    filtro = f"pan=mono|c0=c{canal}" if canal is not None else None
    lo = loudness(caminho, inicio, duracao, filtro)
    x = ff.ler_audio(caminho, taxa=48000, inicio=inicio, duracao=duracao, canal=canal)
    if x.size == 0:
        raise ErroAudio("áudio vazio")
    jan = 2400  # 50 ms
    n = x.size // jan
    rms = np.sqrt((x[: n * jan].reshape(n, jan).astype(np.float64) ** 2).mean(axis=1)) if n else np.array([0.0])
    rms_db = 20 * np.log10(np.maximum(rms, 1e-6))
    ativo = rms_db[rms_db > -95]  # ignora silêncio digital (pausas cortadas, começo do arquivo)
    ruido = float(np.percentile(ativo, 10)) if ativo.size else -120.0
    fala = float(np.percentile(ativo, 95)) if ativo.size else -120.0
    clip = int((np.abs(x) >= 0.989).sum())
    return {
        "lufs": lo["lufs"], "lra": lo["lra"], "pico_dbtp": lo["pico_dbtp"],
        "pico_amostra_db": _db(float(np.abs(x).max())),
        "ruido_db": round(ruido, 1), "fala_db": round(fala, 1), "snr_db": round(fala - ruido, 1),
        "clipping_amostras": clip, "clipping_pct": round(100 * clip / x.size, 4),
        "dc": round(float(x.mean()), 5), "duracao": round(x.size / 48000, 3),
    }


def recomendacoes(m: dict, alvo: float = -14.0, pico: float = -1.0) -> list[str]:
    r = []
    if m["clipping_pct"] > 0.01:
        r.append(f"clipping em {m['clipping_pct']}% das amostras: a gravação estourou; o tratamento não recupera "
                 "(regrave se for importante, ou aceite)")
    if m["ruido_db"] > -45:
        r.append(f"ruído de fundo alto ({m['ruido_db']} dBFS): redução de ruído forte; confira se a voz não fica metálica")
    elif m["ruido_db"] > -58:
        r.append(f"ruído de fundo perceptível ({m['ruido_db']} dBFS): redução de ruído média")
    if m["snr_db"] < 20:
        r.append(f"fala só {m['snr_db']} dB acima do ruído: o microfone estava longe ou o ambiente é barulhento")
    if abs(m["dc"]) > 0.01:
        r.append(f"deslocamento DC ({m['dc']}): o passa-alta resolve")
    if m["lufs"] < alvo - 10:
        r.append(f"voz muito baixa ({m['lufs']} LUFS): o ganho até {alvo} vai subir o ruído junto")
    if m["pico_dbtp"] > pico:
        r.append(f"pico real {m['pico_dbtp']} dBTP acima do teto {pico}: a normalização limita")
    return r


def ruido_auto(m: dict) -> str:
    if m["ruido_db"] > -45 or m["snr_db"] < 18:
        return "forte"
    if m["ruido_db"] > -58 or m["snr_db"] < 28:
        return "media"
    if m["ruido_db"] > -70:
        return "leve"
    return "nenhuma"


# --------------------------------------------------------------- tratar
def cadeia(m: dict, ruido: str = "auto", passa_alta: int | None = 80, compressao: str = "leve",
           canal: int | None = None) -> tuple[str, dict]:
    """Os filtros da voz (sem o loudnorm), e o que foi escolhido."""
    partes = []
    if canal is not None:
        partes.append(f"pan=mono|c0=c{canal}")
    else:
        partes.append("aformat=channel_layouts=mono")  # mistura os canais
    if passa_alta:
        partes.append(f"highpass=f={int(passa_alta)}:poles=2")
    escolha_ruido = ruido_auto(m) if ruido == "auto" else ruido
    nr = PERFIS_RUIDO.get(escolha_ruido)
    if nr:
        nf = max(-80, min(-20, round(m["ruido_db"])))
        partes.append(f"afftdn=nr={nr}:nf={nf}:tn=1")
    comp = PERFIS_COMPRESSAO.get(compressao)
    if comp:
        partes.append(comp)
    return ",".join(partes), {"ruido": escolha_ruido, "compressao": compressao, "passa_alta": passa_alta}


def tratar(entrada, saida, alvo: float = -14.0, pico: float = -1.0, ruido: str = "auto",
           passa_alta: int | None = 80, compressao: str = "leve", canal: int | None = None,
           inicio: float | None = None, duracao: float | None = None) -> dict:
    """Trata a voz e grava um WAV mono 48 kHz/24 bits com a mesma duração da entrada."""
    saida = Path(saida)
    if saida.exists():
        raise ErroAudio(f"{saida} já existe: nunca sobrescrever (use um nome com versão nova)")
    antes = medir(entrada, inicio, duracao, canal)
    filtros, escolha = cadeia(antes, ruido, passa_alta, compressao, canal)
    lra = 11
    # 1ª passada: mede depois da cadeia
    p1 = subprocess.run([ff.ffmpeg(), "-hide_banner", "-nostdin", *_entrada(entrada, inicio, duracao), "-vn", "-af",
                         f"{filtros},loudnorm=I={alvo}:TP={pico}:LRA={lra}:print_format=json", "-f", "null", "-"],
                        capture_output=True, text=True)
    if p1.returncode != 0:
        raise ErroAudio(p1.stderr[-1500:])
    m1 = _loudnorm_json(p1.stderr)
    ln = (f"loudnorm=I={alvo}:TP={pico}:LRA={lra}:measured_I={m1['input_i']}:measured_TP={m1['input_tp']}"
          f":measured_LRA={m1['input_lra']}:measured_thresh={m1['input_thresh']}:offset={m1['target_offset']}"
          ":linear=true:print_format=json")
    saida.parent.mkdir(parents=True, exist_ok=True)
    p2 = subprocess.run([ff.ffmpeg(), "-hide_banner", "-nostdin", "-y", *_entrada(entrada, inicio, duracao), "-vn",
                         "-af", f"{filtros},{ln},aresample=48000", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le",
                         str(saida)], capture_output=True, text=True)
    if p2.returncode != 0:
        raise ErroAudio(p2.stderr[-1500:])
    m2 = _loudnorm_json(p2.stderr)
    # Alguns filtros (o afftdn, por exemplo) atrasam o sinal e cortam o fim para manter a duração.
    # Mede o atraso real e compensa: a voz tratada precisa cair na mesma amostra do original.
    atraso_inicial = atraso(entrada, saida, inicio, canal)
    if atraso_inicial:
        _deslocar(saida, atraso_inicial)
    atraso_final = atraso(entrada, saida, inicio, canal)
    if atraso_final:
        raise ErroAudio(f"a voz tratada continua deslocada {atraso_final} amostras depois da compensação")
    depois = medir(saida)
    dur_in = antes["duracao"]
    return {
        "entrada": str(entrada), "saida": str(saida), "alvo": alvo, "pico": pico, "escolhas": escolha,
        "filtros": filtros, "normalizacao": m2.get("normalization_type"),
        "antes": antes, "depois": depois,
        "diferenca_duracao_ms": round((depois["duracao"] - dur_in) * 1000, 1),
        "atraso_compensado_amostras": atraso_inicial,
        "avisos": ([f"normalização caiu para o modo dinâmico ({m2.get('normalization_type')}): o pico real não "
                    "cabia no ganho linear; a voz pode soar um pouco mais comprimida"]
                   if m2.get("normalization_type") not in (None, "linear") else [])
                  + ([f"loudness final {depois['lufs']} LUFS longe do alvo {alvo}"] if abs(depois["lufs"] - alvo) > 1.0 else []),
    }


def atraso(original, tratado, inicio: float | None = None, canal: int | None = None,
           janela: float = 20.0, max_atraso: float = 0.5) -> int:
    """Atraso do tratado em relação ao original, em amostras a 48 kHz (positivo = tratado atrasado).

    Correlação cruzada num trecho de `janela` segundos com fala (o de maior energia entre alguns candidatos).
    """
    import numpy as np

    info = ff.sondar(tratado)
    dur = float(info["format"].get("duration") or 0)
    if dur <= 0:
        return 0
    j = min(janela, dur)
    melhor, energia = 0.0, -1.0
    for frac in (0.1, 0.35, 0.6):  # trechos candidatos dentro do tratado
        t0 = max(0.0, min(dur - j, dur * frac))
        y = ff.ler_audio(tratado, taxa=8000, inicio=t0, duracao=min(j, 3.0))
        e = float((y.astype(np.float64) ** 2).mean()) if y.size else 0.0
        if e > energia:
            melhor, energia = t0, e
    t0 = melhor
    a = ff.ler_audio(original, taxa=48000, inicio=(inicio or 0.0) + t0, duracao=j, canal=canal)
    b = ff.ler_audio(tratado, taxa=48000, inicio=t0, duracao=j)
    n = min(a.size, b.size)
    if n < 4800:
        return 0
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
    m = 1 << (2 * n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(b, m) * np.conj(np.fft.rfft(a, m)), m)
    lim = int(max_atraso * 48000)
    lags = np.concatenate([c[: lim + 1], c[-lim:]])
    idx = int(np.argmax(lags))
    return idx if idx <= lim else idx - (2 * lim + 1)


def _deslocar(arquivo: Path, amostras: int) -> None:
    """Desloca o áudio `amostras` para trás (positivo) ou para frente, mantendo a duração."""
    tmp = arquivo.with_suffix(".alinhando.wav")
    if amostras > 0:
        af = f"atrim=start_sample={amostras},asetpts=PTS-STARTPTS,apad=pad_len={amostras}"
    else:
        total = int(round(float(ff.sondar(arquivo)["format"]["duration"]) * 48000))
        af = f"adelay={-amostras}S:all=1,atrim=end_sample={total}"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(arquivo), "-af", af, "-c:a", "pcm_s24le", "-ar", "48000", str(tmp)])
    tmp.replace(arquivo)


# --------------------------------------------------------------- música com ducking
def intervalos_de_fala(palavras_seq: list[dict], juntar: float = 0.6) -> list[list[float]]:
    out: list[list[float]] = []
    for w in sorted(palavras_seq, key=lambda w: w["inicio"]):
        if out and w["inicio"] - out[-1][1] <= juntar:
            out[-1][1] = max(out[-1][1], w["fim"])
        else:
            out.append([w["inicio"], w["fim"]])
    return out


def envelope(duracao: float, fala: list[list[float]], ganho_livre: float, ganho_fala: float,
             ataque: float = 0.3, liberacao: float = 0.8, fade_in: float = 1.0, fade_out: float = 2.5,
             taxa_ctrl: int = 100):
    """Ganho em dB, `taxa_ctrl` pontos por segundo. Já está baixo quando a fala começa (antecipa o ataque)."""
    import numpy as np

    n = int(math.ceil(duracao * taxa_ctrl)) + 1
    t = np.arange(n) / taxa_ctrl
    alvo = np.full(n, ganho_livre, dtype=np.float64)
    for a, b in fala:
        alvo[(t >= a - ataque) & (t <= b)] = ganho_fala
    g = np.empty(n)
    g[0] = alvo[0]
    desce = (ganho_livre - ganho_fala) / max(ataque, 1e-3) / taxa_ctrl
    sobe = (ganho_livre - ganho_fala) / max(liberacao, 1e-3) / taxa_ctrl
    for i in range(1, n):
        d = alvo[i] - g[i - 1]
        g[i] = g[i - 1] + (max(d, -desce) if d < 0 else min(d, sobe))
    # fades em dB lineares no tempo (soam naturais)
    fi = np.clip(t / max(fade_in, 1e-3), 0, 1)
    fo = np.clip((duracao - t) / max(fade_out, 1e-3), 0, 1)
    fade = np.minimum(fi, fo)
    g = g + 20 * np.log10(np.maximum(fade, 1e-4))
    return t, g


def musica(arquivo_musica, saida, duracao: float, fala: list[list[float]], nivel_livre: float = -20.0,
           nivel_fala: float = -32.0, ataque: float = 0.3, liberacao: float = 0.8, fade_in: float = 1.0,
           fade_out: float = 2.5, inicio_musica: float = 0.0) -> dict:
    """WAV estéreo 48 kHz com a música do tamanho do vídeo e o ducking aplicado.

    nivel_livre / nivel_fala: loudness aproximada (LUFS) da música sem fala e sob a fala.
    """
    import numpy as np

    saida = Path(saida)
    if saida.exists():
        raise ErroAudio(f"{saida} já existe: nunca sobrescrever")
    lo = loudness(arquivo_musica, inicio_musica or None)
    p = subprocess.run([ff.ffmpeg(), "-v", "error", "-nostdin", *_entrada(arquivo_musica, inicio_musica or None, None),
                        "-vn", "-ac", "2", "-ar", "48000", "-f", "f32le", "-"], capture_output=True)
    if p.returncode != 0:
        raise ErroAudio(p.stderr.decode("utf-8", "replace")[-1500:])
    x = np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2)
    if x.shape[0] == 0:
        raise ErroAudio("música vazia")
    total = int(round(duracao * 48000))
    voltas = 0
    if x.shape[0] < total:  # repete com um crossfade curto na emenda
        cf = min(24000, x.shape[0] // 4)
        y = x.copy()
        while y.shape[0] < total:
            rampa = np.linspace(0, 1, cf, dtype=np.float32)[:, None]
            emenda = y[-cf:] * (1 - rampa) + x[:cf] * rampa
            y = np.concatenate([y[:-cf], emenda, x[cf:]])
            voltas += 1
        x = y
    x = x[:total]
    base = lo["lufs"]
    t, g = envelope(duracao, fala, nivel_livre - base, nivel_fala - base, ataque, liberacao, fade_in, fade_out)
    ts = np.arange(total) / 48000
    ganho = 10 ** (np.interp(ts, t, g) / 20)
    y = (x * ganho[:, None].astype(np.float32)).astype(np.float32)
    pico = float(np.abs(y).max())
    if pico > 0.89:  # teto de −1 dBFS
        y *= 0.89 / pico
    saida.parent.mkdir(parents=True, exist_ok=True)
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", "-",
              "-c:a", "pcm_s24le", str(saida)], entrada=y.tobytes(), texto=False)
    return {"saida": str(saida), "duracao": round(total / 48000, 3), "lufs_musica": base,
            "ganho_livre_db": round(nivel_livre - base, 1), "ganho_fala_db": round(nivel_fala - base, 1),
            "trechos_de_fala": len(fala), "repeticoes": voltas}
