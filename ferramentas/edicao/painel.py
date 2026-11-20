"""Painel de revisão: o que a interface mostra e as mudanças que ela pode fazer.

Não tem nada de HTTP aqui (isso fica em ferramentas/painel.py): são funções
sobre o estado do vídeo, testáveis sem navegador.

- `dados(pasta)`: tudo o que a interface precisa, num JSON só (segmentos com o
  tempo da origem e da sequência, transcrição marcando o que ficou no corte,
  legendas, animações, câmera, som, marcadores, pendências, etapas, alertas).
- Mudanças: ajustar/remover/restaurar trechos do corte (com desfazer), pedidos
  (pendências) com aprendizado opcional, status das animações, aprovar etapa,
  corrigir legenda. Toda gravação passa por `estado.gravar` com a revisão lida:
  se o Claude gravou no meio, a mudança é recusada (Conflito) em vez de apagar
  a dele.
- Prévias: o navegador não toca ProRes, HEVC 10 bits nem áudio PCM dentro de
  MOV. Para essas mídias (e para ouvir a voz tratada), o painel gera uma prévia
  leve em _CLAUDE/painel/ (H.264 + AAC; animações com transparência em WebM VP9).
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading

from . import efeitos as EF
from . import estado as E
from . import ff
from . import legendas as L
from . import transcricao as T
from .linha import Linha
from .tempo import Taxa

PASTA = "painel"
HISTORICO_MAX = 50
FOLGA_CORTE = 0.12      # respiro mantido em cada lado de um trecho cortado pelo roteiro
FOLGA_INCLUIR = 0.12    # respiro antes de um trecho restaurado
FOLGA_INCLUIR_FIM = 0.15
JUNTAR_ATE = 2.0        # trecho restaurado se junta ao vizinho se entre eles só houver silêncio até isto

VIDEO_NAVEGADOR = {"h264", "vp8", "vp9", "av1"}
AUDIO_NAVEGADOR = {"aac", "mp3", "opus", "vorbis", "flac"}
PCM_WAV = {"pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_u8"}
PIXEL_NAVEGADOR = {"yuv420p", "yuvj420p", "yuva420p", None}
CONTEINER_VIDEO = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}


class ErroPainel(E.ErroEstado):
    pass


# ------------------------------------------------------------------ caminhos
def raiz(pasta) -> Path:
    return E.caminho_estado(pasta).parent.parent


def pasta_painel(pasta) -> Path:
    p = E.caminho_estado(pasta).parent / PASTA
    p.mkdir(parents=True, exist_ok=True)
    return p


def _abs(base: Path, c: str | None) -> Path | None:
    if not c:
        return None
    p = Path(c)
    return p if p.is_absolute() else base / p


def _taxa(d: dict) -> Taxa | None:
    fps = (d.get("midia") or {}).get("fps")
    return Taxa.de(fps) if fps else None


def _transcricoes(d: dict, base: Path) -> dict:
    out = {}
    for vid, c in ((d.get("transcricao") or {}).get("palavras") or {}).items():
        arq = _abs(base, c)
        if arq and arq.exists():
            out[vid] = T.ler(arq)
    return out


# ------------------------------------------------------------------ o navegador toca?
_cache_sonda: dict = {}


def _assinatura(*caminhos: Path | None) -> list:
    out = []
    for c in caminhos:
        if c is None:
            out.append(None)
            continue
        try:
            st = Path(c).stat()
            out.append([str(c), st.st_mtime_ns, st.st_size])
        except OSError:
            out.append([str(c), None, None])
    return out


def tocavel(caminho: Path) -> tuple[bool, str]:
    """O navegador (Chrome, Edge, Firefox) toca este arquivo como ele está?"""
    caminho = Path(caminho)
    if not caminho.exists():
        return False, "o arquivo não existe"
    chave = json.dumps(_assinatura(caminho))
    if chave in _cache_sonda:
        return _cache_sonda[chave]
    try:
        info = ff.sondar(caminho)
    except Exception as e:  # noqa: BLE001 (arquivo que nem o ffprobe abre)
        r = (False, f"não deu para ler ({e})")
        _cache_sonda[chave] = r
        return r
    sts = info.get("streams", [])
    v = [s for s in sts if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    a = [s for s in sts if s.get("codec_type") == "audio"]
    suf = caminho.suffix.lower()
    r = (True, "")
    if v:
        if suf not in CONTEINER_VIDEO:
            r = (False, f"contêiner {suf}")
        elif v[0].get("codec_name") not in VIDEO_NAVEGADOR:
            r = (False, f"vídeo em {v[0].get('codec_name')}")
        elif v[0].get("pix_fmt") not in PIXEL_NAVEGADOR:
            r = (False, f"vídeo em {v[0].get('pix_fmt')}")
    if r[0] and a:
        cod = a[0].get("codec_name")
        if not (cod in AUDIO_NAVEGADOR or (suf == ".wav" and cod in PCM_WAV)):
            r = (False, f"áudio em {cod}")
    _cache_sonda[chave] = r
    return r


# ------------------------------------------------------------------ fontes e prévias
def _manifesto(pasta) -> dict:
    arq = pasta_painel(pasta) / "previas.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_manifesto(pasta, m: dict) -> None:
    arq = pasta_painel(pasta) / "previas.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, arq)


def fontes(d: dict, base: Path) -> dict:
    """chave → de onde vem cada mídia que o painel pode tocar."""
    out = {}
    usados = {s["video"] for s in (d.get("cortes") or {}).get("segmentos") or []}
    for a in (d.get("midia") or {}).get("arquivos") or []:
        if a.get("tipo") == "audio" and a["id"] not in usados:
            continue
        out[f"v:{a['id']}"] = {"tipo": "video", "origem": _abs(base, a["caminho"]),
                               "proxy": _abs(base, a.get("proxy")), "voz": _abs(base, a.get("audio_tratado")),
                               "usado": a["id"] in usados}
    for it in (d.get("motions") or {}).get("itens") or []:
        arq = (it.get("render") or {}).get("arquivo")
        if arq:
            out[f"mo:{it['id']}"] = {"tipo": "motion", "origem": _abs(base, arq),
                                     "alpha": it.get("formato") != "tela_cheia", "usado": True}
    sfx = d.get("sfx") or {}
    for it in sfx.get("itens") or []:
        if it.get("arquivo"):
            out[f"sfx:{it['id']}"] = {"tipo": "audio", "origem": _abs(base, it["arquivo"]), "usado": True}
    if (sfx.get("musica") or {}).get("arquivo"):
        out["musica"] = {"tipo": "audio", "origem": _abs(base, sfx["musica"]["arquivo"]), "usado": True}
    return out


def _destino_previa(pasta, chave: str, f: dict) -> Path:
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", chave.replace(":", "_"))
    ext = ".webm" if f["tipo"] == "motion" and f.get("alpha") else ".mp4"
    return pasta_painel(pasta) / f"previa_{nome}{ext}"


def previa_valida(pasta, chave: str, f: dict, manifesto: dict | None = None) -> Path | None:
    m = (manifesto if manifesto is not None else _manifesto(pasta)).get(chave)
    if not m:
        return None
    arq = Path(m["arquivo"])
    if not arq.exists() or m.get("assinatura") != _assinatura(f["origem"], f.get("voz")):
        return None
    return arq


def resolver(pasta, chave: str, f: dict, manifesto: dict | None = None) -> dict:
    """Qual arquivo o navegador vai tocar para esta chave, e se falta prévia."""
    pv = previa_valida(pasta, chave, f, manifesto)
    if pv:
        return {"arquivo": pv, "fonte": "previa", "precisa_previa": False, "motivo": "", "aviso": ""}
    origem = f["origem"]
    if f["tipo"] == "video":
        aviso = "a prévia ainda não tem a voz tratada" if f.get("voz") and Path(f["voz"]).exists() else ""
        if f.get("proxy") and tocavel(f["proxy"])[0]:
            return {"arquivo": f["proxy"], "fonte": "proxy", "precisa_previa": bool(aviso), "motivo": "", "aviso": aviso}
        ok, motivo = tocavel(origem)
        if ok:
            return {"arquivo": origem, "fonte": "original", "precisa_previa": bool(aviso), "motivo": "", "aviso": aviso}
        return {"arquivo": None, "fonte": None, "precisa_previa": origem.exists(), "motivo": motivo, "aviso": aviso}
    ok, motivo = tocavel(origem)
    if ok:
        return {"arquivo": origem, "fonte": "original", "precisa_previa": False, "motivo": "", "aviso": ""}
    return {"arquivo": None, "fonte": None, "precisa_previa": origem.exists() and f["tipo"] == "motion",
            "motivo": motivo, "aviso": ""}


def arquivo(pasta, chave: str) -> Path | None:
    """O arquivo que o servidor entrega para /arquivo/<chave> (só o que o estado cita)."""
    d = E.ler(pasta)
    f = fontes(d, raiz(pasta)).get(chave)
    if not f:
        return None
    return resolver(pasta, chave, f)["arquivo"]


def tarefas_previa(pasta, todas: bool = False) -> list[dict]:
    """O que precisa de prévia (ou, com todas=True, tudo o que dá para converter)."""
    d = E.ler(pasta)
    man = _manifesto(pasta)
    out = []
    for chave, f in fontes(d, raiz(pasta)).items():
        if f["tipo"] == "audio" or not f.get("usado") or not f["origem"].exists():
            continue
        r = resolver(pasta, chave, f, man)
        if r["fonte"] == "previa":
            continue
        if r["precisa_previa"] or todas:
            out.append({"chave": chave, "origem": str(f["origem"]), "voz": str(f["voz"]) if f.get("voz") else None,
                        "destino": str(_destino_previa(pasta, chave, f)), "tipo": f["tipo"],
                        "alpha": bool(f.get("alpha")), "motivo": r["motivo"] or r["aviso"] or "leveza"})
    return out


def _cmd_previa(t: dict) -> list[str]:
    tmp = t["destino"] + ".parcial" + Path(t["destino"]).suffix
    escala = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'"
    cmd = [ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-i", t["origem"]]
    if t["tipo"] == "video":
        info = ff.sondar(t["origem"])
        v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        try:
            fps = float(Taxa.de(v.get("avg_frame_rate") or v.get("r_frame_rate") or 30))
        except Exception:  # noqa: BLE001
            fps = 30.0
        g = str(max(1, round(fps / 2)))
        if t.get("voz") and Path(t["voz"]).exists():
            cmd += ["-i", t["voz"], "-map", "0:v:0", "-map", "1:a:0"]
        else:
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
        cmd += ["-vf", escala, "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                "-g", g, "-keyint_min", g, "-sc_threshold", "0", "-c:a", "aac", "-b:a", "128k", "-ac", "2",
                "-ar", "48000", "-movflags", "+faststart"]
    elif t.get("alpha"):
        cmd += ["-map", "0:v:0", "-vf", escala + ",format=yuva420p", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", "34", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1",
                "-auto-alt-ref", "0", "-an"]
    else:
        cmd += ["-map", "0:v:0", "-vf", escala, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart"]
    return cmd + ["-progress", "pipe:1", "-nostats", tmp]


def gerar_previa(pasta, t: dict, progresso=None) -> Path:
    """Gera uma prévia (arquivo parcial + rename) e a registra no manifesto."""
    try:
        dur = float(ff.sondar(t["origem"]).get("format", {}).get("duration") or 0)
    except Exception:  # noqa: BLE001
        dur = 0.0
    cmd = _cmd_previa(t)
    tmp = cmd[-1]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace")
    for linha in p.stdout:
        if progresso and dur and linha.startswith("out_time_us="):
            try:
                progresso(min(1.0, int(linha.split("=")[1]) / 1e6 / dur))
            except ValueError:
                pass
    erro = p.stderr.read()
    if p.wait() != 0:
        Path(tmp).unlink(missing_ok=True)
        raise ErroPainel(f"a prévia de {t['chave']} falhou: {erro.strip()[-400:]}")
    os.replace(tmp, t["destino"])
    man = _manifesto(pasta)
    man[t["chave"]] = {"arquivo": t["destino"], "assinatura": _assinatura(Path(t["origem"]),
                                                                          Path(t["voz"]) if t.get("voz") else None),
                       "gerada_em": E.agora()}
    _gravar_manifesto(pasta, man)
    if progresso:
        progresso(1.0)
    return Path(t["destino"])


class Fila:
    """Gera as prévias numa thread, uma por vez, com progresso consultável."""

    def __init__(self, pasta):
        self.pasta = pasta
        self._trava = threading.Lock()
        self.itens: list[dict] = []
        self._thread: threading.Thread | None = None

    def estado(self) -> dict:
        with self._trava:
            return {"rodando": bool(self._thread and self._thread.is_alive()),
                    "itens": [dict(i) for i in self.itens]}

    def iniciar(self, todas: bool = False) -> dict:
        with self._trava:
            if self._thread and self._thread.is_alive():
                return {"rodando": True, "itens": [dict(i) for i in self.itens]}
            self.itens = [{"chave": t["chave"], "motivo": t["motivo"], "progresso": 0.0, "status": "na_fila",
                           "erro": None, "_t": t} for t in tarefas_previa(self.pasta, todas)]
            self._thread = threading.Thread(target=self._rodar, daemon=True)
            self._thread.start()
        return self.estado()

    def _rodar(self):
        for item in self.itens:
            item["status"] = "gerando"

            def prog(x, item=item):
                item["progresso"] = round(x, 3)
            try:
                gerar_previa(self.pasta, item["_t"], prog)
                item["status"] = "pronta"
            except Exception as e:  # noqa: BLE001 (a fila segue com as outras)
                item["status"] = "falhou"
                item["erro"] = str(e)


def miniatura(pasta, video: str, t: float, largura: int = 192) -> Path:
    """Um quadro do vídeo de origem (cache em _CLAUDE/painel/miniaturas)."""
    d = E.ler(pasta)
    f = fontes(d, raiz(pasta)).get(f"v:{video}")
    if not f or not f["origem"].exists():
        raise ErroPainel(f"a mídia {video} não está no estado")
    taxa = _taxa(d) or Taxa.de(30)
    quadro = taxa.frames(max(0.0, t))
    dest = pasta_painel(pasta) / "miniaturas" / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', video)}_{quadro}_{largura}.jpg"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".parcial.jpg")
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{taxa.segundos(quadro):.4f}",
              "-i", str(f["origem"]), "-frames:v", "1", "-vf", f"scale={largura}:-2", "-q:v", "5", str(tmp)])
    os.replace(tmp, dest)
    return dest


# ------------------------------------------------------------------ o que a interface mostra
def _tema(d: dict) -> dict:
    try:
        from . import config as C
        cfg = C.carregar(obrigatorio=False) or {}
        perfil = d.get("perfil") or cfg.get("perfil_padrao")
        t = EF.tema_de(perfil_dir=C.pasta() / "perfis" / perfil) if perfil else EF.mesclar_tema()
    except Exception:  # noqa: BLE001 (sem config, o tema neutro)
        cfg = {}
        t = EF.mesclar_tema()
    return {"cores": t["cores"], "fontes": t["fontes"], "legendas": {**L_PADRAO, **(cfg.get("legendas") or {})},
            "formato": (cfg.get("video") or {}).get("formato")}


L_PADRAO = {"modo": "frase", "posicao": "baixo", "caixa_alta": False}


def _seq_de(linha: Linha | None, video: str, t: float) -> tuple[float | None, bool]:
    if not linha:
        return None, False
    seq, _p, dentro = linha.origem_para_seq_proximo(video, t)
    return round(seq, 3), dentro


def dados(pasta) -> dict:
    """Tudo o que a interface precisa, a partir do estado (e dos arquivos que ele cita)."""
    d = E.ler(pasta)
    base = raiz(pasta)
    midia = d.get("midia") or {}
    taxa = _taxa(d)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    linha = Linha(segs, taxa) if segs and taxa else None
    man = _manifesto(pasta)
    arqs = {a["id"]: a for a in midia.get("arquivos") or []}

    out: dict = {
        "projeto": d.get("projeto"), "revisao": d.get("revisao"), "fps": str(taxa) if taxa else None,
        "fps_num": float(taxa) if taxa else None, "fluxo": d.get("fluxo", []), "etapas": d.get("etapas", {}),
        "proxima": E.proxima_etapa(d), "alertas": E.alertas(d), "aprendizados": E.contar_aprendizados(pasta),
        "cortes_versao": (d.get("cortes") or {}).get("versao"),
        "resolucao": midia.get("resolucao") or (arqs.get(midia.get("principal") or "") or {}).get("resolucao"),
        "desfazer": len(_historico(pasta)),
        "formato": (d.get("video") or {}).get("formato"),
        "origem_curto": (d.get("video") or {}).get("origem"),
    }
    if not out["resolucao"] and segs:
        out["resolucao"] = (arqs.get(segs[0]["video"]) or {}).get("resolucao")
    out["tema"] = _tema(d)

    # mídias
    fts = fontes(d, base)
    midias = {}
    for chave, f in fts.items():
        r = resolver(pasta, chave, f, man)
        midias[chave] = {"url": f"/arquivo/{chave}" if r["arquivo"] else None, "fonte": r["fonte"],
                         "precisa_previa": r["precisa_previa"], "motivo": r["motivo"], "aviso": r["aviso"],
                         "tipo": f["tipo"], "usado": f.get("usado", False)}
        if chave.startswith("v:"):
            a = arqs.get(chave[2:], {})
            midias[chave].update({"id": chave[2:], "duracao": a.get("duracao"), "resolucao": a.get("resolucao"),
                                  "nome": Path(a.get("caminho", chave)).name, "tipo_midia": a.get("tipo")})
    out["midias"] = midias
    out["previas_faltando"] = sum(1 for m in midias.values() if m["precisa_previa"] and m["usado"])

    # segmentos (tempos quantizados, como na entrega) + tempos gravados
    if linha:
        brutos = {s["id"]: s for s in segs}
        out["segmentos"] = [{"id": p.id, "video": p.video, "in": taxa.segundos(p.in_f), "out": taxa.segundos(p.out_f),
                             "seq_ini": taxa.segundos(p.seq_ini), "seq_fim": taxa.segundos(p.seq_fim),
                             "in_f": p.in_f, "out_f": p.out_f, "texto": brutos[p.id].get("texto", ""),
                             "quadro": brutos[p.id].get("quadro")}
                            for p in linha.pedacos]
        out["duracao"] = linha.duracao
    else:
        out["segmentos"], out["duracao"] = [], 0.0

    # transcrição (roteiro): cada palavra com o que ficou no corte
    roteiro = {}
    for vid, t in _transcricoes(d, base).items():
        janelas = [(p.in_f, p.out_f) for p in (linha.pedacos if linha else []) if p.video == vid]
        ps = []
        for i, w in enumerate(t["palavras"]):
            if w.get("tipo") == "evento":
                continue
            meio = taxa.frames((w["inicio"] + w["fim"]) / 2) if taxa else 0
            dentro = any(a <= meio < b for a, b in janelas)
            ps.append([w["texto"], w["inicio"], w["fim"], 1 if dentro else 0, 1 if w.get("tipo") == "hesitacao" else 0, i])
        roteiro[vid] = ps
    out["roteiro"] = roteiro

    # legendas
    leg = None
    if (d.get("legendas") or {}).get("arquivo"):
        try:
            conteudo, arq = L.ler_atual(pasta)
            bls = conteudo["blocos"]
            leg = {"versao": conteudo.get("versao"), "arquivo": arq.name,
                   "desatualizada": conteudo.get("base_cortes_versao") != out["cortes_versao"],
                   "opcoes": conteudo.get("opcoes", {}),
                   "avisos": L.avisos(bls, max_car=conteudo.get("opcoes", {}).get("max_caracteres", 42)),
                   "blocos": [{"id": b["id"], "i": b["inicio"], "f": b["fim"], "linhas": b["linhas"],
                               "p": [[w["texto"], w["inicio"], w["fim"]] for w in b["palavras"]]} for b in bls]}
        except (OSError, ValueError, E.ErroEstado) as e:
            leg = {"erro": str(e), "blocos": []}
    out["legendas"] = leg

    # animações, câmera, som
    out["motions"] = [{"id": it["id"], "status": it.get("status"), "inicio_seq": it.get("inicio_seq"),
                       "fim_seq": it.get("fim_seq"), "formato": it.get("formato"), "ideia": it.get("ideia", ""),
                       "efeito": it.get("efeito"), "chave": f"mo:{it['id']}" if f"mo:{it['id']}" in fts else None}
                      for it in (d.get("motions") or {}).get("itens") or []]
    out["camera"] = [{k: v for k, v in it.items() if not isinstance(v, (list, dict)) or k in ("keyframes",)}
                     for it in (d.get("camera") or {}).get("movimentos") or []]
    sfx = d.get("sfx") or {}
    out["sfx"] = [{"id": it["id"], "inicio_seq": it.get("inicio_seq"), "ganho_db": it.get("ganho_db", 0),
                   "status": it.get("status"), "nome": Path(it.get("arquivo") or it["id"]).stem,
                   "evento": it.get("evento") or it.get("motivo") or "", "chave": f"sfx:{it['id']}"}
                  for it in sfx.get("itens") or [] if it.get("inicio_seq") is not None]
    mus = sfx.get("musica")
    out["musica"] = ({"inicio_seq": mus.get("inicio_seq", 0.0), "duracao": mus.get("duracao"),
                      "ganho_db": mus.get("ganho_db", 0), "chave": "musica"} if mus and mus.get("arquivo") else None)

    # marcadores, notas faladas e pedidos, todos com o tempo da sequência
    out["marcadores"] = []
    for m in d.get("marcadores") or []:
        seq, dentro = _seq_de(linha, m["video"], m["tempo"])
        out["marcadores"].append({**m, "seq": seq, "dentro": dentro})
    for n in d.get("notas_edicao") or []:
        seq, dentro = _seq_de(linha, n["video"], n["inicio"])
        out["marcadores"].append({"id": n["id"], "tipo": "nota_falada", "texto": n["texto"], "seq": seq,
                                  "dentro": dentro, "etapa": n.get("etapa")})
    pend = []
    for p in d.get("pendencias") or []:
        q = dict(p)
        if p.get("video") and p.get("tempo") is not None:
            q["seq"], q["dentro"] = _seq_de(linha, p["video"], p["tempo"])
        pend.append(q)
    out["pendencias"] = pend
    return out


# ------------------------------------------------------------------ cortes
def _historico(pasta) -> list:
    arq = E.caminho_estado(pasta).parent / PASTA / "historico_cortes.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _gravar_historico(pasta, h: list) -> None:
    arq = pasta_painel(pasta) / "historico_cortes.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(h[-HISTORICO_MAX:], ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, arq)


def texto_do_trecho(palavras: list[dict], ini: float, fim: float) -> str:
    return " ".join(w["texto"] for w in palavras
                    if w.get("tipo") != "evento" and ini <= (w["inicio"] + w["fim"]) / 2 < fim)


def _validar_segmentos(segs: list[dict], taxa: Taxa, duracoes: dict) -> None:
    vistos = set()
    for s in segs:
        if s["id"] in vistos:
            raise ErroPainel(f"id repetido nos cortes: {s['id']}")
        vistos.add(s["id"])
        if taxa.frames(s["fim"]) - taxa.frames(s["inicio"]) < 1:
            raise ErroPainel(f"{s['id']} ficaria com menos de um quadro")
        if s["inicio"] < 0:
            raise ErroPainel(f"{s['id']} começaria antes do início do arquivo")
        dur = duracoes.get(s["video"])
        if dur and s["fim"] > dur + 1e-6:
            raise ErroPainel(f"{s['id']} passaria do fim do arquivo {s['video']} ({dur:.2f} s)")


def gravar_cortes(pasta, novos: list[dict], revisao: int | None, motivo: str) -> dict:
    """Grava uma lista de segmentos nova (com o texto refeito) e guarda a anterior para desfazer."""
    d = E.ler(pasta)
    if revisao is not None and d.get("revisao") != revisao:
        raise E.Conflito("o estado mudou enquanto você revisava (o Claude gravou algo); a tela foi atualizada, "
                         "refaça a mudança")
    taxa = _taxa(d)
    if not taxa:
        raise ErroPainel("o estado não tem midia.fps")
    duracoes = {a["id"]: a.get("duracao") for a in (d.get("midia") or {}).get("arquivos") or []}
    _validar_segmentos(novos, taxa, duracoes)
    transcs = _transcricoes(d, raiz(pasta))
    velhos = {s["id"]: s for s in (d.get("cortes") or {}).get("segmentos") or []}
    for s in novos:
        v = velhos.get(s["id"])
        mudou = not v or (v["inicio"], v["fim"], v["video"]) != (s["inicio"], s["fim"], s["video"])
        if (mudou or "texto" not in s) and s["video"] in transcs:
            s["texto"] = texto_do_trecho(transcs[s["video"]]["palavras"], s["inicio"], s["fim"])
    antes = copy.deepcopy((d.get("cortes") or {}))
    d.setdefault("cortes", {})["segmentos"] = novos
    gravado = E.gravar(pasta, d, revisao_lida=d.get("revisao"))
    h = _historico(pasta)
    h.append({"segmentos": antes.get("segmentos", []), "versao_antes": antes.get("versao"),
              "versao_depois": gravado["cortes"]["versao"], "motivo": motivo, "em": E.agora()})
    _gravar_historico(pasta, h)
    return gravado


def _q(taxa: Taxa, t: float) -> float:
    return round(taxa.segundos(taxa.frames(t)), 6)


def _por_fora(taxa: Taxa, ini: float, fim: float) -> tuple[float, float]:
    """Quantiza um trecho para fora (início para baixo, fim para cima): cobre as palavras inteiras."""
    fps = float(taxa.fps)
    a = math.floor(ini * fps + 1e-6)
    b = math.ceil(fim * fps - 1e-6)
    return round(taxa.segundos(max(0, a)), 6), round(taxa.segundos(b), 6)


def ajustar_segmento(segs: list[dict], sid: str, taxa: Taxa, inicio: float | None = None,
                     fim: float | None = None, duracao: float | None = None) -> list[dict]:
    out = copy.deepcopy(segs)
    s = next((x for x in out if x["id"] == sid), None)
    if not s:
        raise ErroPainel(f"segmento {sid} não encontrado")
    if inicio is not None:
        s["inicio"] = _q(taxa, max(0.0, inicio))
    if fim is not None:
        f = _q(taxa, fim)
        s["fim"] = min(f, duracao) if duracao else f
    if taxa.frames(s["fim"]) - taxa.frames(s["inicio"]) < 1:
        raise ErroPainel(f"{sid}: o fim precisa ficar depois do início")
    return out


def remover_trecho(segs: list[dict], video: str, ini: float, fim: float, taxa: Taxa) -> list[dict]:
    """Tira [ini, fim) do arquivo `video` de todos os segmentos (apara, divide ou apaga)."""
    if fim <= ini:
        raise ErroPainel("trecho vazio")
    ini, fim = _por_fora(taxa, ini, fim)
    um = taxa.segundos(1)
    out: list[dict] = []
    todos = list(segs)
    for s in segs:
        if s["video"] != video or s["fim"] <= ini or s["inicio"] >= fim:
            out.append(dict(s))
            continue
        partes = []
        if ini - s["inicio"] >= um:
            partes.append({**s, "fim": ini})
        if s["fim"] - fim >= um:
            novo = {**s, "inicio": fim}
            if partes:
                novo["id"] = E.proximo_id(todos + out + partes, "s")
                todos.append(novo)
            partes.append(novo)
        out.extend(partes)
    if out == [dict(s) for s in segs]:
        raise ErroPainel("esse trecho já está fora do corte")
    return out


def restaurar_trecho(segs: list[dict], video: str, ini: float, fim: float, taxa: Taxa,
                     palavras: list[dict] | None = None) -> list[dict]:
    """Devolve [ini, fim) do arquivo `video` ao corte.

    Junta com o segmento vizinho do mesmo arquivo quando entre eles só há
    silêncio (até JUNTAR_ATE segundos); senão entra como segmento novo, na
    posição que a ordem do arquivo indica.
    """
    if fim <= ini:
        raise ErroPainel("trecho vazio")
    ini, fim = _por_fora(taxa, ini, fim)
    out = copy.deepcopy(segs)

    def so_silencio(a: float, b: float) -> bool:
        if b - a > JUNTAR_ATE:
            return False
        return not any(a < (w["inicio"] + w["fim"]) / 2 < b for w in palavras or [] if w.get("tipo") != "evento")

    vizinhos = [i for i, s in enumerate(out) if s["video"] == video and
                (s["inicio"] <= fim and s["fim"] >= ini or
                 (s["fim"] < ini and so_silencio(s["fim"], ini)) or
                 (s["inicio"] > fim and so_silencio(fim, s["inicio"])))]
    if vizinhos:
        if vizinhos != list(range(vizinhos[0], vizinhos[-1] + 1)):
            raise ErroPainel("o trecho encosta em segmentos que estão fora de ordem no corte; peça pelo chat")
        alvo = out[vizinhos[0]]
        novo_ini = min([ini] + [out[i]["inicio"] for i in vizinhos])
        novo_fim = max([fim] + [out[i]["fim"] for i in vizinhos])
        if (novo_ini, novo_fim) == (alvo["inicio"], alvo["fim"]) and len(vizinhos) == 1:
            raise ErroPainel("esse trecho já está no corte")
        alvo["inicio"], alvo["fim"] = novo_ini, novo_fim
        for i in reversed(vizinhos[1:]):
            del out[i]
        return out
    novo = {"id": E.proximo_id(out, "s"), "video": video, "inicio": ini, "fim": fim}
    antes = [i for i, s in enumerate(out) if s["video"] == video and s["inicio"] < ini]
    depois = [i for i, s in enumerate(out) if s["video"] == video and s["inicio"] > ini]
    pos = antes[-1] + 1 if antes else (depois[0] if depois else len(out))
    out.insert(pos, novo)
    return out


def trecho_das_palavras(palavras: list[dict], i: int, j: int, acao: str) -> tuple[float, float]:
    """O trecho do arquivo para cortar ou restaurar as palavras i..j (índices da transcrição)."""
    ws = palavras
    if not (0 <= i <= j < len(ws)):
        raise ErroPainel("seleção fora da transcrição")
    reais = [k for k in range(len(ws)) if ws[k].get("tipo") != "evento"]
    ant = max((k for k in reais if k < i), default=None)
    prox = min((k for k in reais if k > j), default=None)
    a, b = ws[i]["inicio"], ws[j]["fim"]
    if acao == "cortar":
        ini = ws[ant]["fim"] + min(FOLGA_CORTE, max(0.0, a - ws[ant]["fim"]) / 2) if ant is not None else max(0.0, a - 0.1)
        fim = ws[prox]["inicio"] - min(FOLGA_CORTE, max(0.0, ws[prox]["inicio"] - b) / 2) if prox is not None else b + 0.1
    else:
        ini = a - min(FOLGA_INCLUIR, max(0.0, a - ws[ant]["fim"]) / 2) if ant is not None else max(0.0, a - FOLGA_INCLUIR)
        fim = b + min(FOLGA_INCLUIR_FIM, max(0.0, ws[prox]["inicio"] - b) / 2) if prox is not None else b + FOLGA_INCLUIR_FIM
    return max(0.0, ini), max(ini, fim)


def editar_cortes(pasta, revisao: int | None, acao: str, **kw) -> dict:
    """Uma mudança no corte vinda do painel. Devolve o estado gravado."""
    d = E.ler(pasta)
    taxa = _taxa(d)
    if not taxa:
        raise ErroPainel("o estado não tem midia.fps")
    segs = (d.get("cortes") or {}).get("segmentos") or []
    duracoes = {a["id"]: a.get("duracao") for a in (d.get("midia") or {}).get("arquivos") or []}
    if acao == "ajustar":
        s = next((x for x in segs if x["id"] == kw["id"]), None)
        if not s:
            raise ErroPainel(f"segmento {kw['id']} não encontrado")
        novos = ajustar_segmento(segs, kw["id"], taxa, kw.get("inicio"), kw.get("fim"), duracoes.get(s["video"]))
        motivo = f"ajuste de {kw['id']}"
    elif acao == "remover_segmento":
        if not any(s["id"] == kw["id"] for s in segs):
            raise ErroPainel(f"segmento {kw['id']} não encontrado")
        if len(segs) == 1:
            raise ErroPainel("é o único segmento do corte")
        novos = [dict(s) for s in segs if s["id"] != kw["id"]]
        motivo = f"{kw['id']} removido"
    elif acao == "quadro":
        q = kw.get("quadro") or {}
        if q.get("modo") not in ("inteiro", "cortar", "encaixar"):
            raise ErroPainel("enquadramento: modo inteiro, cortar ou encaixar")
        q = {"modo": q["modo"], **({"x": round(min(1.0, max(0.0, float(q.get("x", 0.5)))), 4),
                                    "y": round(min(1.0, max(0.0, float(q.get("y", 0.5)))), 4)}
                                   if q["modo"] == "cortar" else {})}
        novos = [dict(s, quadro=q) if s["id"] == kw["id"] else dict(s) for s in segs]
        if not any(s["id"] == kw["id"] for s in segs):
            raise ErroPainel(f"segmento {kw['id']} não encontrado")
        motivo = f"enquadramento de {kw['id']}"
    elif acao in ("cortar", "restaurar"):
        transc = _transcricoes(d, raiz(pasta)).get(kw["video"])
        if not transc:
            raise ErroPainel(f"sem transcrição de {kw['video']}")
        ws = transc["palavras"]
        ini, fim = trecho_das_palavras(ws, int(kw["i"]), int(kw["j"]), acao)
        if acao == "cortar":
            novos = remover_trecho(segs, kw["video"], ini, fim, taxa)
        else:
            novos = restaurar_trecho(segs, kw["video"], ini, fim, taxa, ws)
        trecho = " ".join(w["texto"] for w in ws[int(kw["i"]):int(kw["j"]) + 1])
        motivo = f"{acao}: “{trecho[:60]}”"
    else:
        raise ErroPainel(f"ação de corte desconhecida: {acao}")
    return gravar_cortes(pasta, novos, revisao, motivo)


def desfazer_cortes(pasta, revisao: int | None) -> dict:
    h = _historico(pasta)
    if not h:
        raise ErroPainel("não há mudança de corte do painel para desfazer")
    d = E.ler(pasta)
    ultimo = h[-1]
    if (d.get("cortes") or {}).get("versao") != ultimo["versao_depois"]:
        raise ErroPainel("o corte mudou fora do painel depois da última mudança daqui; desfazer só volta o que "
                         "foi feito aqui (peça pelo chat)")
    gravado = gravar_cortes(pasta, ultimo["segmentos"], revisao, "desfazer")
    h2 = _historico(pasta)[:-2]  # tira o 'desfazer' que acabou de entrar e a mudança desfeita
    if h2:  # o corte agora é o que a mudança anterior deixou, numa versão nova
        h2[-1]["versao_depois"] = gravado["cortes"]["versao"]
    _gravar_historico(pasta, h2)
    return gravado


# ------------------------------------------------------------------ pedidos, animações, etapas, legendas
def anotar_aprendizado(pasta, etapa: str, texto: str) -> None:
    arq = E.caminho_estado(pasta).parent / "aprendizados.md"
    novo = not arq.exists()
    data = _dt.date.today().strftime("%d/%m")
    with open(arq, "a", encoding="utf-8", newline="\n") as f:
        if novo:
            f.write("# Aprendizados deste vídeo\n\n")
        f.write(f"- [ ] {E.nome_etapa(etapa)} · {' '.join(texto.split())} (pelo painel) · {data}\n")


def novo_pedido(pasta, revisao: int | None, etapa: str, texto: str, item: str | None = None,
                tempo_seq: float | None = None, aprendizado: bool = False) -> dict:
    texto = " ".join((texto or "").split())
    if not texto:
        raise ErroPainel("escreva o pedido")
    with _editar(pasta, revisao) as d:
        etapa = E.nome_etapa(etapa or E.proxima_etapa(d) or "geral")
        pid = E.nova_pendencia(d, etapa if etapa in d.get("fluxo", []) else (E.proxima_etapa(d) or etapa), texto, item)
        p = next(x for x in d["pendencias"] if x["id"] == pid)
        p["origem"] = "painel"
        if tempo_seq is not None:
            p["tempo_seq"] = round(float(tempo_seq), 3)
            taxa = _taxa(d)
            segs = (d.get("cortes") or {}).get("segmentos") or []
            if taxa and segs:
                o = Linha(segs, taxa).seq_para_origem(float(tempo_seq))
                if o:  # o tempo da origem sobrevive a mudanças no corte
                    p["video"], p["tempo"] = o[0], round(o[1], 3)
    if aprendizado:
        anotar_aprendizado(pasta, etapa, texto)
    return d


def resolver_pedido(pasta, revisao: int | None, pid: str) -> dict:
    with _editar(pasta, revisao) as d:
        E.resolver_pendencia(d, pid)
    return d


STATUS_PLANO = {"proposto", "aprovado", "ajustar", "riscado"}


def status_motion(pasta, revisao: int | None, mid: str, status: str, texto: str | None = None,
                  aprendizado: bool = False) -> dict:
    with _editar(pasta, revisao) as d:
        itens = (d.get("motions") or {}).get("itens") or []
        it = next((x for x in itens if x["id"] == mid), None)
        if not it:
            raise ErroPainel(f"animação {mid} não encontrada")
        atual = it.get("status")
        etapa = "motion_mapa" if atual in STATUS_PLANO else "motion_render"
        if status == "ajustar":
            if not texto:
                raise ErroPainel("diga o que ajustar")
            if atual in STATUS_PLANO:
                it["status"] = "ajustar"
            etapa = etapa if etapa in d.get("fluxo", []) else (E.proxima_etapa(d) or etapa)
            E.nova_pendencia(d, etapa, texto, mid)
            d["pendencias"][-1]["origem"] = "painel"
        elif status in STATUS_PLANO:
            if atual not in STATUS_PLANO:
                raise ErroPainel(f"{mid} já foi construída ({atual}): para mudar, peça um ajuste")
            it["status"] = status
        else:
            raise ErroPainel(f"status '{status}' não vale pelo painel")
    if aprendizado and texto:
        anotar_aprendizado(pasta, etapa, f"{mid}: {texto}")
    return d


def aprovar_etapa(pasta, revisao: int | None, etapa: str) -> dict:
    with _editar(pasta, revisao) as d:
        etapa = E.nome_etapa(etapa)
        st = d.get("etapas", {}).get(etapa)
        if st != "aguardando_aprovacao":
            raise ErroPainel(f"a etapa {etapa} não está esperando aprovação (está '{st}')")
        abertas = [p["id"] for p in E.pendencias_abertas(d) if p.get("etapa") == etapa]
        if abertas:
            raise ErroPainel(f"ainda há pedidos abertos nesta etapa ({', '.join(abertas)}): o Claude aplica, "
                             "ou você marca como resolvidos")
        E.mudar_etapa(d, etapa, "concluido")
    return d


def corrigir_legenda(pasta, lid: str, texto: str) -> dict:
    b, _arq = L.corrigir_bloco(pasta, lid, texto)
    return b


class _editar:
    """Como estado.editar, mas com a revisão que a interface leu (não a de agora)."""

    def __init__(self, pasta, revisao):
        self.pasta, self.revisao = pasta, revisao

    def __enter__(self):
        self.d = E.ler(self.pasta)
        if self.revisao is not None and self.d.get("revisao") != self.revisao:
            raise E.Conflito("o estado mudou enquanto você revisava (o Claude gravou algo); a tela foi atualizada, "
                             "refaça a mudança")
        self.lida = self.d.get("revisao")
        return self.d

    def __exit__(self, tipo, *_):
        if tipo is None:
            novo = E.gravar(self.pasta, self.d, revisao_lida=self.lida)
            self.d.clear()
            self.d.update(novo)
        return False

