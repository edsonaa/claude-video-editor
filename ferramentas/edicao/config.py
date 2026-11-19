"""A configuração da pessoa, separada do motor.

Motor (este repositório, atualizável): skills, guias, ferramentas.
Pessoa (~/.edicao/, ou a pasta em EDICAO_HOME), que nenhuma atualização toca:
  config.json        as escolhas (programa de revisão, formato, etapas, transcrição…)
  perfis/<nome>/     o gosto (identidade, estilo de motion, câmera, cortes, som)
  ajustes/<etapa>.md o ofício pessoal: aprendizados que valem para os vídeos dela
                     e que as skills do motor leem depois das próprias instruções
  etapas/            etapas que ela mesma criou
  scripts/           scripts que ela escreveu (sincronia, render…), reaproveitados
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil

from . import estado as _estado

MOTOR = Path(__file__).resolve().parent.parent.parent      # raiz do plugin
SCHEMA = MOTOR / "ferramentas" / "schema" / "config.schema.json"
PRESETS = MOTOR / "presets"
PERFIL_INICIAL = MOTOR / "modelos" / "perfil-inicial"
CHANGELOG = MOTOR / "CHANGELOG.md"

# As etapas que o motor sabe fazer, na ordem de referência.
ETAPAS = {
    "iniciar": "abre o projeto e organiza o briefing",
    "preparar": "inventário, sincronia, transcrição, silêncios e notas faladas",
    "cortes": "escolhe takes, tira erros e pausas, entrega o primeiro corte",
    "motion_mapa": "planeja as animações e a câmera em volta delas, sem animar",
    "assets": "busca logos, ícones e prints que as animações precisam",
    "motion_render": "constrói e renderiza cada animação",
    "camera": "zooms e movimentos casados com a fala e as animações",
    "sfx": "efeitos sonoros em camadas, alinhados ao que se vê",
    "render": "monta e exporta o vídeo pronto (quem não revisa num programa)",
}

PADRAO = {
    "schema": 1,
    "nome": "",
    "preset": None,
    "motor_versao_lida": None,
    "python": None,
    "fluxo": list(ETAPAS)[:-1],
    "etapas_proprias": {},
    "revisao": {"programa": "premiere", "etapas_no_programa": ["cortes", "motion_render", "camera", "sfx"],
                "correcoes": "ambos"},
    "video": {"tipo": "apresentador", "formato": "16:9", "fps": None, "duracao_tipica_min": None},
    "pastas": {"padrao_projeto": "AAAA-MM-DD_Nome", "brutos": "Brutos", "assets": "Assets", "docs": "Docs",
               "renders": "Renders", "proxies": None},
    "transcricao": {"motor": "whisperx", "idioma": "pt", "modelo": "large-v3", "dispositivo": None, "termos": []},
    "notas_faladas": {"ativas": True, "abertura": "nota de edição", "fechamento": "fim da nota"},
    "cortes": {"usa_roteiro": False},
    "motion": {"ativo": True, "ferramenta": "hyperframes", "densidade": "media"},
    "camera": {"ativa": True, "seguir_rosto": True},
    "som": {"ativo": True, "biblioteca": None, "musica": "manual"},
    "perfil_padrao": "padrao",
}


class ErroConfig(Exception):
    pass


def pasta() -> Path:
    return Path(os.environ.get("EDICAO_HOME") or Path.home() / ".edicao").expanduser()


def arquivo() -> Path:
    return pasta() / "config.json"


def mesclar(base: dict, por_cima: dict) -> dict:
    """Mescla dicionários em profundidade; listas e valores simples são substituídos."""
    out = copy.deepcopy(base)
    for k, v in (por_cima or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = mesclar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# --------------------------------------------------------------- presets
def listar_presets() -> dict[str, dict]:
    out = {}
    for f in sorted(PRESETS.glob("*.json")):
        out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return out


def config_do_preset(nome_preset: str) -> dict:
    presets = listar_presets()
    if nome_preset not in presets:
        raise ErroConfig(f"preset '{nome_preset}' não existe; há: {', '.join(presets)}")
    p = presets[nome_preset]
    cfg = mesclar(PADRAO, p.get("config", {}))
    cfg["preset"] = nome_preset
    return cfg


# --------------------------------------------------------------- ler / gravar
def carregar(obrigatorio: bool = True) -> dict | None:
    arq = arquivo()
    if not arq.exists():
        if obrigatorio:
            raise ErroConfig(f"não existe {arq}: rode a montagem (/edicao:montar) primeiro")
        return None
    with open(arq, encoding="utf-8") as f:
        dados = json.load(f)
    # campos novos do motor entram com o padrão, sem gravar nada
    return mesclar(PADRAO, dados)


def gravar(cfg: dict) -> None:
    erros, _ = validar(cfg)
    if erros:
        raise ErroConfig("configuração inválida, nada foi gravado:\n- " + "\n- ".join(erros))
    arq = arquivo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    with _estado.trava(arq):
        _estado._gravar_atomico(arq, cfg)


def validar(cfg: dict) -> tuple[list[str], list[str]]:
    """(erros, avisos). Erros impedem gravar; avisos são incoerências a mostrar à pessoa."""
    erros: list[str] = []
    try:
        import jsonschema  # type: ignore
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for e in jsonschema.Draft202012Validator(schema).iter_errors(cfg):
            erros.append(f"{'.'.join(str(p) for p in e.path) or '(raiz)'}: {e.message}")
    except ImportError:
        for campo in ("schema", "nome", "fluxo", "revisao", "video"):
            if campo not in cfg:
                erros.append(f"falta o campo '{campo}'")
    if erros:
        return erros, []

    proprias = cfg.get("etapas_proprias") or {}
    for e in cfg["fluxo"]:
        if e not in ETAPAS and e not in proprias:
            erros.append(f"fluxo: etapa '{e}' não existe no motor nem em etapas_proprias")
    for e, caminho in proprias.items():
        if e in ETAPAS:
            erros.append(f"etapas_proprias: '{e}' já é uma etapa do motor; use ajustes/{e}.md para mudar o ofício dela")
        elif not (pasta() / caminho).exists() and not Path(caminho).exists():
            erros.append(f"etapas_proprias.{e}: arquivo {caminho} não encontrado")

    avisos: list[str] = []
    fl = cfg["fluxo"]
    ordem = list(ETAPAS)
    do_motor = [e for e in fl if e in ETAPAS]
    if do_motor != sorted(do_motor, key=ordem.index):
        avisos.append(f"as etapas do motor estão fora da ordem de referência ({' → '.join(do_motor)}): "
                      "confira que cada uma tem o que precisa da anterior")
    if "camera" in fl and "motion_render" in fl and fl.index("camera") < fl.index("motion_render"):
        avisos.append("a câmera vem antes das animações prontas: ela não vai poder casar com elas")
    sem_programa = cfg["revisao"]["programa"] == "nenhum"
    if sem_programa and "render" not in fl:
        avisos.append("sem programa de revisão e sem a etapa 'render': o vídeo pronto nunca é montado")
    if not sem_programa and "render" in fl:
        avisos.append("a etapa 'render' está no fluxo, mas a revisão é num programa: o acabamento costuma ser lá")
    if not cfg["motion"]["ativo"] and any(e in fl for e in ("motion_mapa", "motion_render", "assets")):
        avisos.append("motion desligado, mas há etapas de animação no fluxo")
    if cfg["motion"]["ativo"] and "motion_render" in fl and "motion_mapa" not in fl:
        avisos.append("motion-render sem motion-mapa: as animações não têm plano")
    if not cfg["camera"]["ativa"] and "camera" in fl:
        avisos.append("câmera desligada, mas a etapa 'camera' está no fluxo")
    if not cfg["som"]["ativo"] and "sfx" in fl:
        avisos.append("som desligado, mas a etapa 'sfx' está no fluxo")
    if "sfx" in fl and cfg["som"]["ativo"] and not cfg["som"].get("biblioteca"):
        avisos.append("a etapa de som não tem biblioteca de sons (som.biblioteca)")
    if cfg["revisao"]["programa"] == "finalcut":
        avisos.append("Final Cut lê FCPXML, que o motor ainda não gera: a primeira entrega escreve esse script")
    if not cfg.get("python"):
        avisos.append("python não definido: as skills vão usar o python do sistema")
    perfil = pasta() / "perfis" / cfg["perfil_padrao"]
    if not perfil.exists():
        avisos.append(f"o perfil padrão '{cfg['perfil_padrao']}' não existe em {perfil}")
    return erros, avisos


# --------------------------------------------------------------- montar a pasta
def criar(nome: str, preset: str, perfil: str = "padrao", python: str | None = None,
          extra: dict | None = None, estilo: str | None = None) -> dict:
    """Cria ~/.edicao com config, perfil inicial e pastas. Nunca sobrescreve."""
    if arquivo().exists():
        raise ErroConfig(f"{arquivo()} já existe: mude com 'config.py set' (nada foi sobrescrito)")
    cfg = config_do_preset(preset)
    cfg = mesclar(cfg, extra or {})
    cfg["nome"] = nome
    cfg["perfil_padrao"] = perfil
    cfg["python"] = python
    cfg["motor_versao_lida"] = versao_motor()
    base = pasta()
    for sub in ("perfis", "ajustes", "etapas", "scripts"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    if not (base / "perfis" / perfil).exists():
        novo_perfil(perfil, estilo=estilo)
    leia = base / "ajustes" / "LEIA-ME.md"
    if not leia.exists():
        leia.write_text(
            "# Ajustes pessoais de ofício\n\n"
            "Um arquivo por etapa (`cortes.md`, `camera.md`…) e `geral.md` para todas.\n"
            "As skills do motor leem o ajuste da etapa DEPOIS das próprias instruções: o que está aqui prevalece.\n"
            "Gosto (cores, quanto zoom, quanto som) vai no perfil; aqui fica o jeito de trabalhar que vale\n"
            "para todos os vídeos desta pessoa. As atualizações do motor nunca mexem nesta pasta.\n\n"
            "Formato de cada linha: `- <regra> (<origem: aprendizado de dd/mm, vídeo X>)`\n",
            encoding="utf-8")
    gi = base / ".gitignore"
    if not gi.exists():
        gi.write_text("venv/\n__pycache__/\n*.pyc\n", encoding="utf-8")
    gravar(cfg)
    return cfg


ESTILOS = MOTOR / "estilos"


def listar_estilos() -> list[str]:
    return sorted(d.name for d in ESTILOS.iterdir() if (d / "tema.json").exists()) if ESTILOS.exists() else []


def novo_perfil(nome: str, de: str | None = None, estilo: str | None = None) -> Path:
    """Perfil novo a partir do perfil inicial, de outro perfil da pessoa ou de um estilo da biblioteca."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", nome):
        raise ErroConfig("nome de perfil: só letras, números, ponto, hífen e sublinhado")
    destino = pasta() / "perfis" / nome
    if destino.exists():
        raise ErroConfig(f"o perfil {destino} já existe")
    if de and estilo:
        raise ErroConfig("use --de ou --estilo, não os dois")
    if estilo and estilo not in listar_estilos():
        raise ErroConfig(f"estilo '{estilo}' não existe; há: {', '.join(listar_estilos())}")
    origem = (pasta() / "perfis" / de) if de else (ESTILOS / estilo if estilo else PERFIL_INICIAL)
    if not origem.exists():
        raise ErroConfig(f"perfil de origem não encontrado: {origem}")
    shutil.copytree(origem, destino)
    return destino


# --------------------------------------------------------------- versões do motor
_RE_VERSAO = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", re.MULTILINE)


def versao_motor() -> str | None:
    pj = MOTOR / ".claude-plugin" / "plugin.json"
    if pj.exists():
        v = json.loads(pj.read_text(encoding="utf-8")).get("version")
        if v:
            return v
    if CHANGELOG.exists():
        m = _RE_VERSAO.search(CHANGELOG.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return None


def _tupla(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def novidades(desde: str | None) -> list[tuple[str, str]]:
    """Entradas do CHANGELOG mais novas que `desde` (a mais nova primeiro)."""
    if not CHANGELOG.exists():
        return []
    texto = CHANGELOG.read_text(encoding="utf-8")
    partes = list(_RE_VERSAO.finditer(texto))
    out = []
    for i, m in enumerate(partes):
        v = m.group(1)
        if desde and _tupla(v) <= _tupla(desde):
            break
        fim = partes[i + 1].start() if i + 1 < len(partes) else len(texto)
        out.append((v, texto[m.end():fim].strip()))
    return out


# --------------------------------------------------------------- resumo
def etapa_skill(etapa: str) -> str:
    """Nome da skill do motor para uma etapa (motion_mapa → motion-mapa)."""
    return etapa.replace("_", "-")


def resumo(cfg: dict) -> list[str]:
    r = cfg["revisao"]
    linhas = [
        f"{cfg['nome']} · preset {cfg.get('preset') or '—'} · perfil padrão {cfg['perfil_padrao']}",
        f"vídeo: {cfg['video']['tipo']}, {cfg['video']['formato']}"
        + (f", {cfg['video']['fps']} fps" if cfg['video'].get('fps') else ", fps do material"),
        f"revisão: {r['programa']}" + (f" (no programa: {', '.join(r.get('etapas_no_programa') or [])})"
                                       if r['programa'] != 'nenhum' else " (vídeo pronto, ajustes pelo chat)"),
        "fluxo: " + " → ".join(cfg["fluxo"]),
        f"transcrição: {cfg['transcricao']['motor']} ({cfg['transcricao']['idioma']})"
        + (f", termos: {', '.join(cfg['transcricao']['termos'][:6])}" if cfg['transcricao']['termos'] else ""),
        "notas faladas: " + (f"\"{cfg['notas_faladas']['abertura']}\" … \"{cfg['notas_faladas']['fechamento']}\""
                             if cfg['notas_faladas']['ativas'] else "não"),
        f"motion: {cfg['motion']['ferramenta'] + ', ' + cfg['motion']['densidade'] if cfg['motion']['ativo'] else 'não'}"
        f" · câmera: {('sim' + (', segue o rosto' if cfg['camera']['seguir_rosto'] else '')) if cfg['camera']['ativa'] else 'não'}"
        f" · som: {('sim, biblioteca ' + (cfg['som']['biblioteca'] or 'não definida')) if cfg['som']['ativo'] else 'não'}",
        f"python: {cfg.get('python') or 'o do sistema'}",
    ]
    return linhas
