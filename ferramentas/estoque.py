#!/usr/bin/env python3
"""O seu estoque de peças: estilos de legenda, transições, efeitos e motions seus, fora do motor.

Uso:
  estoque.py novo --tipo legenda|transicao|efeito|motion --nome "…" --gostei "o que gostou"
                  [--arquivo trecho.mp4 [--de S] [--ate S]] [--parecido <id>]
      põe uma peça na entrada (com o trecho de referência, até 90 s) para o Claude analisar
  estoque.py listar [--tipo T] [--status entrada|rascunho|ativo|recusado|arquivado] [--json]
  estoque.py mostrar <id>                     a ficha, o item e os dados da peça
  estoque.py folha <id> [--cada 2]            folha de contato do trecho (folha.png na pasta da peça)
  estoque.py construir <id> [--base <id>]     tira da entrada e abre o rascunho, partindo de uma peça parecida
  estoque.py analise <id> "texto"             grava a análise na ficha (o que mediu e como construiu)
  estoque.py previa <id> [--perfil <pasta do perfil>]
                                              PNG (legenda) ou GIF (transição, efeito, motion) na pasta da peça
  estoque.py verificar <id>                   o que falta para a peça entrar no estoque
  estoque.py aprovar <id>                     rascunho → ativo (aparece na galeria, nas boas-vindas e no plano)
  estoque.py ajuste <id> "texto"              anota um ajuste pedido (a peça volta a rascunho)
  estoque.py recusar <id> [--motivo "…"]      |  estoque.py arquivar <id>

O estoque fica em <pessoa>/estoque/ (EDICAO_HOME, padrão ~/.edicao): sobrevive às atualizações do plugin.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import estoque as ES  # noqa: E402

ROTULO = {"entrada": "esperando análise", "rascunho": "para aprovar", "ativo": "no estoque",
          "recusado": "recusado", "arquivado": "arquivado"}


def _linha(it: dict) -> str:
    aj = [a for a in it.get("ajustes") or [] if not a.get("feito")]
    extra = f"  · ajuste pedido: {aj[-1]['texto']}" if aj and it["status"] == "rascunho" else ""
    return f"  {it['id']:<26} {ES.NOME_TIPO[it['tipo']]:<18} {it['nome']} — {it.get('gostei', '')[:70]}{extra}"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("novo")
    p.add_argument("--tipo", required=True, choices=list(ES.TIPOS)); p.add_argument("--nome", required=True)
    p.add_argument("--gostei", required=True); p.add_argument("--arquivo"); p.add_argument("--de", type=float)
    p.add_argument("--ate", type=float); p.add_argument("--parecido")
    p = sub.add_parser("listar"); p.add_argument("--tipo", choices=list(ES.TIPOS)); p.add_argument("--status", choices=ES.STATUS)
    p.add_argument("--json", action="store_true")
    for nome in ("mostrar", "verificar", "aprovar", "arquivar"):
        sub.add_parser(nome).add_argument("id")
    p = sub.add_parser("folha"); p.add_argument("id"); p.add_argument("--cada", type=int, default=2)
    p = sub.add_parser("construir"); p.add_argument("id"); p.add_argument("--base")
    p = sub.add_parser("analise"); p.add_argument("id"); p.add_argument("texto")
    p = sub.add_parser("previa"); p.add_argument("id"); p.add_argument("--perfil")
    p = sub.add_parser("ajuste"); p.add_argument("id"); p.add_argument("texto")
    p = sub.add_parser("recusar"); p.add_argument("id"); p.add_argument("--motivo")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "novo":
            it = ES.nova_entrada(a.tipo, a.nome, a.gostei, a.arquivo, a.de, a.ate, a.parecido, por="claude")
            print(f"{it['id']} na entrada do estoque ({ES.NOME_TIPO[it['tipo']]}): {it['pasta']}")
        elif a.cmd == "listar":
            st = (a.status,) if a.status else None
            lista = [i for i in ES.itens(a.tipo, st) if a.status or i["status"] not in ("recusado",)]
            if a.json:
                print(json.dumps(lista, ensure_ascii=False, indent=2))
                return 0
            if not lista:
                print("o estoque está vazio" if not (a.tipo or a.status) else "nada com esse filtro")
            for status in ES.STATUS:
                grupo = [i for i in lista if i["status"] == status]
                if grupo:
                    print(f"{ROTULO[status]} ({len(grupo)}):")
                    print("\n".join(_linha(i) for i in grupo))
        elif a.cmd == "mostrar":
            it = ES.item(a.id)
            print((Path(it["pasta"]) / "ficha.md").read_text(encoding="utf-8"))
            print(f"pasta: {it['pasta']}")
            dd = ES.dados(it)
            if dd is not None:
                print(f"{ES.DADOS[it['tipo']]}:\n{json.dumps(dd, ensure_ascii=False, indent=2)}")
        elif a.cmd == "folha":
            from edicao import contato
            it = ES.item(a.id)
            trecho = Path(it["pasta"]) / (it.get("trecho") or "")
            if not it.get("trecho") or trecho.suffix != ".mp4":
                print(f"{a.id} não tem trecho de vídeo", file=sys.stderr)
                return 2
            r = contato.folha(trecho, Path(it["pasta"]) / "folha.png", 0.0, None, a.cada, 6, 320, 72)
            print(json.dumps(r, ensure_ascii=False))
        elif a.cmd == "construir":
            it = ES.construir(a.id, a.base)
            base = f"a partir de {it['base']}" if it.get("base") else "a partir do modelo padrão"
            print(f"{a.id}: rascunho em {it['pasta']} ({base}). "
                  f"Edite {ES.DADOS[it['tipo']]}" + (" e index.html" if it["tipo"] in ("efeito", "motion") else "")
                  + f", depois: estoque.py previa {a.id}")
        elif a.cmd == "analise":
            ES.anotar_analise(a.id, a.texto)
            print(f"análise gravada na ficha de {a.id}")
        elif a.cmd == "previa":
            tema = None
            if a.perfil:
                from edicao import efeitos as EF
                tema = EF.tema_de(perfil_dir=a.perfil)
            print(ES.previa(a.id, tema))
        elif a.cmd == "verificar":
            erros = ES.verificar(a.id)
            print("pronta para aprovar" if not erros else "\n".join(f"  ! {e}" for e in erros))
            return 0 if not erros else 1
        elif a.cmd == "aprovar":
            it = ES.aprovar(a.id)
            print(f"{a.id} entrou no estoque ({ES.NOME_TIPO[it['tipo']]}): já aparece na galeria e no plano")
        elif a.cmd == "ajuste":
            ES.pedir_ajuste(a.id, a.texto)
            print(f"ajuste anotado em {a.id}")
        elif a.cmd == "recusar":
            ES.mudar_status(a.id, "recusado", a.motivo)
            print(f"{a.id} recusado")
        elif a.cmd == "arquivar":
            ES.mudar_status(a.id, "arquivado")
            print(f"{a.id} arquivado (sai da galeria; volta com estoque.py aprovar)")
    except (ES.ErroEstoque, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
