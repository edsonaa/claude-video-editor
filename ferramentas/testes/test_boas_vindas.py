import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

import pytest

from edicao import boas_vindas as BV
from edicao import config as C
from edicao import efeitos as EF
from edicao import estado as E
from edicao import legendas as L
import painel as SRV

F = Path(__file__).resolve().parent.parent


@pytest.fixture
def pessoa(tmp_path, monkeypatch):
    casa = tmp_path / "edicao"
    monkeypatch.setenv("EDICAO_HOME", str(casa))
    C.criar("Edson", "youtube-apresentador", perfil="padrao", estilo="tech-neon")
    return casa


@pytest.fixture
def video(tmp_path, pessoa, clipe):
    v = tmp_path / "2026-11-20_Placas"
    (v / "Brutos").mkdir(parents=True)
    shutil.copy(clipe / "cam01.mp4", v / "Brutos" / "A001.mp4")
    E.criar(v, v.name, "padrao", C.carregar()["fluxo"])
    return v


ESCOLHAS = {"briefing": "Vídeo sobre 20 placas com o mesmo defeito.", "termos": ["VRM", " ", "BIOS"],
            "preset": "reels", "tema": {"tipo": "estilo", "id": "impacto"},
            "legenda": {"estilo": "impacto", "queimar": False, "posicao": "centro", "ativas": True}}


# ------------------------------------------------------------------ estilos de legenda
def test_biblioteca_de_estilos_de_legenda():
    est = L.estilos_legenda()
    assert list(est) == ["classica", "caixa", "karaoke", "impacto", "minimalista", "brilho"]
    for k, e in est.items():
        for campo in ("titulo", "descricao", "bom_para", "modo", "caixa_alta", "max_caracteres",
                      "max_caracteres_vertical", "linhas", "fonte", "peso", "tamanho", "cor", "cor_destaque",
                      "contorno", "sombra", "caixa", "brilho", "escala_destaque", "posicao", "opacidade_contorno"):
            assert campo in e, (k, campo)
        assert e["modo"] in ("frase", "palavra") and e["posicao"] in L.POSICOES
    with pytest.raises(ValueError, match="não existe"):
        L.estilo_legenda("comic-sans")


def _bloco():
    ws = [{"texto": t, "inicio": i * 0.3, "fim": i * 0.3 + 0.28} for i, t in enumerate("o defeito estava ali".split())]
    return [{"id": "l001", "inicio": 0.0, "fim": 1.3, "linhas": ["o defeito", "estava ali"], "palavras": ws}]


def test_ass_por_estilo():
    tema = EF.tema_de(estilo="tech-neon")
    caixa = L.ass(_bloco(), tema, 1920, 1080, estilo=L.estilo_legenda("caixa"))
    estilo_linha = next(l for l in caixa.splitlines() if l.startswith("Style:")).split(",")
    assert estilo_linha[15] == "3", "caixa: BorderStyle 3 (faixa opaca)"
    impacto = L.ass(_bloco(), tema, 1080, 1920, estilo=L.estilo_legenda("impacto"))
    ev = [l for l in impacto.splitlines() if l.startswith("Dialogue:")]
    assert len(ev) == 4 and "DEFEITO\\NESTAVA ALI" in ev[0] and "&H0015CCFA" in ev[0] and "\\fscx112" in ev[0]
    brilho = L.ass(_bloco(), tema, 1920, 1080, estilo=L.estilo_legenda("brilho"))
    ev = [l for l in brilho.splitlines() if l.startswith("Dialogue:")]
    assert len(ev) == 8 and ev[0].startswith("Dialogue: 0,") and "\\1a&HFF&" in ev[0] and "\\blur" in ev[0]
    assert ev[1].startswith("Dialogue: 1,") and "\\1a&HFF&" not in ev[1], "a camada da frente é o texto nítido"
    topo = L.ass(_bloco(), tema, 1920, 1080, estilo=L.estilo_legenda("classica"), posicao="topo")
    assert next(l for l in topo.splitlines() if l.startswith("Style:")).split(",")[18] == "8"


@pytest.mark.skipif("ass" not in subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                                                text=True).stdout, reason="FFmpeg sem libass")
@pytest.mark.parametrize("ident", list(L.estilos_legenda()))
def test_cada_estilo_queima_no_ffmpeg(ident, tmp_path):
    from edicao import ff
    arq = tmp_path / "l.ass"
    arq.write_text(L.ass(_bloco(), EF.tema_de(estilo="impacto"), 640, 360, estilo=L.estilo_legenda(ident)), encoding="utf-8")
    subprocess.run([ff.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=1", "-vf",
                    "ass=l.ass", "-frames:v", "1", "q.png"], cwd=tmp_path, check=True)
    assert (tmp_path / "q.png").stat().st_size > 500


def test_opcoes_de_legenda_em_camadas():
    # configuração antiga, sem estilo: os campos dela valem (reels: palavra, caixa alta, 20)
    reels = C.config_do_preset("reels")
    op = L.opcoes_legenda(None, reels)
    assert op["estilo"]["id"] == "karaoke" and op["modo"] == "palavra" and op["max_caracteres"] == 20
    assert op["caixa_alta"] and op["queimar"]
    # estilo na configuração: o estilo manda no modo e nos caracteres (vertical usa o limite vertical)
    cfg = {"legendas": {"estilo": "classica", "modo": "palavra", "max_caracteres": 20, "queimar": False},
           "video": {"formato": "9:16"}}
    op = L.opcoes_legenda(None, cfg)
    assert op["modo"] == "frase" and op["max_caracteres"] == L.estilo_legenda("classica")["max_caracteres_vertical"]
    # escolha do vídeo por cima de tudo
    d = {"video": {"formato": "16:9", "legendas": {"estilo": "impacto", "queimar": True, "posicao": "topo"}}}
    op = L.opcoes_legenda(d, cfg)
    assert op["estilo"]["id"] == "impacto" and op["queimar"] and op["posicao"] == "topo"
    assert op["max_caracteres"] == L.estilo_legenda("impacto")["max_caracteres"]


def test_config_valida_estilo_de_legenda(pessoa):
    cfg = C.carregar()
    cfg["legendas"]["estilo"] = "inexistente"
    erros, _ = C.validar(cfg)
    assert any("legendas.estilo" in e for e in erros)
    cfg["legendas"]["estilo"] = "brilho"
    assert C.validar(cfg)[0] == []


# ------------------------------------------------------------------ boas-vindas
def test_verificacao(video, pessoa):
    v = {i["titulo"]: i for i in BV.verificacao(video)}
    assert v["Pasta do projeto"]["ok"] is True
    assert v["Subpastas"]["ok"] is None and "Assets" in v["Subpastas"]["detalhe"]
    assert v["Gravações"]["ok"] is True and "1 vídeo" in v["Gravações"]["detalhe"]
    assert v["FFmpeg"]["ok"] is True
    assert "Biblioteca de sons" in v
    outra = video.parent / "sem_padrao"
    E.criar(outra, "x", "padrao")
    w = {i["titulo"]: i for i in BV.verificacao(outra)}
    assert w["Pasta do projeto"]["ok"] is None and w["Gravações"]["ok"] is None


def test_opcoes(video):
    o = BV.opcoes(video)
    assert {p["id"] for p in o["presets"]} >= {"reels", "youtube-apresentador", "so-cortes"}
    reels = next(p for p in o["presets"] if p["id"] == "reels")
    assert reels["formato"] == "9:16" and "render" in reels["fluxo"] and reels["legenda"]["queimar"]
    assert [p["id"] for p in o["perfis"]] == ["padrao"]
    assert "padrao" not in [e["id"] for e in o["estilos"]] and "impacto" in [e["id"] for e in o["estilos"]]
    assert [l["id"] for l in o["legendas"]][:2] == ["classica", "caixa"]
    assert o["atual"]["preset"] == "youtube-apresentador" and o["atual"]["perfil"] == "padrao"
    assert o["tem_exemplo"] and o["nome"] == "Edson" and o["enviado"] is None
    json.dumps(o)


def test_quadro_exemplo_e_previas(video):
    q = BV.quadro_exemplo(video)
    assert q.exists() and q.suffix == ".jpg"
    assert BV.previa_tema("estilo", "impacto").name == "previa.png"
    assert BV.previa_tema("estilo", "../../etc") is None
    assert BV.previa_tema("perfil", "nao-existe") is None


def test_salvar_so_para_o_video(video, pessoa):
    antes = json.loads((pessoa / "config.json").read_text(encoding="utf-8"))
    r = BV.salvar(video, ESCOLHAS)
    d = E.ler(video)
    assert d["fluxo"][0] == "iniciar" and d["fluxo"][-1] == "render" and "legendas" in d["fluxo"]
    assert d["etapas"]["iniciar"] == "em_andamento" and set(d["etapas"]) == set(d["fluxo"])
    assert d["perfil"] == "impacto" and (pessoa / "perfis" / "impacto" / "tema.json").exists()
    assert r["perfil_criado"] == "impacto"
    assert d["video"]["formato"] == "9:16" and d["video"]["preset"] == "reels"
    assert d["video"]["legendas"] == {"estilo": "impacto", "queimar": True, "posicao": "centro", "ativas": True}, \
        "palavra a palavra só existe queimada"
    assert d["boas_vindas"]["termos"] == ["VRM", "BIOS"] and not d["boas_vindas"]["padrao"]
    br = (video / "_CLAUDE" / "briefing_painel.md").read_text(encoding="utf-8")
    assert "20 placas" in br and "- VRM" in br and "Impacto queimada" in br and "costuma revisar" in br
    assert json.loads((pessoa / "config.json").read_text(encoding="utf-8")) == antes, "sem 'padrão', a config não muda"
    # as escolhas do vídeo já valem para as legendas e o render deste vídeo
    op = L.opcoes_legenda(d, C.carregar())
    assert op["estilo"]["id"] == "impacto" and op["posicao"] == "centro"
    from edicao import render as R
    assert R.formato_do_projeto(d) == "9:16"


def test_salvar_como_padrao(video, pessoa):
    BV.salvar(video, {**ESCOLHAS, "tema": {"tipo": "perfil", "id": "padrao"}, "padrao": True,
                      "legenda": {"estilo": "caixa", "queimar": False, "posicao": "baixo", "ativas": True}})
    c = C.carregar()
    assert c["preset"] == "reels" and c["video"]["formato"] == "9:16" and c["perfil_padrao"] == "padrao"
    assert c["legendas"]["estilo"] == "caixa" and c["legendas"]["queimar"] is False and c["legendas"]["ativas"]
    assert C.validar(c)[0] == []


def test_sem_legenda_tira_a_etapa(video):
    BV.salvar(video, {**ESCOLHAS, "preset": "youtube-apresentador", "legenda": {"ativas": False}})
    d = E.ler(video)
    assert "legendas" not in d["fluxo"] and d["video"]["legendas"]["ativas"] is False
    BV.salvar(video, {**ESCOLHAS, "preset": "so-cortes"})
    assert E.ler(video)["fluxo"] == ["iniciar", "preparar", "cortes", "legendas"], "legenda pedida entra no fluxo"


def test_salvar_recusa_o_que_nao_existe(video):
    for ruim, msg in [({"preset": "tiktok-dancinha"}, "tipo de vídeo"), ({"tema": {}}, "escolha um estilo"),
                      ({"tema": {"tipo": "perfil", "id": "nao-existe"}}, "não existe"),
                      ({"legenda": {"estilo": "comic"}}, "legenda"),
                      ({"legenda": {"estilo": "classica", "posicao": "lateral"}}, "posição")]:
        with pytest.raises(BV.ErroBoasVindas, match=msg):
            BV.salvar(video, {**ESCOLHAS, **ruim})


def _req(porta, metodo, caminho, corpo=None, token="tok", host=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
    h = {"Host": host or f"127.0.0.1:{porta}", "X-Painel-Token": token, "Content-Type": "application/json"}
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None, headers=h)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_servidor_de_boas_vindas(video):
    srv, painel = SRV.criar_servidor(str(video), 0, token="tok", modo="boas_vindas")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        st, h, corpo = _req(painel.porta, "GET", "/")
        assert st == 200 and b"/web/boas-vindas.js" in corpo
        assert _req(painel.porta, "GET", "/api/boas-vindas", token="errado")[0] == 401
        st, _, corpo = _req(painel.porta, "GET", "/api/boas-vindas")
        assert st == 200 and json.loads(corpo)["projeto"] == video.name
        assert _req(painel.porta, "GET", "/api/exemplo.jpg")[1]["Content-Type"] == "image/jpeg"
        assert _req(painel.porta, "GET", "/api/previa-tema/estilo/limpo")[0] == 200
        assert _req(painel.porta, "GET", "/api/previa-tema/estilo/..%2F..%2Fx")[0] == 404
        st, _, corpo = _req(painel.porta, "POST", "/api/boas-vindas", {**ESCOLHAS, "preset": "nada"})
        assert st == 400 and not painel.enviado
        st, _, corpo = _req(painel.porta, "POST", "/api/boas-vindas", ESCOLHAS)
        assert st == 200 and json.loads(corpo)["resumo"]["preset"] == "reels"
        assert painel.fim.wait(5), "o servidor encerra sozinho depois de enviar"
    finally:
        srv.shutdown()
        srv.server_close()


def test_cli_boas_vindas_termina_ao_enviar(video, pessoa):
    import os
    p = subprocess.Popen([sys.executable, "-I", str(F / "painel.py"), "boas-vindas", str(video), "--porta", "0"],
                         stdout=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, "EDICAO_HOME": str(pessoa)})
    linha = p.stdout.readline()
    m = re.search(r"127\.0\.0\.1:(\d+)/\?t=(\S+)", linha)
    assert m, linha
    porta, token = int(m.group(1)), m.group(2)
    st, _, _ = _req(porta, "POST", "/api/boas-vindas", ESCOLHAS, token=token)
    assert st == 200
    saida, _ = p.communicate(timeout=20)
    assert p.returncode == 0
    resumo = json.loads(next(l for l in saida.splitlines() if l.startswith("ENVIADO "))[8:])
    assert resumo["preset"] == "reels" and resumo["legenda"]["estilo"] == "impacto"


def test_painel_usa_o_estilo_de_legenda_do_video(video):
    from edicao import painel as P
    BV.salvar(video, ESCOLHAS)
    d = P.dados(video)
    assert d["tema"]["legendas"]["estilo"]["id"] == "impacto" and d["tema"]["legendas"]["posicao"] == "centro"
    assert d["formato"] == "9:16"


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node.js")
@pytest.mark.parametrize("js", ["boas-vindas.js", "legenda-estilo.js"])
def test_javascript_sem_erro_de_sintaxe(js):
    r = subprocess.run(["node", "--check", str(F / "painel_web" / js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
