"""Biblioteca de efeitos e de estilos.

Sem o HyperFrames, confere a estrutura e o que o `criar` gera para todo efeito, formato e estilo.
Com HYPERFRAMES_CMD apontando para o CLI (e GSAP_LOCAL para um gsap.min.js, se não houver internet),
roda também o `check` do HyperFrames em cada efeito.
"""
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from edicao import config as C
from edicao import efeitos as E

EFEITOS = E.listar()
ESTILOS = E.listar_estilos()
TIPOS = {"texto", "numero", "cor", "booleano", "opcao", "lista", "imagem"}
FORMATOS_EFEITO = {"tela_cheia", "sobreposicao", "sobreposicao_lateral", "enfase"}
VARS_TEMA = set(E.variaveis_do_tema(E.mesclar_tema(), "30"))


def test_ha_efeitos_e_estilos():
    assert len(EFEITOS) >= 12 and len(ESTILOS) >= 4
    assert {"limpo", "tech-neon", "editorial", "impacto"} <= set(ESTILOS)


@pytest.mark.parametrize("nome", EFEITOS)
def test_estrutura_do_efeito(nome):
    m = EFEITOS[nome]
    for campo in ("titulo", "descricao", "formato", "duracao", "parametros", "exemplo", "eventos_som", "bom_para", "evitar"):
        assert m.get(campo) not in (None, ""), campo
    assert m["formato"] in FORMATOS_EFEITO
    d = m["duracao"]
    assert d["min"] <= d["padrao"] <= d["max"]
    ids = [p["id"] for p in m["parametros"]]
    assert len(ids) == len(set(ids))
    assert not set(ids) & VARS_TEMA, "parâmetro com o nome de uma variável do tema"
    for p in m["parametros"]:
        assert p["tipo"] in TIPOS and p["rotulo"]
        assert re.fullmatch(r"[a-z][a-z0-9_]*", p["id"]) and not p["id"].startswith("t_")
        if p["tipo"] == "opcao":
            assert p["padrao"] in p["opcoes"]
    assert set(m["exemplo"]) <= set(ids), "o exemplo usa parâmetro que não existe"
    html = (E.EFEITOS / nome / "index.html").read_text(encoding="utf-8")
    assert 'href="../_comum/tema.css"' in html and 'src="../_comum/tema.js"' in html
    assert E.GSAP_CDN in html
    assert "Math.random" not in html and "Date.now" not in html, "só lógica determinística"
    assert re.search(r'id="root"[^>]*data-duration="' + re.escape(str(d["padrao"])) + '"', html)
    assert "HF.pronto(tl)" in html
    # transform no CSS de elemento animado some quando o GSAP anima (guias/hyperframes.md)
    assert not re.search(r"#(balao|rot)\s*\{[^}]*transform", html)
    assert (E.EFEITOS / nome / "previa.gif").exists()


@pytest.mark.parametrize("nome,formato,estilo", list(itertools.product(EFEITOS, ["16:9", "9:16"], [None, "limpo", "impacto"])))
def test_criar_em_todo_formato_e_estilo(nome, formato, estilo, tmp_path):
    m = EFEITOS[nome]
    tema = E.tema_de(estilo=estilo) if estilo else None
    r = E.criar(nome, tmp_path / "p", tema, m["exemplo"], None, "30000/1001", formato)
    html = (tmp_path / "p" / "index.html").read_text(encoding="utf-8")
    w, h = E.FORMATOS[formato]
    assert f'data-width="{w}"' in html and f'data-height="{h}"' in html and f"width={w}, height={h}" in html
    # duração da raiz: (N − 0,5)/fps
    n, dur = E.frames_e_duracao(m["duracao"]["padrao"], "30000/1001")
    assert r["frames"] == n and f'data-duration="{dur}"' in html
    decl = json.loads(re.search(r"data-composition-variables='([^']*)'", html).group(1).replace("&#39;", "'"))
    ids = {x["id"] for x in decl}
    assert {p["id"] for p in m["parametros"]} <= ids and VARS_TEMA <= ids
    padroes = {x["id"]: x["default"] for x in decl}
    for k, v in m["exemplo"].items():
        esperado = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
        assert padroes[k] == esperado
    if estilo:
        assert padroes["cor_destaque"] == ESTILOS[estilo]["cores"]["destaque"]
    assert "<style>" in html and "../_comum" not in html and (tmp_path / "p" / "tema.js").exists()
    ev = json.loads((tmp_path / "p" / "eventos.json").read_text(encoding="utf-8"))
    total = n / (30000 / 1001)
    assert all(0 <= e["t"] <= total + 1e-6 for e in ev)


def test_eventos_por_item_e_velocidade(tmp_path):
    r = E.criar("lista-passos", tmp_path / "a", None, {"itens": ["a", "b", "c"], "intervalo_f": 30}, 6)
    t = [e["t"] for e in r["eventos_som"] if e["tipo"] == "passo_entra"]
    assert t == pytest.approx([0.4, 1.4, 2.4], abs=0.01)
    rapido = E.criar("lista-passos", tmp_path / "b", E.tema_de(estilo="impacto"), {"itens": ["a", "b"], "intervalo_f": 30}, 6)
    t2 = [e["t"] for e in rapido["eventos_som"] if e["tipo"] == "passo_entra"]
    assert t2[1] - t2[0] == pytest.approx(1.0 / ESTILOS["impacto"]["movimento"]["velocidade"], abs=0.01)
    saida = [e for e in r["eventos_som"] if e["t"] > 5]
    assert all(e["t"] <= 6 for e in saida)


def test_erros_claros(tmp_path):
    with pytest.raises(E.ErroEfeito, match="não existe"):
        E.criar("nao-existe", tmp_path / "x")
    with pytest.raises(E.ErroEfeito, match="desconhecidos"):
        E.criar("contador", tmp_path / "a", params={"valor": 1, "inventado": 2})
    with pytest.raises(E.ErroEfeito, match="falta o parâmetro"):
        E.criar("tarja-nome", tmp_path / "b", params={})
    with pytest.raises(E.ErroEfeito, match="precisa ser um de"):
        E.criar("tarja-nome", tmp_path / "c", params={"nome": "x", "lado": "cima"})
    with pytest.raises(E.ErroEfeito, match="fora do intervalo"):
        E.criar("transicao-rampa", tmp_path / "d", duracao=5)
    with pytest.raises(E.ErroEfeito, match="formato"):
        E.criar("contador", tmp_path / "e", params={"valor": 1}, formato="21:9")
    (tmp_path / "f").mkdir(); (tmp_path / "f" / "algo").write_text("x")
    with pytest.raises(E.ErroEfeito, match="sobrescrever"):
        E.criar("contador", tmp_path / "f", params={"valor": 1})
    with pytest.raises(E.ErroEfeito, match="imagem"):
        E.criar("logo-revela", tmp_path / "g", params={"imagem": str(tmp_path / "nao.png")})


def test_imagem_e_gsap_local(tmp_path):
    logo = tmp_path / "Logo Oficial.SVG"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    gsap = tmp_path / "gsap.min.js"
    gsap.write_text("/* gsap */")
    r = E.criar("logo-revela", tmp_path / "p", params={"imagem": str(logo), "nome": "X"}, gsap=str(gsap))
    assert r["variaveis"]["imagem"] == "assets/imagem.svg"
    assert (tmp_path / "p" / "assets" / "imagem.svg").exists()
    html = (tmp_path / "p" / "index.html").read_text(encoding="utf-8")
    assert 'src="gsap.min.js"' in html and E.GSAP_CDN not in html


def test_ajuste_de_tema_por_item(tmp_path):
    r = E.criar("contador", tmp_path / "p", E.tema_de(estilo="limpo"), {"valor": 3, "cor_destaque": "#FF0000"})
    assert r["variaveis"]["cor_destaque"] == "#FF0000"


@pytest.mark.parametrize("estilo", ESTILOS)
def test_estilo_e_um_perfil_completo(estilo):
    d = E.ESTILOS / estilo
    for f in ("identidade.md", "estilo-motion.md", "estilo-camera.md", "estilo-cortes.md", "estilo-som.md",
              "catalogo.md", "LEIA-ME.md", "tema.json", "previa.png"):
        assert (d / f).exists(), f
    t = ESTILOS[estilo]
    for chave in ("cores", "fontes", "pesos", "raio", "material", "movimento", "titulo", "descricao", "para"):
        assert chave in t
    assert set(t["cores"]) == set(E.TEMA_PADRAO["cores"])
    assert set(t["movimento"]) == set(E.TEMA_PADRAO["movimento"])
    assert t["material"] in ("plano", "vidro", "papel", "neon")
    for cor in t["cores"].values():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", cor)
    # o catálogo só cita efeitos que existem
    for ef in re.findall(r"`([a-z-]+)`", (d / "catalogo.md").read_text(encoding="utf-8")):
        assert ef in EFEITOS, ef


def test_presets_sugerem_estilos_que_existem():
    for nome, p in C.listar_presets().items():
        assert p.get("estilo_sugerido") in ESTILOS, nome


def test_perfil_inicial_tem_tema(tmp_path):
    t = E.tema_de(perfil_dir=C.PERFIL_INICIAL)
    assert t["cores"] == E.TEMA_PADRAO["cores"]


def test_perfil_a_partir_de_estilo(tmp_path, monkeypatch):
    monkeypatch.setenv("EDICAO_HOME", str(tmp_path / "e"))
    C.criar("X", "reels", perfil="curtos", estilo="impacto")
    t = E.tema_de(perfil_dir=tmp_path / "e" / "perfis" / "curtos")
    assert t["cores"]["destaque"] == ESTILOS["impacto"]["cores"]["destaque"]
    with pytest.raises(C.ErroConfig):
        C.novo_perfil("y", estilo="nao-existe")


HF = os.environ.get("HYPERFRAMES_CMD")


@pytest.mark.skipif(not HF, reason="HyperFrames não configurado (HYPERFRAMES_CMD)")
@pytest.mark.parametrize("nome", EFEITOS)
def test_check_do_hyperframes(nome, tmp_path):
    proj = tmp_path / nome
    E.criar(nome, proj, E.tema_de(estilo="limpo"), EFEITOS[nome]["exemplo"], gsap=os.environ.get("GSAP_LOCAL"))
    ok, saida = E.checar(proj)
    assert ok, saida[-2000:]
