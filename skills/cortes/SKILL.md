---
name: cortes
description: "Faz o primeiro corte limpo de um vídeo: escolhe os takes, tira erros, falsas largadas, notas faladas e pausas, marca as dúvidas na linha do tempo e entrega no programa de edição (ou como rascunho). Também lê os ajustes que a pessoa fez no programa. Use em /edicao:cortes, depois do preparar."
---

# cortes

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

Sem zoom, animação ou efeito. Não é o corte final: é a base que a pessoa refina.

- **Lê:** `_CLAUDE/frases_<id>.txt` (é isso que você lê; o arquivo por palavra só por script, num trecho), `notas_edicao` e `transcricao.lacunas` do estado, o briefing, o roteiro (se `cortes.usa_roteiro`), o perfil (`estilo-cortes.md`: ar, folga, hesitações, como a pessoa grava), `<pessoa>/ajustes/cortes.md` e `geral.md`.
- **Escreve:** `cortes` e `marcadores` no estado; a entrega.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-cortes.md`. Leia antes de decidir.

## Passo a passo
1. `<py> <f>/estado.py . status` e as pendências desta etapa.
2. **Decida por frase**, com o ofício do guia: takes, ordem de escolha (nota de edição → último take completo → anterior limpo), lacunas antes de descartar uma frase, pausas pelo perfil, hesitação só isolada e longa, notas faladas saem inteiras. Na dúvida, não corta e marca.
3. **Bordas:** dê início e fim pelas palavras de borda (tempo de origem, em segundos), com a folga do perfil. O ajuste fino pela energia do áudio ainda não vem pronto: na primeira vez, escreva `<pessoa>/scripts/bordas.py` como o guia descreve (energia, folga, muleta colada vira marcador, arredondar por `edicao.tempo`) e use-o daí em diante. **Nunca** rode o ajuste sobre cortes que voltaram do programa.
4. **Grave:** um JSON `{"segmentos": [{"id": "s001", "video": "cam01", "inicio": 3.10, "fim": 15.62, "texto": "começo da frase"}, …]}` com `estado.py . --gravar cortes <arquivo>` (ao regravar, leve junto o `quadro` e a `transicao` de cada segmento que continua: são escolhas da pessoa no painel), e os marcadores (`m001`…; tipos `duvida_take`, `hesitacao`, `nota`, `sugestao`, `alerta`) com `--gravar marcadores <arquivo>`. A versão do corte sobe sozinha.
5. **Entrega** conforme as regras comuns, §4 (`exportar_xml.py exportar . --etapa cortes`; primeira vez de todas: `--teste`).
6. **Resumo** curto: duração do bruto → duração do corte, quantos marcadores de cada tipo, o que for realmente importante, o caminho do arquivo. `--etapa cortes=aguardando_aprovacao`.

## Revisão
- Pelo chat: tempo da sequência ou id (`s014`); converta pela lista de cortes. Ajuste, grave, entregue versão nova.
- Pelo programa: a pessoa exporta a sequência para `_CLAUDE/`; `<py> <f>/exportar_xml.py volta . <arquivo>` mostra a diferença e os avisos (L-cut, velocidade, clipes desconhecidos); com o "sim", `--aplicar`. Os marcadores dela viram instrução. Os ajustes dela valem mais; se contradizem algo que você afirmou, reconheça.
- Anote os aprendizados (regras comuns, §5).

## Aprovação
`--etapa cortes=concluido`. **O corte trava:** se mudar depois do plano de animação ou da câmera, o status vai avisar, e essas etapas precisam ser revistas. Sugira `/clear` e `/edicao:editar`.
