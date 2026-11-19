"""O fluxo pelas linhas de comando, de ponta a ponta, no clipe de teste.

É o mesmo caminho que as etapas iniciar → preparar → cortes → entrega seguem
num vídeo de verdade (sem o motor de transcrição, que entra pelo JSON de exemplo).
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

F = Path(__file__).resolve().parent.parent
MODELO = F / "modelos" / "face_detection_yunet_2023mar.onnx"


def rodar(*args, ok=True):
    p = subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8")
    if ok and p.returncode != 0:
        raise AssertionError(f"{args}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    return p


@pytest.fixture
def video(clipe, tmp_path):
    """Uma pasta de projeto com o clipe nos brutos."""
    proj = tmp_path / "2026-01-15_Teste"
    (proj / "Brutos").mkdir(parents=True)
    shutil.copy(clipe / "cam01.mp4", proj / "Brutos" / "cam01.mp4")
    return proj


def test_ponta_a_ponta(video, dados_teste):
    C = video / "_CLAUDE"
    # iniciar
    r = rodar(F / "estado.py", video, "--init", video.name, "--perfil", "padrao")
    assert "próxima etapa: iniciar" in r.stdout
    rodar(F / "estado.py", video, "--etapa", "iniciar=concluido")
    # preparar: inventário no estado
    r = rodar(F / "midia.py", video / "Brutos", "--estado", video)
    assert "principal cam01 (30000/1001 fps, 1280x720)" in r.stdout
    # silêncios + transcrição (normalizada a partir do exemplo do WhisperX)
    rodar(F / "silencios.py", video / "Brutos" / "cam01.mp4", "--saida", C / "silencios_cam01.json")
    rodar(F / "transcrever.py", "normalizar", dados_teste / "whisperx.json", C / "palavras_cam01.json")
    r = rodar(F / "transcrever.py", "frases", C / "palavras_cam01.json", "--silencios",
              C / "silencios_cam01.json", "--video", "cam01", "--saida", C / "frases_cam01.txt")
    assert "1 lacunas" in r.stdout
    frases = (C / "frases_cam01.txt").read_text(encoding="utf-8")
    assert "⟨som sem palavra" in frases and "(ééé)" in frases
    r = rodar(F / "transcrever.py", "notas", C / "palavras_cam01.json")
    assert "usa esse take" in r.stdout
    rodar(F / "estado.py", video, "--set", "transcricao",
          json.dumps({"motor": "whisperx", "palavras": {"cam01": "_CLAUDE/palavras_cam01.json"}}))
    rodar(F / "estado.py", video, "--etapa", "preparar=concluido")

    # cortes: o Claude escolhe pelo texto, o script grava
    cortes = {"segmentos": [
        {"id": "s001", "video": "cam01", "inicio": 0.45, "fim": 2.05, "texto": "Olá pessoal"},
        {"id": "s002", "video": "cam01", "inicio": 2.55, "fim": 4.15, "texto": "hoje vamos falar"},
        {"id": "s003", "video": "cam01", "inicio": 8.95, "fim": 11.05, "texto": "(take recuperado)"}]}
    (C / "cortes.json").write_text(json.dumps(cortes), encoding="utf-8")
    r = rodar(F / "estado.py", video, "--gravar", "cortes", C / "cortes.json")
    assert "versão 1" in r.stdout
    marc = [{"id": "m001", "video": "cam01", "tempo": 9.0, "tipo": "alerta", "texto": "take que a transcrição perdeu"}]
    (C / "marc.json").write_text(json.dumps(marc), encoding="utf-8")
    rodar(F / "estado.py", video, "--gravar", "marcadores", C / "marc.json")
    rodar(F / "estado.py", video, "--validar")

    # entrega: primeiro o arquivo de teste, depois a versão de verdade (sem sobrescrever)
    r = rodar(F / "exportar_xml.py", "exportar", video, "--teste")
    assert "_cortes_teste_v01.xml" in r.stdout and "TESTE" in r.stdout
    r1 = rodar(F / "exportar_xml.py", "exportar", video)
    r2 = rodar(F / "exportar_xml.py", "exportar", video)
    assert "_cortes_v01.xml" in r1.stdout and "_cortes_v02.xml" in r2.stdout
    assert "3 clipes em V1 · 1 marcadores" in r1.stdout
    d = json.loads((C / "projeto.json").read_text(encoding="utf-8"))
    assert [e["versao"] for e in d["entregas"]] == [1, 2]

    # a fala no tempo da sequência, para o plano de animação
    r = rodar(F / "transcrever.py", "fala", video)
    assert "┄ corte" in r.stdout and "s003  ⟨sem fala transcrita⟩" in r.stdout

    # a volta: a pessoa apertou o fim do s001 no programa e exportou
    xml = (C / "entregas" / f"{video.name}_cortes_v01.xml").read_text(encoding="utf-8")
    xml = xml.replace("<end>48</end>\n            <in>13</in>\n            <out>61</out>",
                      "<end>42</end>\n            <in>13</in>\n            <out>55</out>", 1)
    (C / "editado.xml").write_text(xml, encoding="utf-8")
    r = rodar(F / "exportar_xml.py", "volta", video, C / "editado.xml")
    assert "nada gravado" in r.stdout
    r = rodar(F / "exportar_xml.py", "volta", video, C / "editado.xml", "--aplicar")
    assert "versão 2" in r.stdout
    d = json.loads((C / "projeto.json").read_text(encoding="utf-8"))
    assert d["cortes"]["segmentos"][0]["fim"] == pytest.approx(55 * 1001 / 30000, abs=1e-3)
    assert d["cortes"]["segmentos"][0]["texto"] == "Olá pessoal"   # o texto acompanha

    # status e itens
    r = rodar(F / "estado.py", video, "status")
    assert "[✓] preparar" in r.stdout and "próxima etapa: cortes" in r.stdout
    r = rodar(F / "estado.py", video, "--item", "s002")
    assert '"video": "cam01"' in r.stdout
    r = rodar(F / "estado.py", video, "--item", "zzz", ok=False)
    assert r.returncode == 1


def test_erros_claros(tmp_path):
    r = rodar(F / "estado.py", tmp_path, "status", ok=False)
    assert r.returncode == 2 and "ainda não foi iniciado" in r.stderr
    rodar(F / "estado.py", tmp_path, "--init", "x")
    r = rodar(F / "exportar_xml.py", "exportar", tmp_path, ok=False)
    assert r.returncode == 2 and "cortes.segmentos" in r.stderr
    r = rodar(F / "estado.py", tmp_path, "--etapa", "cortes", ok=False)
    assert "use --etapa" in r.stderr


def test_outras_ferramentas(clipe, tmp_path):
    r = rodar(F / "tempo.py", "--fps", "29.97", "--frame", "1800", "--df")
    assert "00:01:00;02" in r.stdout
    r = rodar(F / "contato.py", clipe / "cam01.mp4", tmp_path / "f.png", "--inicio", "0:01", "--fim", "0:02")
    assert json.loads(r.stdout)["quadros"] > 0
    bib = tmp_path / "sons"
    shutil.copytree(clipe / "sfx", bib)
    r = rodar(F / "sons.py", "indexar", bib)
    assert "3 sons" in r.stdout
    r = rodar(F / "sons.py", "buscar", bib / "indice.json", "--categoria", "whoosh")
    assert "whoosh_01" in r.stdout and "pico 0.80s" in r.stdout
    r = rodar(F / "midia.py", clipe)
    assert "VFR" not in r.stdout and "sem áudio" in r.stdout
    if MODELO.exists():
        r = rodar(F / "rosto.py", "rastrear", clipe / "rosto.mp4", tmp_path / "r.json", "--modelo", MODELO)
        assert "100%" in r.stdout or "95%" in r.stdout
