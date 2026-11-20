"""Boas-vindas de um vídeo novo pelo painel: verificação, briefing e as escolhas do vídeo.

O `/edicao:iniciar` pergunta se o briefing é pelo Claude ou pelo painel. Pelo painel,
a pessoa vê o que está pronto (pasta, gravações, ferramentas), escreve o briefing,
escolhe o tipo de vídeo (preset), o estilo das animações e o padrão de legenda, com
prévia, e envia. `salvar` grava:

- no estado do vídeo: o fluxo do tipo escolhido, o perfil, `video` (formato, tipo,
  preset e `legendas`: estilo, queimar, posição) e o bloco `boas_vindas`;
- `_CLAUDE/briefing_painel.md`: o texto da pessoa e as escolhas, para o Claude
  organizar o `briefing.md` do jeito de sempre (sem inventar nada);
- com "usar como padrão": os mesmos campos na configuração (`~/.edicao/config.json`).

As escolhas valem para este vídeo; a configuração só muda se a pessoa pedir.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

from . import config as C
from . import efeitos as EF
from . import estado as E
from . import ff
from . import legendas as L

EXT_VIDEO = {".mp4", ".mov", ".mkv", ".mxf", ".avi", ".m4v", ".webm", ".mts"}
EXT_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac"}


class ErroBoasVindas(E.ErroEstado):
    pass


def _raiz(pasta) -> Path:
    return E.caminho_estado(pasta).parent.parent


def _cfg() -> dict:
    return C.carregar(obrigatorio=False) or C.mesclar(C.PADRAO, {})


def _fontes_instaladas() -> set[str] | None:
    """Famílias de fonte do sistema (fc-list); None quando não dá para saber (Windows sem fontconfig)."""
    exe = shutil.which("fc-list")
    if not exe:
        return None
    try:
        p = subprocess.run([exe, ":", "family"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    fams = set()
    for linha in p.stdout.splitlines():
        for f in linha.split(","):
            fams.add(f.strip().lower())
    return fams


def _brutos(pasta, cfg) -> list[Path]:
    b = _raiz(pasta) / ((cfg.get("pastas") or {}).get("brutos") or "Brutos")
    if not b.exists():
        return []
    return sorted(p for p in b.rglob("*") if p.is_file() and p.suffix.lower() in EXT_VIDEO | EXT_AUDIO
                  and not p.name.startswith("."))


# ------------------------------------------------------------------ verificação
def verificacao(pasta) -> list[dict]:
    """O que está pronto para começar. ok: True (pronto), False (falta), None (aviso, não trava)."""
    cfg = _cfg()
    raiz = _raiz(pasta)
    d = E.ler(pasta)
    itens = []
    padrao = (cfg.get("pastas") or {}).get("padrao_projeto") or "AAAA-MM-DD_Nome"
    rx = re.escape(padrao).replace("AAAA", r"\d{4}").replace("MM", r"\d{2}").replace("DD", r"\d{2}").replace("Nome", ".+")
    itens.append({"titulo": "Pasta do projeto", "ok": True if re.fullmatch(rx, raiz.name) else None,
                  "detalhe": raiz.name if re.fullmatch(rx, raiz.name)
                  else f"{raiz.name} (o seu padrão é {padrao}; dá para seguir assim)"})
    pastas = cfg.get("pastas") or {}
    faltam = [pastas.get(k) for k in ("brutos", "assets", "docs", "renders") if pastas.get(k)
              and not (raiz / pastas[k]).exists()]
    itens.append({"titulo": "Subpastas", "ok": None if faltam else True,
                  "detalhe": f"faltam {', '.join(faltam)}: o Claude cria (vazias) com o seu ok" if faltam
                  else ", ".join(pastas.get(k) for k in ("brutos", "assets", "docs", "renders") if pastas.get(k))})
    arqs = _brutos(pasta, cfg)
    nv = sum(1 for a in arqs if a.suffix.lower() in EXT_VIDEO)
    na = len(arqs) - nv
    itens.append({"titulo": "Gravações", "ok": True if arqs else None,
                  "detalhe": (f"{nv} vídeo(s)" + (f" e {na} áudio(s)" if na else "") + f" em {pastas.get('brutos', 'Brutos')}")
                  if arqs else f"nenhuma ainda em {pastas.get('brutos', 'Brutos')}: dá para seguir e colocar antes da preparação"})
    try:
        v = subprocess.run([ff.ffmpeg(), "-version"], capture_output=True, text=True, timeout=10).stdout.split("\n")[0]
        itens.append({"titulo": "FFmpeg", "ok": True, "detalhe": " ".join(v.split()[:3])})
    except (OSError, subprocess.TimeoutExpired):
        itens.append({"titulo": "FFmpeg", "ok": False, "detalhe": "não encontrado: sem ele nada roda (o Claude ajuda a instalar)"})
    fluxo = d.get("fluxo") or cfg.get("fluxo") or []
    tr = cfg.get("transcricao") or {}
    if tr.get("motor") == "scribe":
        ok = bool(os.environ.get("ELEVENLABS_API_KEY"))
        itens.append({"titulo": "Transcrição (Scribe)", "ok": ok,
                      "detalhe": "chave encontrada" if ok else "falta a chave ELEVENLABS_API_KEY"})
    else:
        ok = bool(os.environ.get("WHISPERX") or shutil.which("whisperx"))
        itens.append({"titulo": "Transcrição (WhisperX)", "ok": True if ok else None,
                      "detalhe": "instalado" if ok else "não encontrado no ambiente: o Claude instala na preparação"})
    if "motion_render" in fluxo:
        ok = bool(shutil.which("npx") or os.environ.get("HYPERFRAMES_CMD"))
        itens.append({"titulo": "Animações (Node.js para o HyperFrames)", "ok": ok,
                      "detalhe": "npx encontrado" if ok else "falta o Node.js: só é preciso na etapa de animações"})
    if "sfx" in fluxo:
        bib = (cfg.get("som") or {}).get("biblioteca")
        if bib and Path(bib).exists():
            ok = (Path(bib) / "indice.json").exists()
            itens.append({"titulo": "Biblioteca de sons", "ok": True if ok else None,
                          "detalhe": bib + ("" if ok else " (ainda sem índice: o Claude indexa na etapa de som)")})
        else:
            itens.append({"titulo": "Biblioteca de sons", "ok": None,
                          "detalhe": "não configurada: dá para montar uma básica na etapa de som"})
    return itens


# ------------------------------------------------------------------ o que mostrar
def _tema_resumo(t: dict) -> dict:
    return {"cores": t["cores"], "fontes": t["fontes"], "titulo": t.get("titulo"), "descricao": t.get("descricao")}


def opcoes(pasta) -> dict:
    cfg = _cfg()
    d = E.ler(pasta)
    fams = _fontes_instaladas()

    def faltando(t):
        if fams is None:
            return None
        return sorted({f for f in t["fontes"].values() if f and f.lower() not in fams})

    presets = []
    for nome, p in C.listar_presets().items():
        pc = p.get("config") or {}
        presets.append({"id": nome, "titulo": p.get("titulo", nome), "descricao": p.get("descricao", ""),
                        "para_quem": p.get("para_quem", ""), "formato": (pc.get("video") or {}).get("formato", "16:9"),
                        "fluxo": pc.get("fluxo") or C.PADRAO["fluxo"], "estilo_sugerido": p.get("estilo_sugerido"),
                        "programa": (pc.get("revisao") or {}).get("programa"),
                        "legenda": {"estilo": "impacto" if (pc.get("legendas") or {}).get("modo") == "palavra" else "classica",
                                    "queimar": bool((pc.get("legendas") or {}).get("queimar")),
                                    "ativas": bool((pc.get("legendas") or {}).get("ativas"))}})
    perfis = []
    pp = C.pasta() / "perfis"
    for p in sorted(pp.iterdir()) if pp.exists() else []:
        if p.is_dir() and (p / "tema.json").exists():
            t = EF.tema_de(perfil_dir=p)
            perfis.append({"id": p.name, "tipo": "perfil", **_tema_resumo(t), "previa": (p / "previa.png").exists(),
                           "fontes_faltando": faltando(t)})
    nomes_perfis = {p["id"] for p in perfis}
    estilos = []
    for nome in C.listar_estilos():
        if nome in nomes_perfis:
            continue
        t = EF.tema_de(estilo=nome)
        estilos.append({"id": nome, "tipo": "estilo", **_tema_resumo(t), "previa": True, "fontes_faltando": faltando(t)})
    leg = L.estilos_legenda()
    atual_leg = L.opcoes_legenda(d, cfg)
    return {
        "projeto": d.get("projeto"), "nome": cfg.get("nome"),
        "verificacao": verificacao(pasta),
        "presets": presets, "perfis": perfis, "estilos": estilos,
        "legendas": [{"id": k, **v} for k, v in leg.items()],
        "atual": {"preset": ((d.get("video") or {}).get("preset") or cfg.get("preset")),
                  "perfil": d.get("perfil") or cfg.get("perfil_padrao"),
                  "legenda": {"estilo": atual_leg["estilo"]["id"], "queimar": bool(atual_leg["queimar"]),
                              "posicao": atual_leg["posicao"], "ativas": bool(atual_leg["ativas"])}},
        "tem_exemplo": bool(_primeiro_video(pasta, cfg)),
        "enviado": (d.get("boas_vindas") or {}).get("em"),
    }


def _primeiro_video(pasta, cfg) -> Path | None:
    return next((a for a in _brutos(pasta, cfg) if a.suffix.lower() in EXT_VIDEO), None)


def quadro_exemplo(pasta) -> Path | None:
    """Um quadro das gravações (a 30% do primeiro vídeo), para a prévia da legenda."""
    cfg = _cfg()
    v = _primeiro_video(pasta, cfg)
    if not v:
        return None
    dest = E.caminho_estado(pasta).parent / "painel" / "exemplo.jpg"
    if dest.exists() and dest.stat().st_mtime >= v.stat().st_mtime:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dur = float(ff.sondar(v).get("format", {}).get("duration") or 0)
    except Exception:  # noqa: BLE001
        dur = 0
    tmp = dest.with_suffix(".parcial.jpg")
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{dur * 0.3:.2f}", "-i", str(v), "-frames:v", "1",
              "-vf", "scale='min(1280,iw)':-2", "-q:v", "4", str(tmp)])
    os.replace(tmp, dest)
    return dest


def previa_tema(tipo: str, ident: str) -> Path | None:
    """A vitrine de um estilo do motor ou de um perfil da pessoa (só esses caminhos)."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ident or ""):
        return None
    base = C.ESTILOS if tipo == "estilo" else C.pasta() / "perfis"
    arq = base / ident / "previa.png"
    return arq if arq.exists() else None


# ------------------------------------------------------------------ enviar
def _fluxo_para(preset_fluxo: list[str], legendas_ativas: bool) -> list[str]:
    fl = [E.nome_etapa(e) for e in preset_fluxo]
    if "iniciar" not in fl:
        fl.insert(0, "iniciar")
    if legendas_ativas and "legendas" not in fl:
        fl.insert(fl.index("render") if "render" in fl else len(fl), "legendas")
    if not legendas_ativas and "legendas" in fl:
        fl.remove("legendas")
    return fl


def salvar(pasta, dados: dict) -> dict:
    """Grava as escolhas no vídeo (e na configuração, com `padrao`). Devolve o resumo."""
    cfg = _cfg()
    presets = C.listar_presets()
    preset = dados.get("preset")
    if preset not in presets:
        raise ErroBoasVindas(f"tipo de vídeo '{preset}' não existe")
    pc = presets[preset].get("config") or {}
    tema = dados.get("tema") or {}
    tipo, ident = tema.get("tipo"), tema.get("id")
    if tipo not in ("perfil", "estilo") or not ident:
        raise ErroBoasVindas("escolha um estilo")
    leg = dados.get("legenda") or {}
    ativas = bool(leg.get("ativas", True))
    estilo_leg = leg.get("estilo") or "classica"
    if estilo_leg not in L.estilos_legenda():
        raise ErroBoasVindas(f"estilo de legenda '{estilo_leg}' não existe")
    posicao = leg.get("posicao") or L.estilo_legenda(estilo_leg).get("posicao", "baixo")
    if posicao not in L.POSICOES:
        raise ErroBoasVindas("posição da legenda: baixo, centro ou topo")
    palavra = L.estilo_legenda(estilo_leg)["modo"] == "palavra"
    queimar = bool(leg.get("queimar")) or palavra  # palavra a palavra só existe queimada
    briefing = (dados.get("briefing") or "").strip()
    termos = [t.strip() for t in (dados.get("termos") or []) if str(t).strip()]

    # o perfil: um dos da pessoa, ou um estilo do motor que vira perfil dela agora
    criado = None
    if tipo == "estilo":
        if (C.pasta() / "perfis" / ident).exists():
            perfil = ident
        else:
            C.novo_perfil(ident, estilo=ident)
            perfil, criado = ident, ident
    else:
        if not (C.pasta() / "perfis" / ident).exists():
            raise ErroBoasVindas(f"o perfil {ident} não existe")
        perfil = ident

    fluxo = _fluxo_para(pc.get("fluxo") or cfg["fluxo"], ativas)
    vleg = {"estilo": estilo_leg, "queimar": queimar, "posicao": posicao, "ativas": ativas}
    observacoes = []
    prog = (pc.get("revisao") or {}).get("programa")
    if prog and prog != (cfg.get("revisao") or {}).get("programa"):
        observacoes.append(f"o tipo '{presets[preset].get('titulo', preset)}' costuma revisar em '{prog}'; "
                           f"a configuração usa '{(cfg.get('revisao') or {}).get('programa')}'")
    with E.editar(pasta) as d:
        etapas_antes = dict(d.get("etapas") or {})
        d["fluxo"] = fluxo
        d["etapas"] = {e: etapas_antes.get(e, "pendente") for e in fluxo}
        if d["etapas"].get("iniciar") == "pendente":
            d["etapas"]["iniciar"] = "em_andamento"
        d["perfil"] = perfil
        v = d.setdefault("video", {})
        v.update({"formato": (pc.get("video") or {}).get("formato", "16:9"), "tipo": (pc.get("video") or {}).get("tipo"),
                  "preset": preset, "legendas": vleg})
        d["boas_vindas"] = {"em": E.agora(), "preset": preset, "perfil": perfil, "perfil_criado": criado,
                            "legenda": vleg, "termos": termos, "padrao": bool(dados.get("padrao")),
                            "briefing": "_CLAUDE/briefing_painel.md"}

    titulo_leg = L.estilo_legenda(estilo_leg)["titulo"]
    linhas = [f"# Briefing pelo painel · {E.agora()}", "",
              "## O que a pessoa escreveu", briefing or "(nada escrito)", ""]
    if termos:
        linhas += ["## Termos e nomes próprios", *[f"- {t}" for t in termos], ""]
    linhas += ["## Escolhas deste vídeo",
               f"- Tipo de vídeo: {presets[preset].get('titulo', preset)} (`{preset}`): {' → '.join(fluxo)}",
               f"- Estilo: `{perfil}`" + (" (perfil criado agora a partir do estilo do motor)" if criado else ""),
               f"- Legenda: {'sem legenda' if not ativas else titulo_leg + (' queimada' if queimar else ' em arquivo (SRT)') + f', posição {posicao}'}",
               f"- Usar como padrão nos próximos vídeos: {'sim' if dados.get('padrao') else 'não'}"]
    linhas += [f"- Observação: {o}" for o in observacoes]
    (E.caminho_estado(pasta).parent / "briefing_painel.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    if dados.get("padrao"):
        c = C.carregar(obrigatorio=False)
        if c is not None:
            c["preset"] = preset
            c["fluxo"] = fluxo
            c.setdefault("video", {}).update({k: x for k, x in (pc.get("video") or {}).items() if k in ("tipo", "formato")})
            c.setdefault("legendas", {}).update({"estilo": estilo_leg, "queimar": queimar, "posicao": posicao,
                                                 "ativas": ativas})
            c["perfil_padrao"] = perfil
            C.gravar(c)
        else:
            observacoes.append("sem configuração em ~/.edicao: as escolhas valeram só para este vídeo")
    return {"preset": preset, "perfil": perfil, "perfil_criado": criado, "fluxo": fluxo, "legenda": vleg,
            "termos": termos, "padrao": bool(dados.get("padrao")), "observacoes": observacoes,
            "briefing": str(E.caminho_estado(pasta).parent / "briefing_painel.md")}
