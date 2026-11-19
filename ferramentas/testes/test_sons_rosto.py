import json
import os
from pathlib import Path
import shutil

import pytest

from edicao import rosto, sons
import gerar_clipe

MODELO = Path(__file__).resolve().parent.parent / "modelos" / rosto.NOME_MODELO


def test_indice_de_sons(clipe, tmp_path):
    bib = tmp_path / "sons"
    shutil.copytree(clipe / "sfx", bib)
    ind = sons.indexar(bib)
    por_id = {s["id"]: s for s in ind["sons"]}
    for nome, (dur, pico) in gerar_clipe.SFX.items():
        s = por_id[Path(nome).stem]
        assert s["categoria"] == nome.split("/")[0]
        assert s["duracao"] == pytest.approx(dur, abs=0.01)
        assert s["pico"] == pytest.approx(pico, abs=0.02)
    # incremental, e os campos escritos à mão ficam
    ind["sons"][0]["licenca"] = "CC0"
    ind2 = sons.indexar(bib, ind)
    assert ind2["reaproveitados"] == 3 and ind2["sons"][0]["licenca"] == "CC0"
    # um arquivo quebrado não para o índice
    (bib / "pop" / "quebrado.wav").write_bytes(b"nada")
    ind3 = sons.indexar(bib, ind2)
    assert len(ind3["sons"]) == 3 and any("quebrado" in e for e in ind3["erros"])


def test_buscar():
    ind = {"sons": [
        {"id": "w1", "arquivo": "whoosh/vidro_rapido.wav", "categoria": "whoosh", "duracao": 0.8},
        {"id": "w2", "arquivo": "whoosh/longo.wav", "categoria": "whoosh", "duracao": 2.5, "favorito": True},
        {"id": "p1", "arquivo": "pop/p.wav", "categoria": "pop", "duracao": 0.2, "tags": ["vidro"]},
    ]}
    assert [s["id"] for s in sons.buscar(ind, categoria="whoosh")] == ["w2", "w1"]
    assert [s["id"] for s in sons.buscar(ind, texto="vidro")] == ["p1", "w1"]
    assert [s["id"] for s in sons.buscar(ind, dur_max=1)] == ["p1", "w1"]


@pytest.mark.skipif(not MODELO.exists(), reason="modelo YuNet não baixado (rosto.py baixar)")
def test_rastreio_segue_o_rosto(clipe):
    r = rosto.rastrear(clipe / "rosto.mp4", MODELO, amostras_por_s=5)
    assert r["resumo"]["cobertura"] >= 0.9
    cx = [a["cx"] for a in r["amostras"] if a.get("cx") is not None]
    assert cx[0] == pytest.approx(250 / 960, abs=0.03)        # o rosto desenhado começa em x=250
    assert cx[-1] > cx[0] + 0.3                                # e anda para a direita
    assert all(t["cx"] is not None for t in r["trilha"])


@pytest.mark.skipif(not MODELO.exists(), reason="modelo YuNet não baixado (rosto.py baixar)")
def test_rastreio_sem_rosto(clipe):
    r = rosto.rastrear(clipe / "cam01.mp4", MODELO, amostras_por_s=2, fim=3)
    assert r["resumo"]["com_rosto"] == 0
    assert all(t["cx"] is None for t in r["trilha"])


def test_suavizar_tapa_buracos_e_ignora_um_erro():
    a = [{"t": i / 5, "cx": 0.5, "cy": 0.5, "w": 0.2} for i in range(10)]
    a[4] = {"t": 0.8, "cx": None}
    a[6] = {"t": 1.2, "cx": 0.95, "cy": 0.5, "w": 0.2}     # um quadro errado
    tr = rosto.suavizar(a, janela=3)
    assert tr[4]["cx"] == pytest.approx(0.5) and tr[4]["interpolado"]
    assert tr[6]["cx"] == pytest.approx(0.5)
