import http.client
import json
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from edicao import estado as E
from edicao import ff
from edicao import painel as P
from edicao.tempo import Taxa
import painel as SRV
import video_demo

TAXA = Taxa.de("30000/1001")


@pytest.fixture(scope="module")
def modelo(tmp_path_factory, clipe):
    return video_demo.montar(tmp_path_factory.mktemp("demo"), clipe)


@pytest.fixture
def video(modelo, tmp_path):
    """Uma cópia do vídeo de demonstração (o estado aponta para as mídias do modelo)."""
    v = tmp_path / modelo.name
    shutil.copytree(modelo, v, ignore=shutil.ignore_patterns("Brutos", "Renders"))
    return v


def _palavras(d, video="cam01"):
    return {w[0]: w for w in d["roteiro"][video]}


# ------------------------------------------------------------------ o navegador toca?
def test_tocavel(modelo, tmp_path):
    assert P.tocavel(modelo / "Brutos" / "cam01.mp4") == (True, "")
    ok, motivo = P.tocavel(modelo / "Brutos" / "tela01.mov")
    assert not ok and "prores" in motivo
    assert P.tocavel(modelo / "_CLAUDE" / "musica_v01.wav")[0]
    pcm = tmp_path / "h264_pcm.mov"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(modelo / "Brutos" / "cam01.mp4"), "-t", "1", "-c:v", "copy",
              "-c:a", "pcm_s16le", str(pcm)])
    ok, motivo = P.tocavel(pcm)
    assert not ok and "pcm_s16le" in motivo, "câmera com áudio PCM em MOV toca muda no navegador"
    assert P.tocavel(tmp_path / "nao_existe.mp4") == (False, "o arquivo não existe")


# ------------------------------------------------------------------ dados para a interface
def test_dados(video):
    d = P.dados(video)
    segs = d["segmentos"]
    assert [s["id"] for s in segs] == ["s001", "s002", "s003", "s004"]
    assert segs[0]["seq_ini"] == 0 and all(a["seq_fim"] == b["seq_ini"] for a, b in zip(segs, segs[1:]))
    assert segs[2]["in"] == TAXA.segundos(TAXA.frames(1.0)) and segs[2]["video"] == "tela01"
    assert d["duracao"] == pytest.approx(segs[-1]["seq_fim"])
    assert d["midias"]["v:cam01"]["url"] == "/arquivo/v:cam01" and d["midias"]["v:cam01"]["fonte"] == "original"
    assert d["midias"]["v:tela01"]["url"] is None and d["midias"]["v:tela01"]["precisa_previa"]
    assert d["previas_faltando"] == 2  # tela01 (ProRes) e a animação mo01 (ProRes 4444)
    ws = _palavras(d)
    assert ws["Olá"][3] == 1 and ws["ééé"][4] == 1  # no corte; hesitação marcada
    assert d["legendas"]["versao"] == 1 and not d["legendas"]["desatualizada"]
    assert {m["id"] for m in d["motions"]} == {"mo01", "mo02", "mo03"}
    assert d["musica"]["chave"] == "musica" and len(d["sfx"]) == 2
    m1 = next(m for m in d["marcadores"] if m["id"] == "m001")
    assert m1["dentro"] and m1["seq"] == pytest.approx(1.4 - TAXA.segundos(TAXA.frames(0.45)), abs=0.04)
    assert next(m for m in d["marcadores"] if m["id"] == "m002")["dentro"] is False
    assert d["etapas"]["motion_render"] == "aguardando_aprovacao"
    json.dumps(d)  # tudo serializável


# ------------------------------------------------------------------ cortes
SEGS = [{"id": "s001", "video": "a", "inicio": 1.0, "fim": 5.0}, {"id": "s002", "video": "a", "inicio": 8.0, "fim": 12.0}]


def test_remover_trecho_divide_apara_e_apaga():
    q = lambda t: round(TAXA.segundos(TAXA.frames_piso(t)), 6)  # noqa: E731
    c = lambda t: round(TAXA.segundos(-TAXA.frames_piso(-t)), 6)  # noqa: E731
    r = P.remover_trecho(SEGS, "a", 2.0, 3.0, TAXA)
    assert [(s["id"], s["inicio"], s["fim"]) for s in r] == [("s001", 1.0, q(2.0)), ("s003", c(3.0), 5.0),
                                                               ("s002", 8.0, 12.0)]
    r = P.remover_trecho(SEGS, "a", 0.0, 2.0, TAXA)
    assert r[0]["inicio"] == c(2.0) and r[0]["id"] == "s001"
    r = P.remover_trecho(SEGS, "a", 4.0, 9.0, TAXA)
    assert [(s["id"], s["inicio"], s["fim"]) for s in r] == [("s001", 1.0, q(4.0)), ("s002", c(9.0), 12.0)]
    assert [s["id"] for s in P.remover_trecho(SEGS, "a", 0.5, 6.0, TAXA)] == ["s002"]
    with pytest.raises(P.ErroPainel, match="já está fora"):
        P.remover_trecho(SEGS, "a", 5.5, 7.5, TAXA)
    with pytest.raises(P.ErroPainel, match="já está fora"):
        P.remover_trecho(SEGS, "b", 2.0, 3.0, TAXA)


def test_restaurar_trecho_junta_ou_insere():
    pal = [{"texto": "x", "inicio": 6.0, "fim": 6.4, "tipo": "palavra"}]
    # só silêncio entre o fim de s001 e o trecho: junta
    r = P.restaurar_trecho(SEGS, "a", 5.3, 5.8, TAXA, pal)
    assert len(r) == 2 and r[0]["fim"] == round(TAXA.segundos(-TAXA.frames_piso(-5.8)), 6)
    # há fala entre os dois: segmento novo, na ordem do arquivo
    r = P.restaurar_trecho(SEGS, "a", 6.5, 7.0, TAXA, [*pal, {"texto": "y", "inicio": 7.4, "fim": 7.6, "tipo": "palavra"}])
    assert [s["id"] for s in r] == ["s001", "s003", "s002"]
    # encosta nos dois: vira um segmento só
    r = P.restaurar_trecho(SEGS, "a", 4.8, 8.2, TAXA, pal)
    assert [(s["id"], s["inicio"], s["fim"]) for s in r] == [("s001", 1.0, 12.0)]
    # outro arquivo, sem vizinhos: entra no fim
    assert P.restaurar_trecho(SEGS, "b", 1, 2, TAXA)[-1]["video"] == "b"
    with pytest.raises(P.ErroPainel, match="já está no corte"):
        P.restaurar_trecho(SEGS, "a", 2.0, 3.0, TAXA)


def test_trecho_das_palavras():
    ws = [{"texto": t, "inicio": a, "fim": b, "tipo": "palavra"} for t, a, b in
          [("um", 1.0, 1.3), ("dois", 1.4, 1.7), ("três", 3.0, 3.3), ("quatro", 3.4, 3.8)]]
    ini, fim = P.trecho_das_palavras(ws, 1, 1, "cortar")
    assert ini == pytest.approx(1.35) and fim == pytest.approx(3.0 - P.FOLGA_CORTE)
    ini, fim = P.trecho_das_palavras(ws, 0, 0, "cortar")
    assert ini == pytest.approx(0.9)
    ini, fim = P.trecho_das_palavras(ws, 2, 2, "restaurar")
    assert ini == pytest.approx(3.0 - P.FOLGA_INCLUIR) and fim == pytest.approx(3.35)
    with pytest.raises(P.ErroPainel):
        P.trecho_das_palavras(ws, 3, 5, "cortar")


def test_cortar_restaurar_e_desfazer_pelo_roteiro(video):
    d0 = P.dados(video)
    i = _palavras(d0)["falar"][5]
    antes = E.ler(video)["cortes"]
    P.editar_cortes(video, d0["revisao"], "cortar", video="cam01", i=i, j=i + 1)
    d1 = P.dados(video)
    dentro = {w[5]: w[3] for w in d1["roteiro"]["cam01"]}
    assert (dentro[i - 1], dentro[i], dentro[i + 1], dentro[i + 2]) == (1, 0, 0, 1)  # vamos [falar de] 20
    assert d1["cortes_versao"] == antes["versao"] + 1 and d1["desfazer"] == 1
    textos = {s["id"]: s.get("texto", "") for s in E.ler(video)["cortes"]["segmentos"]}
    assert textos["s002"].endswith("vamos") and textos["s005"].startswith("20")
    assert any("o corte mudou" in a for a in d1["alertas"])  # animações e legendas ficaram para trás
    P.editar_cortes(video, d1["revisao"], "restaurar", video="cam01", i=i, j=i + 1)
    assert all(w[3] for w in P.dados(video)["roteiro"]["cam01"][:8])
    # desfazer volta, na ordem, até o corte original
    P.desfazer_cortes(video, None)
    P.desfazer_cortes(video, None)
    sem_texto = lambda segs: [{k: v for k, v in x.items() if k != "texto"} for x in segs]  # noqa: E731
    assert sem_texto(E.ler(video)["cortes"]["segmentos"]) == sem_texto(antes["segmentos"])
    with pytest.raises(P.ErroPainel, match="não há mudança"):
        P.desfazer_cortes(video, None)


def test_desfazer_nao_passa_por_cima_do_claude(video):
    P.editar_cortes(video, None, "remover_segmento", id="s003")
    with E.editar(video) as d:  # o Claude mexeu no corte depois
        d["cortes"]["segmentos"][0]["fim"] = 2.0
    with pytest.raises(P.ErroPainel, match="mudou fora do painel"):
        P.desfazer_cortes(video, None)


def test_ajustar_segmento(video):
    d = P.dados(video)
    s = d["segmentos"][1]
    P.editar_cortes(video, d["revisao"], "ajustar", id="s002", inicio=(s["in_f"] + 5) / float(TAXA.fps))
    s2 = next(x for x in P.dados(video)["segmentos"] if x["id"] == "s002")
    assert s2["in_f"] == s["in_f"] + 5 and s2["out_f"] == s["out_f"]
    with pytest.raises(P.ErroPainel, match="depois do início"):
        P.editar_cortes(video, None, "ajustar", id="s002", fim=s2["in"])
    with pytest.raises(P.ErroPainel, match="passaria do fim"):
        P.gravar_cortes(video, [{"id": "s001", "video": "tela01", "inicio": 1.0, "fim": 9.0}], None, "teste")
    with pytest.raises(P.ErroPainel, match="único segmento"):
        P.gravar_cortes(video, [{"id": "s001", "video": "cam01", "inicio": 1.0, "fim": 2.0}], None, "x")
        P.editar_cortes(video, None, "remover_segmento", id="s001")


def test_conflito_quando_o_claude_gravou_no_meio(video):
    rev = P.dados(video)["revisao"]
    with E.editar(video) as d:
        d["marcadores"][0]["texto"] = "o Claude mudou"
    with pytest.raises(E.Conflito):
        P.editar_cortes(video, rev, "remover_segmento", id="s003")
    with pytest.raises(E.Conflito):
        P.novo_pedido(video, rev, "cortes", "x")
    assert E.ler(video)["marcadores"][0]["texto"] == "o Claude mudou"


# ------------------------------------------------------------------ pedidos, animações, etapas, legendas
def test_pedido_guarda_o_tempo_da_origem_e_o_aprendizado(video):
    d = P.dados(video)
    P.novo_pedido(video, d["revisao"], "motion_render", "  respiro   maior  ", tempo_seq=4.0, aprendizado=True)
    p = E.ler(video)["pendencias"][-1]
    assert p["texto"] == "respiro maior" and p["origem"] == "painel" and p["etapa"] == "motion_render"
    assert p["video"] == "tela01" and p["tempo"] == pytest.approx(1.0 + (4.0 - d["segmentos"][2]["seq_ini"]), abs=0.04)
    linhas = (video / "_CLAUDE" / "aprendizados.md").read_text(encoding="utf-8")
    assert "- [ ] motion_render · respiro maior (pelo painel)" in linhas
    assert P.dados(video)["aprendizados"] == 1
    with pytest.raises(P.ErroPainel, match="escreva"):
        P.novo_pedido(video, None, "cortes", "   ")
    P.resolver_pedido(video, None, p["id"])
    assert E.ler(video)["pendencias"][-1]["resolvida_em"]


def test_status_das_animacoes(video):
    P.status_motion(video, None, "mo03", "aprovado")
    P.status_motion(video, None, "mo03", "riscado")
    assert next(m for m in E.ler(video)["motions"]["itens"] if m["id"] == "mo03")["status"] == "riscado"
    with pytest.raises(P.ErroPainel, match="já foi construída"):
        P.status_motion(video, None, "mo01", "aprovado")
    P.status_motion(video, None, "mo01", "ajustar", "entrar mais devagar", aprendizado=True)
    d = E.ler(video)
    assert next(m for m in d["motions"]["itens"] if m["id"] == "mo01")["status"] == "renderizado", \
        "pedir ajuste numa animação pronta não a tira do XML"
    p = d["pendencias"][-1]
    assert p["item"] == "mo01" and p["etapa"] == "motion_render"
    assert "mo01: entrar mais devagar" in (video / "_CLAUDE" / "aprendizados.md").read_text(encoding="utf-8")
    with pytest.raises(P.ErroPainel, match="diga o que"):
        P.status_motion(video, None, "mo02", "ajustar")


def test_aprovar_etapa(video):
    P.novo_pedido(video, None, "motion_render", "trocar a cor da tarja")
    with pytest.raises(P.ErroPainel, match="pedidos abertos"):
        P.aprovar_etapa(video, None, "motion_render")
    pid = E.ler(video)["pendencias"][-1]["id"]
    P.resolver_pedido(video, None, pid)
    P.aprovar_etapa(video, None, "motion-render")
    assert E.ler(video)["etapas"]["motion_render"] == "concluido"
    with pytest.raises(P.ErroPainel, match="não está esperando"):
        P.aprovar_etapa(video, None, "sfx")


def test_corrigir_legenda(video):
    b = P.corrigir_legenda(video, "l001", "Olá, pessoal! Hoje vamos falar de vinte placas")
    assert b["linhas"][0].startswith("Olá, pessoal!")
    d = P.dados(video)
    assert d["legendas"]["versao"] == 2 and d["legendas"]["blocos"][0]["linhas"] == b["linhas"]
    with pytest.raises(E.ErroEstado, match="vazio"):
        P.corrigir_legenda(video, "l001", "  ")


# ------------------------------------------------------------------ prévias
def test_previas(video, modelo, tmp_path):
    ts = {t["chave"]: t for t in P.tarefas_previa(video)}
    assert set(ts) == {"v:tela01", "mo:mo01"}
    progresso = []
    for t in ts.values():
        P.gerar_previa(video, t, progresso.append)
    assert progresso[-1] == 1.0
    d = P.dados(video)
    assert d["previas_faltando"] == 0 and d["midias"]["v:tela01"]["fonte"] == "previa"
    tela = P.arquivo(video, "v:tela01")
    assert tela.suffix == ".mp4" and P.tocavel(tela)[0]
    info = ff.sondar(tela)
    assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"}
    # a animação continua transparente (VP9 com alfa), e o fundo dela segue transparente
    mo = P.arquivo(video, "mo:mo01")
    assert mo.suffix == ".webm"
    png = tmp_path / "q.png"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-c:v", "libvpx-vp9", "-ss", "1", "-i", str(mo), "-frames:v", "1",
              "-pix_fmt", "rgba", str(png)])
    from PIL import Image
    im = Image.open(png)
    assert im.getpixel((300, 580))[3] > 200 and im.getpixel((10, 10))[3] == 0
    assert P.tarefas_previa(video) == []
    assert {t["chave"] for t in P.tarefas_previa(video, todas=True)} == {"v:cam01", "mo:mo02"}


def test_previa_com_a_voz_tratada(video, modelo):
    voz = video / "_CLAUDE" / "voz.wav"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=500:sample_rate=48000:duration=12",
              str(voz)])
    with E.editar(video) as d:
        d["midia"]["arquivos"][0]["audio_tratado"] = str(voz)
    m = P.dados(video)["midias"]["v:cam01"]
    assert m["url"] and m["precisa_previa"] and "voz tratada" in m["aviso"]
    t = next(t for t in P.tarefas_previa(video) if t["chave"] == "v:cam01")
    arq = P.gerar_previa(video, t)
    a = next(s for s in ff.sondar(arq)["streams"] if s["codec_type"] == "audio")
    assert float(a["duration"]) == pytest.approx(12.0, abs=0.1)
    assert P.dados(video)["midias"]["v:cam01"]["fonte"] == "previa"
    # a voz tratada mudou: a prévia fica velha
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=600:sample_rate=48000:duration=12",
              str(voz)])
    assert P.dados(video)["midias"]["v:cam01"]["fonte"] == "original"


def test_miniatura(video):
    arq = P.miniatura(video, "cam01", 1.0)
    assert arq.exists() and arq.suffix == ".jpg"
    assert P.miniatura(video, "cam01", 1.0) == arq  # cache
    with pytest.raises(P.ErroPainel):
        P.miniatura(video, "naoexiste", 1.0)


# ------------------------------------------------------------------ servidor
@pytest.fixture
def servidor(video):
    srv, painel = SRV.criar_servidor(str(video), 0, token="tok123")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield painel
    srv.shutdown()
    srv.server_close()


def _req(painel, metodo, caminho, corpo=None, token=True, host=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", painel.porta, timeout=10)
    h = {"Host": host or f"127.0.0.1:{painel.porta}", **(cab or {})}
    if token:
        h["X-Painel-Token"] = "tok123"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    if dados:
        h["Content-Type"] = "application/json"
    c.request(metodo, caminho, body=dados, headers=h)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_servidor_seguranca(servidor):
    assert _req(servidor, "GET", "/", token=False)[0] == 200
    assert _req(servidor, "GET", "/web/painel.js", token=False)[0] == 200
    assert _req(servidor, "GET", "/api/dados", token=False)[0] == 401
    assert _req(servidor, "GET", "/api/dados?t=errado", token=False)[0] == 401
    assert _req(servidor, "GET", "/api/dados", host="exemplo.com")[0] == 403, "proteção contra DNS rebinding"
    assert _req(servidor, "GET", "/web/../painel.py", token=False)[0] == 404
    assert _req(servidor, "GET", "/web/%2e%2e/edicao/painel.py", token=False)[0] == 404
    assert _req(servidor, "GET", "/arquivo/v:../../etc/passwd")[0] == 404
    assert _req(servidor, "GET", "/arquivo/v:tela01")[0] == 404, "ProRes sem prévia não é servido"
    # POST exige o cabeçalho (o token só na URL não basta: um formulário de outro site não manda cabeçalho)
    assert _req(servidor, "POST", "/api/pedido?t=tok123", {"texto": "x"}, token=False)[0] == 401


def test_servidor_api(servidor):
    st, h, corpo = _req(servidor, "GET", "/api/dados?t=tok123", token=False)
    d = json.loads(corpo)
    assert st == 200 and d["projeto"] == "2026-01-15_Demo"
    st, h, corpo = _req(servidor, "GET", "/arquivo/v:cam01", cab={"Range": "bytes=100-199"})
    assert st == 206 and len(corpo) == 100 and h["Content-Range"].startswith("bytes 100-199/")
    total = int(h["Content-Range"].split("/")[1])
    st, h, corpo = _req(servidor, "GET", "/arquivo/v:cam01", cab={"Range": "bytes=-50"})
    assert st == 206 and len(corpo) == 50 and h["Content-Range"] == f"bytes {total - 50}-{total - 1}/{total}"
    assert _req(servidor, "GET", "/arquivo/v:cam01", cab={"Range": f"bytes={total}-"})[0] == 416
    assert _req(servidor, "GET", "/api/miniatura?video=cam01&tempo=1.0")[1]["Content-Type"] == "image/jpeg"

    st, _, corpo = _req(servidor, "POST", "/api/pedido", {"revisao": d["revisao"], "texto": "mais curto", "etapa": "cortes",
                                                          "tempo_seq": 1.0})
    novo = json.loads(corpo)["dados"]
    assert st == 200 and novo["pendencias"][-1]["texto"] == "mais curto"
    # revisão velha: 409 com os dados atuais para a tela se atualizar
    st, _, corpo = _req(servidor, "POST", "/api/cortes", {"revisao": d["revisao"], "acao": "remover_segmento", "id": "s003"})
    r = json.loads(corpo)
    assert st == 409 and r["dados"]["revisao"] == novo["revisao"]
    st, _, corpo = _req(servidor, "POST", "/api/cortes", {"revisao": novo["revisao"], "acao": "remover_segmento", "id": "s003"})
    assert st == 200 and [s["id"] for s in json.loads(corpo)["dados"]["segmentos"]] == ["s001", "s002", "s004"]
    st, _, corpo = _req(servidor, "POST", "/api/cortes", {"acao": "voar"})
    assert st == 400 and "desconhecida" in json.loads(corpo)["erro"]
    st, _, corpo = _req(servidor, "POST", "/api/motion", {"id": "mo03"})
    assert st == 400 and "status" in json.loads(corpo)["erro"]


def test_servidor_gera_previas(servidor):
    import time
    st, _, corpo = _req(servidor, "POST", "/api/previas", {})
    assert st == 200 and json.loads(corpo)["rodando"]
    for _ in range(200):
        r = json.loads(_req(servidor, "GET", "/api/revisao")[2])
        if not r["previas"]["rodando"]:
            break
        time.sleep(0.1)
    assert {i["status"] for i in r["previas"]["itens"]} == {"pronta"}
    assert _req(servidor, "GET", "/arquivo/v:tela01", cab={"Range": "bytes=0-9"})[0] == 206


def test_cli_verificar_e_previas(video):
    import sys
    f = Path(SRV.__file__)
    r = subprocess.run([sys.executable, str(f), "verificar", str(video)], capture_output=True, text=True, encoding="utf-8")
    assert "v:tela01: precisa de prévia (vídeo em prores)" in r.stdout and "prévias faltando: 2" in r.stdout
    r = subprocess.run([sys.executable, str(f), "previas", str(video)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, str(f), "verificar", str(video)], capture_output=True, text=True, encoding="utf-8")
    assert "prévias faltando: 0" in r.stdout
    r = subprocess.run([sys.executable, str(f), "abrir", str(video.parent / "nao_iniciado")], capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 2 and "não foi iniciado" in r.stderr


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node.js")
def test_javascript_sem_erro_de_sintaxe():
    js = Path(SRV.__file__).parent / "painel_web" / "painel.js"
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
