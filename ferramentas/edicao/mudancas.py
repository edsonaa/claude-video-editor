"""Mudanças que a pessoa faz no painel arrastando, como num programa de edição.

- **No tempo:** mover uma animação ou um som; esticar ou encurtar uma animação; mexer na
  entrada e na saída de um bloco de legenda. (Aparar e reordenar segmentos do corte ficam
  em `painel.editar_cortes`, com o histórico do corte.)
- **Na tela:** a posição e o tamanho de uma animação por cima do vídeo (`motions.itens[i].posicao`)
  e o deslocamento da legenda (`video.legendas.deslocamento`). O render, o ASS e o XML aplicam.
- **Desfazer:** um histórico só, com o do corte, em `_CLAUDE/painel/historico_cortes.json`.
  Cada mudança daqui guarda os blocos do estado como estavam; desfazer devolve, se ninguém
  mexeu neles depois.
- **Registro para o Claude:** `painel.mudancas` no estado, com o que mudou em palavras.
  `painel.py mudancas .` mostra o que ainda não foi lido.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import estado as E
from . import painel as P

REGISTRO_MAX = 300
BLOCOS = ("motions", "sfx", "video", "cortes", "legendas")
FORMATOS_MOVEIS = ("sobreposicao", "sobreposicao_lateral", "enfase")
ESCALA = (0.25, 2.0)
DESLOCAMENTO = 0.5          # até meio quadro para cada lado
DUR_MIN = 0.2


class ErroMudanca(P.ErroPainel):
    pass


# ------------------------------------------------------------------ registro
def registrar(d: dict, texto: str, item: str | None = None) -> None:
    p = d.setdefault("painel", {})
    n = int(p.get("n", 0)) + 1
    p["n"] = n
    lst = p.setdefault("mudancas", [])
    lst.append({"n": n, "em": E.agora(), "texto": texto, **({"item": item} if item else {})})
    del lst[:-REGISTRO_MAX]


def nao_lidas(d: dict) -> list[dict]:
    p = d.get("painel") or {}
    return [m for m in p.get("mudancas", []) if m["n"] > int(p.get("lidas", 0))]


def marcar_lidas(pasta) -> int:
    with E.editar(pasta) as d:
        p = d.setdefault("painel", {})
        n = len(nao_lidas(d))
        p["lidas"] = int(p.get("n", 0))
    return n


# ------------------------------------------------------------------ aplicar com desfazer
def _hash(x) -> str:
    # a versão (cortes.versao, motions.versao) sobe sozinha ao gravar: não conta como mudança
    if isinstance(x, dict):
        x = {k: v for k, v in x.items() if k != "versao"}
    return hashlib.sha1(json.dumps(x, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _guardar(pasta, antes: dict, depois: dict, mudou: list[str], motivo: str) -> None:
    h = P._historico(pasta)
    h.append({"tipo": "estado", "blocos": {k: antes[k] for k in mudou},
              "depois": {k: _hash(depois.get(k)) for k in mudou}, "motivo": motivo, "em": E.agora()})
    P._gravar_historico(pasta, h)


def aplicar(pasta, revisao, fn) -> dict:
    """fn(d) muda o estado e devolve {"texto": o que mudou, "item": id, ...}. Grava, guarda para
    desfazer e anota no registro. Devolve o que fn devolveu (sem texto/item)."""
    with P._editar(pasta, revisao) as d:
        antes = {k: copy.deepcopy(d.get(k)) for k in BLOCOS}
        r = dict(fn(d) or {})
        texto, item = r.pop("texto", None), r.pop("item", None)
        mudou = [k for k in BLOCOS if d.get(k) != antes[k]]
        if mudou and texto:
            registrar(d, texto, item)
    if mudou:
        _guardar(pasta, antes, d, mudou, texto or "mudança no painel")
    r["mudou"] = bool(mudou)
    return r


def desfazer(pasta, revisao) -> str:
    """Desfaz a última mudança feita no painel (de corte ou não). Devolve o que foi desfeito."""
    h = P._historico(pasta)
    if not h:
        raise ErroMudanca("não há mudança do painel para desfazer")
    ult = h[-1]
    if ult.get("tipo") != "estado":
        P.desfazer_cortes(pasta, revisao)
        return ult.get("motivo") or "mudança no corte"
    with P._editar(pasta, revisao) as d:
        for k, hh in ult["depois"].items():
            if _hash(d.get(k)) != hh:
                raise ErroMudanca(f"'{ult['motivo']}' não dá para desfazer: {k} mudou depois disso (pelo Claude ou "
                                  "por outra mudança). Peça pelo chat, se precisar")
        for k, v in ult["blocos"].items():
            if v is None:
                d.pop(k, None)
            else:
                d[k] = v
        registrar(d, f"desfez: {ult['motivo']}")
    P._gravar_historico(pasta, P._historico(pasta)[:-1])
    if "legendas" in ult["blocos"]:
        _refazer_revisao_legendas(pasta)
    return ult["motivo"]


def _refazer_revisao_legendas(pasta) -> None:
    from . import legendas as L
    try:
        conteudo, _ = L.ler_atual(pasta)
    except Exception:  # noqa: BLE001 (sem legenda: nada a refazer)
        return
    (L.pasta_legendas(pasta) / "revisao.txt").write_text(L.texto_revisao(conteudo["blocos"]), encoding="utf-8")


# ------------------------------------------------------------------ no tempo
def _fps(d: dict) -> float:
    fps = (d.get("midia") or {}).get("fps")
    if not fps:
        raise ErroMudanca("o estado não tem midia.fps")
    from .tempo import Taxa
    return float(Taxa.de(fps).fps)


def _total(d: dict) -> float:
    from .linha import Linha
    from .tempo import Taxa
    segs = (d.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise ErroMudanca("o vídeo ainda não tem corte")
    return Linha(segs, Taxa.de(d["midia"]["fps"])).duracao


def _q(t: float, fps: float) -> float:
    return round(round(t * fps) / fps, 4)


def _f(t: float | None) -> str:
    if t is None:
        return "—"
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def mover(d: dict, tipo: str, ident: str, inicio: float, fim: float | None = None) -> dict:
    """Muda o tempo de uma animação (mover, ou esticar com `fim`) ou de um som, na sequência."""
    fps, total = _fps(d), _total(d)
    if tipo == "motion":
        itens = (d.get("motions") or {}).get("itens") or []
        it = next((x for x in itens if x["id"] == ident), None)
        if not it or it.get("inicio_seq") is None:
            raise ErroMudanca(f"animação {ident} não encontrada (ou sem tempo no plano)")
        a0, b0 = it["inicio_seq"], it.get("fim_seq")
        dur0 = (b0 - a0) if b0 is not None else 2.0
        pronta = bool((it.get("render") or {}).get("arquivo")) or it.get("status") in ("renderizado", "entregue")
        # só a borda que mudou vai para o quadro (a outra fica como estava)
        a = a0 if abs(float(inicio) - a0) < 1e-6 else _q(float(inicio), fps)
        b = None if fim is None else (b0 if b0 is not None and abs(float(fim) - b0) < 1e-6 else _q(float(fim), fps))
        if b is not None and abs((b - a) - dur0) > 1.5 / fps:
            if pronta:
                raise ErroMudanca(f"{ident} já está renderizada: dá para mover, mas não mudar a duração "
                                  "(peça um ajuste para refazer mais curta ou mais longa)")
            dur = b - a
            if dur < DUR_MIN:
                raise ErroMudanca(f"{ident} ficaria com menos de {DUR_MIN:g} s")
            if it.get("efeito"):
                from . import efeitos as EF
                lim = EF.carregar(it["efeito"])["duracao"]
                if not lim["min"] - 1e-6 <= dur <= lim["max"] + 1e-6:
                    raise ErroMudanca(f"{ident} ({it['efeito']}): a duração vai de {lim['min']:g} a {lim['max']:g} s; "
                                      f"ficaria com {dur:.2f} s")
        else:
            dur = dur0
        if b is None or abs((b - a) - dur0) <= 1.5 / fps:   # mover: a duração fica
            a = min(max(0.0, a), max(0.0, total - dur))
            b = a + dur
        else:                                                # esticar ou encurtar
            a, b = max(0.0, a), min(total, b)
        it["inicio_seq"], it["fim_seq"] = round(a, 4), round(b, 4)
        acao = "movida" if abs((b - a) - dur0) <= 1.5 / fps else "duração mudada"
        return {"item": ident, "texto": f"{ident} {acao}: de {_f(a0)}–{_f(b0)} para {_f(a)}–{_f(b)} da sequência"}
    if tipo == "sfx":
        itens = (d.get("sfx") or {}).get("itens") or []
        it = next((x for x in itens if x["id"] == ident), None)
        if not it:
            raise ErroMudanca(f"som {ident} não encontrado")
        a0 = it.get("inicio_seq")
        a = min(max(0.0, _q(float(inicio), fps)), max(0.0, total - 1 / fps))
        it["inicio_seq"] = round(a, 4)
        itens.sort(key=lambda x: x.get("inicio_seq") or 0)
        return {"item": ident, "texto": f"{ident} movido: de {_f(a0)} para {_f(a)} da sequência"}
    raise ErroMudanca(f"não dá para mover '{tipo}' por aqui")


def tempo_legenda(pasta, revisao, ident: str, inicio: float, fim: float) -> dict:
    """Entrada e saída de um bloco de legenda (versão nova do arquivo de blocos)."""
    from . import legendas as L
    d = E.ler(pasta)
    if revisao is not None and d.get("revisao") != revisao:
        raise E.Conflito("o estado mudou enquanto você revisava (o Claude gravou algo); a tela foi atualizada, "
                         "refaça a mudança")
    fps = _fps(d)
    antes = {k: copy.deepcopy(d.get(k)) for k in BLOCOS}
    conteudo, _ = L.ler_atual(pasta)
    bls = conteudo["blocos"]
    i = next((k for k, b in enumerate(bls) if b["id"] == ident), None)
    if i is None:
        raise ErroMudanca(f"bloco {ident} não encontrado")
    b = bls[i]
    a0, b0 = b["inicio"], b["fim"]
    a = a0 if abs(float(inicio) - a0) < 1e-6 else _q(float(inicio), fps)
    z = b0 if abs(float(fim) - b0) < 1e-6 else _q(float(fim), fps)
    ant = bls[i - 1]["fim"] if i > 0 else 0.0
    prox = bls[i + 1]["inicio"] if i + 1 < len(bls) else None
    a = max(a, ant)
    if prox is not None:
        z = min(z, prox)
    if z - a < DUR_MIN:
        raise ErroMudanca(f"{ident} ficaria com menos de {DUR_MIN:g} s (encosta no bloco vizinho)")
    b["inicio"], b["fim"] = round(a, 4), round(z, 4)
    L.gravar_versao(pasta, conteudo)
    texto = f"legenda {ident}: de {_f(a0)}–{_f(b0)} para {_f(a)}–{_f(z)} da sequência"
    with E.editar(pasta) as d2:
        registrar(d2, texto, ident)
        depois = d2
    _guardar(pasta, antes, depois, ["legendas"], texto)
    return {"id": ident, "inicio": b["inicio"], "fim": b["fim"]}


# ------------------------------------------------------------------ na tela
def _num(v, lo, hi, nome) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ErroMudanca(f"{nome}: número inválido") from None
    return round(min(hi, max(lo, x)), 4)


def posicionar(d: dict, tipo: str, ident: str | None, x, y, escala=None) -> dict:
    x = _num(x, -DESLOCAMENTO, DESLOCAMENTO, "x")
    y = _num(y, -DESLOCAMENTO, DESLOCAMENTO, "y")
    if tipo == "motion":
        itens = (d.get("motions") or {}).get("itens") or []
        it = next((m for m in itens if m["id"] == ident), None)
        if not it:
            raise ErroMudanca(f"animação {ident} não encontrada")
        if it.get("formato") not in FORMATOS_MOVEIS:
            raise ErroMudanca(f"{ident} é {it.get('formato') or 'sem formato'}: ocupa o quadro inteiro, não tem o que "
                              "mover (só sobreposições, laterais e ênfases)")
        e = _num(1.0 if escala is None else escala, *ESCALA, "tamanho")
        if abs(x) < 1e-3 and abs(y) < 1e-3 and abs(e - 1) < 1e-3:
            it.pop("posicao", None)
            return {"item": ident, "texto": f"{ident} voltou à posição original na tela"}
        it["posicao"] = {"x": x, "y": y, "escala": e}
        return {"item": ident, "texto": f"{ident} na tela: {x * 100:+.0f}% na horizontal, {y * 100:+.0f}% na vertical, "
                                        f"tamanho {e * 100:.0f}%"}
    if tipo == "legenda":
        v = d.setdefault("video", {}).setdefault("legendas", {})
        if abs(x) < 1e-3 and abs(y) < 1e-3:
            v.pop("deslocamento", None)
            return {"item": "legendas", "texto": "legenda voltou à posição do estilo"}
        v["deslocamento"] = {"x": x, "y": y}
        return {"item": "legendas", "texto": f"legenda deslocada {x * 100:+.0f}% na horizontal e {y * 100:+.0f}% na vertical"}
    raise ErroMudanca(f"não dá para posicionar '{tipo}'")
