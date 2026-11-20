"""Leitura e gravação do estado do vídeo (_CLAUDE/projeto.json).

Regras:
- toda gravação é atômica (arquivo temporário + rename) e sob trava,
  porque o Claude e o painel podem gravar no mesmo arquivo;
- `revisao` sobe a cada gravação; quem leu a revisão N e tenta gravar
  quando o arquivo já está na N+1 recebe um Conflito, em vez de apagar
  a mudança do outro;
- `cortes.versao` e `motions.versao` sobem sozinhas quando o conteúdo muda,
  e é por elas que os alertas de "plano desatualizado" aparecem.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as _dt
import json
import os
from pathlib import Path
import re
import tempfile
import time

PASTA_CLAUDE = "_CLAUDE"
ARQUIVO = "projeto.json"
SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "projeto.schema.json"

FLUXO_PADRAO = ["iniciar", "preparar", "cortes", "motion_mapa", "assets",
                "motion_render", "camera", "sfx"]
STATUS_FEITO = {"concluido", "nao_precisa"}

# Blocos que são listas de itens com id, e o prefixo do id.
LISTAS = {
    "notas_edicao": "n", "marcadores": "m", "pendencias": "p", "entregas": None,
    "cortes.segmentos": "s", "motions.itens": "mo", "camera.movimentos": "cam",
    "sfx.itens": "sfx",
}


class ErroEstado(Exception):
    pass


class Conflito(ErroEstado):
    pass


def agora() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def nome_etapa(nome: str) -> str:
    """'motion-mapa' e 'motion_mapa' são a mesma etapa."""
    return nome.strip().lower().replace("-", "_")


def caminho_estado(pasta: str | os.PathLike) -> Path:
    p = Path(pasta)
    if p.name == ARQUIVO:
        return p
    if p.name == PASTA_CLAUDE:
        return p / ARQUIVO
    return p / PASTA_CLAUDE / ARQUIVO


# --------------------------------------------------------------- trava
@contextlib.contextmanager
def trava(arquivo: Path, espera: float = 10.0, velha: float = 60.0):
    """Trava simples por arquivo (.lock), portátil entre Windows e Unix."""
    lock = arquivo.with_name("." + arquivo.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    limite = time.monotonic() + espera
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > velha:
                    lock.unlink(missing_ok=True)  # trava esquecida por um processo morto
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > limite:
                raise ErroEstado(f"o estado está travado por outro processo ({lock})")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


# --------------------------------------------------------------- ler / gravar
def ler(pasta) -> dict:
    arq = caminho_estado(pasta)
    if not arq.exists():
        raise ErroEstado(f"não existe {arq}: o vídeo ainda não foi iniciado")
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def _gravar_atomico(arq: Path, dados: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".projeto.", suffix=".tmp", dir=arq.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        try:  # mkstemp cria com 0600; manter as permissões de um arquivo comum
            modo = arq.stat().st_mode & 0o777 if arq.exists() else 0o666 & ~_umask()
            os.chmod(tmp, modo)
        except OSError:
            pass
        os.replace(tmp, arq)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _umask() -> int:
    atual = os.umask(0)
    os.umask(atual)
    return atual


def _ajustar_versoes(antes: dict | None, depois: dict) -> None:
    """Sobe cortes.versao / motions.versao quando o conteúdo mudou."""
    for bloco, campo in (("cortes", "segmentos"), ("motions", "itens")):
        novo = depois.get(bloco)
        if not isinstance(novo, dict):
            continue
        velho = (antes or {}).get(bloco) or {}
        if bloco == "motions":
            # Mudar só o status/render de um item não é mudar o plano.
            def plano(itens):
                return [{k: v for k, v in i.items() if k not in ("status", "render")}
                        for i in itens or []]
            mudou = plano(novo.get(campo)) != plano(velho.get(campo))
        else:
            mudou = novo.get(campo) != velho.get(campo)
        versao_velha = velho.get("versao", 0)
        if mudou and novo.get("versao", 0) <= versao_velha:
            novo["versao"] = versao_velha + 1
        novo.setdefault("versao", max(versao_velha, 1))


def gravar(pasta, dados: dict, revisao_lida: int | None = None, validar_antes: bool = True) -> dict:
    """Grava o estado. Com `revisao_lida`, recusa se alguém gravou no meio."""
    arq = caminho_estado(pasta)
    with trava(arq):
        antes = None
        if arq.exists():
            with open(arq, encoding="utf-8") as f:
                antes = json.load(f)
            if revisao_lida is not None and antes.get("revisao") != revisao_lida:
                raise Conflito(
                    f"o estado mudou desde a leitura (revisão {revisao_lida} → {antes.get('revisao')}); "
                    "leia de novo e refaça a mudança")
        dados = copy.deepcopy(dados)
        _ajustar_versoes(antes, dados)
        dados["revisao"] = (antes or {}).get("revisao", 0) + 1
        dados["atualizado_em"] = agora()
        if validar_antes:
            erros = validar(dados)
            if erros:
                raise ErroEstado("estado inválido, nada foi gravado:\n- " + "\n- ".join(erros))
        _gravar_atomico(arq, dados)
        return dados


@contextlib.contextmanager
def editar(pasta):
    """with editar(pasta) as e: e['x'] = 1  → lê, deixa mudar e grava sem perder concorrência."""
    dados = ler(pasta)
    rev = dados.get("revisao")
    yield dados
    gravar(pasta, dados, revisao_lida=rev)


def criar(pasta, projeto: str, perfil: str | None = None, fluxo: list[str] | None = None) -> dict:
    arq = caminho_estado(pasta)
    if arq.exists():
        raise ErroEstado(f"{arq} já existe: o vídeo já foi iniciado (nada foi mudado)")
    arq.parent.mkdir(parents=True, exist_ok=True)
    etapas = [nome_etapa(e) for e in (fluxo or FLUXO_PADRAO)]
    dados = {
        "schema": 1, "revisao": 0, "projeto": projeto, "perfil": perfil,
        "criado_em": agora(), "fluxo": etapas,
        "etapas": {e: "pendente" for e in etapas},
        "ferramentas": {}, "pendencias": [], "entregas": [],
    }
    return gravar(pasta, dados)


# --------------------------------------------------------------- validação
def validar(dados: dict) -> list[str]:
    """Lista de erros (vazia = válido). Usa jsonschema se instalado."""
    erros: list[str] = []
    try:
        import jsonschema  # type: ignore
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        with open(SCHEMA, encoding="utf-8") as f:
            schema = json.load(f)
        v = jsonschema.Draft202012Validator(schema)
        for e in sorted(v.iter_errors(dados), key=lambda e: list(e.path)):
            caminho = ".".join(str(p) for p in e.path) or "(raiz)"
            erros.append(f"{caminho}: {e.message}")
    else:
        for campo in ("schema", "revisao", "projeto", "fluxo", "etapas"):
            if campo not in dados:
                erros.append(f"falta o campo '{campo}'")
    # Regras que o JSON Schema não expressa bem.
    for etapa in dados.get("etapas", {}):
        if etapa not in dados.get("fluxo", []):
            erros.append(f"etapas.{etapa}: etapa fora do fluxo {dados.get('fluxo')}")
    for nome, _ in LISTAS.items():
        itens = obter(dados, nome, [])
        if not isinstance(itens, list):
            continue
        vistos = set()
        for i in itens:
            if isinstance(i, dict) and "id" in i:
                if i["id"] in vistos:
                    erros.append(f"{nome}: id repetido '{i['id']}'")
                vistos.add(i["id"])
        for i in itens:
            if isinstance(i, dict) and "inicio" in i and "fim" in i:
                if isinstance(i["inicio"], (int, float)) and isinstance(i["fim"], (int, float)) and i["fim"] <= i["inicio"]:
                    erros.append(f"{nome}.{i.get('id', '?')}: fim ({i['fim']}) não é depois do início ({i['inicio']})")
    return erros


# --------------------------------------------------------------- caminhos
def _partes(caminho: str) -> list:
    partes = []
    for p in caminho.split("."):
        partes.append(int(p) if re.fullmatch(r"\d+", p) else p)
    return partes


def obter(dados: dict, caminho: str, padrao=None):
    atual = dados
    for p in _partes(caminho):
        try:
            atual = atual[p]
        except (KeyError, IndexError, TypeError):
            return padrao
    return atual


def definir(dados: dict, caminho: str, valor) -> None:
    partes = _partes(caminho)
    atual = dados
    for i, p in enumerate(partes[:-1]):
        prox = partes[i + 1]
        if isinstance(atual, list):
            atual = atual[p]
            continue
        if p not in atual or atual[p] is None:
            atual[p] = [] if isinstance(prox, int) else {}
        atual = atual[p]
    ultimo = partes[-1]
    if isinstance(atual, list) and ultimo == len(atual):
        atual.append(valor)
    else:
        atual[ultimo] = valor


def interpretar_valor(texto: str):
    """'3' → 3, 'true' → True, '{"a":1}' → dict; o resto fica texto."""
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return texto


def proximo_id(itens: list, prefixo: str) -> str:
    maior = 0
    largura = 2
    for i in itens or []:
        m = re.fullmatch(rf"{re.escape(prefixo)}(\d+)", str(i.get("id", "")))
        if m:
            maior = max(maior, int(m.group(1)))
            largura = max(largura, len(m.group(1)))
    return f"{prefixo}{maior + 1:0{largura}d}"


def achar_item(dados: dict, ident: str):
    """Procura um id em todas as listas. Devolve (caminho_da_lista, índice, item)."""
    for nome in LISTAS:
        itens = obter(dados, nome, [])
        if isinstance(itens, list):
            for idx, i in enumerate(itens):
                if isinstance(i, dict) and i.get("id") == ident:
                    return nome, idx, i
    return None


# --------------------------------------------------------------- operações
def mudar_etapa(dados: dict, etapa: str, status: str) -> None:
    etapa = nome_etapa(etapa)
    if etapa not in dados["fluxo"]:
        raise ErroEstado(f"a etapa '{etapa}' não está no fluxo: {', '.join(dados['fluxo'])}")
    dados["etapas"][etapa] = status
    # Guarda em que versão do corte/plano cada etapa dependente foi feita.
    if status in ("aguardando_aprovacao", "concluido"):
        cortes_v = obter(dados, "cortes.versao")
        motions_v = obter(dados, "motions.versao")
        if etapa == "motion_mapa" and cortes_v:
            dados.setdefault("motions", {})["base_cortes_versao"] = cortes_v
        if etapa in ("camera", "sfx"):
            bloco = dados.setdefault(etapa, {})
            if cortes_v:
                bloco["base_cortes_versao"] = cortes_v
            if motions_v:
                bloco["base_motions_versao"] = motions_v


def nova_pendencia(dados: dict, etapa: str, texto: str, item: str | None = None) -> str:
    lista = dados.setdefault("pendencias", [])
    pid = proximo_id(lista, "p")
    p = {"id": pid, "etapa": nome_etapa(etapa), "texto": texto, "criada_em": agora()}
    if item:
        p["item"] = item
    lista.append(p)
    return pid


def resolver_pendencia(dados: dict, pid: str) -> None:
    for p in dados.get("pendencias", []):
        if p["id"] == pid:
            if p.get("resolvida_em"):
                raise ErroEstado(f"a pendência {pid} já estava resolvida")
            p["resolvida_em"] = agora()
            return
    raise ErroEstado(f"pendência {pid} não encontrada")


def pendencias_abertas(dados: dict) -> list[dict]:
    return [p for p in dados.get("pendencias", []) if not p.get("resolvida_em")]


def alertas(dados: dict) -> list[str]:
    """O que ficou desatualizado ou fora de ordem."""
    out = []
    etapas = dados.get("etapas", {})
    cortes_v = obter(dados, "cortes.versao")
    motions_v = obter(dados, "motions.versao")

    base = obter(dados, "motions.base_cortes_versao")
    if cortes_v and base and base != cortes_v and obter(dados, "motions.itens"):
        out.append(f"o corte mudou (v{base} → v{cortes_v}) depois do plano de animação: "
                   "rever os tempos do motion-mapa antes de seguir")
    for bloco in ("camera", "sfx"):
        if etapas.get(bloco) not in ("aguardando_aprovacao", "concluido", "em_andamento"):
            continue
        bc = obter(dados, f"{bloco}.base_cortes_versao")
        bm = obter(dados, f"{bloco}.base_motions_versao")
        if cortes_v and bc and bc != cortes_v:
            out.append(f"{bloco}: feito sobre o corte v{bc}, o corte agora é v{cortes_v}")
        if motions_v and bm and bm != motions_v:
            out.append(f"{bloco}: feito sobre o plano de animação v{bm}, o plano agora é v{motions_v}")

    bl = obter(dados, "legendas.base_cortes_versao")
    if cortes_v and bl and bl != cortes_v:
        out.append(f"legendas: geradas sobre o corte v{bl}, o corte agora é v{cortes_v} (gere de novo)")
    for a in obter(dados, "midia.arquivos", []) or []:
        if a.get("audio_tratado") and not Path(a["audio_tratado"]).exists():
            out.append(f"{a['id']}: a voz tratada {a['audio_tratado']} não existe mais")

    fluxo = dados.get("fluxo", [])
    for i, e in enumerate(fluxo):
        if etapas.get(e) in ("concluido", "aguardando_aprovacao"):
            antes = [a for a in fluxo[:i] if etapas.get(a) not in STATUS_FEITO]
            if antes:
                out.append(f"{e} está '{etapas[e]}', mas {', '.join(antes)} ainda não terminou")
    return out


def proxima_etapa(dados: dict) -> str | None:
    etapas = dados.get("etapas", {})
    for e in dados.get("fluxo", []):
        if etapas.get(e) not in STATUS_FEITO:
            return e
    return None


# --------------------------------------------------------------- resumos
def _hms(s):
    from .tempo import hms
    return hms(s, 1) if isinstance(s, (int, float)) else "?"


def _resumo_cortes(d):
    c = d.get("cortes") or {}
    segs = c.get("segmentos") or []
    total = sum(s["fim"] - s["inicio"] for s in segs)
    linhas = [f"cortes v{c.get('versao', '?')}: {len(segs)} segmentos, {_hms(total)} de vídeo"]
    for s in segs:
        texto = (s.get("texto") or "")[:60]
        linhas.append(f"  {s['id']}  {s['video']}  {_hms(s['inicio'])}–{_hms(s['fim'])}  {texto}")
    return linhas


def _resumo_motions(d):
    m = d.get("motions") or {}
    itens = m.get("itens") or []
    cont = {}
    for i in itens:
        cont[i.get("status", "?")] = cont.get(i.get("status", "?"), 0) + 1
    linhas = [f"motions v{m.get('versao', '?')}: {len(itens)} itens ({', '.join(f'{v} {k}' for k, v in cont.items()) or 'nenhum'})"]
    for i in itens:
        t = f"{_hms(i['inicio_seq'])}" if "inicio_seq" in i else "?"
        linhas.append(f"  {i['id']}  {i.get('status', '?'):<12} {t:>9}  {i.get('formato', ''):<14} {(i.get('ideia') or '')[:50]}")
    return linhas


def _resumo_lista(d, nome, campos):
    itens = obter(d, nome, []) or []
    linhas = [f"{nome}: {len(itens)}"]
    for i in itens:
        partes = [str(i.get("id", "?"))]
        for c in campos:
            v = i.get(c)
            if v is None:
                continue
            partes.append(_hms(v) if c in ("tempo", "inicio", "fim") else str(v)[:70])
        linhas.append("  " + "  ".join(partes))
    return linhas


def resumo_bloco(dados: dict, bloco: str) -> list[str]:
    bloco = bloco.strip()
    if bloco == "cortes":
        return _resumo_cortes(dados)
    if bloco == "motions":
        return _resumo_motions(dados)
    if bloco == "marcadores":
        return _resumo_lista(dados, "marcadores", ["video", "tempo", "tipo", "texto"])
    if bloco == "notas_edicao":
        return _resumo_lista(dados, "notas_edicao", ["video", "inicio", "etapa", "texto"])
    if bloco == "pendencias":
        abertas = pendencias_abertas(dados)
        return [f"pendências abertas: {len(abertas)}"] + [
            f"  {p['id']}  {p['etapa']}  {p['texto']}" for p in abertas]
    if bloco in ("camera", "sfx"):
        b = dados.get(bloco) or {}
        lista = b.get("movimentos" if bloco == "camera" else "itens") or []
        return [f"{bloco}: {len(lista)} itens, recortes feitos: {len(b.get('recortes') or [])}"] + [
            "  " + "  ".join(str(v)[:40] for k, v in i.items() if k in ("id", "inicio_seq", "tipo", "som", "descricao"))
            for i in lista]
    valor = obter(dados, bloco)
    if valor is None:
        raise ErroEstado(f"o bloco '{bloco}' não existe neste estado")
    if isinstance(valor, dict):
        return [f"{bloco}:"] + [f"  {k}: {_curto(v)}" for k, v in valor.items()]
    if isinstance(valor, list):
        return [f"{bloco}: {len(valor)} itens"] + [f"  {_curto(v)}" for v in valor[:50]]
    return [f"{bloco}: {valor}"]


def _curto(v, n=90):
    if isinstance(v, (dict, list)):
        texto = json.dumps(v, ensure_ascii=False)
        if len(texto) > n:
            tipo = "itens" if isinstance(v, list) else "campos"
            return f"<{len(v)} {tipo}> " + texto[: n - 15] + "…"
        return texto
    return str(v)


def _onde_pendencia(dados: dict, p: dict) -> str:
    """' (sobre mo04 · em 1:12.40 da sequência = cam01 3:05.20 · pelo painel)', o que houver."""
    partes = []
    if p.get("item"):
        partes.append(f"sobre {p['item']}")
    if p.get("video") and p.get("tempo") is not None:
        seq = None
        segs = obter(dados, "cortes.segmentos") or []
        fps = obter(dados, "midia.fps")
        if segs and fps:
            from .linha import Linha
            seq, _p = Linha(segs, fps).origem_para_seq(p["video"], p["tempo"])
        onde = f"{p['video']} {_hms(p['tempo'])}"
        partes.append(f"em {_hms(seq)} da sequência = {onde}" if seq is not None else f"em {onde} (fora do corte atual)")
    elif p.get("tempo_seq") is not None:
        partes.append(f"em {_hms(p['tempo_seq'])} da sequência")
    if p.get("origem") == "painel":
        partes.append("pelo painel")
    return f"  ({' · '.join(partes)})" if partes else ""


def resumo_status(dados: dict) -> list[str]:
    etapas = dados.get("etapas", {})
    marcas = {"concluido": "✓", "nao_precisa": "–", "em_andamento": "…",
              "aguardando_aprovacao": "?", "pendente": " "}
    linhas = [f"{dados.get('projeto')} · perfil {dados.get('perfil') or '—'} · revisão {dados.get('revisao')}"]
    for e in dados.get("fluxo", []):
        st = etapas.get(e, "pendente")
        marca = marcas.get(st, "?" if st.startswith("aguardando") else " ")
        extra = ""
        if e == "cortes" and dados.get("cortes"):
            extra = f"  (v{dados['cortes'].get('versao')}, {len(dados['cortes'].get('segmentos', []))} segmentos)"
        if e in ("motion_mapa", "motion_render") and dados.get("motions"):
            itens = dados["motions"].get("itens", [])
            if e == "motion_mapa":
                extra = f"  ({len(itens)} itens)"
            else:
                prontos = sum(1 for i in itens if i.get("status") in ("renderizado", "entregue"))
                ativos = sum(1 for i in itens if i.get("status") != "riscado")
                extra = f"  ({prontos}/{ativos} renderizados)"
        trechos = obter(dados, f"{e}.recortes") or []
        if trechos:
            extra += f"  (trechos feitos: {', '.join(str(t.get('ate', t)) if isinstance(t, dict) else str(t) for t in trechos)})"
        linhas.append(f"  [{marca}] {e:<14} {st}{extra}")
    prox = proxima_etapa(dados)
    linhas.append(f"próxima etapa: {prox}" if prox else "todas as etapas terminaram")
    abertas = pendencias_abertas(dados)
    if abertas:
        linhas.append(f"pendências ({len(abertas)}):")
        linhas += [f"  {p['id']}  {p['etapa']}: {p['texto']}{_onde_pendencia(dados, p)}" for p in abertas]
    al = alertas(dados)
    if al:
        linhas.append(f"alertas ({len(al)}):")
        linhas += [f"  ! {a}" for a in al]
    return linhas


def contar_aprendizados(pasta) -> int:
    arq = caminho_estado(pasta).parent / "aprendizados.md"
    if not arq.exists():
        return 0
    return sum(1 for l in arq.read_text(encoding="utf-8").splitlines() if l.lstrip().startswith("- [ ]"))
