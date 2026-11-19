"""XML: estrutura, ligações, fades, volta e o teste de regressão congelado.

Para atualizar o arquivo esperado DEPOIS de conferir no programa que a mudança é desejada:
    ATUALIZAR_ESPERADO=1 python -m pytest testes/test_xmeml.py
"""
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from edicao import xmeml
from edicao.linha import Linha

ESPERADO = Path(__file__).parent / "esperado" / "estado_fixo.xml"


def _arvore(texto):
    return ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", texto))


def test_regressao_congelada(estado_fixo):
    texto = xmeml.montar(estado_fixo).xml()
    if os.environ.get("ATUALIZAR_ESPERADO") or not ESPERADO.exists():
        ESPERADO.parent.mkdir(exist_ok=True)
        ESPERADO.write_text(texto, encoding="utf-8")
        if not os.environ.get("ATUALIZAR_ESPERADO"):
            pytest.skip("arquivo esperado criado agora; confira e rode de novo")
    assert texto == ESPERADO.read_text(encoding="utf-8"), \
        "o XML mudou: mudança que ninguém pediu é bug (veja o docstring para atualizar de propósito)"


def test_estrutura(estado_fixo):
    seq = xmeml.montar(estado_fixo)
    raiz = _arvore(seq.xml())
    s = raiz.find("sequence")
    assert s.findtext("rate/timebase") == "30" and s.findtext("rate/ntsc") == "TRUE"
    vt = s.findall("media/video/track")
    at = s.findall("media/audio/track")
    assert len(vt) == 4                                   # V1 câmera, V2 vazia, V3 tela cheia, V4 sobreposição
    assert [len(t.findall("clipitem")) for t in vt] == [4, 0, 1, 1]
    assert len(at) % 2 == 0 and len(at) >= 4              # pares estéreo: voz + efeitos
    for i, t in enumerate(at):
        assert t.get("totalExplodedTrackCount") == "2" and t.get("premiereTrackType") == "Stereo"
        assert t.get("currentExplodedTrackIndex") == str(i % 2)
        assert t.findtext("outputchannelindex") == str(i % 2 + 1)
    # duração da sequência = soma dos segmentos em frames
    linha = Linha(estado_fixo["cortes"]["segmentos"], "30000/1001")
    assert int(s.findtext("duration")) == linha.duracao_frames
    # V1 contínua
    clipes = vt[0].findall("clipitem")
    assert clipes[0].findtext("start") == "0"
    for a, b in zip(clipes, clipes[1:]):
        assert a.findtext("end") == b.findtext("start")
    # tela cheia sem alpha, sobreposição com alpha; animação riscada não entra
    assert vt[2].find("clipitem/alphatype").text == "none"
    assert vt[3].find("clipitem/alphatype").text == "straight"
    assert "mo03" not in seq.xml()


def test_cada_arquivo_declarado_uma_vez(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo).xml())
    completos = [f for f in raiz.iter("file") if f.find("pathurl") is not None]
    ids = [f.get("id") for f in completos]
    assert len(ids) == len(set(ids))
    referencias = {f.get("id") for f in raiz.iter("file")}
    assert referencias == set(ids)


def test_ligacoes_apontam_para_o_lugar_certo(estado_fixo):
    """O índice do clipe conta clipes E transições da trilha; cada link precisa bater."""
    raiz = _arvore(xmeml.montar(estado_fixo).xml())
    s = raiz.find("sequence")
    onde = {}
    for tipo in ("video", "audio"):
        for ti, t in enumerate(s.findall(f"media/{tipo}/track"), start=1):
            itens = [e for e in t if e.tag in ("clipitem", "transitionitem")]
            for ci, e in enumerate(itens, start=1):
                if e.tag == "clipitem":
                    onde[e.get("id")] = (tipo, ti, ci)
    links = 0
    for ci in raiz.iter("clipitem"):
        for ln in ci.findall("link"):
            ref = ln.findtext("linkclipref")
            assert onde[ref] == (ln.findtext("mediatype"), int(ln.findtext("trackindex")),
                                 int(ln.findtext("clipindex"))), ref
            links += 1
    assert links == 4 * 3 * 3  # 4 takes × (vídeo + 2 canais) × 3 links cada


def test_fades_da_voz(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo).xml())
    a1 = raiz.find("sequence/media/audio/track")
    trs = a1.findall("transitionitem")
    alins = [t.findtext("alignment") for t in trs]
    # s002 → s003: s003 começa no frame 0 de cam02, não há mídia antes para cruzar;
    # cada lado ganha o seu fade de 1 frame em vez de um corte seco
    assert alins == ["start-black", "center", "end-black", "start-black", "center", "end-black"]
    for t in trs:
        dur = int(t.findtext("end")) - int(t.findtext("start"))
        assert dur == (2 if t.findtext("alignment") == "center" else 1)
    # o crossfade fica centrado na junção
    clipes = a1.findall("clipitem")
    assert int(trs[1].findtext("start")) + 1 == int(clipes[0].findtext("end"))
    # as transições não se sobrepõem
    pares = sorted((int(t.findtext("start")), int(t.findtext("end"))) for t in trs)
    assert all(a[1] <= b[0] for a, b in zip(pares, pares[1:]))


def test_sem_midia_sobrando_avisa(estado_fixo):
    seq = xmeml.montar(estado_fixo)
    seq.xml()
    assert sum("sem mídia sobrando" in a for a in seq.avisos) == 1
    estado_fixo["cortes"]["segmentos"][2]["inicio"] = 0.5      # agora há sobra em cam02
    seq = xmeml.montar(estado_fixo)
    seq.xml()
    assert not any("sem mídia sobrando" in a for a in seq.avisos)


def test_menos_um(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo, menos_um=True).xml())
    a1 = raiz.find("sequence/media/audio/track")
    assert [c.findtext("start") for c in a1.findall("clipitem")][0] == "-1"
    v1 = raiz.find("sequence/media/video/track")
    assert "-1" not in [c.findtext("start") for c in v1.findall("clipitem")]


def test_sem_fades(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo, fade_frames=0).xml())
    assert not list(raiz.iter("transitionitem"))


def test_efeitos_sonoros(estado_fixo):
    seq = xmeml.montar(estado_fixo)
    raiz = _arvore(seq.xml())
    at = raiz.findall("sequence/media/audio/track")
    nomes = {c.findtext("name"): c for c in raiz.iter("clipitem")}
    # sfx01 e sfx02 se sobrepõem: o segundo vai para a trilha seguinte
    assert any("sfx02" in a for a in seq.avisos)
    assert nomes["sfx01"].find("filter/effect/parameter/value").text == f"{10 ** (-6 / 20):.6f}"
    assert nomes["sfx03"].find("filter") is None
    # efeito mono usa o canal 1 nas duas trilhas do par
    mono = [c for c in raiz.iter("clipitem") if c.findtext("name") == "sfx02"]
    assert [c.findtext("sourcetrack/trackindex") for c in mono] == ["1", "1"]
    assert len(at) == 6


def test_marcadores(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo).xml())
    ms = raiz.findall("sequence/marker")
    assert [m.findtext("name") for m in ms] == ["m001 duvida_take", "m002 hesitacao"]
    linha = Linha(estado_fixo["cortes"]["segmentos"], "30000/1001")
    t, _ = linha.origem_para_seq("cam01", 9.0)
    assert int(ms[0].findtext("in")) == linha.taxa.frames(t)
    assert "fora do corte" in ms[1].findtext("comment")
    assert ms[0].findtext("out") == "-1"


def test_cor_de_marcador(estado_fixo):
    raiz = _arvore(xmeml.montar(estado_fixo, cores={"duvida_take": 4281740498}).xml())
    assert raiz.find("sequence/marker/pproColor").text == "4281740498"


def test_modo_teste(estado_fixo):
    estado_fixo["cortes"]["segmentos"] += [
        {"id": f"s{i:03d}", "video": "cam01", "inicio": 30 + i, "fim": 30.5 + i} for i in range(5, 12)]
    raiz = _arvore(xmeml.montar(estado_fixo, teste=True).xml())
    assert len(raiz.find("sequence/media/video/track").findall("clipitem")) == 4
    assert len(raiz.findall("sequence/marker")) == 1


@pytest.mark.parametrize("caminho,url", [
    ("/videos/a b/cam 01.mp4", "file://localhost/videos/a%20b/cam%2001.mp4"),
    ("C:\\Videos\\câmera 2.mov", "file://localhost/C:/Videos/c%C3%A2mera%202.mov"),
    ("D:/x/y.wav", "file://localhost/D:/x/y.wav"),
])
def test_pathurl(caminho, url):
    assert xmeml.pathurl(caminho) == url
    assert xmeml.caminho_de_url(url).replace("\\", "/") == caminho.replace("\\", "/")


def test_volta_reconstroi_os_cortes(estado_fixo):
    texto = xmeml.montar(estado_fixo).xml()
    r = xmeml.ler_volta(texto, estado_fixo["midia"]["arquivos"])
    assert r["avisos"] == []
    linha = Linha(estado_fixo["cortes"]["segmentos"], "30000/1001")
    assert [s["video"] for s in r["segmentos"]] == [p.video for p in linha.pedacos]
    for s, p in zip(r["segmentos"], linha.pedacos):
        assert linha.taxa.frames(s["inicio"]) == p.in_f and linha.taxa.frames(s["fim"]) == p.out_f
    assert len(r["marcadores"]) == 2


def test_volta_avisa_o_que_esta_fora_do_modelo(estado_fixo):
    texto = xmeml.montar(estado_fixo).xml()
    texto = texto.replace("cam%2001.mp4", "outro.mp4", 1)       # arquivo desconhecido
    texto = texto.replace("<enabled>TRUE</enabled>", "<enabled>FALSE</enabled>", 1)
    r = xmeml.ler_volta(texto, estado_fixo["midia"]["arquivos"])
    assert any("desligado" in a for a in r["avisos"])


def test_sobreposicao_na_mesma_trilha_e_erro():
    seq = xmeml.Sequencia("x", 25, 1920, 1080)
    m = xmeml.Midia("a", "/a.mp4", 10)
    seq.adicionar(xmeml.Clipe(m, 0, 50, 0, "video", 1))
    seq.adicionar(xmeml.Clipe(m, 0, 50, 25, "video", 1))
    with pytest.raises(xmeml.ErroXML, match="sobrepostos"):
        seq.xml()


def test_clipe_fora_do_arquivo_e_erro():
    seq = xmeml.Sequencia("x", 25, 1920, 1080)
    with pytest.raises(xmeml.ErroXML, match="fora do arquivo"):
        seq.adicionar(xmeml.Clipe(xmeml.Midia("a", "/a.mp4", 2), 0, 100, 0, "video", 1))


def test_linha_ida_e_volta(estado_fixo):
    linha = Linha(estado_fixo["cortes"]["segmentos"], "30000/1001")
    for t_seq in (0.0, 1.0, 4.29, 4.4, 10.0, 18.0):
        video, t_orig, p = linha.seq_para_origem(t_seq)
        volta, p2 = linha.origem_para_seq(video, t_orig)
        assert linha.taxa.frames(volta) == linha.taxa.frames(t_seq) and p2 == p
    assert linha.seq_para_origem(999) is None
    seq, p, dentro = linha.origem_para_seq_proximo("cam01", 6.5)   # cortado: cai no início de s002
    assert not dentro and p.id == "s002" and linha.taxa.frames(seq) == p.seq_ini
