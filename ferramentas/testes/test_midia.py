import pytest

from edicao import contato, midia, silencios
import gerar_clipe


def test_inventario(clipe):
    inv = midia.inventario([str(clipe)])
    por_nome = {i["nome"]: i for i in inv["arquivos"]}
    cam = por_nome["cam01.mp4"]
    assert cam["fps"] == "30000/1001" and cam["resolucao"] == [1280, 720]
    assert cam["canais_audio"] == 2 and cam["vfr"] is False
    assert cam["duracao"] == pytest.approx(12.0, abs=0.05)
    assert por_nome["cam02.mp4"]["fps"] == "25" and por_nome["cam02.mp4"]["canais_audio"] == 0
    # ordem pela data de gravação: cam01 (10:00) antes de cam02 (10:05)
    nomes = [i["nome"] for i in inv["arquivos"]]
    assert nomes.index("cam01.mp4") < nomes.index("cam02.mp4")
    assert any("taxas de quadros diferentes" in a for a in inv["alertas"])
    assert any("cam02.mp4: vídeo sem áudio" in a for a in inv["alertas"])


def test_arquivo_ilegivel(tmp_path):
    ruim = tmp_path / "quebrado.mp4"
    ruim.write_bytes(b"isto nao e video")
    i = midia.analisar(ruim)
    assert i["tipo"] == "ilegivel" and i["alertas"]


def test_silencios_batem_com_as_falas(clipe):
    r = silencios.detectar(clipe / "cam01.mp4", minimo=0.3)
    assert len(r["som"]) == len(gerar_clipe.FALAS)
    for (a, b), (x, y) in zip(r["som"], gerar_clipe.FALAS):
        assert a == pytest.approx(x, abs=0.03) and b == pytest.approx(y, abs=0.03)
    assert r["silencios"][-1][1] <= r["duracao"] + 1e-6  # não passa do fim do arquivo


def test_silencios_num_trecho(clipe):
    r = silencios.detectar(clipe / "cam01.mp4", inicio=5.0, duracao=4.0)
    assert len(r["som"]) == 1
    assert r["som"][0][0] == pytest.approx(5.5, abs=0.03) and r["som"][0][1] == pytest.approx(8.0, abs=0.03)


def test_complemento():
    assert silencios.complemento([[1, 2], [3, 4]], 0, 5) == [[0, 1], [2, 3], [4, 5]]
    assert silencios.complemento([], 0, 2) == [[0, 2]]


def test_folha_de_contato(clipe, tmp_path):
    r = contato.folha(clipe / "cam01.mp4", tmp_path / "f.png", inicio=1, fim=3, cada=6, colunas=5)
    assert r["quadros"] == 10 and (tmp_path / "f.png").stat().st_size > 10_000
    assert r["tempos"][0] == pytest.approx(1.001, abs=0.001)
    r2 = contato.folha(clipe / "cam01.mp4", tmp_path / "g.png", cada=1, maximo=20)
    assert r2["aviso"] and r2["quadros"] <= 20
