---
name: preparar
description: "Transforma os brutos de um vídeo em algo que o Claude lê: inventário da mídia, sincronia de tela e áudio externo, transcrição com tempo por palavra, silêncios, takes que a transcrição engoliu e as notas de edição faladas na gravação. Use em /edicao:preparar, depois do iniciar."
---

# preparar

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** os brutos, `_CLAUDE/briefing.md` (termos), a configuração (`transcricao`, `notas_faladas`, `pastas`), `<pessoa>/ajustes/preparar.md` e `geral.md`.
- **Escreve:** blocos `midia`, `transcricao` e `notas_edicao` no estado; em `_CLAUDE/`: `palavras_<id>.json`, `silencios_<id>.json`, `frases_<id>.txt`.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-iniciar-preparar.md`, parte "Preparar". Leia antes.

## Passo a passo
1. **Inventário no estado:** `<py> <f>/midia.py <brutos> --estado .`. Confira com a pessoa o `tipo` de cada arquivo (camera, tela, audio) e qual é a câmera principal (`estado.py . --set midia.arquivos.<n>.tipo tela`, `--set midia.principal cam01`). Mostre os alertas (VFR, fps diferente, sem áudio). Proxies: anote o caminho em `midia.arquivos.<n>.proxy`.
2. **Sincronia** (só se houver tela ou áudio externo): o motor ainda não traz o script; na primeira vez escreva `<pessoa>/scripts/sync.py` (correlação cruzada, áudio da câmera como referência, `edicao.ff.ler_audio`), como o guia descreve. Grave em `midia.sync` com offset e confiança. Confiança baixa: avise e peça ajuda, não chute.
3. **Silêncios** de cada arquivo com fala: `<py> <f>/silencios.py <arquivo> --saida _CLAUDE/silencios_<id>.json`.
4. **Transcrição** do áudio principal de cada câmera:
   `<py> <f>/transcrever.py rodar <arquivo> _CLAUDE/palavras_<id>.json --motor <transcricao.motor> --idioma <transcricao.idioma> --termos "<termos do config + do briefing>"` (com `--offset` se o áudio veio de outro arquivo; `--modelo` do config). Com GPU, confirme antes que o PyTorch enxerga a placa (cair para CPU sem avisar fica muito lento).
5. **Takes engolidos:** `<py> <f>/transcrever.py lacunas _CLAUDE/palavras_<id>.json _CLAUDE/silencios_<id>.json`. Para cada trecho: extraia com o FFmpeg, transcreva **sem** `--termos` e com `--offset <início do trecho>`, e junte as palavras novas no `palavras_<id>.json` em ordem de início. Grave os que continuarem sem palavra em `transcricao.lacunas` (a `cortes` procura takes ali).
6. **Frases para ler:** `<py> <f>/transcrever.py frases _CLAUDE/palavras_<id>.json --silencios _CLAUDE/silencios_<id>.json --video <id> --saida _CLAUDE/frases_<id>.txt`. Confira a grafia dos termos pelo roteiro, se houver, sem trocar o que foi falado.
7. **Notas faladas** (se `notas_faladas.ativas`): `<py> <f>/transcrever.py notas _CLAUDE/palavras_<id>.json --abertura "<abertura>" --fechamento "<fechamento>" --json`. Para cada uma, escreva uma interpretação curta e a etapa a que se refere, e grave em `notas_edicao` (ids `n01`…). Confiança baixa vira pergunta para a pessoa.
8. **Estado:** `--set transcricao '{"motor": …, "palavras": {"cam01": "_CLAUDE/palavras_cam01.json"}, "frases": {…}, "silencios": {…}, "lacunas": […]}'`.
9. **Resumo** curto: arquivos, duração total, alertas, lacunas, notas encontradas. Não há o que revisar no programa: com a pessoa de acordo, `--etapa preparar=concluido`, sugerir `/clear` e `/edicao:editar`.
