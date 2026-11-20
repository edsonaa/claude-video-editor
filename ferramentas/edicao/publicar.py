"""Publicação: capítulos, capa, textos por plataforma (validados) e a pasta pronta para subir.

Os textos (título, descrição, legenda, tags, hashtags) quem escreve é o Claude com a
pessoa; aqui ficam as regras que as plataformas aplicam em silêncio (capítulo que não
aparece, hashtag ignorada, título cortado) e o trabalho mecânico.

Limites conferidos em novembro de 2026 (mudam; o guia diz como conferir de novo):
- YouTube: título 100 caracteres (~70 aparecem na busca; ~40 no feed de Shorts),
  descrição 5.000 bytes, tags 500 caracteres somadas (vírgulas contam; tag com espaço
  conta as aspas), até 15 hashtags (passou disso, o YouTube ignora todas).
  Capítulos: o primeiro em 0:00, pelo menos 3, em ordem, cada um com 10 s ou mais.
- Shorts: até 3 minutos, vertical ou quadrado.
- Instagram (Reels): legenda 2.200 caracteres (~125 aparecem), até 5 hashtags; até 3
  minutos para ser recomendado a quem não segue.
- TikTok: legenda 2.200 caracteres (limite seguro), 10 minutos é o limite seguro de envio.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from . import estado as E
from . import ff
from .linha import Linha
from .tempo import Taxa

CONFERIDO = "2026-11"
LIMITES = {
    "youtube": {"titulo": 100, "titulo_visivel": 70, "descricao_bytes": 5000, "tags_total": 500, "hashtags": 15},
    "shorts": {"titulo": 100, "titulo_visivel": 40, "descricao_bytes": 5000, "tags_total": 500, "hashtags": 15,
               "duracao_max": 180, "vertical": True},
    "instagram": {"legenda": 2200, "legenda_visivel": 125, "hashtags": 5, "duracao_recomendada": 180, "vertical": True},
    "tiktok": {"legenda": 2200, "duracao_max": 600, "vertical": True},
}
CAPITULO_MIN = 10.0
HASHTAG = re.compile(r"(?<![\w#])#([\wÀ-ÿ]+)", re.U)


class ErroPublicar(E.ErroEstado):
    pass


# ------------------------------------------------------------------ tempo
def tc(s: float, longo: bool = False) -> str:
    s = int(s + 1e-6)  # o YouTube lê segundos inteiros; arredondar para baixo nunca passa do ponto
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if longo else f"{m}:{s:02d}"


def de_tc(t: str) -> float:
    partes = [float(p) for p in t.strip().split(":")]
    v = 0.0
    for p in partes:
        v = v * 60 + p
    return v


def _duracao(d: dict) -> float:
    segs = (d.get("cortes") or {}).get("segmentos") or []
    fps = (d.get("midia") or {}).get("fps")
    return Linha(segs, fps).duracao if segs and fps else 0.0


# ------------------------------------------------------------------ capítulos
def validar_capitulos(caps: list[dict], duracao: float) -> tuple[list[str], list[str]]:
    erros, avisos = [], []
    if len(caps) < 3:
        erros.append(f"o YouTube pede pelo menos 3 capítulos (há {len(caps)})")
    if caps and int(caps[0]["tempo"] + 1e-6) != 0:
        erros.append("o primeiro capítulo precisa ser em 0:00 (sem ele, o YouTube ignora a lista inteira)")
    for a, b in zip(caps, caps[1:]):
        if b["tempo"] <= a["tempo"]:
            erros.append(f"fora de ordem: “{b['titulo']}” ({tc(b['tempo'])}) vem depois de “{a['titulo']}”")
        elif b["tempo"] - a["tempo"] < CAPITULO_MIN:
            erros.append(f"“{a['titulo']}” tem {b['tempo'] - a['tempo']:.0f} s; cada capítulo precisa de 10 s ou mais")
    if caps and duracao and duracao - caps[-1]["tempo"] < CAPITULO_MIN:
        erros.append(f"o último capítulo (“{caps[-1]['titulo']}”) tem menos de 10 s até o fim do vídeo")
    for c in caps:
        if not c["titulo"].strip():
            erros.append(f"capítulo em {tc(c['tempo'])} sem título")
        elif len(c["titulo"]) > 60:
            avisos.append(f"“{c['titulo'][:40]}…”: título de capítulo longo ({len(c['titulo'])} caracteres) aparece cortado")
    return erros, avisos


def formatar_capitulos(caps: list[dict], duracao: float) -> str:
    longo = duracao >= 3600
    return "\n".join(f"{tc(c['tempo'], longo)} {c['titulo'].strip()}" for c in caps)


def ler_capitulos(pasta, texto: str) -> list[dict]:
    """Linhas "<onde> <título>": onde = 1:23 (tempo do vídeo), f012 (frase), s003 (segmento) ou mo04 (animação)."""
    d = E.ler(pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    linha = Linha(segs, d["midia"]["fps"]) if segs else None
    frases = None
    caps = []
    for bruta in texto.splitlines():
        bruta = bruta.strip()
        if not bruta or bruta.startswith("#"):
            continue
        m = re.match(r"^(\S+)\s+[-–—:]?\s*(.+)$", bruta)
        if not m:
            raise ErroPublicar(f"linha sem título: “{bruta}”")
        onde, titulo = m.groups()
        if re.fullmatch(r"\d+(:\d{1,2}){1,2}(\.\d+)?", onde):
            t = de_tc(onde)
        elif re.fullmatch(r"f\d+", onde):
            if frases is None:
                from .curtos import frases_atuais
                frases = {f["id"]: f for f in frases_atuais(pasta)["frases"]}
            if onde not in frases:
                raise ErroPublicar(f"frase {onde} não existe na lista atual")
            t = frases[onde]["inicio"]
        elif re.fullmatch(r"s\d+", onde) and linha:
            p = next((p for p in linha.pedacos if p.id == onde), None)
            if not p:
                raise ErroPublicar(f"segmento {onde} não existe")
            t = linha.taxa.segundos(p.seq_ini)
        elif re.fullmatch(r"mo\d+", onde):
            it = next((i for i in (d.get("motions") or {}).get("itens") or [] if i["id"] == onde), None)
            if not it or it.get("inicio_seq") is None:
                raise ErroPublicar(f"animação {onde} não existe ou não tem tempo")
            t = it["inicio_seq"]
        else:
            raise ErroPublicar(f"não sei onde fica “{onde}” (use 1:23, f012, s003 ou mo04)")
        caps.append({"tempo": round(t, 3), "titulo": titulo.strip()})
    caps.sort(key=lambda c: c["tempo"])
    return caps


def capitulos_das_animacoes(pasta) -> list[dict]:
    """Os marcadores de capítulo do plano de animação (efeito `capitulo`), com 0:00 se faltar."""
    d = E.ler(pasta)
    caps = []
    for it in (d.get("motions") or {}).get("itens") or []:
        if it.get("efeito") == "capitulo" and it.get("status") != "riscado" and it.get("inicio_seq") is not None:
            p = it.get("parametros") or it.get("params") or {}
            titulo = p.get("titulo") or p.get("texto") or it.get("titulo") or it.get("ideia") or it["id"]
            caps.append({"tempo": it["inicio_seq"], "titulo": str(titulo)})
    caps.sort(key=lambda c: c["tempo"])
    return caps


def ajustar_inicio(caps: list[dict], titulo: str = "Introdução") -> list[dict]:
    if caps and int(caps[0]["tempo"]) == 0:
        return [dict(caps[0], tempo=0.0)] + caps[1:]
    if caps and caps[0]["tempo"] < CAPITULO_MIN:
        return [dict(caps[0], tempo=0.0)] + caps[1:]
    return [{"tempo": 0.0, "titulo": titulo}] + caps


# ------------------------------------------------------------------ textos
def tags_total(tags: list[str]) -> int:
    """Como o YouTube conta: vírgulas entre as tags e aspas nas que têm espaço."""
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def hashtags(texto: str) -> list[str]:
    return HASHTAG.findall(texto or "")


def plataformas_padrao(d: dict) -> list[str]:
    f = (d.get("video") or {}).get("formato")
    if not f:
        try:
            from . import config as C
            f = ((C.carregar(obrigatorio=False) or {}).get("video") or {}).get("formato")
        except Exception:  # noqa: BLE001
            f = None
    return ["shorts", "instagram", "tiktok"] if f in ("9:16", "1:1", "4:5") else ["youtube"]


def validar(pub: dict, plataforma: str, duracao: float, formato: str | None, caps: list[dict] | None = None
            ) -> tuple[list[str], list[str]]:
    lim = LIMITES[plataforma]
    erros, avisos = [], []
    p = pub.get("youtube" if plataforma == "shorts" and "shorts" not in pub else plataforma) or {}
    if not p:
        return [f"sem textos para {plataforma} (publicar.py definir)"], []
    if plataforma in ("youtube", "shorts"):
        titulo = p.get("titulo", "")
        if not titulo.strip():
            erros.append("sem título")
        elif len(titulo) > lim["titulo"]:
            erros.append(f"título com {len(titulo)} caracteres (máximo {lim['titulo']})")
        elif len(titulo) > lim["titulo_visivel"]:
            avisos.append(f"título com {len(titulo)} caracteres: só uns {lim['titulo_visivel']} aparecem "
                          f"{'no feed de Shorts' if plataforma == 'shorts' else 'na busca'}")
        desc = descricao_final(pub, plataforma, caps)
        nb = len(desc.encode("utf-8"))
        if nb > lim["descricao_bytes"]:
            erros.append(f"descrição com {nb} bytes (máximo {lim['descricao_bytes']}; acento conta 2)")
        tags = p.get("tags") or []
        tt = tags_total(tags)
        if tt > lim["tags_total"]:
            erros.append(f"tags somam {tt} caracteres (máximo {lim['tags_total']}, contando vírgulas e aspas)")
        n = len(hashtags(titulo) + hashtags(desc))
        if n > lim["hashtags"]:
            erros.append(f"{n} hashtags: acima de {lim['hashtags']}, o YouTube ignora todas")
        if plataforma == "youtube" and caps:
            e2, a2 = validar_capitulos(caps, duracao)
            erros += [f"capítulos: {x}" for x in e2]
            avisos += [f"capítulos: {x}" for x in a2]
    else:
        leg = p.get("legenda", "")
        texto = montar_legenda(p)
        if not leg.strip():
            erros.append("sem legenda")
        if len(texto) > lim["legenda"]:
            erros.append(f"legenda com {len(texto)} caracteres (máximo {lim['legenda']})")
        elif lim.get("legenda_visivel") and len(leg.split("\n")[0]) > lim["legenda_visivel"]:
            avisos.append(f"a primeira linha passa de {lim['legenda_visivel']} caracteres: o gancho fica escondido")
        n = len(hashtags(texto))
        if lim.get("hashtags") and n > lim["hashtags"]:
            erros.append(f"{n} hashtags (o {plataforma.capitalize()} aceita até {lim['hashtags']})")
    if lim.get("vertical") and formato == "16:9":
        erros.append(f"{plataforma}: o vídeo é horizontal (16:9); faça um curto vertical (curtos.py criar)")
    if lim.get("duracao_max") and duracao > lim["duracao_max"]:
        erros.append(f"{duracao:.0f} s passa do limite de {lim['duracao_max']} s de {plataforma}")
    if lim.get("duracao_recomendada") and duracao > lim["duracao_recomendada"]:
        avisos.append(f"{duracao:.0f} s: acima de {lim['duracao_recomendada']} s o {plataforma} não recomenda a quem não segue")
    if plataforma == "shorts" and duracao > 60:
        avisos.append("Shorts com mais de 60 s não podem usar música com direitos (Content ID) da biblioteca")
    return erros, avisos


def montar_legenda(p: dict) -> str:
    leg = (p.get("legenda") or "").strip()
    tags = [t if t.startswith("#") else f"#{t}" for t in p.get("hashtags") or []]
    faltam = [t for t in tags if t.lower() not in leg.lower()]
    return leg + ("\n\n" + " ".join(faltam) if faltam else "")


def descricao_final(pub: dict, plataforma: str, caps: list[dict] | None) -> str:
    p = pub.get("youtube" if plataforma == "shorts" and "shorts" not in pub else plataforma) or {}
    desc = (p.get("descricao") or "").strip()
    if plataforma == "youtube" and caps and "0:00" not in desc:
        desc += "\n\nCapítulos\n" + formatar_capitulos(caps, 0)
    tags = [t if t.startswith("#") else f"#{t}" for t in p.get("hashtags") or []]
    faltam = [t for t in tags if t.lower() not in desc.lower()]
    if faltam:
        desc += "\n\n" + " ".join(faltam)
    return desc


# ------------------------------------------------------------------ capa
def capa_candidatas(pasta, n: int = 6, intervalo: float = 0.5, distancia: float = 4.0) -> list[dict]:
    """Quadros do corte final bons para capa: nítidos, bem expostos, com rosto (se o modelo existir)."""
    import cv2
    import numpy as np

    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:  # noqa: BLE001
        pass
    d = E.ler(pasta)
    base = E.caminho_estado(pasta).parent.parent
    segs = (d.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise ErroPublicar("o vídeo não tem cortes")
    taxa = Taxa.de(d["midia"]["fps"])
    linha = Linha(segs, taxa)
    arqs = {a["id"]: a for a in d["midia"].get("arquivos") or []}
    from . import render as R
    formato = R.formato_do_projeto(d)
    detector = None
    from .rosto import NOME_MODELO
    modelo = Path(__file__).resolve().parent.parent / "modelos" / NOME_MODELO
    if modelo.exists():
        try:
            detector = cv2.FaceDetectorYN.create(str(modelo), "", (320, 180), 0.7)
        except Exception:  # noqa: BLE001
            detector = None
    cands = []
    for p in linha.pedacos:
        info = arqs[p.video]
        if info.get("tipo") == "tela":
            continue
        caminho = Path(info["caminho"]) if Path(info["caminho"]).is_absolute() else base / info["caminho"]
        ini, dur = taxa.segundos(p.in_f), taxa.segundos(p.dur)
        larg = 320
        proc = subprocess.run([ff.ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{ini:.4f}", "-i", str(caminho),
                               "-t", f"{dur:.4f}", "-vf", f"fps=1/{intervalo},scale={larg}:-2", "-f", "rawvideo",
                               "-pix_fmt", "bgr24", "-"], capture_output=True)
        if proc.returncode != 0 or not proc.stdout:
            continue
        res = info.get("resolucao") or [1920, 1080]
        alt = int(round(larg * res[1] / res[0] / 2) * 2)
        quadros = np.frombuffer(proc.stdout, np.uint8)
        n_q = quadros.size // (larg * alt * 3)
        quadros = quadros[: n_q * larg * alt * 3].reshape(n_q, alt, larg, 3)
        if detector is not None:
            detector.setInputSize((larg, alt))
        for k, q in enumerate(quadros):
            cinza = cv2.cvtColor(q, cv2.COLOR_BGR2GRAY)
            nitidez = float(cv2.Laplacian(cinza, cv2.CV_64F).var())
            brilho = float(cinza.mean())
            nota = min(nitidez / 300.0, 1.5) - abs(brilho - 120) / 160
            motivos = [f"nitidez {nitidez:.0f}"]
            if detector is not None:
                _, faces = detector.detect(q)
                if faces is not None and len(faces):
                    f = max(faces, key=lambda x: x[2] * x[3])
                    area = f[2] * f[3] / (larg * alt)
                    nota += 1.0 + min(area * 8, 1.0)
                    motivos.append("rosto")
            t_origem = ini + k * intervalo
            t_seq = taxa.segundos(p.seq_ini) + k * intervalo
            cands.append({"t_seq": round(t_seq, 3), "video": p.video, "t_origem": round(t_origem, 3),
                          "nota": round(nota, 3), "motivos": motivos, "caminho": str(caminho), "segmento": p.id,
                          "src": list(res), "tipo_midia": info.get("tipo")})
    cands.sort(key=lambda c: -c["nota"])
    escolhidas: list[dict] = []
    for c in cands:
        if all(abs(c["t_seq"] - e["t_seq"]) >= distancia for e in escolhidas):
            escolhidas.append(c)
        if len(escolhidas) >= n:
            break
    escolhidas.sort(key=lambda c: c["t_seq"])
    destino = E.caminho_estado(pasta).parent / "publicar" / "capas"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    miniaturas = []
    for k, c in enumerate(escolhidas, 1):
        arq = destino / f"capa_{k:02d}_{tc(c['t_seq']).replace(':', 'm')}s.png"
        # a capa sai no formato do vídeo: 1280x720 no horizontal; no vertical, recortada como o próprio curto
        tam = (1280, 720) if formato == "16:9" else R.tamanho(formato)
        bruto = next((s for s in segs if s["id"] == c["segmento"]), {})
        quadro = bruto.get("quadro") or R.quadro_padrao(c["tipo_midia"], tuple(c["src"]), tam)
        filtro = "[0:v]null[v0];" + R.filtro_quadro(tuple(c["src"]), tam, quadro)
        ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{c['t_origem']:.4f}", "-i", c["caminho"],
                  "-filter_complex", filtro, "-map", "[vq]", "-frames:v", "1", str(arq)])
        c["arquivo"] = str(arq)
        c["n"] = k
        img = cv2.imread(str(arq))
        if img is not None:
            h = 200
            mini = cv2.resize(img, (int(img.shape[1] * h / img.shape[0]), h))
            cv2.rectangle(mini, (0, 0), (150, 26), (20, 20, 20), -1)
            cv2.putText(mini, f"{k}  {tc(c['t_seq'])}", (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1,
                        cv2.LINE_AA)
            miniaturas.append(mini)
    if miniaturas:
        colunas = 3
        h = 200
        w = max(m.shape[1] for m in miniaturas)
        linhas_ = (len(miniaturas) + colunas - 1) // colunas
        folha = np.full((linhas_ * (h + 8) + 8, colunas * (w + 8) + 8, 3), 40, np.uint8)
        for i, m in enumerate(miniaturas):
            y, x = 8 + (i // colunas) * (h + 8), 8 + (i % colunas) * (w + 8)
            folha[y:y + h, x:x + m.shape[1]] = m
        cv2.imwrite(str(destino / "candidatas.png"), folha)
    (destino / "candidatas.json").write_text(json.dumps(escolhidas, ensure_ascii=False, indent=1), encoding="utf-8")
    return escolhidas


def escolher_capa(pasta, n: int) -> str:
    arq = E.caminho_estado(pasta).parent / "publicar" / "capas" / "candidatas.json"
    if not arq.exists():
        raise ErroPublicar("gere as candidatas antes (publicar.py capa)")
    c = next((x for x in json.loads(arq.read_text(encoding="utf-8")) if x["n"] == n), None)
    if not c:
        raise ErroPublicar(f"não há a candidata {n}")
    base = E.caminho_estado(pasta).parent.parent
    with E.editar(pasta) as d:
        d.setdefault("publicacao", {})["capa"] = os.path.relpath(c["arquivo"], base).replace(os.sep, "/")
    return c["arquivo"]


# ------------------------------------------------------------------ definir, conferir, empacotar
def definir(pasta, novo: dict) -> dict:
    with E.editar(pasta) as d:
        pub = d.setdefault("publicacao", {})
        for k, v in novo.items():
            if isinstance(v, dict) and isinstance(pub.get(k), dict):
                pub[k].update(v)
            else:
                pub[k] = v
    return E.ler(pasta)["publicacao"]


def conferir(pasta, plataformas: list[str] | None = None) -> dict:
    d = E.ler(pasta)
    pub = d.get("publicacao") or {}
    dur = _duracao(d)
    formato = (d.get("video") or {}).get("formato")
    if not formato:
        try:
            from . import config as C
            formato = ((C.carregar(obrigatorio=False) or {}).get("video") or {}).get("formato") or "16:9"
        except Exception:  # noqa: BLE001
            formato = "16:9"
    caps = pub.get("capitulos")
    out = {}
    for pl in plataformas or plataformas_padrao(d):
        if pl not in LIMITES:
            raise ErroPublicar(f"plataforma '{pl}' desconhecida ({', '.join(LIMITES)})")
        erros, avisos = validar(pub, pl, dur, formato, caps)
        out[pl] = {"erros": erros, "avisos": avisos}
    return {"duracao": dur, "formato": formato, "plataformas": out}


def ultimo_final(d: dict, base: Path) -> Path | None:
    finais = [e for e in d.get("entregas") or [] if e.get("etapa") == "render" and e.get("tipo") == "final"
              and e.get("de", 0) == 0]
    if not finais:
        return None
    arq = Path(finais[-1]["arquivo"])
    return arq if arq.is_absolute() else base / arq


def pacote(pasta, plataformas: list[str] | None = None, forcar: bool = False) -> dict:
    d = E.ler(pasta)
    base = E.caminho_estado(pasta).parent.parent
    video = ultimo_final(d, base)
    if not video or not video.exists():
        raise ErroPublicar("não há render final do vídeo inteiro (render.py final)")
    conf = conferir(pasta, plataformas)
    com_erro = {p: c["erros"] for p, c in conf["plataformas"].items() if c["erros"]}
    if com_erro and not forcar:
        raise ErroPublicar("corrija antes de empacotar:\n" + "\n".join(f"- {p}: {e}" for p, es in com_erro.items()
                                                                        for e in es))
    pub = d.get("publicacao") or {}
    caps = pub.get("capitulos")
    from . import audio as A
    medida = A.loudness(video)
    feitos = {}
    for pl in conf["plataformas"]:
        dest = base / "Publicar" / pl
        dest.mkdir(parents=True, exist_ok=True)
        alvo = dest / f"{d['projeto']}{video.suffix}"
        if alvo.exists():
            alvo.unlink()
        try:
            os.link(video, alvo)  # sem gastar espaço quando dá
        except OSError:
            shutil.copy2(video, alvo)
        p = pub.get("youtube" if pl == "shorts" and "shorts" not in pub else pl) or {}
        if pl in ("youtube", "shorts"):
            texto = (f"TÍTULO\n{p.get('titulo', '')}\n\nDESCRIÇÃO\n{descricao_final(pub, pl, caps)}\n\n"
                     f"TAGS\n{', '.join(p.get('tags') or [])}\n")
        else:
            texto = f"LEGENDA\n{montar_legenda(p)}\n"
        (dest / "texto.txt").write_text(texto, encoding="utf-8")
        for fmt, arq in ((d.get("legendas") or {}).get("saidas") or {}).items():
            if fmt in ("srt", "vtt") and Path(arq).exists():
                shutil.copy2(arq, dest / f"{d['projeto']}.{fmt}")
        if pub.get("capa"):
            capa = Path(pub["capa"]) if Path(pub["capa"]).is_absolute() else base / pub["capa"]
            if capa.exists():
                shutil.copy2(capa, dest / f"capa{capa.suffix}")
        c = conf["plataformas"][pl]
        linhas = [f"# {pl} · {d['projeto']}", "",
                  f"- vídeo: {alvo.name} ({conf['duracao']:.1f} s, {conf['formato']}, {medida['lufs']:.1f} LUFS, "
                  f"pico {medida['pico_dbtp']:.1f} dBTP)",
                  f"- limites conferidos em {CONFERIDO}"]
        linhas += [f"- ✗ {e}" for e in c["erros"]] + [f"- ! {a}" for a in c["avisos"]]
        if not c["erros"] and not c["avisos"]:
            linhas.append("- ✓ tudo dentro dos limites")
        (dest / "conferencia.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        feitos[pl] = str(dest)
    with E.editar(pasta) as e:
        e.setdefault("publicacao", {})["pacote"] = {"em": E.agora(), "pastas": {k: os.path.relpath(v, base).replace(
            os.sep, "/") for k, v in feitos.items()}, "video": os.path.relpath(video, base).replace(os.sep, "/")}
    return {"pastas": feitos, "video": str(video), "conferencia": conf}
