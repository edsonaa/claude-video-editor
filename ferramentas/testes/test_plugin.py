"""O plugin inteiro fica coerente: manifesto, versão, skills, caminhos e comandos citados.

As skills são texto: um caminho errado ou um comando que não existe só aparece
quando alguém está editando um vídeo. Estes testes pegam isso antes.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from edicao import config as C

RAIZ = Path(__file__).resolve().parent.parent.parent
SKILLS = sorted((RAIZ / "skills").glob("*/SKILL.md"))
MDS = sorted(p for p in RAIZ.rglob("*.md") if ".git" not in p.parts and ".pytest_cache" not in p.parts)


def _frontmatter(texto):
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    assert m, "sem frontmatter"
    campos = {}
    for linha in m.group(1).splitlines():
        k, _, v = linha.partition(":")
        campos[k.strip()] = v.strip().strip('"')
    return campos


def test_manifesto_e_marketplace():
    pj = json.loads((RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mk = json.loads((RAIZ / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert pj["name"] == "edicao" and not pj["name"].startswith("claude")
    assert mk["plugins"][0]["name"] == pj["name"] and mk["plugins"][0]["source"] == "./"
    assert mk["owner"]["name"]


def test_versao_bate_com_o_changelog():
    pj = json.loads((RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    topo = re.search(r"^## (\d+\.\d+\.\d+)", (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert pj["version"] == topo, "suba o version do plugin.json junto com o CHANGELOG"


def test_uma_skill_por_etapa_do_motor_mais_montar_e_editar():
    nomes = {p.parent.name for p in SKILLS}
    esperadas = {C.etapa_skill(e) for e in C.ETAPAS} | {"montar", "editar", "painel", "curtos", "publicar", "estoque"}
    assert nomes == esperadas
    assert not (RAIZ / "SKILL.md").exists(), "SKILL.md na raiz faria o plugin carregar como uma skill só"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter(skill):
    fm = _frontmatter(skill.read_text(encoding="utf-8"))
    assert fm["name"] == skill.parent.name
    assert 50 < len(fm["description"]) < 1024
    assert "/edicao:" + skill.parent.name in fm["description"], "a descrição diz o comando"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_toda_skill_le_as_regras_comuns_e_aponta_o_motor(skill):
    texto = skill.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md" in texto


@pytest.mark.parametrize("md", MDS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_caminhos_do_motor_existem(md):
    texto = md.read_text(encoding="utf-8")
    for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+[A-Za-z0-9_])", texto):
        assert (RAIZ / rel).exists(), f"{md.name} cita {rel}, que não existe"
    for rel in re.findall(r"`(guias/[a-z0-9-]+\.md)`", texto):
        assert (RAIZ / rel).exists(), f"{md.name} cita {rel}, que não existe"


_CACHE_SUBS = {}


def _subcomandos(script: Path) -> set:
    """Os subcomandos que o próprio script declara (pelo --help do argparse)."""
    if script not in _CACHE_SUBS:
        import sys
        p = subprocess.run([sys.executable, "-I", str(script), "--help"], capture_output=True, text=True, encoding="utf-8")
        m = re.search(r"\{([a-z,-]+)\}", p.stdout)
        _CACHE_SUBS[script] = set(m.group(1).split(",")) if m else set()
    return _CACHE_SUBS[script]


@pytest.mark.parametrize("md", MDS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_comandos_citados_existem(md):
    """`<f>/x.py sub` e `x.py sub`: o script existe e, se tem subcomandos, o citado é um deles."""
    texto = md.read_text(encoding="utf-8")
    for script, sub in re.findall(r"(?:<f>/|ferramentas/|\b)([a-z_]+\.py)\b(?: ([a-z-]+))?", texto):
        caminho = RAIZ / "ferramentas" / script
        if not caminho.exists():
            continue  # scripts que a pessoa escreve (sync.py, render.py…) ou módulos do Python
        subs = _subcomandos(caminho)
        if subs and sub and sub not in ("e", "o", "a", "do", "da", "de", "em", "no", "com", "para", "que"):
            assert sub in subs, f"{md.name}: '{script} {sub}' não é um subcomando ({sorted(subs)})"


def test_comandos_das_skills_citam_skills_que_existem():
    nomes = {p.parent.name for p in SKILLS}
    for md in MDS:
        for cmd in re.findall(r"/edicao:([a-z-]+)", md.read_text(encoding="utf-8")):
            assert cmd in nomes, f"{md.name} cita /edicao:{cmd}, que não existe"


def test_estado_tem_as_etapas_que_as_skills_usam():
    for skill in SKILLS:
        for etapa in re.findall(r"--etapa ([a-z_]+)=", skill.read_text(encoding="utf-8")):
            assert etapa in C.ETAPAS, f"{skill.parent.name}: --etapa {etapa}"


@pytest.mark.skipif(not shutil.which("claude"), reason="claude CLI não instalado")
def test_claude_plugin_validate():
    p = subprocess.run(["claude", "plugin", "validate", str(RAIZ)], capture_output=True, text=True, timeout=120)
    saida = p.stdout + p.stderr
    assert p.returncode == 0 and "passed" in saida.lower(), saida


# ------------------------------------------------------------------ documentação (docs/)
DOCS = RAIZ / "docs"
SCRIPTS = sorted(p for p in (RAIZ / "ferramentas").glob("*.py") if "__main__" in p.read_text(encoding="utf-8"))
EFEITOS = sorted(p.parent.name for p in (RAIZ / "efeitos").glob("*/efeito.json"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_docs_comandos_igual_ao_help(script):
    """docs/comandos.md traz cada script com o mesmo texto do --help (a docstring do script)."""
    import ast
    texto = (DOCS / "comandos.md").read_text(encoding="utf-8")
    assert f"### {script.name}" in texto, f"docs/comandos.md não documenta {script.name}"
    doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))).strip()
    assert doc in texto, (f"o --help de {script.name} mudou: copie a docstring nova para docs/comandos.md "
                          "(a seção do script, dentro do bloco ```text)")


def test_docs_efeitos_cobrem_a_biblioteca():
    texto = (DOCS / "efeitos.md").read_text(encoding="utf-8")
    for nome in EFEITOS:
        assert f"| `{nome}` |" in texto, f"docs/efeitos.md: falta {nome} no catálogo"
    for md in MDS:
        if md.name == "CHANGELOG.md":
            continue  # o histórico conta os efeitos de cada versão
        for n in re.findall(r"\b(\d+) efeitos\b", md.read_text(encoding="utf-8")):
            assert int(n) == len(EFEITOS), f"{md.relative_to(RAIZ)} fala em {n} efeitos; a biblioteca tem {len(EFEITOS)}"


@pytest.mark.parametrize("md", sorted(DOCS.glob("*.md")) + [RAIZ / "README.md"], ids=lambda p: str(p.relative_to(RAIZ)))
def test_links_relativos_existem(md):
    texto = md.read_text(encoding="utf-8")
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)
    for alvo in re.findall(r"\]\(([^)\s]+)\)", texto):
        if re.match(r"[a-z]+:", alvo) or alvo.startswith("#"):
            continue
        caminho = (md.parent / alvo.split("#")[0]).resolve()
        assert caminho.exists(), f"{md.relative_to(RAIZ)}: o link {alvo} não existe"
