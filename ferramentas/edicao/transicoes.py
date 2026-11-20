"""Biblioteca de transições (transicoes/transicoes.json no motor).

A transição fica no segmento que ENTRA (`cortes.segmentos[i].transicao`), centrada
no corte: metade antes, metade depois, sem mudar a duração da sequência. O render
faz com o xfade do FFmpeg, com a mídia que sobra além do corte (ou o quadro
congelado, se não sobrar). A entrega em XML põe a transição equivalente do
programa; as que o programa não tem entram como Cross Dissolve, com um marcador.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ARQ = Path(__file__).resolve().parents[2] / "transicoes" / "transicoes.json"


class ErroTransicao(ValueError):
    pass


def listar(estoque: bool = True, rascunhos: bool = False) -> dict[str, dict]:
    """As transições do motor e, depois, as do estoque da pessoa (com `_estoque`)."""
    t = json.loads(ARQ.read_text(encoding="utf-8"))
    if estoque:
        from . import estoque as ES
        for k, v in ES.pecas("transicao", rascunhos).items():
            t.setdefault(k, v)
    return t


def carregar(tipo: str) -> dict:
    t = listar(rascunhos=True)
    if tipo not in t:
        raise ErroTransicao(f"a transição '{tipo}' não existe; há: {', '.join(listar())}")
    return {"id": tipo, **t[tipo]}


XFADE_EXTRA_OK = ("custom",)


def xfades_disponiveis() -> set[str]:
    import subprocess
    from . import ff
    txt = subprocess.run([ff.ffmpeg(), "-hide_banner", "-h", "filter=xfade"], capture_output=True, text=True).stdout
    i = txt.find("transition")
    return set(re.findall(r"^\s+(\w+)\s+-?\d+", txt[i:], flags=re.M)) | set(XFADE_EXTRA_OK)


def validar(t: dict) -> None:
    """Uma transição nova (do estoque) tem o que o render, o XML e o painel precisam."""
    falta = [k for k in ("titulo", "descricao", "bom_para", "evitar", "xfade", "duracao", "xml") if k not in t]
    if falta:
        raise ErroTransicao(f"faltam campos: {', '.join(falta)}")
    d = t["duracao"]
    if not (d.get("min", 0) > 0 and d["min"] <= d.get("padrao", 0) <= d.get("max", 0)):
        raise ErroTransicao("duracao precisa de min <= padrao <= max (segundos)")
    if t["xfade"] not in xfades_disponiveis():
        raise ErroTransicao(f"o xfade '{t['xfade']}' não existe neste FFmpeg")
    if t["xfade"] == "custom" and not t.get("expr"):
        raise ErroTransicao("xfade custom precisa de 'expr' (a expressão do xfade, com A, B, P, X, Y, W, H)")
    if not (t["xml"].get("nome") and t["xml"].get("effectid")):
        raise ErroTransicao("xml precisa de nome e effectid (Cross Dissolve, se o programa não tiver igual)")
    prev = t.get("previa") or {}
    if prev and not (prev.get("a") or prev.get("b")):
        raise ErroTransicao("previa precisa de 'a' ou 'b' (quadros-chave da prévia no painel)")


def normalizar(tr: dict | None) -> dict | None:
    """{"tipo", "duracao"} conferido contra a biblioteca; None ou tipo "corte" = sem transição."""
    if not tr or tr.get("tipo") in (None, "", "corte"):
        return None
    meta = carregar(tr["tipo"])
    d = meta["duracao"]
    dur = float(tr.get("duracao") or d["padrao"])
    if not d["min"] <= dur <= d["max"]:
        raise ErroTransicao(f"{meta['titulo']}: duração {dur:g} s fora do intervalo ({d['min']:g} a {d['max']:g} s)")
    return {"tipo": meta["id"], "duracao": round(dur, 3)}


def quadros(tr: dict, fps: float) -> int:
    """Quadros da transição (pelo menos 2, número par: metade de cada lado do corte)."""
    n = max(2, round(float(tr["duracao"]) * fps))
    return n + (n % 2)


def do_efeito_xml(nome: str | None, cor: tuple | None = None) -> str:
    """O tipo da biblioteca para uma transição lida do programa (na volta do XML)."""
    nome = (nome or "").lower()
    if "dip" in nome or "color" in nome or "black" in nome:
        return "fade_branco" if cor and min(cor) > 200 else "fade_preto"
    if "white" in nome:
        return "fade_branco"
    return "dissolver"
