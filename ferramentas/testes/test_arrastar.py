import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest

from edicao import config as C
from edicao import estado as E
from edicao import ff
from edicao import legendas as L
from edicao import midia
from edicao import mudancas as M
from edicao import painel as P
from edicao import render as R
from edicao import xmeml
import painel as SRV
import video_demo

F = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def modelo(tmp_path_factory, clipe):
    return video_demo.montar(tmp_path_factory.mktemp("demo_arr"), clipe)


@pytest.fixture
def video(modelo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDICAO_HOME", str(tmp_path / "edicao"))
    C.criar("Edson", "youtube-apresentador", perfil="padrao", estilo="tech-neon")
    v = tmp_path / modelo.name
    shutil.copytree(modelo, v, ignore=shutil.ignore_patterns("Brutos", "Renders"))
    return v


def _mo(v, mid):
    return next(m for m in E.ler(v)["motions"]["itens"] if m["id"] == mid)


# ------------------------------------------------------------------ no tempo
def test_mover_animacao_pronta(video):
    a0 = _mo(video, "mo01")
    r = M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo01", 1.0))
    m = _mo(video, "mo01")
    dur = a0["fim_seq"] - a0["inicio_seq"]
    assert r["mudou"] and m["inicio_seq"] == pytest.approx(1.0, abs=0.02) and m["fim_seq"] - m["inicio_seq"] == pytest.approx(dur, abs=1e-3)
    assert E.ler(video)["motions"]["versao"] > 0
    with pytest.raises(M.ErroMudanca, match="já está renderizada"):
        M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo01", 1.0, 1.5))
    M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo01", 999))
    m = _mo(video, "mo01")
    assert m["fim_seq"] <= R.plano(video, rascunho=True)["duracao"] + 1e-3, "no fim do vídeo, encosta no fim"


def test_esticar_animacao_da_biblioteca(video):
    with E.editar(video) as d:
        d["motions"]["itens"].append({"id": "mo09", "status": "aprovado", "inicio_seq": 1.0, "fim_seq": 5.0,
                                      "formato": "sobreposicao", "efeito": "tarja-nome", "params": {"nome": "x"}})
    M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo09", 1.0, 4.0))
    m = _mo(video, "mo09")
    assert m["inicio_seq"] == 1.0 and m["fim_seq"] == pytest.approx(4.0, abs=0.02), "a borda que não mexeu fica igual"
    with pytest.raises(M.ErroMudanca, match="a duração vai de"):
        M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo09", 1.0, 1.4))


def test_mover_som_e_registro(video):
    sid = E.ler(video)["sfx"]["itens"][0]["id"]
    M.aplicar(video, None, lambda d: M.mover(d, "sfx", sid, 2.5))
    d = E.ler(video)
    assert next(s for s in d["sfx"]["itens"] if s["id"] == sid)["inicio_seq"] == pytest.approx(2.5, abs=0.02)
    novas = M.nao_lidas(d)
    assert novas[-1]["item"] == sid and "movido" in novas[-1]["texto"]
    assert any("mudanças pelo painel ainda não lidas" in l for l in E.resumo_status(d))
    assert M.marcar_lidas(video) == len(novas) and not M.nao_lidas(E.ler(video))
    with pytest.raises(M.ErroMudanca):
        M.aplicar(video, None, lambda d: M.mover(d, "sfx", "sfx99", 1))
    with pytest.raises(M.ErroMudanca, match="não dá para mover"):
        M.aplicar(video, None, lambda d: M.mover(d, "cam", "c1", 1))


def test_tempo_da_legenda(video):
    c0, _ = L.ler_atual(video)
    b0, b1 = c0["blocos"][0], c0["blocos"][1]
    M.tempo_legenda(video, None, b0["id"], b0["inicio"], b0["fim"] - 0.3)
    c1, arq = L.ler_atual(video)
    assert c1["versao"] == c0["versao"] + 1 and c1["blocos"][0]["inicio"] == b0["inicio"]
    assert c1["blocos"][0]["fim"] == pytest.approx(b0["fim"] - 0.3, abs=0.02)
    # não passa por cima do vizinho
    M.tempo_legenda(video, None, b0["id"], b0["inicio"], b1["inicio"] + 2)
    assert L.ler_atual(video)[0]["blocos"][0]["fim"] == b1["inicio"]
    with pytest.raises(M.ErroMudanca, match="menos de"):
        M.tempo_legenda(video, None, b0["id"], b0["inicio"], b0["inicio"] + 0.05)
    # desfazer volta a versão anterior (e o revisao.txt dela)
    M.desfazer(video, None)
    M.desfazer(video, None)
    assert L.ler_atual(video)[0]["blocos"][0]["fim"] == b0["fim"]
    assert L.texto_revisao(c0["blocos"]) == (L.pasta_legendas(video) / "revisao.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ na tela
def test_posicionar(video):
    v0 = E.ler(video)["motions"]["versao"]
    M.aplicar(video, None, lambda d: M.posicionar(d, "motion", "mo01", 0.2, -0.9, 3))
    m = _mo(video, "mo01")
    assert m["posicao"] == {"x": 0.2, "y": -0.5, "escala": 2.0}, "fica nos limites"
    assert E.ler(video)["motions"]["versao"] == v0, "posição não é plano novo"
    assert P.dados(video)["motions"][0]["posicao"]["escala"] == 2.0
    with pytest.raises(M.ErroMudanca, match="quadro inteiro"):
        M.aplicar(video, None, lambda d: M.posicionar(d, "motion", "mo02", 0.1, 0))
    M.aplicar(video, None, lambda d: M.posicionar(d, "motion", "mo01", 0, 0, 1))
    assert "posicao" not in _mo(video, "mo01")
    M.aplicar(video, None, lambda d: M.posicionar(d, "legenda", None, 0.1, -0.3))
    d = E.ler(video)
    assert d["video"]["legendas"]["deslocamento"] == {"x": 0.1, "y": -0.3}
    assert L.opcoes_legenda(d, C.carregar())["deslocamento"] == {"x": 0.1, "y": -0.3}
    assert P.dados(video)["tema"]["legendas"]["deslocamento"]["y"] == -0.3


def test_ass_com_deslocamento():
    from edicao import efeitos as EF
    bl = [{"id": "l1", "inicio": 0, "fim": 1, "linhas": ["oi"], "palavras": [{"texto": "oi", "inicio": 0, "fim": 0.5}]}]
    tema = EF.mesclar_tema()
    base = L.ass(bl, tema, 1920, 1080, estilo=L.estilo_legenda("classica"))
    assert "\\pos" not in base
    # âncora da posição (margem de 8% = 86 px) + deslocamento (10% de 1920 = 192; -10% de 1080 = -108)
    for pos, an, y in (("baixo", 2, 1080 - 86 - 108), ("centro", 5, 540 - 108), ("topo", 8, 86 - 108)):
        x = L.ass(bl, tema, 1920, 1080, estilo=L.estilo_legenda("classica"), posicao=pos, deslocamento={"x": 0.1, "y": -0.1})
        ev = next(l for l in x.splitlines() if l.startswith("Dialogue: 1"))
        assert f"{{\\an{an}\\pos(1152,{y})}}" in ev, (pos, ev)
    br = L.ass(bl, tema, 1920, 1080, estilo=L.estilo_legenda("brilho"), deslocamento={"x": 0, "y": 0.2})
    assert all("\\pos(" in l for l in br.splitlines() if l.startswith("Dialogue:")), "o brilho anda junto"


def _luma_regiao(arq, quadro, x0, y0, x1, y1):
    import numpy as np
    raw = subprocess.run([ff.ffmpeg(), "-v", "error", "-i", str(arq), "-vf", f"select=eq(n\\,{quadro}),format=gray",
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    sond = ff.sondar(arq)["streams"][0]
    img = np.frombuffer(raw, np.uint8).reshape(int(sond["height"]), int(sond["width"]))
    h, w = img.shape
    return float(img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].mean())


def test_render_aplica_a_posicao(video, tmp_path):
    with E.editar(video) as d:
        d["motions"]["itens"] = [m for m in d["motions"]["itens"] if m["id"] == "mo01"]
        d["motions"]["itens"][0]["posicao"] = {"x": 0.35, "y": -0.45, "escala": 0.6}
        d["legendas"] = {}
    pl = R.plano(video, rascunho=True)
    assert pl["sobreposicoes"][0]["posicao"] == {"x": 0.35, "y": -0.45, "escala": 0.6}
    assert "arrastada: +35%, -45%, 60%" in R.resumo_plano(pl)
    R.renderizar(video, rascunho=True, legenda="nao", progresso=lambda m: None, saida=tmp_path / "p.mp4", de=1.0, ate=2.0)
    with E.editar(video) as d:
        d["motions"]["itens"][0].pop("posicao")
    R.renderizar(video, rascunho=True, legenda="nao", progresso=lambda m: None, saida=tmp_path / "o.mp4", de=1.0, ate=2.0)
    # a tarja do demo fica embaixo à esquerda; arrastada, ela sai de lá
    q = 12
    orig = _luma_regiao(tmp_path / "o.mp4", q, 0.18, 0.72, 0.28, 0.82)
    movida = _luma_regiao(tmp_path / "p.mp4", q, 0.18, 0.72, 0.28, 0.82)
    assert abs(orig - movida) > 15


def test_xml_basic_motion(video):
    with E.editar(video) as d:
        for m in d["motions"]["itens"]:
            if m["id"] == "mo01":
                m["posicao"] = {"x": 0.25, "y": -0.1, "escala": 0.8}
    x = xmeml.montar(E.ler(video), sondar=midia.analisar).xml()
    assert x.count("<name>Basic Motion</name>") == 1
    bloco = x[x.index("<name>Basic Motion</name>"):]
    assert "<value>80</value>" in bloco[:800] and "<horiz>0.25</horiz>" in bloco and "<vert>-0.1</vert>" in bloco


# ------------------------------------------------------------------ corte: ordem e desfazer
def test_reordenar_segmentos_e_desfazer_misturado(video):
    ids0 = [s["id"] for s in E.ler(video)["cortes"]["segmentos"]]
    P.editar_cortes(video, None, "mover", id=ids0[0], para=2)
    ids1 = [s["id"] for s in E.ler(video)["cortes"]["segmentos"]]
    assert ids1 == [ids0[1], ids0[2], ids0[0], *ids0[3:]]
    with pytest.raises(P.ErroPainel, match="já está"):
        P.editar_cortes(video, None, "mover", id=ids0[0], para=2)
    M.aplicar(video, None, lambda d: M.posicionar(d, "motion", "mo01", 0.1, 0.1, 1))
    M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo01", 0.2))
    assert P.dados(video)["desfazer_o_que"].startswith("mo01 movida")
    assert M.desfazer(video, None).startswith("mo01 movida")
    assert M.desfazer(video, None).startswith("mo01 na tela") and "posicao" not in _mo(video, "mo01")
    assert "levado" in M.desfazer(video, None)
    assert [s["id"] for s in E.ler(video)["cortes"]["segmentos"]] == ids0
    textos = [m["texto"] for m in E.ler(video)["painel"]["mudancas"]]
    assert sum(t.startswith("desfez") or "desfez" in t for t in textos) == 3


def test_desfazer_recusa_se_o_claude_mudou_depois(video):
    M.aplicar(video, None, lambda d: M.mover(d, "motion", "mo01", 0.4))
    with E.editar(video) as d:     # o Claude mexe no plano
        d["motions"]["itens"][0]["ideia"] = "outra"
    with pytest.raises(M.ErroMudanca, match="mudou depois"):
        M.desfazer(video, None)
    with pytest.raises(E.Conflito):
        M.aplicar(video, 1, lambda d: M.mover(d, "motion", "mo01", 0.4))


# ------------------------------------------------------------------ servidor e linha de comando
def _req(porta, metodo, caminho, corpo=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=60)
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None,
              headers={"Host": f"127.0.0.1:{porta}", "X-Painel-Token": "tok", "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_rotas(video):
    srv, painel = SRV.criar_servidor(str(video), 0, token="tok")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    porta = painel.porta
    rev = lambda: E.ler(video)["revisao"]  # noqa: E731
    try:
        st, j = _req(porta, "POST", "/api/mover", {"revisao": rev(), "tipo": "motion", "id": "mo01", "inicio": 1.2})
        assert st == 200 and j["dados"]["mudancas_painel"] == 1
        bl = L.ler_atual(video)[0]["blocos"][0]
        st, j = _req(porta, "POST", "/api/mover", {"revisao": rev(), "tipo": "leg", "id": bl["id"], "inicio": bl["inicio"],
                                                   "fim": bl["fim"] - 0.2})
        assert st == 200 and j["info"]["fim"] < bl["fim"]
        st, j = _req(porta, "POST", "/api/posicionar", {"revisao": rev(), "tipo": "motion", "id": "mo01", "x": 0.1, "y": 0, "escala": 1.2})
        assert st == 200 and j["dados"]["motions"][0]["posicao"]["escala"] == 1.2
        st, j = _req(porta, "POST", "/api/posicionar", {"revisao": rev(), "tipo": "motion", "id": "mo02", "x": 0.1})
        assert st == 400 and "quadro inteiro" in j["erro"]
        st, j = _req(porta, "POST", "/api/galeria/transicao", {"revisao": rev(), "id": "s002", "tipo": "dissolver"})
        assert st == 200
        st, j = _req(porta, "POST", "/api/desfazer", {"revisao": rev()})
        assert st == 200 and "transição" in j["info"]["desfeito"], "o que veio da galeria também se desfaz"
        st, j = _req(porta, "POST", "/api/cortes", {"revisao": rev(), "acao": "mover", "id": "s001", "para": 1})
        assert st == 200 and j["dados"]["segmentos"][1]["id"] == "s001"
        st, j = _req(porta, "POST", "/api/cortes/desfazer", {"revisao": rev()})
        assert st == 200 and j["dados"]["segmentos"][0]["id"] == "s001"
        assert _req(porta, "POST", "/api/mover", {"revisao": 1, "tipo": "sfx", "id": "x", "inicio": 0})[0] == 409
    finally:
        srv.shutdown()
        srv.server_close()
    r = subprocess.run([sys.executable, str(F / "painel.py"), "mudancas", str(video)], capture_output=True, text=True)
    assert r.returncode == 0 and "mo01 movida" in r.stdout and "ainda não lida" in r.stdout
    r = subprocess.run([sys.executable, str(F / "painel.py"), "mudancas", str(video), "--marcar-lidas", "--json"],
                       capture_output=True, text=True)
    assert json.loads(r.stdout.split("\n(marcadas")[0])[0]["item"] == "mo01"
    r = subprocess.run([sys.executable, str(F / "painel.py"), "mudancas", str(video)], capture_output=True, text=True)
    assert "nenhuma mudança nova" in r.stdout


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node.js")
def test_javascript_sem_erro_de_sintaxe():
    r = subprocess.run(["node", "--check", str(F / "painel_web" / "arrastar.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
