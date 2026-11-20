import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from edicao import audio as A
from edicao import curtos as K
from edicao import estado as E
from edicao import ff
from edicao import painel as P
from edicao import publicar as PB
from edicao import render as R
from edicao.linha import Linha
from edicao.tempo import Taxa
import video_demo

F = Path(__file__).resolve().parent.parent
FPS = "30000/1001"
TAXA = Taxa.de(FPS)
BIPE = 2.002  # s no arquivo de origem (quadro 60)


def _ff(*a):
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-nostdin", *map(str, a)])


@pytest.fixture(scope="module")
def fonte(tmp_path_factory):
    """Vídeo em que cada quadro é diferente no quadro inteiro, com um bipe num quadro conhecido."""
    d = tmp_path_factory.mktemp("fonte")
    arq = d / "fonte.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30000/1001:duration=8", "-f", "lavfi",
        "-i", f"aevalsrc='0.6*sin(2*PI*1000*t)*between(t,{BIPE},{BIPE + 0.03})':s=48000:d=8",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-g", "48", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ac", "1", arq)
    return arq


def _projeto(raiz: Path, fonte: Path, segs, formato=None) -> Path:
    v = raiz / "proj"
    if v.exists():
        shutil.rmtree(v)
    E.criar(v, "proj", fluxo=["cortes", "render"])
    with E.editar(v) as d:
        d["midia"] = {"fps": FPS, "resolucao": [640, 360], "arquivos": [
            {"id": "cam", "caminho": str(fonte), "tipo": "camera", "duracao": 8.0, "resolucao": [640, 360]}]}
        d["cortes"] = {"versao": 1, "segmentos": segs}
        if formato:
            d["video"] = {"formato": formato}
    return v


def _quadros(arq, w=160, h=90):
    p = subprocess.run([ff.ffmpeg(), "-v", "error", "-i", str(arq), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w).astype(float)


SEGS = [{"id": "s001", "video": "cam", "inicio": 1.0, "fim": 3.0},
        {"id": "s002", "video": "cam", "inicio": 5.0, "fim": 6.5},
        {"id": "s003", "video": "cam", "inicio": 0.2, "fim": 0.9}]


# ------------------------------------------------------------------ render
def test_render_quadros_exatos_e_som_sincronizado(fonte, tmp_path):
    v = _projeto(tmp_path, fonte, [dict(s) for s in SEGS])
    pl = R.plano(v)
    r = R.renderizar(v, rascunho=True, progresso=lambda m: None)
    saida = Path(r["arquivo"])
    assert saida.name == "proj_rascunho_v01.mp4" and saida.parent.name == "rascunhos"
    assert r["tamanho"] == [960, 540]
    o, s = _quadros(saida), _quadros(fonte)
    assert len(o) == pl["quadros"]
    for p in pl["pedacos"]:
        for j in range(p["quadros"]):
            q = p["seq_ini_f"] + j
            esperado = p["in_f"] + j
            viz = range(max(0, esperado - 3), min(len(s), esperado + 4))
            achado = min(viz, key=lambda k: np.mean((s[k] - o[q]) ** 2))
            assert achado == esperado, (p["id"], q, achado, esperado)
    # o bipe (quadro 60 da origem) cai em s001, a 1,002 s da sequência
    y = ff.ler_audio(saida, taxa=48000).astype(float)
    janela = np.abs(y[: 48000 * 2])
    t_bipe = int(np.argmax(janela > 0.5 * janela.max())) / 48000  # o início do bipe
    esperado = TAXA.segundos(TAXA.frames(BIPE)) - TAXA.segundos(TAXA.frames(1.0))
    assert t_bipe == pytest.approx(esperado, abs=0.012)
    ent = E.ler(v)["entregas"][-1]
    assert ent["tipo"] == "rascunho" and ent["arquivo"].endswith("proj_rascunho_v01.mp4") and ent["cortes_versao"] == 1


def test_render_trecho_e_versoes(fonte, tmp_path):
    v = _projeto(tmp_path, fonte, [dict(s) for s in SEGS])
    r1 = R.renderizar(v, rascunho=True, de=1.0, ate=2.5, progresso=lambda m: None)
    r2 = R.renderizar(v, rascunho=True, de=1.0, ate=2.5, progresso=lambda m: None)
    assert Path(r2["arquivo"]).name.endswith("_v02.mp4") and Path(r1["arquivo"]).exists()
    n = len(_quadros(r1["arquivo"]))
    assert n == TAXA.frames(2.5) - TAXA.frames(1.0)
    assert not (v / "_CLAUDE" / "render_tmp" / "proj_rascunho_v01").exists(), "intermediários apagados"
    with pytest.raises(R.ErroRender, match="trecho vazio"):
        R.plano(v, de=3.0, ate=3.0)


def test_render_vertical_recorta_e_encaixa(fonte, tmp_path):
    segs = [dict(SEGS[0], quadro={"modo": "cortar", "x": 0.2}), dict(SEGS[1], quadro={"modo": "encaixar"})]
    v = _projeto(tmp_path, fonte, segs, formato="9:16")
    r = R.renderizar(v, rascunho=True, legenda="nao", progresso=lambda m: None)
    assert r["formato"] == "9:16" and r["tamanho"] == [540, 960]
    saida = Path(r["arquivo"])
    # o primeiro quadro é o recorte da origem: largura 202 de 360 de altura, centrado em x=0,2 (encosta à esquerda)
    src = tmp_path / "s.png"
    out = tmp_path / "o.png"
    _ff("-ss", f"{(TAXA.frames(1.0) - 0.5) / float(TAXA.fps):.6f}", "-i", fonte, "-frames:v", "1",
        "-vf", "crop=202:360:27:0,scale=54:96", src)
    _ff("-i", saida, "-frames:v", "1", "-vf", "scale=54:96", out)
    from PIL import Image
    a = np.asarray(Image.open(src).convert("L"), float)
    b = np.asarray(Image.open(out).convert("L"), float)
    assert np.mean((a - b) ** 2) < 60
    # encaixado: o quadro inteiro (16:9) no meio, com o fundo desfocado em cima e embaixo
    q = _quadros(saida, 54, 96)[TAXA.frames(2.0) + 10]
    detalhe = lambda a: np.abs(np.diff(a, axis=1)).mean()  # noqa: E731
    assert detalhe(q[42:54]) > 2 * detalhe(q[:20]), "o fundo desfocado tem menos detalhe que o quadro inteiro"


def test_filtro_quadro_e_padroes():
    assert R.quadro_padrao("camera", (1920, 1080), (1080, 1920)) == {"modo": "cortar", "x": 0.5, "y": 0.5}
    assert R.quadro_padrao("tela", (1920, 1080), (1080, 1920)) == {"modo": "encaixar"}
    assert R.quadro_padrao("camera", (3840, 2160), (1920, 1080)) == {"modo": "inteiro"}
    f = R.filtro_quadro((1920, 1080), (1080, 1920), {"modo": "cortar", "x": 0.9})
    assert "crop=608:1080:1312:0" in f  # encosta na direita sem sair do quadro
    f = R.filtro_quadro((1920, 1080), (1080, 1920), {"modo": "cortar", "x": 0.5, "zoom": 2})
    assert "crop=304:540:808:270" in f  # zoom 2: metade da altura, no centro
    assert R.x_do_rosto([{"t": 1, "cx": 0.3}, {"t": 2, "cx": 0.32}, {"t": 9, "cx": 0.9}], 0, 3) == 0.32
    assert R.x_do_rosto([], 0, 3) is None


@pytest.fixture(scope="module")
def demo(tmp_path_factory, clipe):
    return video_demo.montar(tmp_path_factory.mktemp("demo"), clipe)


@pytest.fixture
def copia(demo, tmp_path):
    v = tmp_path / demo.name
    shutil.copytree(demo, v, ignore=shutil.ignore_patterns("Brutos", "Renders"))
    return v


def test_render_com_animacoes_som_e_legenda(copia):
    pl = R.plano(copia)
    assert [s["id"] for s in pl["sobreposicoes"]] == ["mo01", "mo02"]
    assert {e["id"] for e in pl["efeitos"]} == {"sfx01", "sfx02"} and pl["musica"]
    assert any("câmera" in a for a in pl["avisos"])
    sem = R.renderizar(copia, rascunho=True, legenda="nao", progresso=lambda m: None)
    com = R.renderizar(copia, rascunho=True, legenda="ass", progresso=lambda m: None)
    assert sem["animacoes"] == 2 and com["legenda"] == "ass"
    assert sem["lufs"] == pytest.approx(-14, abs=1.0) and sem["pico_dbtp"] <= -0.5
    assert sem["duracao"] == pytest.approx(pl["duracao"], abs=0.05)
    a, b = _quadros(sem["arquivo"], 192, 108), _quadros(com["arquivo"], 192, 108)
    t = TAXA.frames(0.3)  # a tarja ainda não entrou; a legenda já está na tela
    assert np.abs(a[t][80:100] - b[t][80:100]).mean() > 3, "a legenda queimada aparece embaixo"
    antes, durante = a[TAXA.frames(0.3)], a[TAXA.frames(1.5)]
    assert durante[78:92, 12:60].mean() < antes[78:92, 12:60].mean() - 20, "a tarja escura (com transparência) entrou"
    assert durante[10:40, 100:180].mean() == pytest.approx(antes[10:40, 100:180].mean(), abs=25), \
        "fora da tarja, o vídeo continua visível"
    # formato vertical: animações 16:9 ficam de fora, com aviso
    pv = R.plano(copia, formato="9:16")
    assert pv["sobreposicoes"] == [] and any("não cabe" in x for x in pv["avisos"])


def test_render_recusa_legenda_velha_antes_de_comecar(copia):
    P.editar_cortes(copia, None, "remover_segmento", id="s003")
    with pytest.raises(R.ErroRender, match="outro corte"):
        R.renderizar(copia, rascunho=True, legenda="ass", progresso=lambda m: None)
    assert not list((copia / "_CLAUDE").glob("render_tmp/*")), "nada foi renderizado"


def test_normalizar_nao_desloca(tmp_path):
    entrada = tmp_path / "e.wav"
    _ff("-f", "lavfi", "-i", "aevalsrc='0.05*sin(2*PI*300*t)+0.5*sin(2*PI*900*t)*between(t,1,1.02)':s=48000:d=4:c=stereo",
        entrada)
    saida = tmp_path / "s.wav"
    r = A.normalizar(entrada, saida, -14, -1)
    assert r["depois_lufs"] == pytest.approx(-14, abs=0.6)
    assert A.atraso(entrada, saida) == 0
    with pytest.raises(A.ErroAudio, match="silêncio"):
        silencio = tmp_path / "z.wav"
        _ff("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", silencio)
        A.normalizar(silencio, tmp_path / "z2.wav")


def test_cli_render_plano(copia):
    p = subprocess.run([sys.executable, "-I", str(F / "render.py"), "plano", str(copia)], capture_output=True,
                       text=True, encoding="utf-8")
    assert p.returncode == 0 and "s003 tela01" in p.stdout and "animação mo01" in p.stdout


# ------------------------------------------------------------------ curtos
def test_frases_e_sugestoes(copia):
    c = K.frases(copia)
    fs = c["frases"]
    assert [f["id"] for f in fs] == ["f001", "f002"] and fs[0]["texto"].startswith("Olá")
    assert (copia / "_CLAUDE" / "curtos" / "frases.txt").read_text(encoding="utf-8").startswith("f001 [0:00")
    sug = K.sugerir(copia, 2, 10, 3)
    assert sug and all(2 <= s["duracao"] <= 10 for s in sug)
    assert sug[0]["de"] == "f001"
    # o corte mudou: os ids antigos não valem mais
    P.editar_cortes(copia, None, "remover_segmento", id="s003")
    with pytest.raises(K.ErroCurtos, match="corte mudou"):
        K.frases_atuais(copia)


def test_pontuar_conectivo_e_fim_aberto():
    fs = [{"texto": "Então, isso aqui", "inicio": 0, "fim": 2, "pausa_antes": None, "pausa_depois": 0.1, "palavras": 4},
          {"texto": "Você sabe qual é o erro?", "inicio": 2.5, "fim": 5, "pausa_antes": 0.5, "pausa_depois": 0.6,
           "palavras": 6}]
    n1, m1 = K.pontuar(fs, 0, 0)
    n2, m2 = K.pontuar(fs, 1, 1)
    assert n2 > n1 and any("começa com" in m for m in m1) and any("gancho" in m for m in m2)


def test_criar_curto_mapeia_os_mesmos_quadros(copia):
    with E.editar(copia) as d:  # rastreio de rosto falso: o rosto está à esquerda
        pass
    (copia / "_CLAUDE" / "rosto_cam01.json").write_text(json.dumps(
        {"trilha": [{"t": t / 10, "cx": 0.3, "cy": 0.4, "w": 0.1} for t in range(0, 120)]}), encoding="utf-8")
    K.frases(copia)
    r = K.criar(copia, "Vinte placas!", "f001", "f002", titulo="Vinte placas")
    curto = Path(r["pasta"])
    assert curto == copia / "Curtos" / "vinte-placas"
    n = E.ler(curto)
    assert n["video"]["formato"] == "9:16" and n["etapas"]["cortes"] == "aguardando_aprovacao"
    assert n["fluxo"] == ["cortes", "legendas", "render"] and n["cortes"]["versao"] == 1
    assert all(Path(a["caminho"]).is_absolute() for a in n["midia"]["arquivos"])
    quadros = {s["video"]: s["quadro"] for s in n["cortes"]["segmentos"]}
    assert quadros["cam01"] == {"modo": "cortar", "x": 0.3, "y": 0.5, "pelo_rosto": True}
    assert quadros["tela01"] == {"modo": "encaixar"}
    # quadro a quadro, o curto mostra o mesmo que o longo naquele trecho
    longo = E.ler(copia)
    la = Linha(longo["cortes"]["segmentos"], FPS)
    lc = Linha(n["cortes"]["segmentos"], FPS)
    f0 = TAXA.frames(n["video"]["origem"]["de"])
    for k in range(lc.duracao_frames):
        vc, tc_, _ = lc.seq_para_origem(TAXA.segundos(k))
        vl, tl, _ = la.seq_para_origem(TAXA.segundos(f0 + k))
        assert (vc, TAXA.frames(tc_)) == (vl, TAXA.frames(tl))
    assert longo["curtos"][0]["id"] == "c01" and longo["curtos"][0]["pasta"] == "Curtos/vinte-placas"
    with pytest.raises(K.ErroCurtos, match="já existe"):
        K.criar(copia, "vinte placas", "f001", "f001")
    lst = K.listar(copia)
    assert lst[0]["etapas"]["cortes"] == "aguardando_aprovacao"
    # no painel: o formato do curto e o enquadramento por segmento
    d = P.dados(curto)
    assert d["formato"] == "9:16" and d["segmentos"][0]["quadro"]["x"] == 0.3
    assert d["origem_curto"]["projeto"] == "2026-01-15_Demo"
    # enquadrar não é cortar: a versão do corte não sobe
    P.editar_cortes(curto, None, "quadro", id="s001", quadro={"modo": "cortar", "x": 0.7})
    n2 = E.ler(curto)
    assert n2["cortes"]["versao"] == 1 and n2["cortes"]["segmentos"][0]["quadro"] == {"modo": "cortar", "x": 0.7, "y": 0.5}
    with pytest.raises(P.ErroPainel, match="modo"):
        P.editar_cortes(curto, None, "quadro", id="s001", quadro={"modo": "girar"})


def test_curto_por_tempo_e_erros(copia):
    with pytest.raises(K.ErroCurtos, match="nome"):
        K.criar(copia, "!!!", "1.0", "4.0")
    with pytest.raises(K.ErroCurtos, match="curto demais"):
        K.criar(copia, "x", "1.0", "1.5")
    K.frases(copia)
    with pytest.raises(K.ErroCurtos, match="não existe"):
        K.criar(copia, "x", "f001", "f099")
    r = K.criar(copia, "quadrado", "0.5", "4.0", formato="1:1")
    assert r["formato"] == "1:1" and r["duracao"] == pytest.approx(3.5, abs=0.04)


def test_curto_renderizado_e_publicado(copia):
    K.frases(copia)
    r = K.criar(copia, "vinte", "f001", "f002")
    curto = Path(r["pasta"])
    subprocess.run([sys.executable, "-I", str(F / "legendas.py"), "gerar", str(curto), "--modo", "palavra",
                    "--max-caracteres", "18"], check=True, capture_output=True)
    rr = R.renderizar(curto, rascunho=False, progresso=lambda m: None)
    assert rr["tamanho"] == [1080, 1920] and rr["legenda"] == "ass"
    assert Path(rr["arquivo"]).parent == curto / "Renders"
    textos = {"youtube": {"titulo": "20 placas, 1 defeito", "descricao": "O defeito mais comum.", "tags": ["notebook"]},
              "instagram": {"legenda": "Você sabe qual é?", "hashtags": ["notebook"]},
              "tiktok": {"legenda": "20 placas", "hashtags": ["notebook"]}}
    PB.definir(curto, textos)
    conf = PB.conferir(curto)
    assert set(conf["plataformas"]) == {"shorts", "instagram", "tiktok"}
    assert not any(c["erros"] for c in conf["plataformas"].values())
    cs = PB.capa_candidatas(curto, 2)
    from PIL import Image
    assert Image.open(cs[0]["arquivo"]).size == (1080, 1920), "capa do curto já vertical"
    PB.escolher_capa(curto, 1)
    pk = PB.pacote(curto)
    for pl in ("shorts", "instagram", "tiktok"):
        pasta = Path(pk["pastas"][pl])
        assert (pasta / f"{E.ler(curto)['projeto']}.mp4").stat().st_size > 10_000
        assert (pasta / "capa.png").exists() and (pasta / "texto.txt").exists()
        assert "✓ tudo dentro dos limites" in (pasta / "conferencia.md").read_text(encoding="utf-8")
    assert "#notebook" in (Path(pk["pastas"]["instagram"]) / "texto.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ publicação
def test_tempo_e_capitulos():
    assert PB.tc(0) == "0:00" and PB.tc(83.9) == "1:23" and PB.tc(3725, True) == "1:02:05"
    assert PB.de_tc("1:02:05") == 3725 and PB.de_tc("1:23.5") == 83.5
    caps = [{"tempo": 0, "titulo": "Abertura"}, {"tempo": 15, "titulo": "Medir"}, {"tempo": 40, "titulo": "Trocar"}]
    assert PB.validar_capitulos(caps, 60) == ([], [])
    assert PB.formatar_capitulos(caps, 60) == "0:00 Abertura\n0:15 Medir\n0:40 Trocar"
    assert PB.formatar_capitulos(caps, 4000).startswith("0:00:00 Abertura")
    e, _ = PB.validar_capitulos(caps[:2], 60)
    assert any("pelo menos 3" in x for x in e)
    e, _ = PB.validar_capitulos([dict(caps[0], tempo=5)] + caps[1:], 60)
    assert any("0:00" in x for x in e)
    e, _ = PB.validar_capitulos([caps[0], dict(caps[1], tempo=8), caps[2]], 60)
    assert any("10 s" in x for x in e)
    e, _ = PB.validar_capitulos(caps, 45)
    assert any("último" in x for x in e)
    assert PB.ajustar_inicio([{"tempo": 3, "titulo": "A"}])[0]["tempo"] == 0
    assert PB.ajustar_inicio([{"tempo": 30, "titulo": "A"}])[0]["titulo"] == "Introdução"


def test_ler_capitulos_por_frase_segmento_animacao(copia):
    K.frases(copia)
    caps = PB.ler_capitulos(copia, "0:00 Abertura\nf002 A nota\ns002 Segundo segmento\nmo02 Card\n# comentário\n")
    assert [c["titulo"] for c in caps] == ["Abertura", "Segundo segmento", "A nota", "Card"]
    seg2 = next(s for s in P.dados(copia)["segmentos"] if s["id"] == "s002")
    assert caps[1]["tempo"] == pytest.approx(seg2["seq_ini"], abs=1e-3)
    with pytest.raises(PB.ErroPublicar, match="não sei onde"):
        PB.ler_capitulos(copia, "xyz Título")
    with pytest.raises(PB.ErroPublicar, match="não existe"):
        PB.ler_capitulos(copia, "mo99 Título")
    with E.editar(copia) as d:
        d["motions"]["itens"].append({"id": "mo09", "status": "aprovado", "inicio_seq": 4.0, "efeito": "capitulo",
                                      "parametros": {"titulo": "Segunda parte"}})
    assert PB.capitulos_das_animacoes(copia) == [{"tempo": 4.0, "titulo": "Segunda parte"}]


def test_textos_e_limites():
    assert PB.tags_total(["notebook", "conserto de placa"]) == 8 + 1 + 17 + 2
    assert PB.hashtags("Veja #Notebook e #conserto, não email@x.com#") == ["Notebook", "conserto"]
    pub = {"youtube": {"titulo": "x" * 101, "descricao": "ç" * 2600, "tags": ["t" * 30] * 17,
                       "hashtags": [f"h{i}" for i in range(16)]}}
    e, _ = PB.validar(pub, "youtube", 600, "16:9")
    assert any("título com 101" in x for x in e) and any("bytes" in x for x in e)
    assert any("tags somam" in x for x in e) and any("16 hashtags" in x for x in e)
    _, av = PB.validar({"youtube": {"titulo": "y" * 75, "descricao": "ok"}}, "youtube", 60, "16:9")
    assert any("na busca" in x for x in av)
    e, av = PB.validar({"youtube": {"titulo": "t", "descricao": "d"}}, "shorts", 200, "9:16")
    assert any("200 s" in x for x in e) and any("60 s" in x for x in av)
    e, _ = PB.validar({"youtube": {"titulo": "t", "descricao": "d"}}, "shorts", 30, "16:9")
    assert any("horizontal" in x for x in e)
    e, _ = PB.validar({"instagram": {"legenda": "oi #a #b #c", "hashtags": ["d", "e", "f"]}}, "instagram", 30, "9:16")
    assert any("6 hashtags" in x for x in e)
    e, _ = PB.validar({}, "tiktok", 30, "9:16")
    assert e == ["sem textos para tiktok (publicar.py definir)"]
    caps = [{"tempo": 0, "titulo": "A"}, {"tempo": 20, "titulo": "B"}, {"tempo": 40, "titulo": "C"}]
    desc = PB.descricao_final({"youtube": {"descricao": "Gancho.", "hashtags": ["notebook"]}}, "youtube", caps)
    assert desc == "Gancho.\n\nCapítulos\n0:00 A\n0:20 B\n0:40 C\n\n#notebook"


def test_pacote_recusa_com_erro_e_sem_render(copia):
    with pytest.raises(PB.ErroPublicar, match="render final"):
        PB.pacote(copia)
    R.renderizar(copia, rascunho=False, legenda="nao", progresso=lambda m: None)
    PB.definir(copia, {"youtube": {"titulo": "x" * 120, "descricao": "d"}})
    with pytest.raises(PB.ErroPublicar, match="corrija"):
        PB.pacote(copia)
    PB.definir(copia, {"youtube": {"titulo": "Título bom"}})
    caps = [{"tempo": 0, "titulo": "A"}, {"tempo": 0.5, "titulo": "B"}]
    PB.definir(copia, {"capitulos": caps})
    with pytest.raises(PB.ErroPublicar, match="capítulos"):
        PB.pacote(copia)
    r = PB.pacote(copia, forcar=True)
    conf = (Path(r["pastas"]["youtube"]) / "conferencia.md").read_text(encoding="utf-8")
    assert "✗ capítulos" in conf
    cs = PB.capa_candidatas(copia, 2)
    from PIL import Image
    assert Image.open(cs[0]["arquivo"]).size == (1280, 720)
    assert (copia / "_CLAUDE" / "publicar" / "capas" / "candidatas.png").exists()


def test_cli_publicar(copia):
    def rodar(*a):
        return subprocess.run([sys.executable, "-I", str(F / "publicar.py"), *map(str, a)], capture_output=True,
                               text=True, encoding="utf-8", input="0:00 Abertura\n0:03 Meio\n")
    r = rodar("limites")
    assert r.returncode == 0 and "instagram" in r.stdout and PB.CONFERIDO in r.stdout
    r = rodar("capitulos", copia, "-")
    assert r.returncode == 2 and "0:00 Abertura" in r.stdout and "pelo menos 3" in r.stdout
    r = rodar("capitulos", copia, "-", "--gravar")
    assert r.returncode == 2 and "publicacao" not in E.ler(copia)
