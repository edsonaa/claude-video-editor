"""Inventário da mídia: o que a etapa de preparar precisa saber de cada arquivo."""
from __future__ import annotations

from fractions import Fraction
import os
from pathlib import Path
import re

from . import ff
from .tempo import Taxa

EXT_VIDEO = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".m4v", ".mts", ".m2ts", ".webm", ".braw", ".r3d"}
EXT_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".opus"}


def _fracao(texto: str | None) -> Fraction | None:
    if not texto or texto in ("0/0", "0"):
        return None
    try:
        num, den = texto.split("/") if "/" in texto else (texto, "1")
        f = Fraction(int(num), int(den))
        return f if f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _data(fmt: dict, streams: list[dict]) -> str | None:
    for fonte in [fmt] + streams:
        tags = fonte.get("tags") or {}
        for chave in ("creation_time", "com.apple.quicktime.creationdate", "date"):
            if tags.get(chave):
                return tags[chave]
    return None


def analisar(caminho: str | os.PathLike, contar_frames: bool = False) -> dict:
    """Uma entrada de inventário, com alertas."""
    caminho = Path(caminho).resolve()
    info = {"caminho": str(caminho), "nome": caminho.name, "alertas": []}
    try:
        p = ff.sondar(caminho, contar_frames=contar_frames)
    except ff.ErroFFmpeg as e:
        info["alertas"].append(f"ilegível: {str(e).splitlines()[-1] if str(e) else 'erro'}")
        info["tipo"] = "ilegivel"
        return info

    fmt = p.get("format", {})
    streams = p.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    info["duracao"] = float(fmt.get("duration") or 0) or None
    info["gravado_em"] = _data(fmt, streams)
    info["tipo"] = "video" if videos else ("audio" if audios else "outro")

    if videos:
        v = videos[0]
        r = _fracao(v.get("r_frame_rate"))
        avg = _fracao(v.get("avg_frame_rate"))
        base = r or avg
        if base:
            taxa = Taxa.de(base)
            info["fps"] = str(taxa)
            info["fps_decimal"] = round(float(taxa), 4)
        info["resolucao"] = [v.get("width"), v.get("height")]
        info["codec_video"] = v.get("codec_name")
        info["pix_fmt"] = v.get("pix_fmt")
        rot = None
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                rot = sd["rotation"]
        if rot is None and (v.get("tags") or {}).get("rotate"):
            rot = int(v["tags"]["rotate"])
        if rot:
            info["rotacao"] = rot
        # VFR: média diferente da taxa nominal (gravação de tela, celular).
        info["vfr"] = bool(r and avg and abs(float(r) - float(avg)) / float(r) > 0.002)
        if info["vfr"]:
            info["alertas"].append(
                f"taxa de quadros variável (nominal {float(r):.3f}, média {float(avg):.3f}): "
                "sincronia e programa de edição podem se perder; considere converter para taxa constante")
        nb = v.get("nb_frames") or v.get("nb_read_packets")
        if nb and str(nb).isdigit():
            info["frames"] = int(nb)
        elif base and info["duracao"]:
            info["frames"] = Taxa.de(base).frames(info["duracao"])
        tc = (v.get("tags") or {}).get("timecode") or (fmt.get("tags") or {}).get("timecode")
        if tc:
            info["timecode_inicial"] = tc

    if audios:
        a = audios[0]
        info["canais_audio"] = sum(int(s.get("channels") or 0) for s in audios)
        info["faixas_audio"] = len(audios)
        info["taxa_audio"] = int(a.get("sample_rate") or 0) or None
        info["codec_audio"] = a.get("codec_name")
    else:
        info["canais_audio"] = 0
        if videos:
            info["alertas"].append("vídeo sem áudio: a sincronia por forma de onda não vai funcionar")
    return info


def listar(alvos: list[str], recursivo: bool = True) -> list[Path]:
    arquivos: list[Path] = []
    for alvo in alvos:
        p = Path(alvo)
        if p.is_dir():
            it = p.rglob("*") if recursivo else p.glob("*")
            arquivos += [x for x in it if x.is_file() and x.suffix.lower() in EXT_VIDEO | EXT_AUDIO
                         and not x.name.startswith(".")]
        elif p.exists():
            arquivos.append(p)
    vistos, unicos = set(), []
    for a in arquivos:
        r = a.resolve()
        if r not in vistos:
            vistos.add(r)
            unicos.append(a)
    return unicos


def _chave_ordem(item: dict):
    # Pela data de gravação; sem data, pelo nome com números em ordem natural.
    nome = [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", item["nome"])]
    return (item.get("gravado_em") is None, item.get("gravado_em") or "", nome)


def _ident(nome: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(nome).stem).strip("_") or "midia"
    return base


def para_estado(inv: dict, midia_atual: dict | None = None) -> dict:
    """Bloco `midia` do estado a partir do inventário, preservando ids e campos já decididos."""
    atual = dict(midia_atual or {})
    antigos = {a["caminho"]: a for a in atual.get("arquivos", [])}
    usados = {a["id"] for a in antigos.values()}
    arquivos = []
    for i in inv["arquivos"]:
        if i.get("tipo") == "ilegivel":
            continue
        velho = antigos.get(i["caminho"], {})
        ident = velho.get("id")
        if not ident:
            ident = base = _ident(i["nome"])
            n = 2
            while ident in usados:
                ident, n = f"{base}_{n}", n + 1
            usados.add(ident)
        novo = {"id": ident, "caminho": i["caminho"],
                "tipo": velho.get("tipo") or ("audio" if i["tipo"] == "audio" else "camera"),
                "duracao": i.get("duracao"), "canais_audio": i.get("canais_audio", 0),
                "gravado_em": i.get("gravado_em")}
        if i.get("fps"):
            novo.update(fps=i["fps"], vfr=i.get("vfr", False), resolucao=i.get("resolucao"))
        for k, v in velho.items():  # o que a pessoa ou uma etapa já decidiu fica
            if k not in novo or k in ("tipo", "proxy"):
                novo[k] = v
        arquivos.append({k: v for k, v in novo.items() if v is not None})
    atual["arquivos"] = arquivos
    cameras = [a for a in arquivos if a["tipo"] == "camera" and a.get("fps")]
    if cameras and not atual.get("principal"):
        atual["principal"] = cameras[0]["id"]
    principal = next((a for a in arquivos if a["id"] == atual.get("principal")), None)
    if principal:
        atual.setdefault("fps", principal.get("fps"))
        atual.setdefault("resolucao", principal.get("resolucao"))
    return atual


def inventario(alvos: list[str], contar_frames: bool = False) -> dict:
    itens = [analisar(a, contar_frames) for a in listar(alvos)]
    itens.sort(key=_chave_ordem)
    alertas = []
    taxas = {i["fps"] for i in itens if i.get("tipo") == "video" and i.get("fps")}
    if len(taxas) > 1:
        alertas.append(f"taxas de quadros diferentes entre os vídeos: {', '.join(sorted(taxas))}")
    for i in itens:
        for a in i["alertas"]:
            alertas.append(f"{i['nome']}: {a}")
    return {"arquivos": itens, "alertas": alertas}
