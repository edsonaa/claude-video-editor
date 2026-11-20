"""O estoque da pessoa: estilos de legenda, transições, efeitos e motions dela, fora do motor.

Fica em `<pessoa>/estoque/` (não some quando o plugin atualiza) e passa pelas mesmas portas
do motor: os estilos de legenda, as transições e os efeitos ativos aparecem na galeria do
painel, nas boas-vindas, no plano de animação, no render e no XML como os do motor.

    <pessoa>/estoque/
      entrada/<id>/        o que chegou e espera o Claude analisar
        item.json          {id, tipo, nome, gostei, parecido_com, origem, status: "entrada", ...}
        ficha.md           nome, tipo, o que gostou, de onde veio (e, depois, a análise)
        trecho.mp4         o pedaço de vídeo de referência (se houver)
      legendas/<id>/       estilo.json  (os campos de legendas/estilos.json)
      transicoes/<id>/     transicao.json (os campos de transicoes/transicoes.json, com "previa")
      efeitos/<id>/        index.html + efeito.json (como em efeitos/), previa.gif
      motions/<id>/        idem: um efeito cujo ponto é o jeito de mover

    status: entrada → rascunho (o Claude construiu; a pessoa vê a prévia) → ativo | recusado;
    ativo → arquivado. Ajuste pedido num rascunho fica em item.json "ajustes" e na ficha.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
import re
import shutil
import unicodedata

TIPOS = {"legenda": "legendas", "transicao": "transicoes", "efeito": "efeitos", "motion": "motions"}
NOME_TIPO = {"legenda": "Estilo de legenda", "transicao": "Transição", "efeito": "Efeito", "motion": "Motion"}
DADOS = {"legenda": "estilo.json", "transicao": "transicao.json", "efeito": "efeito.json", "motion": "efeito.json"}
STATUS = ("entrada", "rascunho", "ativo", "recusado", "arquivado")
TRECHO_MAX = 90.0          # segundos de referência por peça


class ErroEstoque(ValueError):
    pass


def agora() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def raiz() -> Path:
    from . import config as C
    return C.pasta() / "estoque"


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:40] or "peca"


def _ler(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _gravar(p: Path, d: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


# ------------------------------------------------------------------ onde estão as peças
def _pastas_itens():
    r = raiz()
    for sub in ("entrada", *TIPOS.values()):
        base = r / sub
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir() and (d / "item.json").exists():
                    yield d


def itens(tipo: str | None = None, status: tuple[str, ...] | None = None) -> list[dict]:
    """Os itens do estoque (com "pasta"), na ordem de chegada."""
    out = []
    for d in _pastas_itens():
        try:
            it = _ler(d / "item.json")
        except (OSError, ValueError):
            continue
        if tipo and it.get("tipo") != tipo:
            continue
        if status and it.get("status") not in status:
            continue
        out.append({**it, "pasta": str(d)})
    out.sort(key=lambda x: x.get("criado_em", ""))
    return out


def item(ident: str) -> dict:
    for it in itens():
        if it["id"] == ident:
            return it
    raise ErroEstoque(f"'{ident}' não está no estoque")


def dados(it: dict) -> dict | None:
    arq = Path(it["pasta"]) / DADOS[it["tipo"]]
    return _ler(arq) if arq.exists() else None


def pecas(tipo: str, rascunhos: bool = False) -> dict[str, dict]:
    """{id: dados da peça} das ativas (e rascunhos, para prévia), para o motor juntar às dele."""
    st = ("ativo", "rascunho") if rascunhos else ("ativo",)
    out = {}
    for it in itens(tipo, st):
        dd = dados(it)
        if dd is not None:
            out[it["id"]] = {**dd, "_estoque": {"status": it["status"], "nome": it["nome"], "gostei": it.get("gostei", ""),
                                               "tipo": it["tipo"], "pasta": it["pasta"]}}
    return out


def pasta_efeito(nome: str) -> Path | None:
    """A pasta de um efeito/motion do estoque (ativo ou rascunho)."""
    for t in ("efeito", "motion"):
        for it in itens(t, ("ativo", "rascunho")):
            if it["id"] == nome:
                return Path(it["pasta"])
    return None


def _ids_ocupados() -> set[str]:
    ocup = {it["id"] for it in itens()}
    try:
        from . import efeitos as EF
        ocup |= set(EF.listar(estoque=False))
    except Exception:  # noqa: BLE001
        pass
    from . import legendas as L
    from . import transicoes as TR
    ocup |= set(L.estilos_legenda(estoque=False)) | set(TR.listar(estoque=False))
    return ocup


def _novo_id(nome: str) -> str:
    base, ocup = _slug(nome), _ids_ocupados()
    ident, k = base, 2
    while ident in ocup:
        ident, k = f"{base}-{k}", k + 1
    return ident


# ------------------------------------------------------------------ a ficha
def _fmt(t: float | None) -> str:
    if t is None:
        return "—"
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}".replace(".", ",")


def escrever_ficha(it: dict) -> Path:
    o = it.get("origem") or {}
    if o.get("tipo") == "arquivo":
        origem = f"o arquivo {o.get('nome') or 'enviado'}" + (f", de {_fmt(o.get('de'))} a {_fmt(o.get('ate'))}"
                                                              if o.get("de") is not None else "")
    elif o.get("tipo") == "video":
        origem = f"o vídeo {o.get('projeto')}, de {_fmt(o.get('de'))} a {_fmt(o.get('ate'))} da sequência"
    else:
        origem = "só a descrição (sem trecho)"
    linhas = [f"# {it['nome']}", "",
              f"- **Tipo:** {NOME_TIPO[it['tipo']]}",
              f"- **O que gostei:** {it.get('gostei') or '—'}",
              *([f"- **Parecido com:** {it['parecido_com']}"] if it.get("parecido_com") else []),
              f"- **De onde veio:** {origem}" + (" (`trecho.mp4` nesta pasta)" if it.get("trecho") else ""),
              f"- **Enviado em:** {it['criado_em'][:16].replace('T', ' ')}, {'pelo painel' if it.get('por') == 'painel' else 'pelo Claude'}",
              f"- **Status:** {it['status']}", ""]
    analise = (it.get("analise") or "").strip()
    linhas += ["## Análise", "", analise or "_(o Claude preenche ao analisar: o que mediu e como construiu)_", ""]
    if it.get("ajustes"):
        linhas += ["## Ajustes pedidos", ""] + [f"- {a['em'][:10]}: {a['texto']}" + (" ✓" if a.get("feito") else "")
                                               for a in it["ajustes"]] + [""]
    arq = Path(it["pasta"]) / "ficha.md"
    arq.write_text("\n".join(linhas), encoding="utf-8")
    return arq


def _salvar(it: dict) -> dict:
    limpo = {k: v for k, v in it.items() if k != "pasta"}
    _gravar(Path(it["pasta"]) / "item.json", limpo)
    escrever_ficha(it)
    return it


# ------------------------------------------------------------------ entrada
def _gitignore() -> None:
    """A pasta da pessoa é versionada: fichas, JSON e HTML entram; vídeos e prévias, não."""
    gi = raiz() / ".gitignore"
    if not gi.exists():
        gi.write_text("_envios/\n*.mp4\n*.mov\n*.webm\n*.gif\nfolha.png\nprevia.png\n", encoding="utf-8")



def _cortar_trecho(origem: Path, destino: Path, de: float | None, ate: float | None) -> float:
    from . import ff
    dur_total = float((ff.sondar(origem).get("format") or {}).get("duration") or 0)
    a = max(0.0, float(de or 0))
    b = float(ate) if ate is not None else dur_total or a + TRECHO_MAX
    if dur_total:
        b = min(b, dur_total)
    if b - a <= 0.05:
        raise ErroEstoque("o trecho ficou vazio: confira o início e o fim")
    if b - a > TRECHO_MAX:
        raise ErroEstoque(f"o trecho tem {b - a:.0f} s; o máximo é {TRECHO_MAX:.0f} s (escolha só a parte que importa)")
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{a:.3f}", "-i", str(origem), "-t", f"{b - a:.3f}",
              "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destino)])
    return round(b - a, 3)


def nova_entrada(tipo: str, nome: str, gostei: str, arquivo: str | os.PathLike | None = None,
                 de: float | None = None, ate: float | None = None, parecido_com: str | None = None,
                 por: str = "claude", origem: dict | None = None) -> dict:
    """Uma peça nova na entrada do estoque, esperando o Claude analisar."""
    if tipo not in TIPOS:
        raise ErroEstoque(f"tipo '{tipo}' não existe; use {', '.join(TIPOS)}")
    nome = " ".join((nome or "").split())
    gostei = (gostei or "").strip()
    if not nome:
        raise ErroEstoque("dê um nome para a peça")
    if not gostei:
        raise ErroEstoque("conte o que você gostou: é o que guia a análise")
    ident = _novo_id(nome)
    pasta = raiz() / "entrada" / ident
    pasta.mkdir(parents=True)
    _gitignore()
    it = {"id": ident, "tipo": tipo, "nome": nome, "gostei": gostei, "parecido_com": parecido_com or None,
          "status": "entrada", "criado_em": agora(), "por": por, "trecho": None,
          "origem": origem or ({"tipo": "arquivo", "nome": Path(arquivo).name, "de": de, "ate": ate} if arquivo else {"tipo": "nenhum"}),
          "pasta": str(pasta)}
    try:
        if arquivo:
            arq = Path(arquivo)
            if not arq.is_file():
                raise ErroEstoque(f"não achei o arquivo {arq}")
            if arq.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                shutil.copy2(arq, pasta / f"referencia{arq.suffix.lower()}")
                it["trecho"] = f"referencia{arq.suffix.lower()}"
            else:
                it["duracao_trecho"] = _cortar_trecho(arq, pasta / "trecho.mp4", de, ate)
                it["trecho"] = "trecho.mp4"
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    return _salvar(it)


def entrada_do_video(pasta_video, tipo: str, nome: str, gostei: str, de: float, ate: float,
                     parecido_com: str | None = None, por: str = "painel") -> dict:
    """Um trecho da sequência do vídeo aberto vira referência: corta da gravação de origem, a
    partir do ponto `de` (até o fim daquele segmento, se o trecho passar dele)."""
    from . import estado as E
    from .linha import Linha
    from .tempo import Taxa
    d = E.ler(pasta_video)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise ErroEstoque("o vídeo ainda não tem corte")
    linha = Linha(segs, Taxa.de(d["midia"]["fps"]))
    o = linha.seq_para_origem(float(de))
    if not o:
        raise ErroEstoque("esse ponto está fora do vídeo")
    video, t, ped = o
    arqs = {a["id"]: a for a in (d.get("midia") or {}).get("arquivos") or []}
    base = E.caminho_estado(pasta_video).parent.parent
    caminho = Path(arqs[video]["caminho"])
    caminho = caminho if caminho.is_absolute() else base / caminho
    fim_seg = linha.taxa.segundos(ped.out_f)
    dur = min(float(ate) - float(de), fim_seg - t)
    return nova_entrada(tipo, nome, gostei, caminho, t, t + dur, parecido_com, por,
                        origem={"tipo": "video", "projeto": d.get("projeto"), "de": round(float(de), 3),
                                "ate": round(float(de) + dur, 3), "video": video, "tempo": round(t, 3)})


# ------------------------------------------------------------------ do rascunho ao estoque
def construir(ident: str, base: str | None = None) -> dict:
    """Tira a peça da entrada e abre o rascunho na pasta do tipo, com uma base do motor (ou do
    estoque) para começar: o Claude ajusta os dados (e o HTML, num efeito) a partir da análise."""
    it = item(ident)
    if it["status"] != "entrada":
        raise ErroEstoque(f"{ident} já está como {it['status']}")
    tipo = it["tipo"]
    destino = raiz() / TIPOS[tipo] / ident
    if destino.exists():
        raise ErroEstoque(f"já existe {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(it["pasta"], destino)
    it["pasta"] = str(destino)
    base = base or it.get("parecido_com")
    if tipo == "legenda":
        from . import legendas as L
        est = dict(L.estilo_legenda(base or "classica"))
        est.pop("_estoque", None)
        est.update({"titulo": it["nome"], "descricao": it["gostei"]})
        _gravar(destino / "estilo.json", est)
    elif tipo == "transicao":
        from . import transicoes as TR
        tr = dict(TR.carregar(base or "dissolver"))
        for k in ("id", "_estoque"):
            tr.pop(k, None)
        tr.update({"titulo": it["nome"], "descricao": it["gostei"]})
        _gravar(destino / "transicao.json", tr)
    else:
        from . import efeitos as EF
        origem = EF.pasta_efeito(base or ("titulo-impacto" if tipo == "motion" else "tarja-nome"))
        for f in origem.iterdir():
            if f.is_file() and f.name not in ("previa.gif", "previa.png", "item.json", "ficha.md", "trecho.mp4"):
                shutil.copy2(f, destino / f.name)
        meta = _ler(destino / "efeito.json")
        meta.update({"titulo": it["nome"], "descricao": it["gostei"]})
        meta.setdefault("tags", [])
        _gravar(destino / "efeito.json", meta)
        # o HTML usa ../_comum/tema.*: o criar troca pelos do motor, onde quer que o efeito esteja
    it.update({"status": "rascunho", "base": base, "construido_em": agora()})
    return _salvar(it)


def verificar(ident: str) -> list[str]:
    """O que impede a peça de entrar no estoque (lista vazia = pronta)."""
    it = item(ident)
    erros = []
    dd = dados(it)
    if dd is None:
        return [f"falta {DADOS[it['tipo']]} em {it['pasta']}"]
    t = it["tipo"]
    if t == "legenda":
        from . import legendas as L
        modelo = L.estilos_legenda(estoque=False)["classica"]
        faltam = [k for k in modelo if k not in dd]
        if faltam:
            erros.append(f"faltam campos: {', '.join(faltam)}")
        if dd.get("modo") not in ("frase", "palavra"):
            erros.append("modo precisa ser frase ou palavra")
        if dd.get("posicao") not in L.POSICOES:
            erros.append(f"posição precisa ser {', '.join(L.POSICOES)}")
    elif t == "transicao":
        from . import transicoes as TR
        try:
            TR.validar(dd)
        except TR.ErroTransicao as e:
            erros.append(str(e))
    else:
        from . import efeitos as EF
        try:
            EF.validar_pasta(Path(it["pasta"]))
        except EF.ErroEfeito as e:
            erros.append(str(e))
    return erros


def aprovar(ident: str) -> dict:
    it = item(ident)
    if it["status"] not in ("rascunho", "arquivado"):
        raise ErroEstoque(f"{ident} está como {it['status']}: só um rascunho (ou arquivado) entra no estoque")
    erros = verificar(ident)
    if erros:
        raise ErroEstoque(f"{ident} ainda não está pronto: " + "; ".join(erros))
    it.update({"status": "ativo", "aprovado_em": agora()})
    for a in it.get("ajustes") or []:
        a["feito"] = True
    return _salvar(it)


def mudar_status(ident: str, status: str, motivo: str | None = None) -> dict:
    if status not in ("recusado", "arquivado", "rascunho"):
        raise ErroEstoque(f"status '{status}' não vale aqui")
    it = item(ident)
    if status == "arquivado" and it["status"] != "ativo":
        raise ErroEstoque("só uma peça ativa se arquiva")
    it["status"] = status
    if motivo:
        it.setdefault("notas", []).append({"em": agora(), "texto": motivo})
    return _salvar(it)


def pedir_ajuste(ident: str, texto: str) -> dict:
    texto = " ".join((texto or "").split())
    if not texto:
        raise ErroEstoque("diga o que ajustar")
    it = item(ident)
    if it["status"] not in ("rascunho", "ativo"):
        raise ErroEstoque(f"{ident} está como {it['status']}")
    it.setdefault("ajustes", []).append({"em": agora(), "texto": texto})
    if it["status"] == "ativo":
        it["status"] = "rascunho"   # volta para o Claude; continua valendo a versão de antes até aprovar
    return _salvar(it)


def anotar_analise(ident: str, texto: str) -> dict:
    it = item(ident)
    it["analise"] = texto.strip()
    return _salvar(it)


def resumo() -> dict:
    """Contagens para o status e o painel."""
    todos = itens()
    conta = lambda st: [i for i in todos if i["status"] == st]  # noqa: E731
    return {"entrada": len(conta("entrada")), "rascunho": len(conta("rascunho")),
            "ajuste": len([i for i in conta("rascunho") if any(not a.get("feito") for a in i.get("ajustes") or [])]),
            "ativo": len(conta("ativo"))}


# ------------------------------------------------------------------ envios do painel
def pasta_envios() -> Path:
    p = raiz() / "_envios"
    p.mkdir(parents=True, exist_ok=True)
    return p


def limpar_envios(horas: float = 24) -> None:
    import time
    p = raiz() / "_envios"
    if not p.is_dir():
        return
    for f in p.iterdir():
        if f.is_file() and time.time() - f.stat().st_mtime > horas * 3600:
            f.unlink(missing_ok=True)


# ------------------------------------------------------------------ prévias
def _quadro(it: dict, onde: str, saida: Path, w: int, h: int) -> Path:
    """Um quadro do trecho de referência (começo ou fim), ou o fundo neutro do motor."""
    from . import ff
    from . import efeitos as EF
    trecho = Path(it["pasta"]) / (it.get("trecho") or "")
    if it.get("trecho") and trecho.suffix == ".mp4" and trecho.exists():
        pos = ["-sseof", "-0.15"] if onde == "fim" else ["-ss", "0.05"]
        ff.rodar([ff.ffmpeg(), "-v", "error", "-y", *pos, "-i", str(trecho), "-frames:v", "1",
                  "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", str(saida)])
    else:
        filtro = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" + (",hflip,hue=h=150" if onde == "fim" else "")
        ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(EF.COMUM / "fundo-previa.png"), "-frames:v", "1",
                  "-vf", filtro, str(saida)])
    return saida


def previa(ident: str, tema: dict | None = None) -> Path:
    """A prévia da peça na pasta dela: PNG (legenda) ou GIF (transição, efeito, motion)."""
    import tempfile
    from . import ff
    it = item(ident)
    pasta = Path(it["pasta"])
    if it["tipo"] == "legenda":
        from . import efeitos as EF
        from . import legendas as L
        est = dados(it)
        W, H = 960, 540
        with tempfile.TemporaryDirectory() as tmp:
            fundo = _quadro(it, "inicio", Path(tmp) / "f.png", W, H)
            ws = [{"texto": t, "inicio": i * 0.4, "fim": i * 0.4 + 0.38}
                  for i, t in enumerate("vinte placas com o mesmo defeito".split())]
            linhas = ["vinte placas com", "o mesmo defeito"] if est["modo"] == "frase" else ["vinte placas"]
            bl = [{"id": "l1", "inicio": 0, "fim": 3, "linhas": linhas, "palavras": ws[:len(" ".join(linhas).split())]}]
            (Path(tmp) / "l.ass").write_text(L.ass(bl, tema or EF.mesclar_tema(), W, H, estilo=est), encoding="utf-8")
            import subprocess  # o filtro ass lê o arquivo pelo caminho relativo (sem ":" de unidade no Windows)
            r = subprocess.run([ff.ffmpeg(), "-v", "error", "-y", "-loop", "1", "-i", "f.png", "-vf", "ass=l.ass",
                                "-ss", "0.5", "-frames:v", "1", str(pasta / "previa.png")], cwd=tmp,
                               capture_output=True, text=True)
            if r.returncode:
                raise ErroEstoque(f"a prévia da legenda falhou: {r.stderr[-400:]}")
        return pasta / "previa.png"
    if it["tipo"] == "transicao":
        tr = dados(it)
        W, H, fps = 480, 270, 25
        dur = float(tr["duracao"]["padrao"])
        with tempfile.TemporaryDirectory() as tmp:
            a = _quadro(it, "inicio", Path(tmp) / "a.png", W, H)
            b = _quadro(it, "fim", Path(tmp) / "b.png", W, H)
            tipo = tr["xfade"] if tr["xfade"] != "custom" else "custom:expr='" + str(tr.get("expr") or "A").replace("'", "") + "'"
            seg = 0.6 + dur
            ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-loop", "1", "-t", f"{seg:.3f}", "-r", str(fps), "-i", str(a),
                      "-loop", "1", "-t", f"{seg:.3f}", "-r", str(fps), "-i", str(b), "-filter_complex",
                      f"[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]xfade=transition={tipo}:duration={dur:.3f}:"
                      f"offset=0.6,split[x][y];[x]palettegen=max_colors=128[p];[y][p]paletteuse",
                      "-loop", "0", str(pasta / "previa.gif")])
        return pasta / "previa.gif"
    from . import efeitos as EF
    return EF.previa(ident, pasta / "previa.gif", tema=tema)
