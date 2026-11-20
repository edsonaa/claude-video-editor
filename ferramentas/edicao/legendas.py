"""Legendas a partir da transcrição e dos cortes, no tempo da sequência.

Fluxo: palavras (tempo da origem) → só as que ficaram no corte, no tempo da
sequência → blocos de legenda (l001, l002…) → SRT, VTT, ASS (queimada, com
destaque palavra a palavra) ou os parâmetros do efeito HyperFrames
`legenda-animada`. Os blocos ficam num JSON editável: corrigir o texto de um
bloco e exportar de novo não refaz a divisão.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .linha import Linha
from .tempo import Taxa

_PONTO_FORTE = re.compile(r"[.!?…]$")
_PONTO_FRACO = re.compile(r"[,;:]$")
# Palavras que não devem terminar uma linha (a próxima linha começa com elas).
_NAO_TERMINA = {"a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "em", "no", "na",
                "nos", "nas", "e", "ou", "que", "com", "por", "para", "pra", "pro", "se", "mas", "nem", "ao", "à",
                "the", "of", "to", "and", "a", "an"}


def _sem_pontuacao(t: str) -> str:
    return re.sub(r"[^\wÀ-ÿ'-]", "", t.lower())


def aplicar_correcoes(texto: str, correcoes: dict[str, str] | None) -> str:
    """Troca palavras inteiras (sem diferenciar maiúsculas), mantendo a pontuação em volta."""
    if not correcoes:
        return texto
    m = re.match(r"^(\W*)(.*?)(\W*)$", texto, re.S)
    antes, nucleo, depois = m.groups()
    for errado, certo in correcoes.items():
        if nucleo.lower() == errado.lower():
            return antes + certo + depois
    return texto


# --------------------------------------------------------------- palavras na sequência
def palavras_na_sequencia(transcricoes: dict, linha: Linha, remover_hesitacoes: bool = True,
                          correcoes: dict | None = None) -> list[dict]:
    """Só as palavras que ficaram no corte, com início e fim no tempo da sequência."""
    taxa = linha.taxa
    out = []
    for p in linha.pedacos:
        t = transcricoes.get(p.video)
        if not t:
            continue
        ini, fim = taxa.segundos(p.in_f), taxa.segundos(p.out_f)
        desloc = taxa.segundos(p.seq_ini) - ini
        for w in t["palavras"]:
            if w["tipo"] == "evento" or not (ini <= w["inicio"] < fim):
                continue
            if remover_hesitacoes and w["tipo"] == "hesitacao":
                continue
            out.append({"texto": aplicar_correcoes(w["texto"], correcoes),
                        "inicio": round(w["inicio"] + desloc, 3),
                        "fim": round(min(w["fim"], fim) + desloc, 3),
                        "segmento": p.id, "estimado": bool(w.get("estimado"))})
    out.sort(key=lambda w: w["inicio"])
    return out


# --------------------------------------------------------------- linhas
def quebrar_linhas(palavras: list[str], max_car: int, linhas: int = 2) -> list[str]:
    """Divide em até `linhas` linhas de até `max_car`, equilibradas, sem terminar linha em artigo/preposição."""
    texto = " ".join(palavras)
    if len(texto) <= max_car or linhas == 1:
        return [texto]
    melhor, nota_melhor = None, None
    for i in range(1, len(palavras)):
        a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
        if len(a) > max_car or len(b) > max_car:
            continue
        nota = abs(len(a) - len(b))
        if _sem_pontuacao(palavras[i - 1]) in _NAO_TERMINA:
            nota += 25
        if _PONTO_FRACO.search(palavras[i - 1]) or _PONTO_FORTE.search(palavras[i - 1]):
            nota -= 12
        if len(a) < len(b):
            nota += 2  # pirâmide: a de cima um pouco maior lê melhor
        if nota_melhor is None or nota < nota_melhor:
            melhor, nota_melhor = [a, b], nota
    return melhor or [texto]


# --------------------------------------------------------------- blocos
def blocos(palavras: list[dict], taxa, max_car: int = 42, linhas: int = 2, max_dur: float = 6.0,
           min_dur: float = 1.0, pausa: float = 0.5, cps_max: float = 17.0, estender: float = 0.25,
           quebrar_no_corte: bool = False, intervalo_min_f: int = 2) -> list[dict]:
    """Agrupa palavras em blocos de legenda.

    Quebra quando: o texto não cabe nas linhas; há uma pausa ≥ `pausa`; o bloco passaria de `max_dur`;
    depois de ponto final com o bloco já pela metade; e, com `quebrar_no_corte`, em cada corte.
    """
    taxa = Taxa.de(taxa)
    cap = max_car * linhas
    grupos: list[list[dict]] = []
    atual: list[dict] = []

    def cabe(ws):
        textos = [w["texto"] for w in ws]
        if len(" ".join(textos)) > cap:
            return False
        ls = quebrar_linhas(textos, max_car, linhas)
        return len(ls) <= linhas and all(len(l) <= max_car for l in ls)

    for w in palavras:
        if atual:
            ant = atual[-1]
            quebra = (
                w["inicio"] - ant["fim"] >= pausa
                or not cabe(atual + [w])
                or w["fim"] - atual[0]["inicio"] > max_dur
                or (quebrar_no_corte and w["segmento"] != ant["segmento"])
                or (_PONTO_FORTE.search(ant["texto"]) and len(" ".join(x["texto"] for x in atual)) >= cap * 0.4)
            )
            if quebra:
                grupos.append(atual)
                atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)

    gap = taxa.segundos(intervalo_min_f)
    out = []
    for i, g in enumerate(grupos):
        ini = taxa.quantizar(g[0]["inicio"])
        fim = g[-1]["fim"] + estender
        prox = grupos[i + 1][0]["inicio"] if i + 1 < len(grupos) else None
        if fim - ini < min_dur:
            fim = ini + min_dur
        if prox is not None:
            fim = min(fim, prox - gap)
        fim = max(taxa.quantizar(fim), ini + taxa.segundos(1))
        texto_ws = [w["texto"] for w in g]
        ls = quebrar_linhas(texto_ws, max_car, linhas)
        n_car = len("".join(ls).replace(" ", "")) + max(0, len(texto_ws) - 1)
        out.append({
            "id": f"l{i + 1:03d}", "inicio": round(ini, 3), "fim": round(fim, 3), "linhas": ls,
            "palavras": [{"texto": w["texto"], "inicio": round(w["inicio"], 3), "fim": round(w["fim"], 3)} for w in g],
            "cps": round(n_car / max(fim - ini, 1e-3), 1),
        })
    return out


def avisos(bls: list[dict], cps_max: float = 17.0, max_car: int = 42) -> list[str]:
    out = []
    for b in bls:
        if b["cps"] > cps_max:
            out.append(f"{b['id']}: {b['cps']} caracteres/s (acima de {cps_max:g}): pouco tempo para ler")
        for l in b["linhas"]:
            if len(l) > max_car:
                out.append(f"{b['id']}: linha com {len(l)} caracteres (máximo {max_car}): \"{l}\"")
    return out


def retexto(bloco: dict, texto: str, max_car: int, linhas: int = 2) -> dict:
    """Troca o texto de um bloco mantendo os tempos (correção pelo chat)."""
    novas = texto.split()
    antigas = bloco["palavras"]
    b = dict(bloco)
    if len(novas) == len(antigas):
        b["palavras"] = [dict(w, texto=t) for w, t in zip(antigas, novas)]
    else:  # tempos redistribuídos de forma proporcional ao tamanho de cada palavra
        ini, fim = antigas[0]["inicio"], antigas[-1]["fim"]
        total = sum(len(t) + 1 for t in novas)
        acc, ws = ini, []
        for t in novas:
            d = (fim - ini) * (len(t) + 1) / total
            ws.append({"texto": t, "inicio": round(acc, 3), "fim": round(acc + d, 3)})
            acc += d
        b["palavras"] = ws
    b["linhas"] = quebrar_linhas(novas, max_car, linhas)
    return b


# --------------------------------------------------------------- formatos
def _tc_srt(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def srt(bls: list[dict], caixa_alta: bool = False) -> str:
    partes = []
    for n, b in enumerate(bls, start=1):
        texto = "\n".join(l.upper() if caixa_alta else l for l in b["linhas"])
        partes.append(f"{n}\n{_tc_srt(b['inicio'])} --> {_tc_srt(b['fim'])}\n{texto}\n")
    return "\n".join(partes)


def vtt(bls: list[dict], caixa_alta: bool = False) -> str:
    partes = ["WEBVTT", ""]
    for b in bls:
        texto = "\n".join(l.upper() if caixa_alta else l for l in b["linhas"])
        partes += [b["id"], f"{_tc_srt(b['inicio']).replace(',', '.')} --> {_tc_srt(b['fim']).replace(',', '.')}", texto, ""]
    return "\n".join(partes)


def _cor_ass(hexa: str, alfa: int = 0) -> str:
    h = hexa.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alfa:02X}{b}{g}{r}".upper()


def _tc_ass(s: float) -> str:
    cs = int(round(s * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    seg, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{seg:02d}.{cs:02d}"


def _esc_ass(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


ESTILOS_ARQ = Path(__file__).resolve().parents[2] / "legendas" / "estilos.json"
POSICOES = {"baixo": 2, "centro": 5, "topo": 8}


def estilos_legenda() -> dict:
    """A biblioteca de estilos de legenda do motor (legendas/estilos.json), na ordem do arquivo."""
    return json.loads(ESTILOS_ARQ.read_text(encoding="utf-8"))


def estilo_legenda(ident: str) -> dict:
    est = estilos_legenda()
    if ident not in est:
        raise ValueError(f"estilo de legenda '{ident}' não existe; há: {', '.join(est)}")
    return {"id": ident, **est[ident]}


def opcoes_legenda(d: dict | None = None, cfg: dict | None = None, vertical: bool | None = None) -> dict:
    """As opções de legenda que valem para um vídeo, com o estilo resolvido.

    Ordem: configuração (`legendas`) → estilo (do vídeo ou da configuração) → escolhas
    do vídeo (`video.legendas` no estado). Sem estilo escolhido em lugar nenhum, os
    campos da configuração (modo, caixa alta, caracteres) valem por cima do estilo
    implícito (palavra a palavra ou clássica), como antes dos estilos existirem.
    """
    cl = dict((cfg or {}).get("legendas") or {})
    dv = dict(((d or {}).get("video") or {}).get("legendas") or {})
    escolhido = dv.get("estilo") or cl.get("estilo")
    ident = escolhido or ("karaoke" if cl.get("modo") == "palavra" else "classica")
    est = estilo_legenda(ident)
    if vertical is None:
        f = ((d or {}).get("video") or {}).get("formato") or ((cfg or {}).get("video") or {}).get("formato") or "16:9"
        vertical = f in ("9:16", "4:5")
    op = {"ativas": cl.get("ativas", False), "saidas": cl.get("saidas", ["srt"]), "queimar": cl.get("queimar", False),
          "remover_hesitacoes": cl.get("remover_hesitacoes", True), "quebrar_no_corte": cl.get("quebrar_no_corte", False),
          "modo": est["modo"], "caixa_alta": est["caixa_alta"], "linhas": est["linhas"],
          "max_caracteres": est["max_caracteres_vertical"] if vertical else est["max_caracteres"],
          "posicao": est.get("posicao", "baixo")}
    if not escolhido:  # configuração antiga, sem estilo: os campos dela valem
        for k in ("modo", "caixa_alta", "linhas", "max_caracteres", "posicao"):
            if k in cl:
                op[k] = cl[k]
        est = dict(est, modo=op["modo"], caixa_alta=op["caixa_alta"])
    for k in ("ativas", "queimar", "posicao"):
        if k in dv:
            op[k] = dv[k]
    op["estilo"] = est
    return op


def _cor_tema(valor: str, tema: dict) -> str:
    """Uma cor do estilo: hexadecimal, ou o nome de uma cor do tema (destaque, apoio, texto…)."""
    if valor and valor.startswith("#"):
        return valor
    return tema["cores"].get(valor or "destaque", "#FFFFFF")


def ass(bls: list[dict], tema: dict, largura: int, altura: int, modo: str | None = None, posicao: str | None = None,
        caixa_alta: bool | None = None, tamanho: int | None = None, estilo: dict | None = None) -> str:
    """ASS para queimar com o FFmpeg (filtro `ass`), no estilo de legenda pedido.

    Sem `estilo`: o comportamento de antes (frase clássica, ou palavra a palavra na cor de
    destaque do tema). `modo`, `posicao` e `caixa_alta` passados aqui valem por cima do estilo.
    """
    if estilo is None:
        estilo = estilo_legenda("karaoke" if modo == "palavra" else "classica")
        if (modo or "frase") == "frase":
            estilo["cor"] = tema["cores"]["texto"]
    est = dict(estilo)
    if modo:
        est["modo"] = modo
    if caixa_alta is not None:
        est["caixa_alta"] = caixa_alta
    posicao = posicao or est.get("posicao", "baixo")
    vertical = altura > largura
    palavra = est["modo"] == "palavra"
    fk = est.get("fonte", "texto")
    fonte = tema["fontes"].get(fk, fk) if fk in ("titulo", "texto", "numeros") else fk
    base = (0.062 if vertical else 0.052) * (largura if vertical else altura)
    tamanho = tamanho or int(round(base * float(est.get("tamanho", 1.0))))
    cor = _cor_ass(_cor_tema(est.get("cor", "#FFFFFF"), tema))
    destaque = _cor_ass(_cor_tema(est.get("cor_destaque", "destaque"), tema))
    caixa = est.get("caixa")
    negrito = -1 if int(est.get("peso", 700)) >= 600 else 0
    alinh = POSICOES.get(posicao, 2)
    margem_v = int(altura * (0.30 if vertical and posicao == "baixo" else 0.08))
    if caixa:
        borda_estilo, contorno_px, sombra_px = 3, max(4, tamanho // 4), 0
        cor_contorno = _cor_ass(caixa.get("cor", "#000000"), int(round((1 - float(caixa.get("opacidade", 0.6))) * 255)))
        cor_fundo = cor_contorno
    else:
        borda_estilo = 1
        contorno_px = round(float(est.get("contorno", 1.0)) * tamanho / 14, 1)
        sombra_px = round(float(est.get("sombra", 1.0)) * tamanho / 28, 1)
        alfa = int(round((1 - float(est.get("opacidade_contorno", 1.0))) * 255))
        cor_contorno = _cor_ass(_cor_tema(est.get("cor_contorno", "#000000"), tema), alfa)
        cor_fundo = _cor_ass("#000000", 0x80)
    efeito = ""
    # brilho: uma camada de trás com o contorno grosso, desfocado, na cor de destaque (e o
    # preenchimento transparente); a camada da frente é o texto nítido de sempre
    brilho = (f"{{\\1a&HFF&\\3c{_cor_ass(_cor_tema(est.get('cor_destaque', 'destaque'), tema))}\\3a&H50&"
              f"\\bord{max(4, tamanho // 5)}\\blur{max(4, tamanho // 6)}\\shad0}}") if est.get("brilho") else ""
    escala = int(round(100 * float(est.get("escala_destaque", 1.08))))
    cab = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {largura}", f"PlayResY: {altura}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Legenda,{fonte},{tamanho},{cor},{cor},{cor_contorno},{cor_fundo},{negrito},0,0,0,"
        f"100,100,0,0,{borda_estilo},{contorno_px:g},{sombra_px:g},{alinh},{int(largura * 0.08)},{int(largura * 0.08)},"
        f"{margem_v},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    alta = bool(est.get("caixa_alta"))
    ev = []
    for b in bls:
        ls = [l.upper() if alta else l for l in b["linhas"]]
        if not palavra:
            texto_b = "\\N".join(_esc_ass(l) for l in ls)
            if brilho:
                ev.append(f"Dialogue: 0,{_tc_ass(b['inicio'])},{_tc_ass(b['fim'])},Legenda,,0,0,0,,{brilho}{texto_b}")
            ev.append(f"Dialogue: 1,{_tc_ass(b['inicio'])},{_tc_ass(b['fim'])},Legenda,,0,0,0,,{efeito}{texto_b}")
            continue
        ws = b["palavras"]
        textos = [w["texto"].upper() if alta else w["texto"] for w in ws]
        # onde cai a quebra de linha (pelas linhas já calculadas)
        quebra_em = len(ls[0].split()) if len(ls) > 1 else None
        for i, w in enumerate(ws):
            t0 = b["inicio"] if i == 0 else w["inicio"]
            t1 = ws[i + 1]["inicio"] if i + 1 < len(ws) else b["fim"]
            if t1 <= t0:
                continue
            partes = []
            for j, t in enumerate(textos):
                if quebra_em and j == quebra_em:
                    partes.append("\\N")
                elif j:
                    partes.append(" ")
                t = _esc_ass(t)
                partes.append(f"{{\\c{destaque}\\fscx{escala}\\fscy{escala}}}{t}{{\\c{cor}\\fscx100\\fscy100}}"
                              if j == i else t)
            if brilho:
                ev.append(f"Dialogue: 0,{_tc_ass(t0)},{_tc_ass(t1)},Legenda,,0,0,0,,{brilho}{''.join(partes)}")
            ev.append(f"Dialogue: 1,{_tc_ass(t0)},{_tc_ass(t1)},Legenda,,0,0,0,,{efeito}{''.join(partes)}")
    return "\n".join(cab + ev) + "\n"


def para_hyperframes(bls: list[dict], de: float, ate: float, modo: str = "palavra", posicao: str = "baixo") -> dict:
    """Parâmetros do efeito `legenda-animada` para o trecho [de, ate) da sequência (tempos relativos ao trecho)."""
    sel = [b for b in bls if b["fim"] > de and b["inicio"] < ate]
    out = []
    for b in sel:
        out.append({"i": round(max(b["inicio"], de) - de, 3), "f": round(min(b["fim"], ate) - de, 3),
                    "l": len(b["linhas"][0].split()) if len(b["linhas"]) > 1 else 0,
                    "p": [[w["texto"], round(max(w["inicio"], de) - de, 3)] for w in b["palavras"]]})
    return {"blocos": out, "modo": modo, "posicao": posicao}


def texto_revisao(bls: list[dict]) -> str:
    from .tempo import hms
    linhas = [f"# {len(bls)} blocos de legenda · tempo da sequência · cps = caracteres por segundo"]
    for b in bls:
        linhas.append(f"{b['id']}  {hms(b['inicio'])}–{hms(b['fim'])}  {b['cps']:>4} cps  {' / '.join(b['linhas'])}")
    return "\n".join(linhas) + "\n"


# ------------------------------------------------------------------ versões no estado do vídeo
def pasta_legendas(pasta) -> Path:
    from . import estado as E
    p = E.caminho_estado(pasta).parent / "legendas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ler_atual(pasta) -> tuple[dict, Path]:
    """Os blocos da versão atual (o JSON de _CLAUDE/legendas) e o caminho dele."""
    from . import estado as E
    d = E.ler(pasta)
    arq = (d.get("legendas") or {}).get("arquivo")
    if not arq:
        raise E.ErroEstado("ainda não há legendas: rode 'legendas.py gerar' antes")
    caminho = Path(arq) if Path(arq).is_absolute() else E.caminho_estado(pasta).parent.parent / arq
    return json.loads(caminho.read_text(encoding="utf-8")), caminho


def gravar_versao(pasta, conteudo: dict) -> Path:
    """Grava blocos_vNN.json (versão nova), o revisao.txt e aponta o estado para ela."""
    from . import estado as E
    dest = pasta_legendas(pasta)
    versoes = [int(m.group(1)) for f in dest.glob("blocos_v*.json") if (m := re.fullmatch(r"blocos_v(\d+)\.json", f.name))]
    n = max(versoes, default=0) + 1
    conteudo["versao"] = n
    arq = dest / f"blocos_v{n:02d}.json"
    arq.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")
    (dest / "revisao.txt").write_text(texto_revisao(conteudo["blocos"]), encoding="utf-8")
    with E.editar(pasta) as d:
        bloco = d.setdefault("legendas", {})
        bloco.update({"versao": n, "arquivo": str(arq.relative_to(E.caminho_estado(pasta).parent.parent).as_posix()),
                      "base_cortes_versao": conteudo["base_cortes_versao"]})
    return arq


def corrigir_bloco(pasta, ident: str, texto: str) -> tuple[dict, Path]:
    """Troca o texto de um bloco (mantém os tempos) e grava uma versão nova."""
    from . import estado as E
    texto = " ".join(texto.split())
    if not texto:
        raise E.ErroEstado("o texto da legenda não pode ficar vazio")
    conteudo, _ = ler_atual(pasta)
    op = conteudo["opcoes"]
    for i, b in enumerate(conteudo["blocos"]):
        if b["id"] == ident:
            conteudo["blocos"][i] = retexto(b, texto, op["max_caracteres"], op["linhas"])
            arq = gravar_versao(pasta, conteudo)
            return conteudo["blocos"][i], arq
    raise E.ErroEstado(f"bloco {ident} não encontrado")
