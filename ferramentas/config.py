#!/usr/bin/env python3
"""A configuração da pessoa (~/.edicao, ou EDICAO_HOME): as escolhas que o motor lê.

Uso:
  config.py presets                          os pontos de partida, com o que cada um faz
  config.py criar --nome N --preset P [--perfil padrao] [--python caminho] [--json '{"video":{…}}']
                                             cria ~/.edicao (config, perfil inicial, pastas); nunca sobrescreve
  config.py mostrar [--json]                 resumo das escolhas + avisos de incoerência
  config.py set <caminho> <valor>            muda um campo (valor em JSON ou texto); valida antes de gravar
  config.py validar
  config.py perfil-novo <nome> [--de <perfil existente>]
  config.py novidades [--marcar-lido]        o que mudou no motor desde a última vez
  config.py caminho                          onde fica a pasta da pessoa
  config.py motor                            onde fica o motor (para os comandos das skills)
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import config as C  # noqa: E402
from edicao import estado as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("presets")
    p = sub.add_parser("criar")
    p.add_argument("--nome", required=True); p.add_argument("--preset", required=True)
    p.add_argument("--perfil", default="padrao"); p.add_argument("--python")
    p.add_argument("--json", help="campos para mudar sobre o preset, em JSON")
    p = sub.add_parser("mostrar"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("set"); p.add_argument("caminho"); p.add_argument("valor")
    sub.add_parser("validar")
    p = sub.add_parser("perfil-novo"); p.add_argument("nome"); p.add_argument("--de")
    p = sub.add_parser("novidades"); p.add_argument("--marcar-lido", action="store_true")
    sub.add_parser("caminho")
    sub.add_parser("motor")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        if a.cmd == "caminho":
            print(C.pasta())
        elif a.cmd == "motor":
            print(C.MOTOR)
        elif a.cmd == "presets":
            for nome, p in C.listar_presets().items():
                cfg = C.config_do_preset(nome)
                print(f"{nome}: {p.get('titulo', '')}")
                print(f"  {p.get('descricao', '')}")
                print(f"  fluxo: {' → '.join(cfg['fluxo'])} · revisão: {cfg['revisao']['programa']}"
                      f" · {cfg['video']['formato']}")
        elif a.cmd == "criar":
            extra = json.loads(a.json) if a.json else None
            cfg = C.criar(a.nome, a.preset, a.perfil, a.python, extra)
            print(f"criado {C.arquivo()}")
            print("\n".join(C.resumo(cfg)))
            _, avisos = C.validar(cfg)
            for av in avisos:
                print(f"! {av}")
        elif a.cmd == "mostrar":
            cfg = C.carregar()
            if a.json:
                print(json.dumps(cfg, ensure_ascii=False, indent=2))
                return 0
            print("\n".join(C.resumo(cfg)))
            erros, avisos = C.validar(cfg)
            for e in erros:
                print(f"erro: {e}")
            for av in avisos:
                print(f"! {av}")
            nov = C.novidades(cfg.get("motor_versao_lida"))
            if nov:
                print(f"novidades no motor: {', '.join(v for v, _ in nov)} (config.py novidades)")
        elif a.cmd == "set":
            cfg = C.carregar()
            E.definir(cfg, a.caminho, E.interpretar_valor(a.valor))
            C.gravar(cfg)
            print(f"{a.caminho} = {json.dumps(E.obter(cfg, a.caminho), ensure_ascii=False)}")
            for av in C.validar(cfg)[1]:
                print(f"! {av}")
        elif a.cmd == "validar":
            erros, avisos = C.validar(C.carregar())
            for e in erros:
                print(f"erro: {e}")
            for av in avisos:
                print(f"! {av}")
            if erros:
                return 1
            print("configuração válida" + (f" ({len(avisos)} avisos)" if avisos else ""))
        elif a.cmd == "perfil-novo":
            print(f"perfil criado em {C.novo_perfil(a.nome, a.de)}")
        elif a.cmd == "novidades":
            cfg = C.carregar()
            nov = C.novidades(cfg.get("motor_versao_lida"))
            if not nov:
                print(f"nada novo (motor {C.versao_motor()})")
            for v, texto in nov:
                print(f"## {v}\n{texto}\n")
            if a.marcar_lido and C.versao_motor():
                cfg["motor_versao_lida"] = C.versao_motor()
                C.gravar(cfg)
                print(f"marcado como lido até {C.versao_motor()}")
    except (C.ErroConfig, E.ErroEstado, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
