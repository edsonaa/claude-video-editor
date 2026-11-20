"""Galeria do painel: o que dá para escolher e pôr no vídeo sem sair do navegador.

Legendas (os estilos de legendas/estilos.json), animações (a biblioteca de efeitos,
tocando no navegador com o tema do vídeo), transições (transicoes/transicoes.json)
e sons (a biblioteca da pessoa, ou o pacote inicial do motor). Tudo o que entra
por aqui vai para o estado do vídeo com `origem: "painel"`, onde o Claude lê:

- animação: um item do plano (`motions.itens`, status `aprovado`, com `efeito` e `params`);
- transição: `cortes.segmentos[i].transicao` do segmento que entra;
- som: um item de `sfx.itens` (alinhado pelo pico no ponto do cursor, arquivo copiado
  para os assets do projeto);
- legenda: `video.legendas.estilo` (e um pedido para refazer os blocos, se a divisão mudou).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from . import efeitos as EF
from . import estado as E
from . import legendas as L
from . import sons as S
from . import transicoes as TR
from .linha import Linha
from .tempo import Taxa

GSAP_ARQ = "gsap.min.js"
IMAGENS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
ORIGEM = "painel"

# A página do efeito no navegador: as variáveis vêm do próprio HTML (o padrão de cada uma)
# e um tocador simples recebe ordens da galeria (tocar, parar, ir) por postMessage.
_SHIM = """<script>
window.__hyperframes = { getVariables() {
  const d = JSON.parse(document.documentElement.dataset.compositionVariables || "[]"), o = {};
  for (const x of d) o[x.id] = x.default;
  return o;
} };
</script>"""
_TOCADOR = """<script>
(function () {
  const tl = (window.__timelines || {}).efeito;
  if (!tl) return;
  document.documentElement.style.background = "transparent";
  document.body.style.background = "transparent";
  document.body.style.margin = "0";
  const D = tl.duration();
  let laco = null;
  const pose = () => tl.pause().seek(D * 0.62, false);
  pose();
  function tocar() {
    clearTimeout(laco);
    tl.eventCallback("onComplete", () => { laco = setTimeout(() => tl.restart(), 700); });
    tl.restart();
  }
  window.addEventListener("message", (e) => {
    const m = e.data || {};
    if (m.cmd === "tocar") tocar();
    else if (m.cmd === "parar") { clearTimeout(laco); tl.eventCallback("onComplete", null); pose(); }
    else if (m.cmd === "ir") { clearTimeout(laco); tl.pause().seek(Math.max(0, Math.min(D, m.t || 0)), false); }
  });
  parent.postMessage({ efeitoPronto: true, duracao: D }, "*");
})();
</script>"""


class ErroGaleria(E.ErroEstado):
    pass


def _cfg() -> dict:
    try:
        from . import config as C
        return C.carregar(obrigatorio=False) or {}
    except Exception:  # noqa: BLE001 (sem configuração: só o motor)
        return {}


def _tema(d: dict, cfg: dict) -> dict:
    from . import config as C
    perfil = d.get("perfil") or cfg.get("perfil_padrao")
    try:
        return EF.tema_de(perfil_dir=C.pasta() / "perfis" / perfil) if perfil else EF.mesclar_tema()
    except Exception:  # noqa: BLE001 (perfil sumiu ou quebrado: o tema neutro)
        return EF.mesclar_tema()


def _formato(d: dict, cfg: dict) -> str:
    return (d.get("video") or {}).get("formato") or (cfg.get("video") or {}).get("formato") or "16:9"


def _gsap_local() -> Path | None:
    for c in (os.environ.get("GSAP_LOCAL"),):
        if c and Path(c).is_file():
            return Path(c)
    return None


def _raiz(pasta) -> Path:
    return E.caminho_estado(pasta).parent.parent


def _pasta_assets(pasta, cfg: dict) -> Path:
    return _raiz(pasta) / ((cfg.get("pastas") or {}).get("assets") or "Assets")


# ------------------------------------------------------------------ o que mostrar
def biblioteca_sons(cfg: dict | None = None) -> Path | None:
    cfg = _cfg() if cfg is None else cfg
    b = (cfg.get("som") or {}).get("biblioteca")
    return Path(b).expanduser() if b else None


def indice_sons(cfg: dict | None = None, reindexar: bool = False) -> dict | None:
    """O índice da biblioteca (indexa na hora se ainda não houver)."""
    bib = biblioteca_sons(cfg)
    if not bib or not bib.is_dir():
        return None
    arq = bib / "indice.json"
    velho = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
    if velho and not reindexar:
        return velho
    ind = S.indexar(bib, velho)
    ind.pop("reaproveitados", None)
    erros = ind.pop("erros", [])
    arq.write_text(json.dumps(ind, ensure_ascii=False, indent=2), encoding="utf-8")
    ind["erros"] = erros
    return ind


def catalogo(pasta) -> dict:
    d = E.ler(pasta)
    cfg = _cfg()
    try:
        atual = L.opcoes_legenda(d, cfg)
    except ValueError:
        atual = L.opcoes_legenda(None, {})
    legendas = [{"id": k, **{c: v for c, v in e.items() if c != "_estoque"}, "estoque": _resumo_estoque(e.get("_estoque"))}
                for k, e in L.estilos_legenda().items()]
    animacoes = []
    for nome, m in EF.listar().items():
        es = m.get("_estoque")
        animacoes.append({"id": nome, "titulo": m["titulo"], "descricao": m["descricao"], "formato": m["formato"],
                          "duracao": m["duracao"], "parametros": m["parametros"], "exemplo": m.get("exemplo") or {},
                          "bom_para": m.get("bom_para", ""), "evitar": m.get("evitar", ""), "tags": m.get("tags", []),
                          "categoria": (es or {}).get("tipo") or ("motion" if "motion" in m.get("tags", []) else "efeito"),
                          "estoque": _resumo_estoque(es)})
    transicoes = [{"id": k, "titulo": t["titulo"], "descricao": t["descricao"], "bom_para": t["bom_para"],
                   "evitar": t["evitar"], "duracao": t["duracao"], "aproximada_xml": bool(t["xml"].get("aproximada")),
                   "previa": t.get("previa"), "estoque": _resumo_estoque(t.get("_estoque"))}
                  for k, t in TR.listar().items()]
    sons: dict = {"biblioteca": None, "categorias": {}, "erro": None}
    bib = biblioteca_sons(cfg)
    if bib:
        sons["biblioteca"] = str(bib)
        if not bib.is_dir():
            sons["erro"] = f"a pasta da biblioteca não existe: {bib}"
        else:
            ind = indice_sons(cfg) or {"sons": []}
            for s in ind["sons"]:
                sons["categorias"].setdefault(s["categoria"], []).append(
                    {"id": s["id"], "nome": Path(s["arquivo"]).stem, "arquivo": s["arquivo"], "duracao": s["duracao"],
                     "pico": s["pico"], "nota": s.get("nota") or "", "licenca": s.get("licenca") or "",
                     "favorito": bool(s.get("favorito"))})
    imagens = []
    assets = _pasta_assets(pasta, cfg)
    if assets.is_dir():
        imagens = sorted(p.relative_to(assets).as_posix() for p in assets.rglob("*")
                         if p.is_file() and p.suffix.lower() in IMAGENS and not p.name.startswith("."))[:200]
    return {"formato": _formato(d, cfg), "legenda_atual": {"estilo": atual["estilo"]["id"], "posicao": atual["posicao"],
                                                         "ativas": atual["ativas"], "queimar": atual["queimar"]},
            "legendas": legendas, "animacoes": animacoes, "transicoes": transicoes, "sons": sons,
            "imagens": imagens, "gsap_local": bool(_gsap_local())}


def _resumo_estoque(es: dict | None) -> dict | None:
    return {"nome": es["nome"], "gostei": es.get("gostei", ""), "status": es.get("status")} if es else None


# ------------------------------------------------------------------ a página de um efeito
def _params_limpos(meta: dict, params: dict | None, pasta=None, cfg: dict | None = None) -> dict:
    """Só os parâmetros que o efeito declara; imagens viram caminho absoluto dentro dos assets do projeto."""
    decl = {p["id"]: p for p in meta["parametros"]}
    out = {}
    for k, v in (params or {}).items():
        if k not in decl or v is None or v == "":
            continue
        if decl[k]["tipo"] == "imagem":
            if pasta is None:
                continue
            base = _pasta_assets(pasta, cfg or {}).resolve()
            alvo = (base / str(v)).resolve()
            if base not in alvo.parents or not alvo.is_file():
                raise ErroGaleria(f"a imagem '{v}' não está na pasta de assets do projeto")
            v = str(alvo)
        elif decl[k]["tipo"] == "numero":
            v = float(v)
        elif decl[k]["tipo"] == "booleano":
            v = bool(v)
        out[k] = v
    return out


def pagina_efeito(pasta, nome: str, params: dict | None = None, formato: str | None = None,
                  duracao: float | None = None) -> str:
    """O HTML do efeito, com o tema do vídeo e o conteúdo dado, autossuficiente para tocar no navegador."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", nome or ""):
        raise ErroGaleria("efeito inválido")
    try:
        meta = EF.carregar(nome)
    except Exception as e:  # noqa: BLE001
        raise ErroGaleria(str(e)) from e
    d = E.ler(pasta)
    cfg = _cfg()
    formato = formato or _formato(d, cfg)
    params = {**(meta.get("exemplo") or {}), **_params_limpos(meta, params, pasta, cfg)}
    params = {k: v for k, v in params.items() if not (
        any(p["id"] == k and p["tipo"] == "imagem" for p in meta["parametros"]) and not Path(str(v)).is_absolute())}
    gsap = _gsap_local()
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / nome
        try:
            EF.criar(nome, proj, _tema(d, cfg), params, duracao, "30", formato, str(gsap) if gsap else None)
        except EF.ErroEfeito as e:
            raise ErroGaleria(str(e)) from e
        html = (proj / "index.html").read_text(encoding="utf-8")
        tema_js = (proj / "tema.js").read_text(encoding="utf-8")
        html = html.replace('<script src="tema.js"></script>', f"<script>\n{tema_js}\n</script>")
        if gsap:
            html = html.replace(f'<script src="{GSAP_ARQ}"></script>', f"<script>\n{gsap.read_text(encoding='utf-8')}\n</script>")
        for img in (proj / "assets").glob("*") if (proj / "assets").is_dir() else []:
            if img.stat().st_size > 8 * 1024 * 1024:
                continue
            tipo = {"svg": "image/svg+xml", "jpg": "image/jpeg"}.get(img.suffix[1:].lower(), f"image/{img.suffix[1:].lower()}")
            uri = f"data:{tipo};base64,{base64.b64encode(img.read_bytes()).decode()}"
            html = html.replace(f"assets/{img.name}", uri)
    html = html.replace("<head>", "<head>\n" + _SHIM, 1)
    html = html.replace("</body>", _TOCADOR + "\n</body>", 1)
    return html


# ------------------------------------------------------------------ pôr no vídeo
def _linha(d: dict) -> Linha:
    segs = (d.get("cortes") or {}).get("segmentos") or []
    fps = (d.get("midia") or {}).get("fps")
    if not segs or not fps:
        raise ErroGaleria("o vídeo ainda não tem corte: a galeria põe as coisas sobre o corte")
    return Linha(segs, Taxa.de(fps))


def inserir_animacao(d: dict, pasta, efeito: str, params: dict | None, inicio_seq: float,
                     duracao: float | None = None) -> str:
    try:
        meta = EF.carregar(efeito)
    except Exception as e:  # noqa: BLE001
        raise ErroGaleria(str(e)) from e
    cfg = _cfg()
    limpos = _params_limpos(meta, params, pasta, cfg)
    dur = float(duracao if duracao is not None else meta["duracao"]["padrao"])
    # confere tudo como o motion-render vai fazer (parâmetros obrigatórios, opções, duração)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            EF.criar(efeito, Path(tmp) / "x", _tema(d, cfg), {**limpos}, dur, "30", _formato(d, cfg))
        except EF.ErroEfeito as e:
            raise ErroGaleria(str(e)) from e
    total = _linha(d).duracao
    ini = max(0.0, min(float(inicio_seq), max(0.0, total - dur)))
    itens = d.setdefault("motions", {}).setdefault("itens", [])
    mid = E.proximo_id(itens, "mo")
    resumo = ", ".join(str(v) for k, v in limpos.items()
                       if not any(p["id"] == k and p["tipo"] == "imagem" for p in meta["parametros"]))[:120]
    itens.append({"id": mid, "status": "aprovado", "inicio_seq": round(ini, 3), "fim_seq": round(ini + dur, 3),
                  "formato": meta["formato"], "efeito": efeito, "params": limpos,
                  "ideia": f"{meta['titulo']}" + (f": {resumo}" if resumo else "") + " (escolhida na galeria do painel)",
                  "origem": ORIGEM})
    itens.sort(key=lambda x: (x.get("inicio_seq") is None, x.get("inicio_seq") or 0))
    return mid


def corte_mais_perto(d: dict, t: float) -> dict | None:
    """O corte (junção entre segmentos) mais perto do tempo t: {id do que entra, tempo}."""
    linha = _linha(d)
    juntas = [(p.id, linha.taxa.segundos(p.seq_ini)) for p in linha.pedacos[1:]]
    if not juntas:
        return None
    sid, tc = min(juntas, key=lambda j: abs(j[1] - t))
    return {"id": sid, "tempo": round(tc, 3)}


def mudar_transicao(d: dict, sid: str, transicao: dict | None) -> dict | None:
    segs = (d.get("cortes") or {}).get("segmentos") or []
    linha = _linha(d)
    if linha.pedacos and linha.pedacos[0].id == sid:
        raise ErroGaleria(f"{sid} é o primeiro segmento: não há corte antes dele")
    s = next((x for x in segs if x["id"] == sid), None)
    if not s:
        raise ErroGaleria(f"segmento {sid} não encontrado")
    try:
        tr = TR.normalizar(transicao)
    except TR.ErroTransicao as e:
        raise ErroGaleria(str(e)) from e
    if tr:
        s["transicao"] = {**tr, "origem": ORIGEM}
    else:
        s.pop("transicao", None)
    return tr


def arquivo_som(som_id: str, cfg: dict | None = None) -> Path | None:
    cfg = _cfg() if cfg is None else cfg
    ind = indice_sons(cfg)
    bib = biblioteca_sons(cfg)
    if not ind or not bib:
        return None
    s = next((x for x in ind["sons"] if x["id"] == som_id), None)
    if not s:
        return None
    arq = (bib / s["arquivo"]).resolve()
    return arq if bib.resolve() in arq.parents and arq.is_file() else None


def inserir_som(d: dict, pasta, som_id: str, tempo_seq: float, ganho_db: float = -12.0,
                alinhar_pico: bool = True) -> str:
    cfg = _cfg()
    ind = indice_sons(cfg)
    s = next((x for x in (ind or {}).get("sons", []) if x["id"] == som_id), None)
    arq = arquivo_som(som_id, cfg)
    if not s or not arq:
        raise ErroGaleria(f"o som '{som_id}' não está na biblioteca")
    total = _linha(d).duracao
    ini = float(tempo_seq) - (s["pico"] if alinhar_pico else 0.0)
    ini = max(0.0, min(ini, total - 0.05))
    destino = _pasta_assets(pasta, cfg) / "sons" / arq.name
    if not destino.exists() or destino.stat().st_size != arq.stat().st_size:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arq, destino)
    sfx = d.setdefault("sfx", {})
    itens = sfx.setdefault("itens", [])
    sid = E.proximo_id(itens, "sfx")
    itens.append({"id": sid, "evento": f"escolhido na galeria do painel em {tempo_seq:.2f} s",
                  "camada": "principal", "arquivo": str(destino.resolve()), "inicio_seq": round(ini, 3),
                  "duracao": s["duracao"], "canais": s.get("canais", 2), "ganho_db": round(float(ganho_db), 1),
                  "categoria": s["categoria"], "pico": s["pico"], "origem": ORIGEM})
    itens.sort(key=lambda x: x.get("inicio_seq") or 0)
    return sid


def escolher_legenda(d: dict, estilo: str, posicao: str | None = None) -> dict:
    """Troca o estilo de legenda deste vídeo. Devolve {"refazer": bool} (a divisão em blocos mudou)."""
    try:
        novo = L.estilo_legenda(estilo)
    except ValueError as e:
        raise ErroGaleria(str(e)) from e
    if posicao and posicao not in L.POSICOES:
        raise ErroGaleria(f"posição '{posicao}' não existe ({', '.join(L.POSICOES)})")
    cfg = _cfg()
    try:
        antes = L.opcoes_legenda(d, cfg)
    except ValueError:
        antes = L.opcoes_legenda(None, {})
    v = d.setdefault("video", {}).setdefault("legendas", {})
    v["estilo"] = estilo
    if posicao:
        v["posicao"] = posicao
    if novo["modo"] == "palavra":
        v["queimar"] = True
    depois = L.opcoes_legenda(d, cfg)
    tem_blocos = bool((d.get("legendas") or {}).get("arquivo"))
    divisao = ("modo", "max_caracteres", "linhas", "caixa_alta")
    refazer = tem_blocos and any(antes.get(k) != depois.get(k) for k in divisao)
    if refazer:
        E.nova_pendencia(d, "legendas" if "legendas" in d.get("fluxo", []) else (E.proxima_etapa(d) or "legendas"),
                         f"Gerar as legendas de novo no estilo {novo['titulo']} (escolhido no painel): "
                         "a divisão em blocos mudou", None)
        d["pendencias"][-1]["origem"] = ORIGEM
    return {"refazer": refazer, "estilo": estilo, "titulo": novo["titulo"]}


def html_escape(t: str) -> str:
    import html
    return html.escape(t)


def criar_pacote_sons() -> dict:
    """O pacote inicial do motor na pasta da pessoa, e a biblioteca da configuração apontando para ele
    (se ainda não houver uma)."""
    from . import config as C
    cfg = C.carregar(obrigatorio=False)
    if cfg is None:
        raise ErroGaleria("sem configuração ainda: rode /edicao:montar antes")
    atual = biblioteca_sons(cfg)
    destino = atual if atual else C.pasta() / "sons"
    r = S.pacote_inicial(destino)
    if not atual:
        cfg.setdefault("som", {})["biblioteca"] = str(destino)
        C.gravar(cfg)
    r["configurada"] = not atual
    return r


# ------------------------------------------------------------------ o estoque da pessoa
ARQUIVOS_ESTOQUE = {"trecho": ("trecho.mp4",), "previa": ("previa.gif", "previa.png"), "folha": ("folha.png",),
                    "referencia": ("referencia.png", "referencia.jpg", "referencia.jpeg", "referencia.webp",
                                   "referencia.gif")}


def estoque() -> dict:
    """O que o painel mostra do estoque: o que espera o Claude, o que espera aprovação e o que já
    está valendo, com o que dá para usar de base ("parecido com")."""
    from . import estoque as ES
    lista = []
    for it in ES.itens():
        if it["status"] == "recusado":
            continue
        p = Path(it["pasta"])
        arquivos = {k: next((n for n in ns if (p / n).exists()), None) for k, ns in ARQUIVOS_ESTOQUE.items()}
        dd = ES.dados(it) if it["status"] in ("rascunho", "ativo", "arquivado") else None
        lista.append({k: it.get(k) for k in ("id", "tipo", "nome", "gostei", "status", "parecido_com", "criado_em",
                                             "ajustes", "analise", "por", "origem", "base")}
                     | {"arquivos": {k: bool(v) for k, v in arquivos.items()}, "dados": dd})
    bases = {"legenda": [{"id": k, "titulo": v["titulo"]} for k, v in L.estilos_legenda().items()],
             "transicao": [{"id": k, "titulo": v["titulo"]} for k, v in TR.listar().items()],
             "efeito": [{"id": k, "titulo": v["titulo"]} for k, v in EF.listar().items()]}
    bases["motion"] = bases["efeito"]
    return {"itens": lista, "resumo": ES.resumo(), "tipos": ES.NOME_TIPO, "bases": bases, "pasta": str(ES.raiz())}


def arquivo_estoque(ident: str, qual: str) -> Path | None:
    from . import estoque as ES
    try:
        it = ES.item(ident)
    except ES.ErroEstoque:
        return None
    for n in ARQUIVOS_ESTOQUE.get(qual, ()):
        if (Path(it["pasta"]) / n).is_file():
            return Path(it["pasta"]) / n
    return None
