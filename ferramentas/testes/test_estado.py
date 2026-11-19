import json
import os
import stat
import threading

import pytest

from edicao import estado as E


@pytest.fixture
def pasta(tmp_path):
    E.criar(tmp_path, "2026-01-15_Teste", "padrao")
    return tmp_path


def test_criar_e_nao_sobrescrever(pasta):
    d = E.ler(pasta)
    assert d["revisao"] == 1 and d["fluxo"] == E.FLUXO_PADRAO
    assert all(v == "pendente" for v in d["etapas"].values())
    assert E.validar(d) == []
    with pytest.raises(E.ErroEstado, match="já existe"):
        E.criar(pasta, "outro")


def test_fluxo_personalizado(tmp_path):
    d = E.criar(tmp_path, "reels", fluxo=["iniciar", "cortes", "motion-render", "render"])
    assert d["fluxo"] == ["iniciar", "cortes", "motion_render", "render"]


def test_revisao_sobe_e_conflito(pasta):
    d1 = E.ler(pasta)
    d2 = E.ler(pasta)
    d1["perfil"] = "a"
    E.gravar(pasta, d1, revisao_lida=d1["revisao"])
    d2["perfil"] = "b"
    with pytest.raises(E.Conflito):
        E.gravar(pasta, d2, revisao_lida=d2["revisao"])
    assert E.ler(pasta)["perfil"] == "a"


def test_estado_invalido_nao_grava(pasta):
    with pytest.raises(E.ErroEstado, match="inválido"):
        with E.editar(pasta) as d:
            d["cortes"] = {"segmentos": [{"id": "s001", "video": "cam01", "inicio": 5, "fim": 2}]}
    assert "cortes" not in E.ler(pasta)


def test_ids_repetidos_invalidos(pasta):
    d = E.ler(pasta)
    d["marcadores"] = [{"id": "m001", "video": "c", "tempo": 1, "tipo": "nota", "texto": "a"},
                       {"id": "m001", "video": "c", "tempo": 2, "tipo": "nota", "texto": "b"}]
    assert any("repetido" in e for e in E.validar(d))


def test_versao_do_corte_e_alertas(pasta):
    with E.editar(pasta) as d:
        d["cortes"] = {"segmentos": [{"id": "s001", "video": "cam01", "inicio": 1, "fim": 4}]}
    assert E.ler(pasta)["cortes"]["versao"] == 1
    with E.editar(pasta) as d:
        for e in ("iniciar", "preparar", "cortes"):
            E.mudar_etapa(d, e, "concluido")
        d["motions"] = {"itens": [{"id": "mo01", "status": "proposto", "inicio_seq": 0.5, "fim_seq": 2}]}
        E.mudar_etapa(d, "motion-mapa", "aguardando_aprovacao")
    d = E.ler(pasta)
    assert d["motions"]["base_cortes_versao"] == 1 and E.alertas(d) == []
    # mudar só o status de uma animação não é mudar o plano
    with E.editar(pasta) as d:
        d["motions"]["itens"][0]["status"] = "aprovado"
    assert E.ler(pasta)["motions"]["versao"] == 1
    # o corte muda depois do plano → alerta
    with E.editar(pasta) as d:
        d["cortes"]["segmentos"][0]["fim"] = 3.5
    d = E.ler(pasta)
    assert d["cortes"]["versao"] == 2
    assert any("corte mudou (v1 → v2)" in a for a in E.alertas(d))


def test_alerta_fora_de_ordem(pasta):
    with E.editar(pasta) as d:
        E.mudar_etapa(d, "cortes", "concluido")
    assert any("cortes" in a and "iniciar" in a for a in E.alertas(E.ler(pasta)))


def test_etapa_fora_do_fluxo(pasta):
    with pytest.raises(E.ErroEstado, match="não está no fluxo"):
        with E.editar(pasta) as d:
            E.mudar_etapa(d, "render", "concluido")


def test_pendencias(pasta):
    with E.editar(pasta) as d:
        a = E.nova_pendencia(d, "motion-render", "mo05 mais lento", "mo05")
        b = E.nova_pendencia(d, "sfx", "menos whoosh")
    assert (a, b) == ("p01", "p02")
    with E.editar(pasta) as d:
        E.resolver_pendencia(d, "p01")
    d = E.ler(pasta)
    assert [p["id"] for p in E.pendencias_abertas(d)] == ["p02"]
    assert d["pendencias"][0]["resolvida_em"]  # histórico fica
    with pytest.raises(E.ErroEstado):
        with E.editar(pasta) as d:
            E.resolver_pendencia(d, "p01")


def test_achar_item_e_caminhos(pasta):
    with E.editar(pasta) as d:
        E.definir(d, "motions.itens", [{"id": "mo04", "status": "proposto"}])
        E.definir(d, "ferramentas.hyperframes", "0.4.2")
    d = E.ler(pasta)
    lista, idx, item = E.achar_item(d, "mo04")
    assert lista == "motions.itens" and idx == 0 and item["status"] == "proposto"
    assert E.obter(d, "motions.itens.0.id") == "mo04"
    assert E.obter(d, "nao.existe", "x") == "x"
    assert E.interpretar_valor("3") == 3 and E.interpretar_valor("texto livre") == "texto livre"


def test_proximo_id():
    assert E.proximo_id([], "p") == "p01"
    assert E.proximo_id([{"id": "s009"}, {"id": "s010"}], "s") == "s011"
    assert E.proximo_id([{"id": "mo99"}], "mo") == "mo100"


def test_permissoes_normais(pasta):
    if os.name == "nt":
        pytest.skip("permissões Unix")
    modo = stat.S_IMODE(E.caminho_estado(pasta).stat().st_mode)
    assert modo & 0o044  # legível pelo grupo/outros, não 0600


def test_gravacoes_concorrentes_nao_corrompem(pasta):
    erros = []

    def trabalho(n):
        for _ in range(10):
            while True:
                try:
                    with E.editar(pasta) as d:
                        E.nova_pendencia(d, "cortes", f"t{n}")
                    break
                except E.Conflito:
                    continue
                except Exception as e:  # pragma: no cover
                    erros.append(e)
                    return

    ts = [threading.Thread(target=trabalho, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not erros
    d = E.ler(pasta)
    assert len(d["pendencias"]) == 40
    assert len({p["id"] for p in d["pendencias"]}) == 40
    json.loads(E.caminho_estado(pasta).read_text(encoding="utf-8"))


def test_resumos(pasta):
    with E.editar(pasta) as d:
        d["cortes"] = {"segmentos": [{"id": "s001", "video": "cam01", "inicio": 1, "fim": 4, "texto": "olá"}]}
        E.nova_pendencia(d, "cortes", "apertar o começo")
    d = E.ler(pasta)
    st = "\n".join(E.resumo_status(d))
    assert "próxima etapa: iniciar" in st and "p01" in st
    assert "s001" in "\n".join(E.resumo_bloco(d, "cortes"))
    with pytest.raises(E.ErroEstado):
        E.resumo_bloco(d, "nao_existe")


def test_aprendizados(pasta):
    (E.caminho_estado(pasta).parent / "aprendizados.md").write_text(
        "- [ ] cortes · menos ar · 12/03\n- [x] sfx · ok → perfil\n- [ ] camera · zoom sutil · 12/03\n", encoding="utf-8")
    assert E.contar_aprendizados(pasta) == 2
