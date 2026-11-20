"""Biblioteca de transições (transicoes/transicoes.json no motor).

A transição fica no segmento que ENTRA (`cortes.segmentos[i].transicao`), centrada
no corte: metade antes, metade depois, sem mudar a duração da sequência. O render
faz com o xfade do FFmpeg, com a mídia que sobra além do corte (ou o quadro
congelado, se não sobrar). A entrega em XML põe a transição equivalente do
programa; as que o programa não tem entram como Cross Dissolve, com um marcador.
"""
from __future__ import annotations

import json
from pathlib import Path

ARQ = Path(__file__).resolve().parents[2] / "transicoes" / "transicoes.json"


class ErroTransicao(ValueError):
    pass


def listar() -> dict[str, dict]:
    return json.loads(ARQ.read_text(encoding="utf-8"))


def carregar(tipo: str) -> dict:
    t = listar()
    if tipo not in t:
        raise ErroTransicao(f"a transição '{tipo}' não existe; há: {', '.join(t)}")
    return {"id": tipo, **t[tipo]}


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
