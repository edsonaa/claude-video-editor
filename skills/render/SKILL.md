---
name: render
description: "Monta e exporta o vídeo pronto pelo FFmpeg, para quem não revisa num programa de edição: cortes, câmera, animações por cima, efeitos sonoros nos níveis certos e a loudness da plataforma, com conferência final. Também gera os rascunhos em resolução baixa que as outras etapas usam para revisão. Use em /edicao:render, ou quando a pessoa pedir o vídeo final."
---

# render

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** todos os blocos do estado (cortes, motions com os renders, camera, sfx), a configuração (`video.formato`, `video.fps`, `pastas.renders`), `<pessoa>/ajustes/render.md` e `geral.md`.
- **Escreve:** `<pastas.renders>/<projeto>_final_vNN.mp4` (e rascunhos em `_CLAUDE/rascunhos/`), sempre em versão nova; a entrega no estado.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/entrega-no-editor.md`, caminho C.

## O script
O render ainda não vem pronto no motor. Na primeira vez, escreva `<pessoa>/scripts/render.py` (regras comuns, §3), sobre `edicao.linha`, `edicao.tempo` e `edicao.ff`:
- cortes da câmera pelos segmentos (tempos em frames por `edicao.tempo`, a mesma conversão da entrega em XML);
- câmera: escala e posição por movimento, com a curva do plano;
- animações por cima: tela cheia (MP4) e sobreposição com transparência (MOV), cada uma no seu tempo;
- áudio: a voz com fades de 1 frame nas junções, os efeitos com o ganho de cada item, e a loudness final da plataforma (ex.: −14 LUFS integrados para YouTube; confirme o alvo atual da plataforma dela);
- `--rascunho`: resolução baixa e preset rápido, para revisão; o final sai na resolução e na taxa do material;
- `--ate <tempo>` para renderizar só um trecho.
Teste num trecho de 10–20 s antes do vídeo inteiro. Ficou bom e serve para qualquer pessoa: sugira propô-lo ao motor.

## Passo a passo
1. `<py> <f>/estado.py . status`: as etapas anteriores aprovadas (ou a pessoa pediu um rascunho).
2. Render em segundo plano. Cada ajuste é um render novo: agrupe vários pedidos antes.
3. **Conferir** antes de entregar: duração igual à da sequência (`edicao.linha.Linha(...).duracao`), resolução e fps (`<py> <f>/midia.py <arquivo>`), loudness (FFmpeg `ebur128`), quadros pretos (`blackdetect`), uma folha de contato dos pontos de animação (`<py> <f>/contato.py`).
4. Registre a entrega (`--set` em `entregas`, ou o script grava), resumo curto com o caminho. `--etapa render=aguardando_aprovacao`.

## Revisão e aprovação
A pessoa assiste e pede pelo chat, citando o tempo do vídeo ("em 01:12 tira essa frase") ou o número do item. Converta o tempo do vídeo para o de origem pela lista de cortes (`Linha.seq_para_origem`) e mande o pedido para a etapa certa (um corte volta para `cortes`, um som para `sfx`). Aprovado: `--etapa render=concluido`, aprendizados, e o vídeo está pronto.
