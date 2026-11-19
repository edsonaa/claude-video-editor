"""Biblioteca de efeitos (HyperFrames) e de estilos.

Um efeito é uma composição pronta e parametrizada em `efeitos/<nome>/`:
  index.html    a composição (usa ../_comum/tema.css e tema.js, copiados junto)
  efeito.json   o que é, formato, duração, parâmetros e eventos de som
Um estilo é um perfil completo em `estilos/<nome>/`, com o `tema.json` que a máquina lê.

`criar` copia um efeito para a pasta do item (ex.: _CLAUDE/motion/mo04/) com o tema
do perfil e o conteúdo do item já nas variáveis da composição, a duração exata em
frames e o tamanho do formato. Daí em diante é um projeto HyperFrames comum: o
motion-render ajusta o que precisar e renderiza.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

from .tempo import Taxa

MOTOR = Path(__file__).resolve().parent.parent.parent
EFEITOS = MOTOR / "efeitos"
ESTILOS = MOTOR / "estilos"
COMUM = EFEITOS / "_comum"
HYPERFRAMES_VERSAO = "0.9.70"
GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"

FORMATOS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}

# tema.json → variáveis da composição
TEMA_PADRAO = {
    "cores": {"fundo": "#0F172A", "superficie": "#1E293B", "texto": "#F8FAFC", "texto_suave": "#94A3B8",
              "destaque": "#3B82F6", "apoio": "#22D3EE"},
    "fontes": {"titulo": "Inter", "texto": "Inter", "numeros": "Inter"},
    "pesos": {"titulo": 800, "texto": 500},
    "tracking_titulo": -0.02,
    "caixa_titulo": "normal",
    "raio": 18,
    "material": "plano",
    "movimento": {"entrada_f": 15, "saida_f": 8, "ease_entrada": "expo.out", "ease_saida": "power3.in",
                  "overshoot": 0, "velocidade": 1},
}


class ErroEfeito(Exception):
    pass


# --------------------------------------------------------------- catálogo
def listar() -> dict[str, dict]:
    out = {}
    for d in sorted(EFEITOS.iterdir()):
        if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "efeito.json").exists():
            out[d.name] = json.loads((d / "efeito.json").read_text(encoding="utf-8"))
    return out


def carregar(nome: str) -> dict:
    todos = listar()
    if nome not in todos:
        raise ErroEfeito(f"efeito '{nome}' não existe; há: {', '.join(todos)}")
    return todos[nome]


def listar_estilos() -> dict[str, dict]:
    out = {}
    for d in sorted(ESTILOS.iterdir()) if ESTILOS.exists() else []:
        if d.is_dir() and (d / "tema.json").exists():
            out[d.name] = json.loads((d / "tema.json").read_text(encoding="utf-8"))
    return out


# --------------------------------------------------------------- tema
def mesclar_tema(*partes: dict) -> dict:
    out = json.loads(json.dumps(TEMA_PADRAO))
    for p in partes:
        for k, v in (p or {}).items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def tema_de(perfil_dir: str | os.PathLike | None = None, estilo: str | None = None,
            arquivo: str | os.PathLike | None = None) -> dict:
    """O tema de um perfil (tema.json dele), de um estilo da biblioteca ou de um arquivo."""
    if arquivo:
        return mesclar_tema(json.loads(Path(arquivo).read_text(encoding="utf-8")))
    if estilo:
        estilos = listar_estilos()
        if estilo not in estilos:
            raise ErroEfeito(f"estilo '{estilo}' não existe; há: {', '.join(estilos)}")
        return mesclar_tema(estilos[estilo])
    if perfil_dir:
        t = Path(perfil_dir) / "tema.json"
        if t.exists():
            return mesclar_tema(json.loads(t.read_text(encoding="utf-8")))
    return mesclar_tema()


def variaveis_do_tema(tema: dict, fps) -> dict:
    c, fo, pe, mo = tema["cores"], tema["fontes"], tema["pesos"], tema["movimento"]
    return {
        "cor_fundo": c["fundo"], "cor_superficie": c["superficie"], "cor_texto": c["texto"],
        "cor_texto_suave": c["texto_suave"], "cor_destaque": c["destaque"], "cor_apoio": c["apoio"],
        "fonte_titulo": fo["titulo"], "fonte_texto": fo["texto"], "fonte_numeros": fo.get("numeros", fo["titulo"]),
        "peso_titulo": pe["titulo"], "peso_texto": pe["texto"], "tracking_titulo": tema["tracking_titulo"],
        "caixa_titulo": tema.get("caixa_titulo", "normal"), "raio": tema["raio"], "material": tema["material"],
        "entrada_f": mo["entrada_f"], "saida_f": mo["saida_f"], "ease_entrada": mo["ease_entrada"],
        "ease_saida": mo["ease_saida"], "overshoot": mo["overshoot"], "velocidade": mo["velocidade"],
        "fps": float(Taxa.de(fps)),
    }


def _tipo(valor) -> str:
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, (int, float)):
        return "number"
    if isinstance(valor, str) and re.fullmatch(r"#[0-9A-Fa-f]{3,8}", valor):
        return "color"
    return "string"


# --------------------------------------------------------------- criar
def frames_e_duracao(duracao_s: float, fps) -> tuple[int, float]:
    """N frames na sequência e a duração da raiz: (N − 0,5)/fps, para o render não sair com 1 frame a mais."""
    taxa = Taxa.de(fps)
    n = max(1, taxa.frames(duracao_s))
    return n, round((n - 0.5) / float(taxa.fps), 6)


def interpretar_param(texto: str):
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def criar(nome: str, destino, tema: dict | None = None, params: dict | None = None,
          duracao: float | None = None, fps="30", formato: str = "16:9", gsap: str | None = None) -> dict:
    """Copia o efeito para `destino` (que não pode existir) já parametrizado. Devolve o resumo."""
    meta = carregar(nome)
    destino = Path(destino)
    if destino.exists() and any(destino.iterdir()):
        raise ErroEfeito(f"{destino} já existe e não está vazio: nunca sobrescrever um projeto")
    if formato not in FORMATOS:
        raise ErroEfeito(f"formato '{formato}' não existe; há: {', '.join(FORMATOS)}")
    w, h = FORMATOS[formato]
    tema = tema or mesclar_tema()
    d = meta["duracao"]
    duracao = float(duracao if duracao is not None else d["padrao"])
    if duracao < d.get("min", 0) or duracao > d.get("max", 1e9):
        raise ErroEfeito(f"{nome}: duração {duracao}s fora do intervalo do efeito ({d.get('min')}–{d.get('max')}s); "
                         "divida em cenas ou escolha outro efeito")
    n, dur_raiz = frames_e_duracao(duracao, fps)

    params = dict(params or {})
    declarados = {p["id"]: p for p in meta["parametros"]}
    desconhecidos = set(params) - set(declarados) - set(variaveis_do_tema(tema, fps))
    if desconhecidos:
        raise ErroEfeito(f"{nome}: parâmetros desconhecidos {sorted(desconhecidos)}; o efeito aceita {sorted(declarados)}")
    for pid, p in declarados.items():
        if p.get("obrigatorio") and pid not in params:
            raise ErroEfeito(f"{nome}: falta o parâmetro '{pid}' ({p['rotulo']})")

    imagens: dict[str, Path] = {}
    valores = variaveis_do_tema(tema, fps)
    decl = [{"id": k, "type": _tipo(v), "label": k, "default": v} for k, v in valores.items()]
    for pid, p in declarados.items():
        val = params.get(pid, p.get("padrao"))
        tipo = p["tipo"]
        if tipo == "lista":
            val = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
            tipo_hf = "string"
        elif tipo == "imagem":
            tipo_hf = "string"
        else:
            tipo_hf = {"texto": "string", "numero": "number", "cor": "color", "booleano": "boolean",
                       "opcao": "string"}.get(tipo, "string")
        if p["tipo"] == "imagem" and val:
            origem = Path(str(val)).expanduser()
            if not origem.exists():
                raise ErroEfeito(f"{nome}: a imagem de '{pid}' não existe: {origem}")
            imagens[pid] = origem
            val = f"assets/{pid}{origem.suffix.lower()}"
        if p["tipo"] == "opcao" and val not in p["opcoes"]:
            raise ErroEfeito(f"{nome}: '{pid}' precisa ser um de {p['opcoes']} (veio {val!r})")
        decl = [x for x in decl if x["id"] != pid]
        decl.append({"id": pid, "type": tipo_hf, "label": p["rotulo"], "default": val})
        valores[pid] = val
    for k in set(params) & set(variaveis_do_tema(tema, fps)):   # ajuste fino de tema por item
        for x in decl:
            if x["id"] == k:
                x["default"] = params[k]
        valores[k] = params[k]

    html = (EFEITOS / nome / "index.html").read_text(encoding="utf-8")
    m = re.search(r'id="root"[^>]*data-duration="([0-9.]+)"', html)
    if not m:
        raise ErroEfeito(f"{nome}: index.html sem #root com data-duration")
    dur_original = m.group(1)
    html = html.replace(f'data-duration="{dur_original}"', f'data-duration="{dur_raiz}"')
    html = re.sub(r'(id="root"[^>]*?)data-width="\d+"', rf'\1data-width="{w}"', html, count=1)
    html = re.sub(r'(id="root"[^>]*?)data-height="\d+"', rf'\1data-height="{h}"', html, count=1)
    html = re.sub(r'<meta name="viewport" content="[^"]*"', f'<meta name="viewport" content="width={w}, height={h}"', html)
    html = re.sub(r'(id="root"[^>]*?)data-fps="[^"]*"', rf'\1data-fps="{Taxa.de(fps)}"', html, count=1)
    decl_json = json.dumps(decl, ensure_ascii=False).replace("'", "&#39;")
    html = re.sub(r"data-composition-variables='[^']*'", f"data-composition-variables='{decl_json}'", html, count=1)
    html = html.replace('src="../_comum/tema.js"', 'src="tema.js"').replace('href="../_comum/tema.css"', 'href="tema.css"')

    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMUM / "tema.js", destino / "tema.js")
    # CSS embutido: com <link>, o desenho das letras mudou no render (guias/hyperframes.md)
    tema_css = (COMUM / "tema.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="tema.css" />', f"<style>\n{tema_css}</style>")
    if gsap:
        shutil.copy2(gsap, destino / "gsap.min.js")
        html = html.replace(GSAP_CDN, "gsap.min.js")
    for extra in (EFEITOS / nome).iterdir():
        if extra.name not in ("index.html", "efeito.json", "previa.gif", "previa.png") and extra.is_file():
            shutil.copy2(extra, destino / extra.name)
    for pid, origem in imagens.items():
        (destino / "assets").mkdir(exist_ok=True)
        shutil.copy2(origem, destino / "assets" / f"{pid}{origem.suffix.lower()}")
    (destino / "index.html").write_text(html, encoding="utf-8")
    eventos = eventos_som(meta, valores, n, fps)
    resumo = {"efeito": nome, "formato": formato, "tamanho": [w, h], "fps": str(Taxa.de(fps)), "frames": n,
              "duracao_raiz": dur_raiz, "variaveis": valores, "eventos_som": eventos,
              "saida": "mov" if meta["formato"] != "tela_cheia" else "mp4"}
    (destino / "efeito.json").write_text(json.dumps({**meta, "instancia": resumo}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    (destino / "eventos.json").write_text(json.dumps(eventos, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo


def _t(expr: str, n: int, fps) -> float:
    """'6f' a partir do início, '-8f' a partir do fim, '0.5s'. Um 'f' é sempre 1/30 s."""
    total = n / float(Taxa.de(fps).fps)
    e = str(expr).strip()
    if e.endswith("f"):
        s = int(e[:-1]) / 30
    elif e.endswith("s"):
        s = float(e[:-1])
    else:
        raise ErroEfeito(f"tempo de evento inválido: {expr!r} (use 6f, -8f ou 0.5s)")
    return s if s >= 0 else total + s


def eventos_som(meta: dict, valores: dict, n: int, fps) -> list[dict]:
    """Eventos para o som, em segundos a partir do início do efeito (somar o inicio_seq do item)."""
    out = []
    vel = float(valores.get("velocidade") or 1)
    for ev in meta.get("eventos_som", []):
        base = {k: ev[k] for k in ("tipo", "forca", "descricao") if k in ev}
        if ev.get("por_item"):
            itens = valores.get(ev["por_item"])
            if isinstance(itens, str):
                try:
                    itens = json.loads(itens)
                except json.JSONDecodeError:
                    itens = [x for x in itens.split("|") if x.strip()]
            t0 = _t(ev["t"], n, fps) / (vel if not str(ev["t"]).startswith("-") else 1)
            passo_txt = str(ev["passo"])
            if passo_txt.startswith("param:"):
                passo_txt = str(valores.get(passo_txt[6:]))
            passo = float(passo_txt.rstrip("f")) / 30 / vel
            for i in range(len(itens or [])):
                out.append({**base, "t": round(t0 + i * passo, 3), "item": i})
        else:
            t = _t(ev["t"], n, fps)
            if not str(ev["t"]).startswith("-"):
                t /= vel
            out.append({**base, "t": round(t, 3)})
    return sorted(out, key=lambda e: e["t"])


# --------------------------------------------------------------- hyperframes
def comando_hyperframes() -> list[str]:
    cmd = os.environ.get("HYPERFRAMES_CMD")
    if cmd:
        return shlex.split(cmd)
    return ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSAO}"]


def snapshots(projeto, tempos: list[float]) -> list[Path]:
    """Quadros PNG nos tempos pedidos (rápido; o render final é que leva tempo)."""
    lista = ",".join(f"{t:.3f}" for t in tempos)
    p = subprocess.run(comando_hyperframes() + ["snapshot", str(projeto), "--at", lista],
                       capture_output=True, text=True, cwd=str(projeto))
    achados = {}
    for x in re.findall(r"(/\S+?frame-(\d+)-at-[0-9.]+s\.png)", p.stdout + p.stderr):
        achados[int(x[1])] = Path(x[0])
    # o HyperFrames pode acrescentar um quadro final; ficam só os pedidos, na ordem
    caminhos = [achados[i] for i in sorted(achados) if i < len(tempos)]
    if p.returncode != 0 or len(caminhos) != len(tempos):
        raise ErroEfeito(f"snapshot falhou ({p.returncode}):\n{(p.stdout + p.stderr)[-1500:]}")
    return caminhos


def checar(projeto) -> tuple[bool, str]:
    p = subprocess.run(comando_hyperframes() + ["check", str(projeto)], capture_output=True, text=True,
                       cwd=str(projeto))
    saida = p.stdout + p.stderr
    return (p.returncode == 0 and "Check passed" in saida), saida


def previa(nome: str, saida, tema: dict | None = None, formato: str = "16:9", quadros: int = 36,
           largura: int = 480, params: dict | None = None, gsap: str | None = None, fundo: str | None = None) -> Path:
    """GIF de prévia: snapshots ao longo do efeito, sobre um fundo neutro quando é sobreposição."""
    from . import ff
    meta = carregar(nome)
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / nome
        r = criar(nome, proj, tema, params or meta.get("exemplo"), None, "30", formato, gsap)
        n = r["frames"]
        tempos = [round((i + 0.5) * (n - 1) / quadros / 30, 3) for i in range(quadros)]
        pngs = snapshots(proj, tempos)
        lista = Path(tmp) / "lista"
        lista.mkdir()
        for i, p in enumerate(pngs):
            shutil.copy2(p, lista / f"q{i:03d}.png")
        w, h = r["tamanho"]
        alt = int(round(h * largura / w / 2) * 2)
        sobre = meta["formato"] != "tela_cheia"
        fundo = fundo or str(COMUM / "fundo-previa.png")
        if sobre:
            filtro = (f"[0:v]scale={largura}:{alt}:force_original_aspect_ratio=increase,crop={largura}:{alt}[bg];"
                      f"[1:v]scale={largura}:{alt}[fg];[bg][fg]overlay=shortest=1,split[a][b];"
                      "[a]palettegen=max_colors=160[p];[b][p]paletteuse=dither=sierra2_4a")
            entradas = ["-loop", "1", "-framerate", "12", "-i", fundo, "-framerate", "12", "-i", str(lista / "q%03d.png")]
        else:
            filtro = (f"[0:v]scale={largura}:{alt},split[a][b];[a]palettegen=max_colors=160[p];"
                      "[b][p]paletteuse=dither=sierra2_4a")
            entradas = ["-framerate", "12", "-i", str(lista / "q%03d.png")]
        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        ff.rodar([ff.ffmpeg(), "-v", "error", "-y", *entradas, "-filter_complex", filtro, "-loop", "0", str(saida)])
    return saida


def vitrine(saida, tema: dict | None = None, efeitos: list[str] | None = None, formato: str = "16:9",
            colunas: int = 3, largura: int = 640, momento: float = 0.72, gsap: str | None = None,
            titulo: str = "") -> Path:
    """Uma imagem com vários efeitos parados no `momento` (fração da duração), no tema dado."""
    import cv2
    import numpy as np

    efeitos = efeitos or ["titulo-impacto", "contador", "barras", "comparacao", "card-lateral", "tarja-nome"]
    quadros = []
    with tempfile.TemporaryDirectory() as tmp:
        for nome in efeitos:
            meta = carregar(nome)
            proj = Path(tmp) / nome
            r = criar(nome, proj, tema, meta.get("exemplo"), None, "30", formato, gsap)
            t = round((r["frames"] - 1) * momento / 30, 3)
            png = snapshots(proj, [t])[0]
            img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
            if meta["formato"] != "tela_cheia":
                fundo = cv2.imread(str(COMUM / "fundo-previa.png"))
                fundo = cv2.resize(fundo, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_AREA)
                if img.shape[2] == 4:
                    a = img[..., 3:4].astype(np.float32) / 255
                    img = (img[..., :3] * a + fundo * (1 - a)).astype(np.uint8)
                else:
                    img = img[..., :3]
            else:
                img = img[..., :3]
            alt = int(round(img.shape[0] * largura / img.shape[1]))
            img = cv2.resize(img, (largura, alt), interpolation=cv2.INTER_AREA)
            cv2.putText(img, nome, (14, alt - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(img, nome, (14, alt - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            quadros.append(img)
    h, w = quadros[0].shape[:2]
    linhas = -(-len(quadros) // colunas)
    topo = 56 if titulo else 0
    grade = np.full((topo + linhas * (h + 8) + 8, colunas * (w + 8) + 8, 3), 18, np.uint8)
    if titulo:
        cv2.putText(grade, titulo, (16, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 2, cv2.LINE_AA)
    for i, q in enumerate(quadros):
        lin, col = divmod(i, colunas)
        y, x = topo + 8 + lin * (h + 8), 8 + col * (w + 8)
        grade[y:y + h, x:x + w] = q
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(saida), grade)
    return saida
