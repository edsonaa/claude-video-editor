"""Cortes curtos a partir do vídeo longo: frases, sugestões e o projeto derivado.

- `frases(pasta)`: a fala do corte final, em frases com id (f001…) no tempo da
  sequência. É o que o Claude lê para escolher os trechos.
- `sugerir(...)`: janelas de frases com a duração pedida, pontuadas por sinais
  simples (começo que se sustenta sozinho, fim fechado, pausa natural nas bordas,
  pergunta ou número no começo, animação no meio). São pontos de partida: quem
  decide é o Claude com a pessoa, pelo conteúdo.
- `criar(...)`: um projeto novo em <vídeo>/Curtos/<nome>/, com os cortes do trecho
  mapeados de volta para o tempo da origem (os mesmos quadros do longo), o
  enquadramento de cada segmento para o formato vertical (centrado no rosto, se o
  rastreio existir; tela encaixada) e o fluxo cortes → legendas → render.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re

from . import estado as E
from . import legendas as L
from . import render as R
from . import transcricao as T
from .linha import Linha
from .tempo import Taxa

PASTA_CURTOS = "Curtos"
FLUXO_CURTO = ["cortes", "legendas", "render"]
CONECTIVOS = {"e", "mas", "então", "entao", "aí", "ai", "porque", "que", "isso", "esse", "essa", "ele", "ela", "eles",
              "elas", "também", "tambem", "daí", "dai", "depois", "senão", "ou", "nem", "pois", "porém", "porem",
              "aqui", "lá", "la", "assim", "inclusive", "tipo"}
GANCHO = re.compile(r"\?|\d|\b(você|voce|nunca|sempre|erro|segredo|ninguém|ninguem|cuidado|pior|melhor|por que|"
                    r"como|o que|qual|quanto)\b", re.I)


class ErroCurtos(E.ErroEstado):
    pass


def _raiz(pasta) -> Path:
    return E.caminho_estado(pasta).parent.parent


def _pasta_curtos(pasta) -> Path:
    p = E.caminho_estado(pasta).parent / "curtos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _transcricoes(d: dict, base: Path) -> dict:
    out = {}
    for vid, c in ((d.get("transcricao") or {}).get("palavras") or {}).items():
        arq = Path(c) if Path(c).is_absolute() else base / c
        if arq.exists():
            out[vid] = T.ler(arq)
    return out


# ------------------------------------------------------------------ frases do corte final
def frases(pasta, pausa: float = 0.6, max_dur: float = 12.0) -> dict:
    d = E.ler(pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    fps = (d.get("midia") or {}).get("fps")
    if not segs or not fps:
        raise ErroCurtos("o vídeo precisa de cortes e de midia.fps")
    transcs = _transcricoes(d, _raiz(pasta))
    if not transcs:
        raise ErroCurtos("o estado não tem transcricao.palavras")
    linha = Linha(segs, fps)
    ws = L.palavras_na_sequencia(transcs, linha, remover_hesitacoes=True)
    for w in ws:
        w["tipo"] = "palavra"
    fs = T.frases(ws, pausa, max_dur)
    out = []
    for k, f in enumerate(fs, 1):
        a, b = f["palavras"]
        out.append({"id": f"f{k:03d}", "inicio": f["inicio"], "fim": f["fim"], "pausa_antes": f["pausa_antes"],
                    "texto": f["texto"], "segmentos": sorted({w["segmento"] for w in ws[a:b + 1]}),
                    "palavras": b - a + 1})
    for i, f in enumerate(out):
        f["pausa_depois"] = round(out[i + 1]["inicio"] - f["fim"], 3) if i + 1 < len(out) else None
    conteudo = {"projeto": d.get("projeto"), "cortes_versao": d["cortes"]["versao"], "duracao": round(linha.duracao, 3),
                "frases": out}
    arq = _pasta_curtos(pasta) / "frases.json"
    arq.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")
    (arq.parent / "frases.txt").write_text(texto_frases(out), encoding="utf-8")
    return conteudo


def _hms(s: float) -> str:
    m, s = divmod(max(0.0, s), 60)
    return f"{int(m)}:{s:04.1f}"


def texto_frases(fs: list[dict]) -> str:
    return "".join(f"{f['id']} [{_hms(f['inicio'])}–{_hms(f['fim'])}] {f['texto']}\n" for f in fs)


def frases_atuais(pasta) -> dict:
    """As frases já listadas, se ainda valem para o corte de agora."""
    arq = E.caminho_estado(pasta).parent / "curtos" / "frases.json"
    d = E.ler(pasta)
    if arq.exists():
        c = json.loads(arq.read_text(encoding="utf-8"))
        if c.get("cortes_versao") == (d.get("cortes") or {}).get("versao"):
            return c
        raise ErroCurtos("o corte mudou depois da lista de frases: rode 'curtos.py frases' de novo e escolha pelos ids novos")
    return frases(pasta)


# ------------------------------------------------------------------ sugestões
def _primeira_palavra(texto: str) -> str:
    m = re.match(r"\W*([\wÀ-ÿ']+)", texto)
    return (m.group(1) if m else "").lower()


def pontuar(fs: list[dict], i: int, j: int, motions: list[dict] | None = None) -> tuple[float, list[str]]:
    a, b = fs[i], fs[j]
    nota, motivos = 0.0, []
    p1 = _primeira_palavra(a["texto"])
    if p1 in CONECTIVOS:
        nota -= 2.0
        motivos.append(f"começa com “{p1}” (pode depender do que veio antes)")
    else:
        nota += 1.0
    if GANCHO.search(a["texto"]):
        nota += 1.5
        motivos.append("começo com pergunta, número ou gancho")
    if (a.get("pausa_antes") is None) or a["pausa_antes"] >= 0.4:
        nota += 0.5
        motivos.append("pausa natural antes")
    fim = b["texto"].rstrip()
    if re.search(r"[.!?…]$", fim):
        nota += 1.0
        motivos.append("termina fechado")
    else:
        nota -= 1.0
        motivos.append("termina no meio da frase")
    if (b.get("pausa_depois") is None) or b["pausa_depois"] >= 0.4:
        nota += 0.5
    dur = b["fim"] - a["inicio"]
    palavras = sum(f["palavras"] for f in fs[i:j + 1])
    ritmo = palavras / max(dur, 0.1)
    if ritmo < 1.6:
        nota -= 1.0
        motivos.append(f"ritmo lento ({ritmo:.1f} palavras/s)")
    for m in motions or []:
        if m.get("inicio_seq") is not None and a["inicio"] <= m["inicio_seq"] < b["fim"] and m.get("status") != "riscado":
            nota += 0.5
            motivos.append(f"tem a animação {m['id']}")
    return round(nota, 2), motivos


def sugerir(pasta, minimo: float = 20.0, maximo: float = 60.0, n: int = 8) -> list[dict]:
    c = frases_atuais(pasta)
    fs = c["frases"]
    d = E.ler(pasta)
    motions = (d.get("motions") or {}).get("itens") or []
    cands = []
    for i in range(len(fs)):
        for j in range(i, len(fs)):
            dur = fs[j]["fim"] - fs[i]["inicio"]
            if dur > maximo:
                break
            if dur < minimo:
                continue
            nota, motivos = pontuar(fs, i, j, motions)
            # um pouco de preferência pelo meio da faixa de duração
            nota -= abs(dur - (minimo + maximo) / 2) / (maximo - minimo + 1e-9) * 0.5
            cands.append({"de": fs[i]["id"], "ate": fs[j]["id"], "inicio": fs[i]["inicio"], "fim": fs[j]["fim"],
                          "duracao": round(dur, 2), "nota": round(nota, 2), "motivos": motivos,
                          "texto": " ".join(f["texto"] for f in fs[i:j + 1])})
    cands.sort(key=lambda x: -x["nota"])
    escolhidas: list[dict] = []
    for cnd in cands:
        sobra = all(min(cnd["fim"], e["fim"]) - max(cnd["inicio"], e["inicio"]) < 0.3 * cnd["duracao"]
                    for e in escolhidas)
        if sobra:
            escolhidas.append(cnd)
        if len(escolhidas) >= n:
            break
    return escolhidas


# ------------------------------------------------------------------ o projeto derivado
def _slug(nome: str) -> str:
    s = re.sub(r"[^\w-]+", "-", nome.strip().lower(), flags=re.U).strip("-")
    if not s:
        raise ErroCurtos("dê um nome ao curto (ex.: erro-da-fonte)")
    return s[:60]


def trecho(pasta, de: str, ate: str, folga_ini: float = 0.12, folga_fim: float = 0.3) -> tuple[float, float, list]:
    """(início, fim) na sequência do longo. `de`/`ate`: ids de frase (f012) ou tempos em segundos."""
    if re.fullmatch(r"f\d+", de) or re.fullmatch(r"f\d+", ate):
        fs = {f["id"]: f for f in frases_atuais(pasta)["frases"]}
        try:
            fa, fb = fs[de], fs[ate]
        except KeyError as e:
            raise ErroCurtos(f"frase {e} não existe na lista atual") from None
        if fb["fim"] < fa["inicio"]:
            raise ErroCurtos(f"{ate} vem antes de {de}")
        ini = max(0.0, fa["inicio"] - min(folga_ini, (fa.get("pausa_antes") or 1) / 2))
        fim = fb["fim"] + min(folga_fim, (fb.get("pausa_depois") or 1) / 2)
        return ini, fim, [de, ate]
    return float(de), float(ate), []


def criar(pasta, nome: str, de: str, ate: str, formato: str = "9:16", titulo: str | None = None) -> dict:
    d = E.ler(pasta)
    base = _raiz(pasta)
    segs = (d.get("cortes") or {}).get("segmentos") or []
    taxa = Taxa.de(d["midia"]["fps"])
    linha = Linha(segs, taxa)
    ini, fim, ids = trecho(pasta, de, ate)
    fim = min(fim, linha.duracao)
    f0, f1 = taxa.frames(ini), taxa.frames(fim)
    if f1 - f0 < taxa.frames(1.0):
        raise ErroCurtos("trecho curto demais (menos de 1 s)")
    slug = _slug(nome)
    destino = base / PASTA_CURTOS / slug
    if (destino / E.PASTA_CLAUDE / E.ARQUIVO).exists():
        raise ErroCurtos(f"já existe um curto chamado {slug} ({destino})")

    arqs = {a["id"]: a for a in d["midia"].get("arquivos") or []}
    W, H = R.tamanho(formato)
    rostos = {}
    novos = []
    for p in linha.pedacos:
        a, b = max(p.seq_ini, f0), min(p.seq_fim, f1)
        if b <= a:
            continue
        in_f = p.in_f + (a - p.seq_ini)
        out_f = in_f + (b - a)
        info = arqs[p.video]
        src = tuple(info.get("resolucao") or (1920, 1080))
        quadro = R.quadro_padrao(info.get("tipo"), src, (W, H))
        if quadro.get("modo") == "cortar":
            if p.video not in rostos:
                arq = E.caminho_estado(pasta).parent / f"rosto_{p.video}.json"
                rostos[p.video] = json.loads(arq.read_text(encoding="utf-8")).get("trilha", []) if arq.exists() else []
            x = R.x_do_rosto(rostos[p.video], taxa.segundos(in_f), taxa.segundos(out_f))
            if x is not None:
                quadro["x"] = x
                quadro["pelo_rosto"] = True
        novos.append({"id": f"s{len(novos) + 1:03d}", "video": p.video, "inicio": taxa.segundos(in_f),
                      "fim": taxa.segundos(out_f), "quadro": quadro, "origem_segmento": p.id})

    def absoluto(c):
        if not c:
            return c
        return str(Path(c) if Path(c).is_absolute() else (base / c).resolve())

    midia = copy.deepcopy(d["midia"])
    for a in midia.get("arquivos") or []:
        for campo in ("caminho", "proxy", "audio_tratado"):
            if a.get(campo):
                a[campo] = absoluto(a[campo])
    transc = copy.deepcopy(d.get("transcricao") or {})
    for bloco in ("palavras", "frases", "silencios"):
        if isinstance(transc.get(bloco), dict):
            transc[bloco] = {k: absoluto(v) for k, v in transc[bloco].items()}

    projeto = f"{d.get('projeto')}_{slug}"
    E.criar(destino, projeto, d.get("perfil"), FLUXO_CURTO)
    with E.editar(destino) as n:
        n["midia"] = midia
        n["transcricao"] = transc
        n["cortes"] = {"versao": 1, "segmentos": novos}
        n["video"] = {"formato": formato, "titulo": titulo or nome,
                      "origem": {"projeto": d.get("projeto"), "pasta": "../..", "de": round(ini, 3), "ate": round(fim, 3),
                                 "frases": ids, "cortes_versao": d["cortes"]["versao"]}}
        n["etapas"]["cortes"] = "aguardando_aprovacao"
    # textos dos segmentos, pelo mesmo cálculo do painel
    from . import painel as P
    P.gravar_cortes(destino, novos, None, "criado a partir do longo")
    P._gravar_historico(destino, [])

    with E.editar(pasta) as e:
        lista = e.setdefault("curtos", [])
        cid = E.proximo_id(lista, "c")
        lista.append({"id": cid, "nome": slug, "titulo": titulo or nome, "pasta": f"{PASTA_CURTOS}/{slug}",
                      "de": round(ini, 3), "ate": round(fim, 3), "frases": ids, "formato": formato,
                      "criado_em": E.agora()})
    return {"id": cid, "pasta": str(destino), "projeto": projeto, "duracao": round(taxa.segundos(f1 - f0), 3),
            "segmentos": len(novos), "formato": formato,
            "pelo_rosto": sum(1 for s in novos if s["quadro"].get("pelo_rosto")),
            "encaixados": sum(1 for s in novos if s["quadro"].get("modo") == "encaixar")}


def listar(pasta) -> list[dict]:
    d = E.ler(pasta)
    base = _raiz(pasta)
    out = []
    for c in d.get("curtos") or []:
        item = dict(c)
        try:
            n = E.ler(base / c["pasta"])
            item["etapas"] = n.get("etapas")
            item["entregas"] = [x for x in n.get("entregas", []) if x.get("tipo") == "final"]
        except E.ErroEstado:
            item["etapas"] = None
        out.append(item)
    return out
