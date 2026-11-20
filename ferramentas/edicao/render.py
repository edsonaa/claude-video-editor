"""Render do vídeo pelo FFmpeg, a partir do estado (sem programa de edição).

Como monta:
1. cada segmento do corte vira um pedaço de vídeo com o número exato de quadros
   (pela mesma conversão da entrega em XML, `edicao.linha`), já no formato de
   saída: inteiro, recortado (vertical a partir do horizontal, centrado no rosto
   ou num ponto escolhido) ou encaixado (tela inteira sobre um fundo desfocado);
2. a voz de cada segmento (a tratada, quando houver) vira um pedaço com o número
   exato de amostras e fades curtos nas junções;
3. os pedaços se juntam sem recodificar; por cima entram as animações (tela
   cheia e com transparência), a legenda queimada (ASS) ou a legenda animada;
4. a mixagem (voz + música + efeitos) vai ao alvo de loudness e entra no arquivo.

Rascunho (`rascunho=True`): metade da resolução e preset rápido, para revisar.
Movimentos de câmera não são aplicados (o formato deles é de cada fluxo): o
render avisa.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

from . import audio as A
from . import efeitos as EF
from . import estado as E
from . import ff
from . import legendas as L
from . import transicoes as TR
from .linha import Linha
from .tempo import Taxa

TAXA_AUDIO = 48000
FADE_JUNCAO = 0.004  # s: tira o estalo na junção sem engolir a fala


class ErroRender(E.ErroEstado):
    pass


# ------------------------------------------------------------------ formato e enquadramento
def _par(n: float) -> int:
    n = int(round(n))
    return n - (n % 2)


def tamanho(formato: str, rascunho: bool = False) -> tuple[int, int]:
    if formato not in EF.FORMATOS:
        raise ErroRender(f"formato '{formato}' desconhecido ({', '.join(EF.FORMATOS)})")
    w, h = EF.FORMATOS[formato]
    if rascunho:
        f = 540 / min(w, h)
        w, h = _par(w * f), _par(h * f)
    return w, h


def quadro_padrao(tipo_midia: str | None, src: tuple[int, int], saida: tuple[int, int]) -> dict:
    """Mesma proporção: inteiro. Câmera: recortada no centro. Tela: encaixada (não corta conteúdo)."""
    if abs(src[0] / src[1] - saida[0] / saida[1]) < 0.01:
        return {"modo": "inteiro"}
    return {"modo": "encaixar"} if tipo_midia == "tela" else {"modo": "cortar", "x": 0.5, "y": 0.5}


def filtro_quadro(src: tuple[int, int], saida: tuple[int, int], quadro: dict | None) -> str:
    """Filtro (entrada [v0], saída [vq]) que põe o quadro de origem no tamanho de saída."""
    sw, sh = src
    w, h = saida
    q = quadro or {"modo": "inteiro"}
    modo = q.get("modo", "inteiro")
    if modo == "inteiro" or abs(sw / sh - w / h) < 0.01:
        return f"[v0]scale={w}:{h}:flags=lanczos,setsar=1[vq]"
    if modo == "cortar":
        zoom = max(1.0, float(q.get("zoom", 1.0)))
        alvo = w / h
        if sw / sh > alvo:  # origem mais larga: corta as laterais
            ch = _par(sh / zoom)
            cw = _par(ch * alvo)
        else:
            cw = _par(sw / zoom)
            ch = _par(cw / alvo)
        x = min(max(0, round(float(q.get("x", 0.5)) * sw - cw / 2)), sw - cw)
        y = min(max(0, round(float(q.get("y", 0.5)) * sh - ch / 2)), sh - ch)
        return f"[v0]crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos,setsar=1[vq]"
    if modo == "encaixar":
        return (f"[v0]split[va][vb];[va]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur=24:2,eq=brightness=-0.10[fundo];[vb]scale={w}:{h}:force_original_aspect_ratio=decrease"
                f":flags=lanczos[frente];[fundo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1[vq]")
    raise ErroRender(f"modo de quadro '{modo}' desconhecido (inteiro, cortar, encaixar)")


def x_do_rosto(trilha: list[dict], ini: float, fim: float) -> float | None:
    """Centro horizontal mediano do rosto num trecho (trilha suavizada do rosto.py)."""
    xs = sorted(a["cx"] for a in trilha if a.get("cx") is not None and ini <= a["t"] <= fim)
    if not xs:
        return None
    return round(xs[len(xs) // 2], 4)


# ------------------------------------------------------------------ plano
_cache_audio: dict = {}


def _tem_audio(caminho: Path) -> bool:
    if caminho not in _cache_audio:
        _cache_audio[caminho] = any(s.get("codec_type") == "audio" for s in ff.sondar(caminho).get("streams", []))
    return _cache_audio[caminho]


def formato_do_projeto(d: dict) -> str:
    f = (d.get("video") or {}).get("formato")
    if f:
        return f
    try:
        from . import config as C
        return ((C.carregar(obrigatorio=False) or {}).get("video") or {}).get("formato") or "16:9"
    except Exception:  # noqa: BLE001
        return "16:9"


def _abs(base: Path, c):
    if not c:
        return None
    p = Path(c)
    return p if p.is_absolute() else base / p


def plano(pasta, rascunho: bool = False, de: float | None = None, ate: float | None = None,
          formato: str | None = None) -> dict:
    """Os pedaços (frames exatos), o formato e o que entra por cima, sem renderizar nada."""
    d = E.ler(pasta)
    base = E.caminho_estado(pasta).parent.parent
    midia = d.get("midia") or {}
    if not midia.get("fps"):
        raise ErroRender("o estado não tem midia.fps")
    segs = (d.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise ErroRender("o estado não tem cortes")
    taxa = Taxa.de(midia["fps"])
    linha = Linha(segs, taxa)
    formato = formato or formato_do_projeto(d)
    W, H = tamanho(formato, rascunho)
    arqs = {a["id"]: a for a in midia.get("arquivos") or []}
    brutos = {s["id"]: s for s in segs}
    f_de = taxa.frames(de) if de is not None else 0
    f_ate = min(taxa.frames(ate), linha.duracao_frames) if ate is not None else linha.duracao_frames
    if f_ate <= f_de:
        raise ErroRender("trecho vazio")
    pedacos = []
    for p in linha.pedacos:
        a, b = max(p.seq_ini, f_de), min(p.seq_fim, f_ate)
        if b <= a:
            continue
        info = arqs.get(p.video)
        if not info:
            raise ErroRender(f"{p.id}: a mídia {p.video} não está em midia.arquivos")
        src = tuple(info.get("resolucao") or (0, 0))
        if not all(src):
            st = next((s for s in ff.sondar(_abs(base, info["caminho"])).get("streams", [])
                       if s.get("codec_type") == "video"), {})
            src = (int(st.get("width", 1920)), int(st.get("height", 1080)))
        quadro = brutos[p.id].get("quadro") or quadro_padrao(info.get("tipo"), src, (W, H))
        pedacos.append({
            "id": p.id, "video": p.video, "origem": str(_abs(base, info["caminho"])),
            "voz": str(_abs(base, info["audio_tratado"])) if info.get("audio_tratado") else None,
            "in_f": p.in_f + (a - p.seq_ini), "quadros": b - a, "seq_ini_f": a - f_de, "src": list(src),
            "quadro": quadro, "tem_audio": bool(info.get("audio_tratado")) or _tem_audio(_abs(base, info["caminho"])),
        })
    t0, t1 = taxa.segundos(f_de), taxa.segundos(f_ate)
    avisos = []
    # transições: no corte entre dois pedaços vizinhos, centradas (metade de cada lado)
    transicoes = []
    total_f = f_ate - f_de
    for k in range(1, len(pedacos)):
        a, b = pedacos[k - 1], pedacos[k]
        try:
            tr = TR.normalizar(brutos[b["id"]].get("transicao"))
        except TR.ErroTransicao as e:
            avisos.append(f"{b['id']}: {e} (ficou corte seco)")
            continue
        if not tr:
            continue
        n = TR.quadros(tr, float(taxa.fps))
        corte = b["seq_ini_f"]
        ini = corte - n // 2
        if ini < 0 or ini + n > total_f:
            avisos.append(f"{b['id']}: a transição passa da borda do trecho renderizado (ficou corte seco)")
            continue
        meta = TR.carregar(tr["tipo"])
        transicoes.append({"id": b["id"], "tipo": tr["tipo"], "xfade": meta["xfade"], "quadros": n, "ini_f": ini,
                           "de": {**a, "fonte_f": a["in_f"] + a["quadros"] - n // 2},
                           "para": {**b, "fonte_f": b["in_f"] - n // 2}})
    sobre = []
    for it in (d.get("motions") or {}).get("itens") or []:
        r = (it.get("render") or {}).get("arquivo")
        if it.get("status") not in ("renderizado", "entregue") or not r:
            continue
        ini, fim = it.get("inicio_seq"), it.get("fim_seq")
        if ini is None or ini >= t1 or (fim is not None and fim <= t0):
            continue
        arq = _abs(base, r)
        st = next((s for s in ff.sondar(arq).get("streams", []) if s.get("codec_type") == "video"), {})
        mw, mh = int(st.get("width", W)), int(st.get("height", H))
        if abs(mw / mh - W / H) > 0.02:
            avisos.append(f"{it['id']}: a animação é {mw}x{mh}, não cabe no formato {formato} (ficou de fora)")
            continue
        sobre.append({"id": it["id"], "arquivo": str(arq), "ini": round(ini - t0, 6),
                      "fim": round((fim if fim is not None else t1) - t0, 6)})
    if (d.get("camera") or {}).get("movimentos"):
        avisos.append("movimentos de câmera não são aplicados por este render (o formato deles é de cada fluxo)")
    sfx = d.get("sfx") or {}
    efeitos = []
    for it in sfx.get("itens") or []:
        if not it.get("arquivo") or it.get("status") == "riscado" or it.get("inicio_seq") is None:
            continue
        if t0 <= it["inicio_seq"] < t1:
            efeitos.append({"id": it["id"], "arquivo": str(_abs(base, it["arquivo"])), "ini": it["inicio_seq"] - t0,
                            "ganho_db": it.get("ganho_db", 0), "inicio_arquivo": it.get("inicio_arquivo", 0.0),
                            "fim_arquivo": it.get("fim_arquivo")})
    musica = None
    mus = sfx.get("musica")
    if mus and mus.get("arquivo"):
        musica = {"arquivo": str(_abs(base, mus["arquivo"])), "ini": mus.get("inicio_seq", 0.0) - t0,
                  "ganho_db": mus.get("ganho_db", 0)}
    return {"projeto": d.get("projeto"), "fps": str(taxa), "formato": formato, "tamanho": [W, H],
            "rascunho": rascunho, "de": t0, "ate": t1, "quadros": f_ate - f_de, "duracao": taxa.segundos(f_ate - f_de),
            "pedacos": pedacos, "transicoes": transicoes, "sobreposicoes": sobre, "efeitos": efeitos, "musica": musica, "avisos": avisos,
            "cortes_versao": (d.get("cortes") or {}).get("versao")}


# ------------------------------------------------------------------ peças
def _rodar(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if p.returncode != 0:
        raise ErroRender("o FFmpeg falhou:\n" + p.stderr.strip()[-1500:])
    return p


def _pedaco_video(p: dict, taxa: Taxa, tam: tuple[int, int], saida: Path, rascunho: bool) -> None:
    ss = max(0.0, (p["in_f"] - 0.5) / float(taxa.fps))  # meio quadro antes: cai no quadro certo
    filtro = f"[0:v]fps={taxa.fps},setpts=PTS-STARTPTS[v0];" + filtro_quadro(tuple(p["src"]), tam, p["quadro"])
    _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{ss:.6f}", "-i", p["origem"],
            "-filter_complex", filtro, "-map", "[vq]", "-frames:v", str(p["quadros"]), "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18" if rascunho else "12", "-pix_fmt", "yuv420p",
            "-r", str(taxa.fps), "-video_track_timescale", "90000", str(saida)])


def _rotular(filtro: str, pfx: str) -> str:
    return re.sub(r"\[(\w+)\]", lambda m: f"[{pfx}{m.group(1)}]", filtro)


def _clipe_transicao(tr: dict, taxa: Taxa, tam: tuple[int, int], saida: Path, rascunho: bool) -> None:
    """Os `quadros` da transição: o fim do pedaço que sai (com a mídia além do corte) cruzando com o começo
    do que entra (com a mídia antes do corte). Sem mídia sobrando, o quadro da borda fica congelado."""
    n, fps = tr["quadros"], float(taxa.fps)
    entradas, cadeias = [], []
    for k, lado in enumerate(("de", "para")):
        p = tr[lado]
        f0 = p["fonte_f"]
        falta = max(0, -f0)               # quadros antes do começo do arquivo
        ss = max(0.0, (max(0, f0) - 0.5) / fps)
        entradas += ["-ss", f"{ss:.6f}", "-i", p["origem"]]
        pfx = "a" if k == 0 else "b"
        q = _rotular(filtro_quadro(tuple(p["src"]), tam, p["quadro"]), pfx)
        pad = f"tpad=start_mode=clone:start={falta}," if falta else ""
        cadeias.append(f"[{k}:v]fps={taxa.fps},setpts=PTS-STARTPTS[{pfx}v0];{q};[{pfx}vq]{pad}"
                       f"tpad=stop_mode=clone:stop={n},trim=end_frame={n},setpts=PTS-STARTPTS,format=yuv420p[{pfx}]")
    dur = n / fps
    filtro = ";".join(cadeias) + f";[a][b]xfade=transition={tr['xfade']}:duration={dur:.6f}:offset=0,format=yuv420p[vt]"
    _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", *entradas, "-filter_complex", filtro, "-map", "[vt]",
            "-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18" if rascunho else "12",
            "-pix_fmt", "yuv420p", "-r", str(taxa.fps), str(saida)])


def _pedaco_audio(p: dict, taxa: Taxa, n: int, saida: Path) -> None:
    fonte = p["voz"] or p["origem"]
    t = p["in_f"] / float(taxa.fps)
    dur = n / TAXA_AUDIO
    fade = min(FADE_JUNCAO, dur / 4)
    af = (f"aresample={TAXA_AUDIO},aformat=channel_layouts=mono,atrim=end_sample={n},apad=whole_len={n},"
          f"afade=t=in:d={fade:.4f},afade=t=out:st={max(0.0, dur - fade):.6f}:d={fade:.4f}")
    if not p["tem_audio"]:
        _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-f", "lavfi", "-i",
                f"anullsrc=r={TAXA_AUDIO}:cl=mono", "-af", f"atrim=end_sample={n}", "-c:a", "pcm_s24le", str(saida)])
        return
    _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{t:.6f}", "-i", fonte, "-map", "0:a:0", "-af", af,
            "-c:a", "pcm_s24le", str(saida)])


def _juntar(pecas: list[Path], saida: Path, pasta: Path) -> None:
    lista = pasta / (saida.stem + "_lista.txt")
    lista.write_text("".join(f"file '{x.name}'\n" for x in pecas), encoding="utf-8")
    _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-f", "concat", "-safe", "0", "-i", lista.name,
            "-c", "copy", saida.name], cwd=pasta)


# ------------------------------------------------------------------ legendas
def ass_do_projeto(pasta, tam: tuple[int, int], de: float, ate: float, perfil_dir=None) -> str | None:
    """O ASS das legendas atuais, no tamanho de saída e deslocado para o trecho."""
    try:
        conteudo, _ = L.ler_atual(pasta)
    except E.ErroEstado:
        return None
    d = E.ler(pasta)
    if conteudo.get("base_cortes_versao") != (d.get("cortes") or {}).get("versao"):
        raise ErroRender("as legendas foram feitas sobre outro corte: gere de novo (legendas.py gerar) antes de queimar")
    bls = []
    for b in conteudo["blocos"]:
        if b["fim"] <= de or b["inicio"] >= ate:
            continue
        nb = dict(b, inicio=max(0.0, b["inicio"] - de), fim=min(ate, b["fim"]) - de,
                  palavras=[dict(w, inicio=max(0.0, w["inicio"] - de), fim=max(0.0, w["fim"] - de))
                            for w in b["palavras"]])
        bls.append(nb)
    op = L.opcoes_legenda(d, _config(), vertical=tam[1] > tam[0])
    tema = EF.tema_de(perfil_dir=perfil_dir) if perfil_dir else EF.mesclar_tema()
    return L.ass(bls, tema, tam[0], tam[1], conteudo.get("opcoes", {}).get("modo", "frase"),
                 op["posicao"], bool(op["caixa_alta"]), estilo=op["estilo"])


def _config() -> dict:
    try:
        from . import config as C
        return C.carregar(obrigatorio=False) or {}
    except Exception:  # noqa: BLE001
        return {}


# ------------------------------------------------------------------ render
def proximo_nome(pasta_saida: Path, projeto: str, tipo: str) -> Path:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in pasta_saida.glob(f"{projeto}_{tipo}_v*.mp4"):
        m = re.search(r"_v(\d+)\.mp4$", f.name)
        if m:
            n = max(n, int(m.group(1)))
    return pasta_saida / f"{projeto}_{tipo}_v{n + 1:02d}.mp4"


def renderizar(pasta, rascunho: bool = False, de: float | None = None, ate: float | None = None,
               formato: str | None = None, legenda: str = "auto", perfil_dir=None, saida: Path | None = None,
               alvo: float = -14.0, pico: float = -1.0, progresso=print, manter: bool = False) -> dict:
    """Renderiza o projeto. `legenda`: auto (queima se o config pede ou se o formato é vertical), ass, animada, nao."""
    pl = plano(pasta, rascunho, de, ate, formato)
    d = E.ler(pasta)
    base = E.caminho_estado(pasta).parent.parent
    taxa = Taxa.de(pl["fps"])
    W, H = pl["tamanho"]
    tipo = "rascunho" if rascunho else "final"
    if saida is None:
        if rascunho:
            destino = E.caminho_estado(pasta).parent / "rascunhos"
        else:
            renders = "Renders"
            try:
                from . import config as C
                renders = ((C.carregar(obrigatorio=False) or {}).get("pastas") or {}).get("renders") or "Renders"
            except Exception:  # noqa: BLE001
                pass
            destino = base / renders
        saida = proximo_nome(destino, pl["projeto"], tipo)
    saida = Path(saida)
    avisos = list(pl["avisos"])
    # a legenda é decidida antes de tudo: legenda velha recusa o render antes de gastar tempo
    cfg_leg = L.opcoes_legenda(d, _config(), vertical=H > W)
    modo_leg = legenda
    if modo_leg == "auto":
        animada = (d.get("legendas") or {}).get("render")
        if animada and animada.get("arquivo") and cfg_leg.get("queimar"):
            modo_leg = "animada"
        elif (d.get("legendas") or {}).get("arquivo") and (cfg_leg.get("queimar") or H > W):
            modo_leg = "ass"
        else:
            modo_leg = "nao"
    texto_ass = None
    if modo_leg == "ass":
        texto_ass = ass_do_projeto(pasta, (W, H), pl["de"], pl["ate"], perfil_dir)
        if texto_ass is None:
            avisos.append("sem legendas no estado: nada para queimar")
    tmp = E.caminho_estado(pasta).parent / "render_tmp" / saida.stem
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        # 1. pedaços de vídeo e de voz, com quadros e amostras exatos
        pv, pa = [], []
        n = len(pl["pedacos"])
        for k, p in enumerate(pl["pedacos"], 1):
            progresso(f"pedaço {k}/{n} ({p['id']}, {p['quadros']} quadros, {p['quadro'].get('modo')})")
            v = tmp / f"v{k:05d}.mp4"
            _pedaco_video(p, taxa, (W, H), v, rascunho)
            pv.append(v)
            a0 = round(taxa.segundos(p["seq_ini_f"]) * TAXA_AUDIO)
            a1 = round(taxa.segundos(p["seq_ini_f"] + p["quadros"]) * TAXA_AUDIO)
            a = tmp / f"a{k:05d}.wav"
            _pedaco_audio(p, taxa, a1 - a0, a)
            pa.append(a)
        _juntar(pv, tmp / "base.mp4", tmp)
        _juntar(pa, tmp / "voz.wav", tmp)
        clipes_tr = []
        for k, tr in enumerate(pl["transicoes"], 1):
            progresso(f"transição {k}/{len(pl['transicoes'])} ({tr['id']}, {tr['tipo']}, {tr['quadros']} quadros)")
            arq = tmp / f"t{k:04d}.mp4"
            _clipe_transicao(tr, taxa, (W, H), arq, rascunho)
            clipes_tr.append((tr, arq))

        # 2. mixagem: voz + música + efeitos, e loudness no alvo
        progresso("mixagem")
        entradas = ["-i", "voz.wav"]
        cadeias = ["[0:a]aformat=channel_layouts=stereo[m0]"]
        rot = ["[m0]"]
        k = 1
        if pl["musica"]:
            mu = pl["musica"]
            atraso_ms = max(0, round(mu["ini"] * 1000))
            pular = max(0.0, -mu["ini"])
            entradas += ["-ss", f"{pular:.6f}", "-i", mu["arquivo"]] if pular else ["-i", mu["arquivo"]]
            cadeias.append(f"[{k}:a]aresample={TAXA_AUDIO},aformat=channel_layouts=stereo,volume={mu['ganho_db']}dB,"
                           f"adelay={atraso_ms}:all=1[m{k}]")
            rot.append(f"[m{k}]")
            k += 1
        for ef in pl["efeitos"]:
            entradas += ["-i", ef["arquivo"]]
            corte = f"atrim=start={ef['inicio_arquivo']}" + (f":end={ef['fim_arquivo']}" if ef.get("fim_arquivo") else "")
            cadeias.append(f"[{k}:a]{corte},asetpts=PTS-STARTPTS,aresample={TAXA_AUDIO},aformat=channel_layouts=stereo,"
                           f"volume={ef['ganho_db']}dB,adelay={round(ef['ini'] * 1000)}:all=1[m{k}]")
            rot.append(f"[m{k}]")
            k += 1
        mistura = ";".join(cadeias) + ";" + "".join(rot) + (
            f"amix=inputs={len(rot)}:normalize=0:duration=first:dropout_transition=0[mix]" if len(rot) > 1 else "anull[mix]")
        _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", *entradas, "-filter_complex", mistura, "-map", "[mix]",
                "-c:a", "pcm_f32le", "-ar", str(TAXA_AUDIO), "mix.wav"], cwd=tmp)
        norm = A.normalizar(tmp / "mix.wav", tmp / "mix_norm.wav", alvo, pico)
        if norm.get("modo") not in (None, "linear"):
            avisos.append(f"a loudness caiu para o modo dinâmico ({norm.get('modo')}): o pico não cabia no ganho linear")

        # 3. por cima: animações e legenda; e o arquivo final
        progresso("montagem final")
        entradas = ["-i", "base.mp4", "-i", "mix_norm.wav"]
        filtros = []
        atual = "[0:v]"
        k = 2
        meio = 0.5 / float(taxa.fps)
        for tr, arq in clipes_tr:
            ini = tr["ini_f"] / float(taxa.fps)
            fim = (tr["ini_f"] + tr["quadros"]) / float(taxa.fps)
            entradas += ["-i", arq.name]
            filtros.append(f"[{k}:v]setpts=PTS-STARTPTS+{ini:.6f}/TB[o{k}]")
            filtros.append(f"{atual}[o{k}]overlay=eof_action=pass:enable='between(t,{ini - meio:.6f},{fim - meio:.6f})'[c{k}]")
            atual = f"[c{k}]"
            k += 1
        for s in pl["sobreposicoes"]:
            entradas += ["-i", s["arquivo"]]
            filtros.append(f"[{k}:v]scale={W}:{H},format=yuva420p,setpts=PTS-STARTPTS+{s['ini']:.6f}/TB[o{k}]")
            filtros.append(f"{atual}[o{k}]overlay=eof_action=pass:enable='between(t,{s['ini']:.4f},{s['fim']:.4f})'[c{k}]")
            atual = f"[c{k}]"
            k += 1
        if modo_leg == "ass" and texto_ass is not None:
            (tmp / "legendas.ass").write_text(texto_ass, encoding="utf-8")
            filtros.append(f"{atual}ass=legendas.ass[cl]")
            atual = "[cl]"
        elif modo_leg == "animada":
            lr = (d.get("legendas") or {}).get("render") or {}
            entradas += ["-i", str(_abs(base, lr["arquivo"]))]
            ini = lr.get("inicio_seq", 0.0) - pl["de"]
            filtros.append(f"[{k}:v]scale={W}:{H},format=yuva420p,setpts=PTS-STARTPTS+{ini:.6f}/TB[o{k}]")
            filtros.append(f"{atual}[o{k}]overlay=eof_action=pass[cl]")
            atual = "[cl]"
            k += 1
        filtros.append(f"{atual}format=yuv420p[vf]")
        saida.parent.mkdir(parents=True, exist_ok=True)
        parcial = saida.with_name(saida.stem + ".parcial.mp4")
        _rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", *entradas, "-filter_complex", ";".join(filtros),
                "-map", "[vf]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast" if rascunho else "medium",
                "-crf", "24" if rascunho else "18", "-r", str(taxa.fps), "-c:a", "aac",
                "-b:a", "128k" if rascunho else "192k", "-movflags", "+faststart", "-frames:v", str(pl["quadros"]),
                str(parcial.resolve())], cwd=tmp)
        os.replace(parcial, saida)
    finally:
        if not manter:
            shutil.rmtree(tmp, ignore_errors=True)

    # 4. conferência e registro
    info = ff.sondar(saida)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    dur = float(info["format"]["duration"])
    if abs(dur - pl["duracao"]) > 2 / float(taxa.fps) + 0.05:
        avisos.append(f"duração {dur:.3f} s diferente da sequência {pl['duracao']:.3f} s")
    medida = A.loudness(saida)
    if abs(medida["lufs"] - alvo) > 1.0:
        avisos.append(f"loudness final {medida['lufs']:.1f} LUFS fora do alvo {alvo}")
    if medida["pico_dbtp"] > pico + 0.5:
        avisos.append(f"pico real {medida['pico_dbtp']:.1f} dBTP acima do teto {pico}")
    rel = os.path.relpath(saida, base) if Path(os.path.commonpath([saida.resolve(), base.resolve()])) == base.resolve() \
        else str(saida)
    with E.editar(pasta) as e:
        ents = e.setdefault("entregas", [])
        versao = 1 + sum(1 for x in ents if x.get("etapa") == "render" and x.get("tipo") == tipo)
        ents.append({"etapa": "render", "tipo": tipo, "arquivo": Path(rel).as_posix(), "versao": versao,
                     "data": E.agora(), "formato": pl["formato"], "de": round(pl["de"], 3), "ate": round(pl["ate"], 3),
                     "cortes_versao": pl["cortes_versao"]})
    return {"arquivo": str(saida), "tipo": tipo, "formato": pl["formato"], "tamanho": [int(vs["width"]), int(vs["height"])],
            "duracao": round(dur, 3), "duracao_sequencia": round(pl["duracao"], 3), "lufs": medida["lufs"],
            "pico_dbtp": medida["pico_dbtp"], "pedacos": len(pl["pedacos"]), "animacoes": len(pl["sobreposicoes"]),
            "efeitos": len(pl["efeitos"]), "transicoes": len(pl["transicoes"]), "musica": bool(pl["musica"]), "legenda": modo_leg, "avisos": avisos}


def resumo_plano(pl: dict) -> str:
    linhas = [f"{pl['projeto']}: {pl['formato']} {pl['tamanho'][0]}x{pl['tamanho'][1]} · {pl['fps']} fps · "
              f"{pl['duracao']:.2f} s ({pl['quadros']} quadros) · {'rascunho' if pl['rascunho'] else 'final'}"]
    for p in pl["pedacos"]:
        q = p["quadro"]
        extra = f" x={q.get('x')}" if q.get("modo") == "cortar" else ""
        linhas.append(f"  {p['id']} {p['video']} quadro {p['in_f']} +{p['quadros']} · {q.get('modo')}{extra}"
                      + (" · voz tratada" if p["voz"] else ""))
    for t in pl.get("transicoes", []):
        linhas.append(f"  transição {t['tipo']} na entrada de {t['id']} ({t['quadros']} quadros, centrada no corte)")
    for s in pl["sobreposicoes"]:
        linhas.append(f"  animação {s['id']} {s['ini']:.2f}–{s['fim']:.2f}")
    if pl["musica"]:
        linhas.append(f"  música a partir de {pl['musica']['ini']:.2f} s ({pl['musica']['ganho_db']} dB)")
    for e in pl["efeitos"]:
        linhas.append(f"  efeito {e['id']} em {e['ini']:.2f} s ({e['ganho_db']} dB)")
    linhas += [f"  ! {a}" for a in pl["avisos"]]
    return "\n".join(linhas)

