import json

import pytest

from edicao import transcricao as T
from edicao.linha import Linha
import gerar_clipe


@pytest.fixture
def wx(dados_teste):
    return T.normalizar(json.loads((dados_teste / "whisperx.json").read_text(encoding="utf-8")), origem="cam01")


@pytest.fixture
def sc(dados_teste):
    return T.normalizar(json.loads((dados_teste / "scribe.json").read_text(encoding="utf-8")), origem="cam01")


def test_detectar_motor(dados_teste):
    assert T.detectar_motor(json.loads((dados_teste / "whisperx.json").read_text())) == "whisperx"
    assert T.detectar_motor(json.loads((dados_teste / "scribe.json").read_text())) == "scribe"
    with pytest.raises(ValueError):
        T.detectar_motor({"outra": 1})


def test_whisperx_normalizado(wx):
    ps = wx["palavras"]
    assert wx["formato"] == T.FORMATO and len(ps) == 19
    assert [p["texto"] for p in ps[:4]] == ["Olá", "pessoal,", "ééé", "hoje"]
    assert ps[2]["tipo"] == "hesitacao" and ps[0]["tipo"] == "palavra"
    vinte = next(p for p in ps if p["texto"] == "20")
    assert vinte["estimado"] is True and 3.80 <= vinte["inicio"] <= vinte["fim"] <= 3.85
    assert all(p["inicio"] <= p["fim"] for p in ps)
    assert [p["inicio"] for p in ps] == sorted(p["inicio"] for p in ps)


def test_scribe_normalizado(sc):
    ps = sc["palavras"]
    assert not any(p["texto"] == " " for p in ps)                 # sem os "spacing"
    risos = next(p for p in ps if p["tipo"] == "evento")
    assert risos["texto"] == "(risos)"
    assert next(p for p in ps if p["texto"] == "ééé")["tipo"] == "hesitacao"
    assert 0 < ps[0]["conf"] <= 1


def test_offset(wx):
    t = T.aplicar_offset(wx, 2.5)
    assert t["palavras"][0]["inicio"] == pytest.approx(wx["palavras"][0]["inicio"] + 2.5)
    assert t["offset"] == 2.5


@pytest.mark.parametrize("texto,hes", [
    ("ééé", True), ("éé", True), ("Hum", True), ("hmm,", True), ("ahn", True), ("eh", True), ("ã", True),
    ("aah", True), ("mmm", True),
    # palavras de verdade
    ("é", False), ("é,", False), ("e", False), ("um", False), ("uma", False), ("ah", True), ("há", False),
    ("tipo", False), ("né", False), ("então", False), ("emoção", False), ("hoje", False), ("humano", False),
])
def test_hesitacoes(texto, hes):
    assert T.eh_hesitacao(texto) is hes


def test_frases(wx):
    fs = T.frases(wx["palavras"])
    assert [f["texto"] for f in fs][:2] == ["Olá pessoal, (ééé) hoje", "hoje vamos falar de 20 placas."]
    assert fs[1]["pausa_antes"] == pytest.approx(0.64, abs=0.01)
    assert fs[1]["estimado"] is True and fs[0]["hesitacoes"] == 1


def test_lacunas_acham_o_take_engolido(wx):
    # sons iguais aos do clipe; o último trecho (9–11 s) não tem palavra nenhuma
    lacs = T.lacunas(wx["palavras"], [list(x) for x in gerar_clipe.FALAS])
    assert lacs == [[9.0, 11.0]]


def test_texto_frases_mostra_lacuna(wx):
    txt = T.texto_frases(wx, "cam01", [[9.0, 11.0]])
    linhas = txt.splitlines()
    assert linhas[-1].startswith("00:09.00–00:11.00") and "som sem palavra 2.0s" in linhas[-1]
    assert "+0.6s" in linhas[2] and " ~ " in linhas[2]


def test_notas_faladas(wx):
    notas = T.notas_faladas(wx["palavras"])
    assert len(notas) == 1
    n = notas[0]
    assert n["texto"] == "usa esse take" and n["inicio"] == 5.52 and n["fim"] == 7.98
    assert n["confianca"] in ("alta", "media")


def test_nota_sem_fechamento():
    ps = [{"texto": t, "inicio": i, "fim": i + 0.3, "tipo": "palavra"} for t, i in
          [("nota", 0), ("de", 0.4), ("edição", 0.8), ("corta", 1.2), ("isso", 1.6), ("depois", 4.0)]]
    n = T.notas_faladas(ps)
    assert len(n) == 1 and n[0]["confianca"] == "baixa" and n[0]["texto"] == "corta isso"
    assert n[0]["fim"] == pytest.approx(1.9)


def test_fala_na_sequencia(wx):
    segs = [{"id": "s001", "video": "cam01", "inicio": 0.45, "fim": 2.05},
            {"id": "s002", "video": "cam01", "inicio": 2.55, "fim": 4.15}]
    txt = T.fala_na_sequencia({"cam01": wx}, Linha(segs, "30000/1001"))
    linhas = txt.splitlines()
    assert "s001" in linhas[1] and "Olá" in linhas[1]
    corte = next(l for l in linhas if l.strip().startswith("┄ corte"))
    assert "frame 48" in corte and "s001 → s002" in corte
    assert linhas[-1].strip().startswith("┄ fim")
