import hashlib
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.parse import quote

import pytest

from edicao import config as C
from edicao import estado as E
from edicao import ff
from edicao import galeria as G
from edicao import legendas as L
from edicao import painel as P
from edicao import render as R
from edicao import sons as S
from edicao import transicoes as TR
from edicao import xmeml
from edicao import midia
import exportar_xml
import painel as SRV
import video_demo

F = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def modelo(tmp_path_factory, clipe):
    return video_demo.montar(tmp_path_factory.mktemp("demo_gal"), clipe)


@pytest.fixture
def pessoa(tmp_path, monkeypatch):
    casa = tmp_path / "edicao"
    monkeypatch.setenv("EDICAO_HOME", str(casa))
    C.criar("Edson", "youtube-apresentador", perfil="padrao", estilo="tech-neon")
    return casa


@pytest.fixture
def video(modelo, tmp_path, pessoa):
    v = tmp_path / modelo.name
    shutil.copytree(modelo, v, ignore=shutil.ignore_patterns("Brutos", "Renders"))
    return v


def _editar(v):
    return P._editar(v, None)


# ------------------------------------------------------------------ biblioteca de transições
def test_biblioteca_de_transicoes():
    xf = subprocess.run([ff.ffmpeg(), "-hide_banner", "-h", "filter=xfade"], capture_output=True, text=True).stdout
    t = TR.listar()
    assert list(t) == ["dissolver", "fade_preto", "fade_branco", "zoom", "empurrar", "chicote"]
    for k, m in t.items():
        for campo in ("titulo", "descricao", "bom_para", "evitar", "xfade", "duracao", "xml"):
            assert campo in m, (k, campo)
        d = m["duracao"]
        assert d["min"] <= d["padrao"] <= d["max"]
        assert m["xfade"] in xf, f"{k}: o xfade '{m['xfade']}' não existe neste FFmpeg"
        assert m["xml"]["nome"] and m["xml"]["effectid"]
    assert TR.normalizar({"tipo": "zoom"}) == {"tipo": "zoom", "duracao": 0.45}
    assert TR.normalizar({"tipo": "corte"}) is None and TR.normalizar(None) is None
    with pytest.raises(TR.ErroTransicao, match="fora do intervalo"):
        TR.normalizar({"tipo": "chicote", "duracao": 3})
    with pytest.raises(TR.ErroTransicao, match="não existe"):
        TR.normalizar({"tipo": "estrela"})
    assert TR.quadros({"duracao": 0.5}, 30000 / 1001) == 16 and TR.quadros({"duracao": 0.01}, 30) == 2
    assert TR.do_efeito_xml("Dip to Color Dissolve", (255, 255, 255)) == "fade_branco"
    assert TR.do_efeito_xml("Dip to Color Dissolve", (0, 0, 0)) == "fade_preto"
    assert TR.do_efeito_xml("Cross Dissolve") == "dissolver"


def test_transicao_nao_muda_a_versao_do_corte(video):
    v0 = E.ler(video)["cortes"]["versao"]
    with E.editar(video) as d:
        d["cortes"]["segmentos"][1]["transicao"] = {"tipo": "dissolver", "duracao": 0.5}
    assert E.ler(video)["cortes"]["versao"] == v0
    assert not any("cortes" in a for a in E.alertas(E.ler(video)) if "mudou" in a)


def _luma(arq: Path, quadro: int) -> float:
    import numpy as np
    raw = subprocess.run([ff.ffmpeg(), "-v", "error", "-i", str(arq), "-vf", f"select=eq(n\\,{quadro}),format=gray",
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return float(np.frombuffer(raw, np.uint8).mean())


def test_render_com_transicoes(video, tmp_path):
    with E.editar(video) as d:
        segs = d["cortes"]["segmentos"]
        segs[1]["transicao"] = {"tipo": "fade_preto", "duracao": 0.6}
        segs[2]["transicao"] = {"tipo": "zoom"}
        segs[3]["transicao"] = {"tipo": "fade_branco", "duracao": 0.4}
        d["motions"]["itens"] = []        # nada por cima: só o vídeo e as transições
    pl = R.plano(video, rascunho=True)
    assert [t["tipo"] for t in pl["transicoes"]] == ["fade_preto", "zoom", "fade_branco"]
    t1 = pl["transicoes"][0]
    corte = pl["pedacos"][1]["seq_ini_f"]
    assert t1["ini_f"] == corte - t1["quadros"] // 2 and t1["quadros"] % 2 == 0
    assert t1["de"]["fonte_f"] == pl["pedacos"][0]["in_f"] + pl["pedacos"][0]["quadros"] - t1["quadros"] // 2
    assert "transição fade_preto" in R.resumo_plano(pl)
    r = R.renderizar(video, rascunho=True, legenda="nao", progresso=lambda m: None, saida=tmp_path / "t.mp4")
    assert r["transicoes"] == 3 and r["duracao"] == pytest.approx(r["duracao_sequencia"], abs=0.05)
    janela = lambda t: range(t["ini_f"], t["ini_f"] + t["quadros"])  # noqa: E731
    preto = min(_luma(tmp_path / "t.mp4", q) for q in janela(t1))
    branco = max(_luma(tmp_path / "t.mp4", q) for q in janela(pl["transicoes"][2]))
    longe = _luma(tmp_path / "t.mp4", corte + 30)
    assert preto < 20 and longe > 60, "dentro do 'passar pelo preto' a imagem chega ao preto"
    assert branco > 200, "dentro do clarão a imagem chega ao branco"
    assert _luma(tmp_path / "t.mp4", t1["ini_f"] - 3) > 60, "antes da janela, a imagem normal"


def test_transicao_sem_espaco_vira_corte_seco(video):
    with E.editar(video) as d:
        d["cortes"]["segmentos"][1]["transicao"] = {"tipo": "dissolver", "duracao": 2.0}
    pl = R.plano(video, rascunho=True, de=1.0)  # o trecho começa logo antes do corte
    assert not pl["transicoes"] and any("borda" in a for a in pl["avisos"])


def test_xml_com_transicoes_e_volta(video, tmp_path):
    with E.editar(video) as d:
        segs = d["cortes"]["segmentos"]
        segs[1]["transicao"] = {"tipo": "dissolver", "duracao": 0.5}
        segs[2]["transicao"] = {"tipo": "chicote"}
        segs[3]["transicao"] = {"tipo": "fade_preto", "duracao": 0.6}
    d = E.ler(video)
    for menos_um in (False, True):
        seq = xmeml.montar(d, sondar=midia.analisar, menos_um=menos_um)
        x = seq.xml()
        v = x.split("      </video>\n      <audio>")[0]
        assert v.count("<transitionitem>") == 3 and "<mediatype>video</mediatype>" in v
        assert "Dip to Color Dissolve" in v and "<red>0</red>" in v
        assert any("Chicote" in m.nome for m in seq.marcadores), "a que o programa não tem ganha um marcador"
        r = xmeml.ler_volta(x, d["midia"]["arquivos"])
        assert [s.get("transicao", {}).get("tipo") for s in r["segmentos"]] == [None, "dissolver", "dissolver", "fade_preto"]
        assert not r["avisos"]
    # a volta mantém o tipo da biblioteca quando o programa devolveu o equivalente
    arq = tmp_path / "volta.xml"
    arq.write_text(xmeml.montar(d, sondar=midia.analisar).xml(), encoding="utf-8")
    exportar_xml.main(["volta", str(video), str(arq), "--aplicar"])
    segs = E.ler(video)["cortes"]["segmentos"]
    assert segs[2]["transicao"]["tipo"] == "chicote" and segs[3]["transicao"]["tipo"] == "fade_preto"
    assert "efeito" not in segs[1]["transicao"]


def test_xml_sem_midia_sobrando_avisa(video):
    with E.editar(video) as d:
        s = d["cortes"]["segmentos"]
        s[0]["fim"] = d["midia"]["arquivos"][0]["duracao"]  # o primeiro vai até o fim do arquivo
        s[1]["transicao"] = {"tipo": "dissolver", "duracao": 0.5}
        s[1]["video"] = s[0]["video"]
    seq = xmeml.montar(E.ler(video), sondar=midia.analisar)
    x = seq.xml()
    assert any("sem mídia sobrando" in a for a in seq.avisos)
    assert x.split("      </video>\n      <audio>")[0].count("<transitionitem>") == 0


# ------------------------------------------------------------------ sons
def test_pacote_inicial_de_sons(tmp_path):
    r = S.pacote_inicial(tmp_path / "a")
    assert len(r["feitos"]) == 12 and r["sons"] == 12 and not r["erros"]
    ind = json.loads((tmp_path / "a" / "indice.json").read_text(encoding="utf-8"))
    cats = {s["categoria"] for s in ind["sons"]}
    assert cats == {"whoosh", "impacto", "pop", "clique", "ding", "riser", "glitch"}
    for s in ind["sons"]:
        assert s["licenca"] == S.LICENCA_PACOTE and s["nota"] and -6 < s["pico_db"] <= 0.5
    riser = next(s for s in ind["sons"] if s["id"] == "subida")
    assert riser["pico"] > 1.5, "a subida tem o pico no fim"
    # determinístico: o mesmo pacote byte a byte
    S.pacote_inicial(tmp_path / "b")
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    assert h(tmp_path / "a/whoosh/whoosh-curto.wav") == h(tmp_path / "b/whoosh/whoosh-curto.wav")
    assert S.pacote_inicial(tmp_path / "a")["pulados"] == list(S.PACOTE)


# ------------------------------------------------------------------ catálogo e páginas
def test_catalogo(video, pessoa):
    c = G.catalogo(video)
    assert [x["id"] for x in c["legendas"]][:3] == ["classica", "caixa", "karaoke"]
    assert {"tarja-nome", "titulo-impacto", "contador"} <= {a["id"] for a in c["animacoes"]}
    assert [t["id"] for t in c["transicoes"]][0] == "dissolver"
    assert c["sons"]["biblioteca"] is None and c["formato"] == "16:9"
    r = G.criar_pacote_sons()
    assert r["configurada"] and Path(C.carregar()["som"]["biblioteca"]) == pessoa / "sons"
    c = G.catalogo(video)
    assert set(c["sons"]["categorias"]) >= {"whoosh", "pop"}
    (video / "Assets").mkdir(exist_ok=True)
    shutil.copy(F.parent / "efeitos" / "_comum" / "fundo-previa.png", video / "Assets" / "logo.png")
    assert G.catalogo(video)["imagens"] == ["logo.png"]


def test_pagina_do_efeito(video):
    h = G.pagina_efeito(video, "tarja-nome", {"nome": "Edson", "nao_existe": 1})
    assert "window.__hyperframes" in h and "efeitoPronto" in h and 'src="tema.js"' not in h
    assert "Edson" in h and "HF.pronto" in h
    for ruim in ("../x", "nao-existe"):
        with pytest.raises(G.ErroGaleria):
            G.pagina_efeito(video, ruim)
    with pytest.raises(G.ErroGaleria, match="precisa ser um de"):
        G.pagina_efeito(video, "tarja-nome", {"lado": "cima"})
    (video / "Assets").mkdir(exist_ok=True)
    shutil.copy(F.parent / "efeitos" / "_comum" / "fundo-previa.png", video / "Assets" / "logo.png")
    h = G.pagina_efeito(video, "logo-revela", {"imagem": "logo.png", "nome": "Placas"})
    assert "data:image/png;base64," in h
    with pytest.raises(G.ErroGaleria, match="assets do projeto"):
        G.pagina_efeito(video, "logo-revela", {"imagem": "../../etc/passwd"})


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node.js")
@pytest.mark.parametrize("js", ["galeria.js", "painel.js"])
def test_javascript_sem_erro_de_sintaxe(js):
    r = subprocess.run(["node", "--check", str(F / "painel_web" / js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------------------ pôr no vídeo
def test_inserir_animacao(video):
    with _editar(video) as d:
        mid = G.inserir_animacao(d, video, "tarja-nome", {"nome": "Edson", "cargo": "Técnico"}, 1.25)
    it = next(m for m in E.ler(video)["motions"]["itens"] if m["id"] == mid)
    assert it["status"] == "aprovado" and it["origem"] == "painel" and it["efeito"] == "tarja-nome"
    assert it["inicio_seq"] == 1.25 and it["fim_seq"] == 5.25 and it["formato"] == "sobreposicao"
    assert it["params"] == {"nome": "Edson", "cargo": "Técnico"} and "Tarja de nome: Edson" in it["ideia"]
    d = P.dados(video)
    assert next(m for m in d["motions"] if m["id"] == mid)["params"]["nome"] == "Edson"
    with _editar(video) as d:
        mid2 = G.inserir_animacao(d, video, "titulo-impacto", {"texto": "Fim"}, 999)
    it2 = next(m for m in E.ler(video)["motions"]["itens"] if m["id"] == mid2)
    total = R.plano(video, rascunho=True)["duracao"]
    assert it2["fim_seq"] <= total + 1e-3, "no fim do vídeo, a animação recua para caber"
    with pytest.raises(G.ErroGaleria, match="falta o parâmetro"), _editar(video) as d:
        G.inserir_animacao(d, video, "tarja-nome", {}, 1.0)
    with pytest.raises(G.ErroGaleria, match="fora do intervalo"), _editar(video) as d:
        G.inserir_animacao(d, video, "tarja-nome", {"nome": "x"}, 1.0, duracao=60)


def test_transicoes_pela_galeria(video):
    d = E.ler(video)
    perto = G.corte_mais_perto(d, 0.1)
    assert perto["id"] == "s002"
    with _editar(video) as d:
        G.mudar_transicao(d, "s003", {"tipo": "empurrar", "duracao": 0.5})
    s3 = next(s for s in E.ler(video)["cortes"]["segmentos"] if s["id"] == "s003")
    assert s3["transicao"] == {"tipo": "empurrar", "duracao": 0.5, "origem": "painel"}
    assert next(s for s in P.dados(video)["segmentos"] if s["id"] == "s003")["transicao"]["tipo"] == "empurrar"
    with _editar(video) as d:
        G.mudar_transicao(d, "s003", None)
    assert "transicao" not in next(s for s in E.ler(video)["cortes"]["segmentos"] if s["id"] == "s003")
    for sid, tr, msg in [("s001", {"tipo": "zoom"}, "primeiro"), ("s999", {"tipo": "zoom"}, "não encontrado"),
                         ("s002", {"tipo": "zoom", "duracao": 5}, "fora do intervalo")]:
        with pytest.raises(G.ErroGaleria, match=msg), _editar(video) as d:
            G.mudar_transicao(d, sid, tr)


def test_inserir_som(video, pessoa):
    G.criar_pacote_sons()
    with _editar(video) as d:
        sid = G.inserir_som(d, video, "whoosh-curto", 3.0, -9)
    it = next(s for s in E.ler(video)["sfx"]["itens"] if s["id"] == sid)
    pico = next(s for s in G.indice_sons()["sons"] if s["id"] == "whoosh-curto")["pico"]
    assert it["inicio_seq"] == pytest.approx(3.0 - pico, abs=1e-3), "o pico cai no cursor"
    assert Path(it["arquivo"]) == (video / "Assets" / "sons" / "whoosh-curto.wav").resolve() and Path(it["arquivo"]).exists()
    assert it["ganho_db"] == -9 and it["origem"] == "painel"
    assert any(e["id"] == sid for e in R.plano(video, rascunho=True)["efeitos"])
    assert G.arquivo_som("whoosh-curto").name == "whoosh-curto.wav" and G.arquivo_som("nada") is None
    with pytest.raises(G.ErroGaleria, match="não está na biblioteca"), _editar(video) as d:
        G.inserir_som(d, video, "nada", 1.0)


def test_escolher_legenda(video):
    d = E.ler(video)
    assert (d.get("legendas") or {}).get("arquivo"), "o demo tem legendas geradas"
    n = len(d.get("pendencias") or [])
    with _editar(video) as d:
        r = G.escolher_legenda(d, "impacto", "topo")
    d = E.ler(video)
    assert r["refazer"] and len(d["pendencias"]) == n + 1 and "Impacto" in d["pendencias"][-1]["texto"]
    assert d["video"]["legendas"] == {"estilo": "impacto", "posicao": "topo", "queimar": True}
    assert L.opcoes_legenda(d, C.carregar())["estilo"]["id"] == "impacto"
    with _editar(video) as d:
        r = G.escolher_legenda(d, "impacto", "centro")   # só a posição: a divisão é a mesma
    assert not r["refazer"] and len(E.ler(video)["pendencias"]) == n + 1
    with pytest.raises(G.ErroGaleria), _editar(video) as d:
        G.escolher_legenda(d, "comic-sans")


# ------------------------------------------------------------------ servidor
def _req(porta, metodo, caminho, corpo=None, token="tok"):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=60)
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None,
              headers={"Host": f"127.0.0.1:{porta}", "X-Painel-Token": token, "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_rotas_da_galeria(video):
    srv, painel = SRV.criar_servidor(str(video), 0, token="tok")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    porta = painel.porta
    try:
        assert _req(porta, "GET", "/api/galeria", token="x")[0] == 401
        st, _, corpo = _req(porta, "GET", "/api/galeria")
        assert st == 200 and json.loads(corpo)["transicoes"]
        st, h, corpo = _req(porta, "GET", "/api/efeito?nome=contador&p=" + quote(json.dumps({"rotulo": "placas"})))
        assert st == 200 and h["Content-Type"].startswith("text/html") and b"__timelines" in corpo
        st, _, corpo = _req(porta, "GET", "/api/efeito?nome=..%2Fx")
        assert st == 200 and b"inv" in corpo, "o erro aparece dentro da prévia"
        st, _, corpo = _req(porta, "POST", "/api/galeria/pacote-sons", {})
        assert st == 200 and json.loads(corpo)["info"]["configurada"]
        st, h, _ = _req(porta, "GET", "/api/som?id=pop")
        assert st == 200 and h["Content-Type"].startswith("audio/")
        rev = E.ler(video)["revisao"]
        st, _, corpo = _req(porta, "POST", "/api/galeria/animacao",
                            {"revisao": rev, "efeito": "tarja-nome", "params": {"nome": "Ana"}, "inicio_seq": 0.5})
        j = json.loads(corpo)
        assert st == 200 and j["info"]["id"].startswith("mo") and any(m["id"] == j["info"]["id"] for m in j["dados"]["motions"])
        st, _, corpo = _req(porta, "POST", "/api/galeria/animacao", {"revisao": rev, "efeito": "tarja-nome", "inicio_seq": 0})
        assert st == 409, "revisão velha: conflito, como no resto do painel"
        rev = E.ler(video)["revisao"]
        st, _, corpo = _req(porta, "POST", "/api/galeria/transicao", {"revisao": rev, "id": "s002", "tipo": "zoom"})
        assert st == 200 and json.loads(corpo)["info"]["transicao"]["tipo"] == "zoom"
        rev = E.ler(video)["revisao"]
        st, _, corpo = _req(porta, "POST", "/api/galeria/som", {"revisao": rev, "id": "pop", "tempo_seq": 2.0})
        assert st == 200 and json.loads(corpo)["info"]["id"].startswith("sfx")
        rev = E.ler(video)["revisao"]
        st, _, corpo = _req(porta, "POST", "/api/galeria/legenda", {"revisao": rev, "estilo": "caixa"})
        assert st == 200 and json.loads(corpo)["info"]["estilo"] == "caixa"
        rev = E.ler(video)["revisao"]
        assert _req(porta, "POST", "/api/galeria/nada", {"revisao": rev})[0] == 400
        assert _req(porta, "GET", "/api/miniatura?video=cam01&tempo=1&largura=480")[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
