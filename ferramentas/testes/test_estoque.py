import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest

from edicao import boas_vindas as BV
from edicao import config as C
from edicao import efeitos as EF
from edicao import estado as E
from edicao import estoque as ES
from edicao import ff
from edicao import galeria as G
from edicao import legendas as L
from edicao import render as R
from edicao import transicoes as TR
import painel as SRV
import video_demo

F = Path(__file__).resolve().parent.parent


@pytest.fixture
def pessoa(tmp_path, monkeypatch):
    casa = tmp_path / "edicao"
    monkeypatch.setenv("EDICAO_HOME", str(casa))
    C.criar("Edson", "youtube-apresentador", perfil="padrao", estilo="tech-neon")
    return casa


@pytest.fixture(scope="module")
def ref(tmp_path_factory):
    arq = tmp_path_factory.mktemp("ref") / "ref.mp4"
    subprocess.run([ff.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=8:r=25", "-f", "lavfi",
                    "-i", "sine=d=8", "-shortest", "-pix_fmt", "yuv420p", str(arq)], check=True)
    return arq


@pytest.fixture(scope="module")
def modelo(tmp_path_factory, clipe):
    return video_demo.montar(tmp_path_factory.mktemp("demo_est"), clipe)


@pytest.fixture
def video(modelo, tmp_path, pessoa):
    v = tmp_path / modelo.name
    shutil.copytree(modelo, v, ignore=shutil.ignore_patterns("Brutos", "Renders"))
    return v


def _duracao(arq) -> float:
    return float(ff.sondar(arq)["format"]["duration"])


# ------------------------------------------------------------------ entrada
def test_entrada_com_trecho_e_ficha(pessoa, ref, monkeypatch):
    it = ES.nova_entrada("motion", "Entrada elástica", "passa do ponto e volta", ref, 1.0, 3.5, "titulo-impacto")
    p = Path(it["pasta"])
    assert it["id"] == "entrada-elastica" and it["status"] == "entrada" and p.parent.name == "entrada"
    assert _duracao(p / "trecho.mp4") == pytest.approx(2.5, abs=0.1)
    ficha = (p / "ficha.md").read_text(encoding="utf-8")
    assert "# Entrada elástica" in ficha and "passa do ponto e volta" in ficha and "titulo-impacto" in ficha
    assert "de 0:01,00 a 0:03,50" in ficha and "trecho.mp4" in ficha
    assert ES.nova_entrada("efeito", "Impacto", "x")["id"] == "impacto-2", "não pega o id de uma peça do motor"
    assert ES.nova_entrada("efeito", "Entrada elástica", "y")["id"] == "entrada-elastica-2"
    img = ref.parent / "r.png"
    subprocess.run([ff.ffmpeg(), "-v", "error", "-y", "-i", str(ref), "-frames:v", "1", str(img)], check=True)
    assert ES.nova_entrada("legenda", "Da imagem", "a cor", img)["trecho"] == "referencia.png"
    for args, msg in [(("bolo", "x", "y"), "tipo"), (("efeito", " ", "y"), "nome"), (("efeito", "x", ""), "gostou"),
                      (("efeito", "x", "y", ref, 0, 6), "máximo"), (("efeito", "x", "y", "/nao/existe.mp4"), "não achei")]:
        monkeypatch.setattr(ES, "TRECHO_MAX", 5.0)
        with pytest.raises(ES.ErroEstoque, match=msg):
            ES.nova_entrada(*args)
    assert not (ES.raiz() / "entrada" / "x").exists(), "entrada com erro não deixa pasta"


def test_resumo_e_status(pessoa, video):
    ES.nova_entrada("efeito", "Um", "x")
    linhas = E.resumo_status(E.ler(video))
    assert any(l.startswith("estoque: 1 esperando análise") for l in linhas)


# ------------------------------------------------------------------ do rascunho ao estoque
def test_legenda_do_estoque(pessoa, ref):
    ES.nova_entrada("legenda", "Amarelo grosso", "letra grossa amarela", ref, 0, 2, "impacto")
    it = ES.construir("amarelo-grosso")
    p = Path(it["pasta"])
    assert it["status"] == "rascunho" and p.parent.name == "legendas" and (p / "trecho.mp4").exists()
    est = json.loads((p / "estilo.json").read_text(encoding="utf-8"))
    assert est["titulo"] == "Amarelo grosso" and est["modo"] == L.estilo_legenda("impacto")["modo"]
    assert "amarelo-grosso" not in L.estilos_legenda(), "rascunho não aparece na galeria"
    assert L.estilo_legenda("amarelo-grosso")["titulo"] == "Amarelo grosso", "mas dá para a prévia"
    assert ES.previa("amarelo-grosso").name == "previa.png"
    est["modo"] = "voando"
    (p / "estilo.json").write_text(json.dumps(est), encoding="utf-8")
    with pytest.raises(ES.ErroEstoque, match="modo"):
        ES.aprovar("amarelo-grosso")
    est["modo"] = "palavra"
    (p / "estilo.json").write_text(json.dumps(est), encoding="utf-8")
    ES.aprovar("amarelo-grosso")
    assert list(L.estilos_legenda())[-1] == "amarelo-grosso" and L.estilos_legenda()["amarelo-grosso"]["_estoque"]["gostei"]
    cfg = C.carregar()
    cfg["legendas"]["estilo"] = "amarelo-grosso"
    assert C.validar(cfg)[0] == [], "a configuração aceita um estilo do estoque"
    ES.mudar_status("amarelo-grosso", "arquivado")
    assert "amarelo-grosso" not in L.estilos_legenda()
    ES.aprovar("amarelo-grosso")
    ES.pedir_ajuste("amarelo-grosso", "contorno mais fino")
    it = ES.item("amarelo-grosso")
    assert it["status"] == "rascunho" and "contorno mais fino" in (p / "ficha.md").read_text(encoding="utf-8")
    assert ES.resumo()["ajuste"] == 1
    ES.anotar_analise("amarelo-grosso", "contorno 1,6; sombra dura")
    assert "contorno 1,6" in (p / "ficha.md").read_text(encoding="utf-8")


def test_transicao_do_estoque_no_render(pessoa, video, ref, tmp_path):
    ES.nova_entrada("transicao", "Círculo", "abre em círculo", ref)
    p = Path(ES.construir("circulo")["pasta"])
    tr = json.loads((p / "transicao.json").read_text(encoding="utf-8"))
    tr.update({"xfade": "custom", "expr": "if(gt(P,0.5),A,B)", "previa": {"b": [{"opacity": 0}, {"opacity": 1}]}})
    (p / "transicao.json").write_text(json.dumps(tr), encoding="utf-8")
    assert ES.previa("circulo").suffix == ".gif"
    tr.pop("expr")
    (p / "transicao.json").write_text(json.dumps(tr), encoding="utf-8")
    assert any("expr" in e for e in ES.verificar("circulo"))
    tr.update({"xfade": "circleopen"})
    (p / "transicao.json").write_text(json.dumps(tr), encoding="utf-8")
    ES.aprovar("circulo")
    assert "circulo" in TR.listar() and TR.normalizar({"tipo": "circulo"})["duracao"] == tr["duracao"]["padrao"]
    assert G.catalogo(video)["transicoes"][-1]["estoque"]["nome"] == "Círculo"
    from edicao import painel as P
    assert P.dados(video)["transicoes"]["circulo"]["previa"]["b"][1]["opacity"] == 1
    with E.editar(video) as d:
        d["cortes"]["segmentos"][1]["transicao"] = {"tipo": "circulo", "duracao": 0.5}
        d["motions"]["itens"] = []
    pl = R.plano(video, rascunho=True)
    assert pl["transicoes"][0]["xfade"] == "circleopen"
    r = R.renderizar(video, rascunho=True, legenda="nao", progresso=lambda m: None, saida=tmp_path / "c.mp4", ate=2.5)
    assert r["transicoes"] == 1


def test_efeito_do_estoque_funciona_como_os_do_motor(pessoa, video, ref):
    ES.nova_entrada("efeito", "Tarja vidro", "vidro fosco", ref, 0, 2)
    p = Path(ES.construir("tarja-vidro", "tarja-nome")["pasta"])
    assert (p / "index.html").exists() and json.loads((p / "efeito.json").read_text())["titulo"] == "Tarja vidro"
    assert "tarja-vidro" not in EF.listar() and EF.carregar("tarja-vidro")["titulo"] == "Tarja vidro"
    assert ES.verificar("tarja-vidro") == []
    ES.aprovar("tarja-vidro")
    assert EF.listar()["tarja-vidro"]["_estoque"]["tipo"] == "efeito"
    r = EF.criar("tarja-vidro", video / "_CLAUDE" / "motion" / "mo09", EF.mesclar_tema(), {"nome": "Ana"}, 3, "30", "16:9")
    proj = video / "_CLAUDE" / "motion" / "mo09"
    assert r["efeito"] == "tarja-vidro" and not (proj / "ficha.md").exists() and not (proj / "trecho.mp4").exists()
    anim = next(a for a in G.catalogo(video)["animacoes"] if a["id"] == "tarja-vidro")
    assert anim["estoque"]["gostei"] == "vidro fosco" and anim["categoria"] == "efeito"
    assert "__hyperframes" in G.pagina_efeito(video, "tarja-vidro", {"nome": "Ana"})
    (p / "index.html").write_text("<html></html>", encoding="utf-8")
    assert any("data-duration" in e for e in ES.verificar("tarja-vidro"))


@pytest.mark.skipif(not os.environ.get("HYPERFRAMES_CMD"), reason="sem HyperFrames")
def test_previa_de_motion(pessoa, ref):
    ES.nova_entrada("motion", "Sobe", "sobe com blur", ref, 0, 1)
    ES.construir("sobe", "titulo-impacto")
    assert ES.previa("sobe").name == "previa.gif"


# ------------------------------------------------------------------ boas-vindas, painel, linha de comando
def test_boas_vindas_com_pecas_do_estoque(pessoa, ref, tmp_path, clipe):
    v = tmp_path / "2026-11-20_Teste"
    (v / "Brutos").mkdir(parents=True)
    shutil.copy(clipe / "cam01.mp4", v / "Brutos" / "A001.mp4")
    E.criar(v, v.name, "padrao", C.carregar()["fluxo"])
    ES.nova_entrada("efeito", "Tarja vidro", "vidro fosco")
    ES.construir("tarja-vidro", "tarja-nome")
    ES.aprovar("tarja-vidro")
    o = BV.opcoes(v)
    assert o["estoque"] == [{"id": "tarja-vidro", "tipo": "efeito", "nome": "Tarja vidro", "gostei": "vidro fosco"}]
    base = {"briefing": "x", "preset": "youtube-apresentador", "tema": {"tipo": "perfil", "id": "padrao"},
            "legenda": {"estilo": "classica"}}
    BV.salvar(v, {**base, "estoque": ["tarja-vidro"]})
    d = E.ler(v)
    assert d["boas_vindas"]["estoque"] == [{"id": "tarja-vidro", "tipo": "efeito", "nome": "Tarja vidro"}]
    br = (v / "_CLAUDE" / "briefing_painel.md").read_text(encoding="utf-8")
    assert "Peças do seu estoque" in br and "Tarja vidro (efeito, `tarja-vidro`): vidro fosco" in br
    with pytest.raises(BV.ErroBoasVindas, match="não está no seu estoque"):
        BV.salvar(v, {**base, "estoque": ["nada"]})


def _req(porta, metodo, caminho, corpo=None, bruto=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=60)
    h = {"Host": f"127.0.0.1:{porta}", "X-Painel-Token": "tok", "Content-Type": "application/json", **(cab or {})}
    c.request(metodo, caminho, body=bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None),
              headers=h)
    r = c.getresponse()
    corpo = r.read()
    try:
        return r.status, json.loads(corpo or b"{}")
    except ValueError:
        return r.status, corpo


def test_rotas_do_estoque(video, ref):
    srv, painel = SRV.criar_servidor(str(video), 0, token="tok")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    porta = painel.porta
    try:
        st, j = _req(porta, "POST", "/api/estoque/envio", bruto=ref.read_bytes(), cab={"X-Nome-Arquivo": "ref%20x.mp4"})
        assert st == 200 and j["envio"].endswith(".mp4")
        assert _req(porta, "POST", "/api/estoque/envio", bruto=b"x", cab={"X-Nome-Arquivo": "a.exe"})[0] == 400
        st, j = _req(porta, "POST", "/api/estoque/novo", {"tipo": "motion", "nome": "Pulo", "gostei": "o pulo",
                                                           "origem": {"tipo": "arquivo", "envio": j["envio"], "nome": "ref x.mp4",
                                                                      "de": 1, "ate": 2}})
        assert st == 200 and j["info"]["id"] == "pulo"
        assert not list((ES.raiz() / "_envios").glob("*")), "o envio some depois de virar trecho"
        st, j = _req(porta, "POST", "/api/estoque/novo", {"tipo": "transicao", "nome": "Do vídeo", "gostei": "o corte",
                                                           "origem": {"tipo": "video", "de": 0.2, "ate": 1.2}})
        assert st == 200
        it = ES.item("do-video")
        assert it["origem"]["tipo"] == "video" and (Path(it["pasta"]) / "trecho.mp4").exists()
        assert _req(porta, "POST", "/api/estoque/novo", {"tipo": "efeito", "nome": "x", "gostei": ""})[0] == 400
        st, j = _req(porta, "GET", "/api/estoque")
        assert st == 200 and {i["id"] for i in j["itens"]} == {"pulo", "do-video"} and j["resumo"]["entrada"] == 2
        assert j["itens"][0]["arquivos"]["trecho"] and j["bases"]["legenda"][0]["id"] == "classica"
        st, corpo = _req(porta, "GET", "/api/estoque/arquivo?id=pulo&qual=trecho")
        assert st == 200 and len(corpo) > 1000
        assert _req(porta, "GET", "/api/estoque/arquivo?id=pulo&qual=../../config")[0] == 404
        ES.construir("pulo", "titulo-impacto")
        assert _req(porta, "POST", "/api/estoque/aprovar", {"id": "pulo"})[0] == 200
        assert ES.item("pulo")["status"] == "ativo"
        assert _req(porta, "POST", "/api/estoque/ajuste", {"id": "pulo", "texto": "mais lento"})[0] == 200
        assert _req(porta, "POST", "/api/estoque/recusar", {"id": "do-video"})[0] == 200
        assert _req(porta, "POST", "/api/estoque/nada", {"id": "pulo"})[0] == 400
    finally:
        srv.shutdown()
        srv.server_close()


def test_cli(pessoa, ref):
    def rodar(*a):
        return subprocess.run([sys.executable, str(F / "estoque.py"), *a], capture_output=True, text=True,
                              env={**os.environ, "EDICAO_HOME": str(pessoa)})
    r = rodar("novo", "--tipo", "transicao", "--nome", "Flash", "--gostei", "o clarão curto", "--arquivo", str(ref), "--ate", "2")
    assert r.returncode == 0 and "flash na entrada" in r.stdout
    assert "esperando análise (1)" in rodar("listar").stdout
    assert "a partir de fade_branco" in rodar("construir", "flash", "--base", "fade_branco").stdout
    assert json.loads(rodar("listar", "--json").stdout)[0]["status"] == "rascunho"
    assert rodar("folha", "flash").returncode == 0 and (ES.raiz() / "transicoes" / "flash" / "folha.png").exists()
    assert rodar("verificar", "flash").stdout.strip() == "pronta para aprovar"
    assert rodar("previa", "flash").stdout.strip().endswith("previa.gif")
    assert "entrou no estoque" in rodar("aprovar", "flash").stdout
    assert "# Flash" in rodar("mostrar", "flash").stdout
    assert rodar("aprovar", "nada").returncode == 2
