import json
from pathlib import Path
import subprocess
import sys

import pytest

from edicao import config as C
from edicao import estado as E

F = Path(__file__).resolve().parent.parent


@pytest.fixture
def casa(tmp_path, monkeypatch):
    """Uma ~/.edicao isolada por teste."""
    monkeypatch.setenv("EDICAO_HOME", str(tmp_path / "edicao"))
    return tmp_path / "edicao"


def test_todo_preset_e_valido_e_coerente(casa):
    presets = C.listar_presets()
    assert {"youtube-apresentador", "tutorial-tela", "aula-tecnica", "reels", "narrado", "so-cortes"} <= set(presets)
    for nome, p in presets.items():
        assert p["titulo"] and p["descricao"] and 1 <= len(p["perguntas"]) <= 4, nome
        cfg = C.config_do_preset(nome)
        cfg["nome"] = "Teste"
        erros, avisos = C.validar(cfg)
        assert erros == [], (nome, erros)
        # os únicos avisos aceitos num preset são os que dependem da pessoa
        sobra = [a for a in avisos if "biblioteca" not in a and "python" not in a and "perfil padrão" not in a]
        assert sobra == [], (nome, sobra)


def test_reels_tem_render_e_nenhum_programa():
    cfg = C.config_do_preset("reels")
    assert cfg["revisao"]["programa"] == "nenhum" and cfg["fluxo"][-1] == "render"
    assert cfg["video"]["formato"] == "9:16"


def test_criar_monta_a_pasta_e_nunca_sobrescreve(casa):
    cfg = C.criar("Edson", "aula-tecnica", python="/usr/bin/python3",
                  extra={"transcricao": {"termos": ["VRM", "BIOS"]}})
    assert cfg["preset"] == "aula-tecnica" and cfg["transcricao"]["termos"] == ["VRM", "BIOS"]
    assert cfg["transcricao"]["motor"] == "whisperx"            # o resto do padrão continua
    for sub in ("perfis/padrao/estilo-motion.md", "ajustes/LEIA-ME.md", "etapas", "scripts", ".gitignore"):
        assert (casa / sub).exists(), sub
    assert cfg["motor_versao_lida"] == C.versao_motor()
    with pytest.raises(C.ErroConfig, match="já existe"):
        C.criar("Outro", "reels")
    assert C.carregar()["nome"] == "Edson"


def test_preset_inexistente(casa):
    with pytest.raises(C.ErroConfig, match="não existe"):
        C.criar("X", "nao-existe")


def test_validacao(casa):
    cfg = C.config_do_preset("youtube-apresentador")
    cfg["nome"] = "X"
    cfg["fluxo"] = ["iniciar", "inventada"]
    erros, _ = C.validar(cfg)
    assert any("inventada" in e for e in erros)
    with pytest.raises(C.ErroConfig, match="inválida"):
        C.gravar(cfg)

    cfg = C.config_do_preset("youtube-apresentador")
    cfg["nome"] = "X"
    cfg["fluxo"] = ["iniciar", "preparar", "cortes", "camera", "motion_mapa", "motion_render"]
    cfg["revisao"]["programa"] = "nenhum"
    _, avisos = C.validar(cfg)
    assert any("antes das animações" in a for a in avisos)
    assert any("render" in a for a in avisos)

    cfg["revisao"]["programa"] = "xpto"
    assert C.validar(cfg)[0]


def test_etapa_propria(casa):
    C.criar("X", "so-cortes")
    cfg = C.carregar()
    (casa / "etapas").mkdir(exist_ok=True)
    (casa / "etapas" / "legenda.md").write_text("# legenda\n", encoding="utf-8")
    cfg["etapas_proprias"] = {"legenda": "etapas/legenda.md"}
    cfg["fluxo"] = cfg["fluxo"] + ["legenda"]
    assert C.validar(cfg)[0] == []
    cfg["etapas_proprias"]["cortes"] = "etapas/legenda.md"     # não pode sombrear uma etapa do motor
    assert any("já é uma etapa do motor" in e for e in C.validar(cfg)[0])


def test_campos_novos_do_motor_entram_com_o_padrao(casa):
    casa.mkdir(parents=True)
    velho = C.config_do_preset("so-cortes")
    velho["nome"] = "X"
    del velho["som"]                                             # config gravado por uma versão antiga
    (casa / "config.json").write_text(json.dumps(velho), encoding="utf-8")
    assert C.carregar()["som"] == C.PADRAO["som"]


def test_perfil_novo(casa):
    C.criar("X", "so-cortes")
    p = C.novo_perfil("cliente-a")
    assert (p / "estilo-cortes.md").exists()
    (p / "estilo-cortes.md").write_text("meu", encoding="utf-8")
    p2 = C.novo_perfil("cliente-b", de="cliente-a")
    assert (p2 / "estilo-cortes.md").read_text(encoding="utf-8") == "meu"
    with pytest.raises(C.ErroConfig):
        C.novo_perfil("cliente-a")
    with pytest.raises(C.ErroConfig):
        C.novo_perfil("nome com espaço")


def test_novidades():
    todas = C.novidades(None)
    assert todas and todas[0][0] == C.versao_motor()
    assert C.novidades(C.versao_motor()) == []
    assert [v for v, _ in C.novidades("0.1.0")] == [C.versao_motor()] or C.versao_motor() == "0.1.0"


def test_estado_init_usa_o_fluxo_da_configuracao(casa, tmp_path):
    C.criar("X", "reels", perfil="vertical")
    video = tmp_path / "video"
    p = subprocess.run([sys.executable, "-I", str(F / "estado.py"), str(video), "--init", "v"],
                       capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "EDICAO_HOME": str(casa)})
    assert p.returncode == 0, p.stderr
    d = E.ler(video)
    assert d["fluxo"] == C.config_do_preset("reels")["fluxo"] and d["perfil"] == "vertical"


def test_cli(casa):
    def rodar(*args):
        return subprocess.run([sys.executable, "-I", str(F / "config.py"), *args], capture_output=True,
                              text=True, encoding="utf-8",
                              env={**__import__("os").environ, "EDICAO_HOME": str(casa)})
    r = rodar("mostrar")
    assert r.returncode == 2 and "/edicao:montar" in r.stderr
    r = rodar("criar", "--nome", "Edson", "--preset", "youtube-apresentador", "--json", '{"revisao":{"programa":"resolve"}}')
    assert r.returncode == 0 and "revisão: resolve" in r.stdout
    r = rodar("set", "som.biblioteca", "/sons")
    assert r.returncode == 0 and '"/sons"' in r.stdout
    r = rodar("set", "fluxo", '["iniciar","xpto"]')
    assert r.returncode == 2 and "xpto" in r.stderr
    assert rodar("validar").returncode == 0
    assert "youtube-apresentador" in rodar("presets").stdout
    assert Path(rodar("motor").stdout.strip()) == C.MOTOR
    assert "nada novo" in rodar("novidades").stdout
