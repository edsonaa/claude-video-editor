import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from edicao import audio as A
from edicao import config as C
from edicao import efeitos as EF
from edicao import estado as E
from edicao import ff
from edicao import legendas as L
from edicao import transcricao as T
from edicao import xmeml
from edicao.linha import Linha
import gerar_clipe

F = Path(__file__).resolve().parent.parent
FPS = "30000/1001"
SEGS = [{"id": "s001", "video": "cam01", "inicio": 0.45, "fim": 2.05},
        {"id": "s002", "video": "cam01", "inicio": 2.55, "fim": 4.15},
        {"id": "s003", "video": "cam01", "inicio": 5.45, "fim": 8.05}]


@pytest.fixture
def wx(dados_teste):
    return T.ler(dados_teste / "whisperx.json")


@pytest.fixture
def palavras(wx):
    return L.palavras_na_sequencia({"cam01": wx}, Linha(SEGS, FPS))


# ------------------------------------------------------------------ legendas
def test_quebra_de_linhas():
    ls = L.quebrar_linhas("o defeito estava na bobina queimada do conversor de tensão".split(), 32)
    assert len(ls) == 2 and all(len(l) <= 32 for l in ls)
    assert L._sem_pontuacao(ls[0].split()[-1]) not in L._NAO_TERMINA
    assert L.quebrar_linhas(["curta"], 42) == ["curta"]
    # pontuação puxa a quebra para ela
    ls = L.quebrar_linhas("Primeiro, você mede a tensão na entrada da placa".split(), 40)
    assert ls[0].endswith("Primeiro,") or len(ls[0]) > 8


def test_palavras_so_do_corte_e_sem_hesitacao(palavras, wx):
    textos = [w["texto"] for w in palavras]
    assert "ééé" not in textos and textos[0] == "Olá"
    assert [w["inicio"] for w in palavras] == sorted(w["inicio"] for w in palavras)  # ordem preservada
    assert all(0 <= w["inicio"] <= w["fim"] for w in palavras)
    com = L.palavras_na_sequencia({"cam01": wx}, Linha(SEGS, FPS), remover_hesitacoes=False)
    assert "ééé" in [w["texto"] for w in com]
    corr = L.palavras_na_sequencia({"cam01": wx}, Linha(SEGS, FPS), correcoes={"edicão": "edição", "20": "vinte"})
    assert "edição" in [w["texto"] for w in corr] and "vinte" in [w["texto"] for w in corr]


def test_correcao_mantem_pontuacao():
    assert L.aplicar_correcoes("placa.", {"placa": "PCB"}) == "PCB."
    assert L.aplicar_correcoes("(Bios),", {"bios": "BIOS"}) == "(BIOS),"
    assert L.aplicar_correcoes("placas", {"placa": "PCB"}) == "placas"


@pytest.mark.parametrize("max_car,linhas", [(42, 2), (20, 2), (16, 1)])
def test_blocos_respeitam_as_regras(palavras, max_car, linhas):
    taxa = Linha(SEGS, FPS).taxa
    bls = L.blocos(palavras, FPS, max_car, linhas)
    todas = [w["texto"] for b in bls for w in b["palavras"]]
    assert todas == [w["texto"] for w in palavras], "nenhuma palavra some ou se repete"
    for b in bls:
        assert len(b["linhas"]) <= linhas and all(len(l) <= max_car for l in b["linhas"])
        assert b["fim"] > b["inicio"]
        assert taxa.frames(b["inicio"]) == pytest.approx(b["inicio"] * float(taxa.fps), abs=0.02)
    for a, b in zip(bls, bls[1:]):
        assert b["inicio"] - a["fim"] >= taxa.segundos(2) - 1e-3, "pelo menos 2 quadros entre blocos"
    assert [b["id"] for b in bls] == [f"l{i:03d}" for i in range(1, len(bls) + 1)]


def test_quebra_no_corte(palavras):
    bls = L.blocos(palavras, FPS, 60, 2, pausa=5, quebrar_no_corte=True)
    for b in bls:
        segs = {w["segmento"] for w in palavras if any(w["inicio"] == x["inicio"] for x in b["palavras"])}
        assert len(segs) == 1


def test_aviso_de_leitura_rapida():
    ws = [{"texto": "palavra", "inicio": i * 0.15, "fim": i * 0.15 + 0.14, "segmento": "s1"} for i in range(12)]
    bls = L.blocos(ws, 30, 42, 2, min_dur=0.3, estender=0)
    assert any("caracteres/s" in a for a in L.avisos(bls))


def test_retexto():
    b = {"id": "l001", "inicio": 1.0, "fim": 3.0, "linhas": ["a b c"],
         "palavras": [{"texto": t, "inicio": 1.0 + i * 0.5, "fim": 1.4 + i * 0.5} for i, t in enumerate("abc")]}
    mesmo = L.retexto(b, "x y z", 42)
    assert [w["inicio"] for w in mesmo["palavras"]] == [1.0, 1.5, 2.0]
    outro = L.retexto(b, "uma frase bem diferente agora", 42)
    assert outro["palavras"][0]["inicio"] == 1.0 and outro["palavras"][-1]["fim"] == pytest.approx(1.4 + 1.0, abs=0.01)
    assert outro["linhas"] == ["uma frase bem diferente agora"]


def test_formatos(palavras):
    bls = L.blocos(palavras, FPS, 42, 2)
    s = L.srt(bls)
    assert s.startswith("1\n00:00:00,")
    assert re.search(r"^\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}$", s, re.M)
    assert L.srt(bls, caixa_alta=True).count("OLÁ") == 1
    v = L.vtt(bls)
    assert v.startswith("WEBVTT\n") and "00:00:00." in v and "," not in v.split("\n")[3]
    tema = EF.tema_de(estilo="impacto")
    a = L.ass(bls, tema, 1080, 1920, modo="palavra", caixa_alta=True)
    assert "PlayResX: 1080" in a and "PlayResY: 1920" in a
    # cor de destaque do estilo em BGR do ASS (#FACC15 → &H0015CCFA)
    assert "&H0015CCFA" in a
    eventos = [l for l in a.splitlines() if l.startswith("Dialogue:")]
    assert len(eventos) == sum(len(b["palavras"]) for b in bls)
    frase = L.ass(bls, tema, 1920, 1080)
    assert len([l for l in frase.splitlines() if l.startswith("Dialogue:")]) == len(bls)
    hf = L.para_hyperframes(bls, 1.0, 4.0)
    assert all(0 <= x["i"] < x["f"] <= 3.0 for x in hf["blocos"])
    assert all(p[1] >= 0 for x in hf["blocos"] for p in x["p"])


@pytest.mark.skipif("ass" not in subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout,
                    reason="FFmpeg sem libass")
def test_ass_queima_no_ffmpeg(clipe, palavras, tmp_path):
    bls = L.blocos(palavras, FPS, 20, 2)
    arq = tmp_path / "l.ass"
    arq.write_text(L.ass(bls, EF.tema_de(estilo="impacto"), 1280, 720, modo="palavra"), encoding="utf-8")
    out = tmp_path / "q.mp4"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(clipe / "cam01.mp4"), "-t", "3", "-vf", f"ass={arq}",
              "-c:v", "libx264", "-preset", "ultrafast", "-an", str(out)])
    assert out.stat().st_size > 10_000


def test_efeito_legenda_animada_aceita_o_exportado(palavras, tmp_path):
    bls = L.blocos(palavras, FPS, 20, 2)
    params = L.para_hyperframes(bls, 0, 5.8)
    r = EF.criar("legenda-animada", tmp_path / "p", EF.tema_de(estilo="impacto"), params, 5.8, FPS, "9:16")
    assert r["frames"] == Linha(SEGS, FPS).taxa.frames(5.8)
    html = (tmp_path / "p" / "index.html").read_text(encoding="utf-8")
    assert "Olá" in html


def _rodar(*args, ok=True):
    p = subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    if ok:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


def test_cli_legendas_de_ponta_a_ponta(tmp_path, dados_teste, monkeypatch):
    v = tmp_path / "video"
    rodar = _rodar
    rodar(F / "estado.py", v, "--init", "teste", "--fluxo", "iniciar,cortes,legendas")
    (v / "_CLAUDE").mkdir(exist_ok=True)
    rodar(F / "transcrever.py", "normalizar", dados_teste / "whisperx.json", v / "_CLAUDE" / "palavras_cam01.json")
    rodar(F / "estado.py", v, "--set", "midia", json.dumps({"fps": FPS, "arquivos": [{"id": "cam01", "caminho": "/x/cam01.mp4", "tipo": "camera", "duracao": 12}]}))
    rodar(F / "estado.py", v, "--set", "transcricao", json.dumps({"palavras": {"cam01": "_CLAUDE/palavras_cam01.json"}}))
    (v / "c.json").write_text(json.dumps({"segmentos": SEGS}))
    rodar(F / "estado.py", v, "--gravar", "cortes", v / "c.json")
    (v / "corr.json").write_text(json.dumps({"edicão": "edição"}))
    r = rodar(F / "legendas.py", "gerar", v, "--correcoes", v / "corr.json")
    assert "blocos_v01.json" in r.stdout
    assert "edição" in (v / "_CLAUDE" / "legendas" / "revisao.txt").read_text(encoding="utf-8")
    r = rodar(F / "legendas.py", "corrigir", v, "l001", "Olá, pessoal! Hoje vamos falar de 20 placas.")
    assert "blocos_v02.json" in r.stdout
    r = rodar(F / "legendas.py", "exportar", v, "--formatos", "srt,vtt,ass,hyperframes")
    for ext in ("srt", "vtt", "ass"):
        assert list((v / "_CLAUDE" / "legendas").glob(f"*_v02.{ext}"))
    d = E.ler(v)
    assert d["legendas"]["versao"] == 2 and set(d["legendas"]["saidas"]) == {"srt", "vtt", "ass", "hyperframes"}
    # o corte mudou: o status avisa e o exportar também
    segs2 = SEGS[:2]
    (v / "c.json").write_text(json.dumps({"segmentos": segs2}))
    rodar(F / "estado.py", v, "--gravar", "cortes", v / "c.json")
    assert any("legendas" in a for a in E.alertas(E.ler(v)))
    r = rodar(F / "legendas.py", "ver", v)
    assert "o corte mudou" in r.stdout
    r = rodar(F / "legendas.py", "corrigir", v, "l999", "x", ok=False)
    assert r.returncode == 2


# ------------------------------------------------------------------ áudio
@pytest.fixture(scope="module")
def voz_ruidosa(tmp_path_factory, clipe):
    d = tmp_path_factory.mktemp("audio")
    arq = d / "ruidosa.wav"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(clipe / "cam01.mp4"), "-f", "lavfi",
              "-i", "anoisesrc=color=pink:amplitude=0.008:seed=3:d=12", "-filter_complex",
              "[0:a]volume=0.5[v];[v][1:a]amix=inputs=2:duration=first:normalize=0", "-c:a", "pcm_s16le",
              "-ar", "48000", str(arq)])
    return arq


def test_medir(voz_ruidosa):
    m = A.medir(voz_ruidosa)
    assert -22 < m["lufs"] < -14
    assert m["snr_db"] > 25 and m["ruido_db"] < -45 and m["clipping_pct"] == 0
    assert m["duracao"] == pytest.approx(12.0, abs=0.05)
    assert A.ruido_auto({"ruido_db": -40, "snr_db": 30}) == "forte"
    assert A.ruido_auto({"ruido_db": -80, "snr_db": 60}) == "nenhuma"
    assert any("clipping" in r for r in A.recomendacoes({**m, "clipping_pct": 1.0}))


def _desvio_amostras(a_arq, b_arq):
    a = ff.ler_audio(a_arq, taxa=48000).astype(np.float64)
    b = ff.ler_audio(b_arq, taxa=48000).astype(np.float64)
    n = min(a.size, b.size)
    c = np.fft.irfft(np.fft.rfft(b[:n], 2 * n) * np.conj(np.fft.rfft(a[:n], 2 * n)))
    k = int(np.argmax(c))
    return k if k < n else k - 2 * n


@pytest.mark.parametrize("ruido", ["forte", "nenhuma"])
def test_tratar_atinge_o_alvo_sem_tirar_de_sincronia(voz_ruidosa, tmp_path, ruido):
    antes = hashlib.sha256(voz_ruidosa.read_bytes()).hexdigest()
    r = A.tratar(voz_ruidosa, tmp_path / "voz.wav", alvo=-14, pico=-1, ruido=ruido)
    assert r["depois"]["lufs"] == pytest.approx(-14, abs=0.5)
    assert r["depois"]["pico_dbtp"] <= -0.9
    info = ff.sondar(tmp_path / "voz.wav")
    s = info["streams"][0]
    assert s["sample_rate"] == "48000" and s["channels"] == 1
    assert int(s["duration_ts"]) == int(ff.sondar(voz_ruidosa)["streams"][0]["duration_ts"]), "mesma quantidade de amostras"
    assert _desvio_amostras(voz_ruidosa, tmp_path / "voz.wav") == 0, "a voz tratada cai na mesma amostra"
    assert hashlib.sha256(voz_ruidosa.read_bytes()).hexdigest() == antes, "o original não muda"
    with pytest.raises(A.ErroAudio, match="sobrescrever"):
        A.tratar(voz_ruidosa, tmp_path / "voz.wav")


def test_tratar_um_trecho(voz_ruidosa, tmp_path):
    r = A.tratar(voz_ruidosa, tmp_path / "t.wav", inicio=2.0, duracao=6.0)
    assert r["depois"]["duracao"] == pytest.approx(6.0, abs=0.01)
    assert A.atraso(voz_ruidosa, tmp_path / "t.wav", inicio=2.0) == 0


def test_atraso_detecta_deslocamento(voz_ruidosa, tmp_path):
    atrasado = tmp_path / "atrasado.wav"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-i", str(voz_ruidosa), "-af", "adelay=480S:all=1", "-ar", "48000",
              str(atrasado)])
    assert A.atraso(voz_ruidosa, atrasado) == 480


def test_envelope_abaixa_sob_a_fala():
    t, g = A.envelope(10, [[3, 5]], 0, -12, ataque=0.3, liberacao=0.8, fade_in=1, fade_out=1)
    def em(s):
        return g[int(round(s * 100))]
    assert em(2.0) == pytest.approx(0, abs=0.01)          # livre
    assert em(3.0) == pytest.approx(-12, abs=0.01)        # já baixo quando a fala começa (antecipa)
    assert em(2.6) > em(2.8) > em(3.0)                    # desce durante o ataque
    assert -12 < em(5.4) < 0                               # volta durante a liberação
    assert em(6.5) == pytest.approx(0, abs=0.01)
    assert em(0.0) < -40 and em(10.0) < -40                # fades


def test_musica_com_ducking(tmp_path):
    mus = tmp_path / "mus.wav"
    ff.rodar([ff.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
              "aevalsrc='0.2*sin(2*PI*220*t)+0.15*sin(2*PI*330*t)|0.2*sin(2*PI*277*t)':s=48000:d=4", str(mus)])
    fala = [[3.0, 5.0], [8.0, 9.0]]
    r = A.musica(mus, tmp_path / "m.wav", 12.0, fala, nivel_livre=-20, nivel_fala=-32, fade_in=0.5, fade_out=0.5)
    assert r["duracao"] == pytest.approx(12.0, abs=0.001) and r["repeticoes"] >= 2
    y = ff.ler_audio(tmp_path / "m.wav", taxa=48000)
    def rms(a, b):
        s = y[int(a * 48000):int(b * 48000)].astype(np.float64)
        return 20 * np.log10(np.sqrt((s ** 2).mean()))
    queda = rms(1.5, 2.5) - rms(3.3, 4.7)
    assert queda == pytest.approx(12, abs=2.0), queda
    st = ff.sondar(tmp_path / "m.wav")["streams"][0]
    assert st["channels"] == 2


def test_intervalos_de_fala(palavras):
    iv = A.intervalos_de_fala(palavras, juntar=0.6)
    assert iv == sorted(iv) and all(a < b for a, b in iv)
    assert len(iv) < len(palavras)


# ------------------------------------------------------------------ XML com voz tratada, música e legenda
def test_xml_com_voz_tratada_musica_e_legenda(estado_fixo):
    d = estado_fixo
    d["midia"]["arquivos"][0]["audio_tratado"] = "/videos/2026-01-15_Teste/_CLAUDE/audio/cam01_voz_v01.wav"
    d["sfx"]["musica"] = {"arquivo": "/videos/2026-01-15_Teste/_CLAUDE/audio/musica_v01.wav", "inicio_seq": 0.0, "duracao": 60}
    d["legendas"] = {"render": {"arquivo": "/videos/2026-01-15_Teste/_CLAUDE/motion/legendas.mov", "inicio_seq": 0.0, "duracao": 18.0}}
    seq = xmeml.montar(d)
    raiz = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", seq.xml()))
    s = raiz.find("sequence")
    vt = s.findall("media/video/track")
    assert len(vt) == 5 and vt[4].find("clipitem/name").text == "legendas"
    assert vt[4].find("clipitem/alphatype").text == "straight"
    at = s.findall("media/audio/track")
    a1 = at[0].findall("clipitem")
    # takes de cam01 usam a voz tratada; o de cam02 continua com o áudio da câmera
    nomes = [c.findtext("name") for c in a1]
    assert nomes.count("cam01 (voz tratada)") == 3 and any(n.endswith("câmera 2.mov") for n in nomes)
    urls = {f.findtext("pathurl") for f in raiz.iter("file") if f.find("pathurl") is not None}
    assert any(u.endswith("cam01_voz_v01.wav") for u in urls)
    # a voz tratada continua ligada ao vídeo do mesmo take
    primeiro = a1[0]
    assert {ln.findtext("mediatype") for ln in primeiro.findall("link")} == {"video", "audio"}
    # A2 música (par estéreo = trilhas xml 3 e 4); efeitos começam na A3 (xml 5+)
    assert at[2].find("clipitem/name").text == "musica"
    efeitos = [c.findtext("name") for t in at[4:] for c in t.findall("clipitem")]
    assert {"sfx01", "sfx02", "sfx03"} <= set(efeitos)


def test_presets_com_legendas_coerentes():
    for nome, p in C.listar_presets().items():
        cfg = C.config_do_preset(nome)
        cfg["nome"] = "x"
        erros, avisos = C.validar(cfg)
        assert erros == []
        assert not [a for a in avisos if "legenda" in a or "música" in a], (nome, avisos)
    reels = C.config_do_preset("reels")
    assert reels["legendas"]["queimar"] and reels["legendas"]["modo"] == "palavra"
    assert reels["fluxo"].index("legendas") < reels["fluxo"].index("render")
    assert "vtt" in C.config_do_preset("aula-tecnica")["legendas"]["saidas"]
