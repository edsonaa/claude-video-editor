#!/usr/bin/env python3
"""Lê e muda o estado do vídeo sem abrir o arquivo inteiro.

Uso (sempre com a pasta do vídeo primeiro):
  estado.py <pasta> status                      onde o vídeo está
  estado.py <pasta> <bloco> [--json]            resumo de um bloco (cortes, motions, marcadores, pendencias, midia…)
  estado.py <pasta> --item <id>                 um item inteiro (s003, mo04, cam07, p02…)
  estado.py <pasta> --set <caminho> <valor>     muda um campo (valor em JSON ou texto)
  estado.py <pasta> --etapa <etapa>=<status>    muda o status de uma etapa
  estado.py <pasta> --pendencia <etapa> "<texto>" [--de <id>]
  estado.py <pasta> --resolver <id>
  estado.py <pasta> --gravar <bloco> <arquivo.json|->   grava um bloco inteiro (scripts de etapa)
  estado.py <pasta> --validar
  estado.py <pasta> --init <nome> [--perfil P] [--fluxo iniciar,preparar,…]

Status de etapa: pendente, em_andamento, aguardando_aprovacao, aguardando_<quem>, concluido, nao_precisa.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import estado as E  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="estado.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", help="pasta do vídeo (ou o próprio projeto.json)")
    ap.add_argument("bloco", nargs="?", help="'status' ou o nome de um bloco")
    ap.add_argument("--json", action="store_true", help="o bloco completo, em JSON")
    ap.add_argument("--item")
    ap.add_argument("--set", nargs=2, metavar=("CAMINHO", "VALOR"))
    ap.add_argument("--etapa", metavar="ETAPA=STATUS")
    ap.add_argument("--pendencia", nargs=2, metavar=("ETAPA", "TEXTO"))
    ap.add_argument("--de", help="id do item a que a pendência se refere")
    ap.add_argument("--resolver", metavar="ID")
    ap.add_argument("--gravar", nargs=2, metavar=("BLOCO", "ARQUIVO"))
    ap.add_argument("--validar", action="store_true")
    ap.add_argument("--init", metavar="NOME")
    ap.add_argument("--perfil")
    ap.add_argument("--fluxo", help="etapas separadas por vírgula")
    a = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        if a.init:
            # Sem --fluxo/--perfil, vale a configuração da pessoa (~/.edicao/config.json).
            from edicao import config as C
            cfg = C.carregar(obrigatorio=False) or {}
            if a.fluxo:
                fluxo = [x for x in a.fluxo.split(",") if x.strip()]
            else:
                fluxo = cfg.get("fluxo")
            perfil = a.perfil or cfg.get("perfil_padrao")
            d = E.criar(a.pasta, a.init, perfil, fluxo)
            print(f"estado criado: {E.caminho_estado(a.pasta)}")
            print("\n".join(E.resumo_status(d)))
            return 0

        if a.validar:
            erros = E.validar(E.ler(a.pasta))
            if erros:
                print("estado inválido:")
                print("\n".join(f"- {e}" for e in erros))
                return 1
            print("estado válido")
            return 0

        if a.item:
            achado = E.achar_item(E.ler(a.pasta), a.item)
            if not achado:
                print(f"item {a.item} não encontrado", file=sys.stderr)
                return 1
            lista, _, item = achado
            print(f"# {lista}")
            print(json.dumps(item, ensure_ascii=False, indent=2))
            return 0

        mudou = []
        if a.set or a.etapa or a.pendencia or a.resolver or a.gravar:
            with E.editar(a.pasta) as d:
                if a.set:
                    caminho, valor = a.set
                    E.definir(d, caminho, E.interpretar_valor(valor))
                    mudou.append(f"{caminho} = {valor}")
                if a.etapa:
                    if "=" not in a.etapa:
                        raise E.ErroEstado("use --etapa <etapa>=<status>")
                    etapa, status = a.etapa.split("=", 1)
                    E.mudar_etapa(d, etapa, status.strip())
                    mudou.append(f"etapa {E.nome_etapa(etapa)} → {status.strip()}")
                if a.pendencia:
                    pid = E.nova_pendencia(d, a.pendencia[0], a.pendencia[1], a.de)
                    mudou.append(f"pendência {pid} anotada")
                if a.resolver:
                    E.resolver_pendencia(d, a.resolver)
                    mudou.append(f"pendência {a.resolver} resolvida")
                if a.gravar:
                    bloco, origem = a.gravar
                    texto = sys.stdin.read() if origem == "-" else Path(origem).read_text(encoding="utf-8")
                    E.definir(d, bloco, json.loads(texto))
                    mudou.append(f"bloco {bloco} gravado")
            d = E.ler(a.pasta)
            print("; ".join(mudou) + f" (revisão {d['revisao']})")
            if a.gravar and a.gravar[0] in ("cortes", "motions"):
                print(f"{a.gravar[0]} agora na versão {d[a.gravar[0]].get('versao')}")
            for al in E.alertas(d):
                print(f"! {al}")
            return 0

        d = E.ler(a.pasta)
        bloco = a.bloco or "status"
        if bloco == "status":
            print("\n".join(E.resumo_status(d)))
            n = E.contar_aprendizados(a.pasta)
            if n:
                print(f"aprendizados anotados e não aplicados: {n}")
            return 0
        if a.json:
            valor = E.obter(d, bloco)
            if valor is None:
                raise E.ErroEstado(f"o bloco '{bloco}' não existe neste estado")
            print(json.dumps(valor, ensure_ascii=False, indent=2))
        else:
            print("\n".join(E.resumo_bloco(d, bloco)))
        return 0
    except E.ErroEstado as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
