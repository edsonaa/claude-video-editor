---
name: camera
description: "Desenha os movimentos de câmera do vídeo depois das animações prontas: alternância de planos nos cortes, aproximação lenta, punch nas ênfases, rosto no terço com sobreposição lateral, chegada na direção da saída de cada animação, trava no rosto. Entrega como keyframes no programa (ou aplicado no render). Use em /edicao:camera, depois das animações aprovadas."
---

# camera

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

Não renderiza vídeo: decide os movimentos e entrega como keyframes.

- **Lê:** cortes, plano e renders das animações (com a direção da saída e a intenção de câmera de cada item), a trilha do rosto, o perfil (`estilo-camera.md`), a configuração (`camera.seguir_rosto`, `video.formato`, `revisao.programa`), `<pessoa>/ajustes/camera.md` e `geral.md`.
- **Escreve:** o bloco `camera` (`movimentos` numerados `cam01`…, `recortes` feitos por trecho), os eventos de câmera para o som, a entrega.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-camera.md` e as curvas de `${CLAUDE_PLUGIN_ROOT}/guias/oficio-motion.md` (§2–§4), para a câmera conversar com as animações. Leia antes.

## Passo a passo
1. `<py> <f>/estado.py . status`: cortes e animações aprovados, sem alerta de desatualizado.
2. **O rosto** (se `camera.seguir_rosto`): para cada câmera usada nos cortes, `<py> <f>/rosto.py rastrear <proxy ou original> _CLAUDE/rosto_<id>.json --inicio <primeiro corte> --fim <último>` (o modelo: `rosto.py baixar`, uma vez). Mostre a cobertura; abaixo de ~80%, avise antes de usar trava no rosto. Sem seguir o rosto (tutorial, bancada): a câmera enquadra regiões de interesse (a tela, a placa) que você combina com a pessoa.
3. **Rascunho** dos movimentos, numerados: o quê, onde (palavra, tempo ou corte), duração, curva, de quanto a quanto. A base (alternância, aproximação lenta) e o que casa com cada animação, como o guia descreve; os cuidados do §4 dele (nada de salto visível, altura dos olhos no plano fechado, nunca mostrar a borda do quadro).
4. **Keyframes:** o cálculo (base + movimentos, keyframes densos com a curva embutida, avisos de conflito) e a escrita no XML (efeito Movimento: escala e posição por keyframe no clipe de V1) ainda não vêm prontos. Na primeira vez, escreva `<pessoa>/scripts/camera.py` sobre `edicao.linha` e `edicao.xmeml` (que já gera o XML dos cortes; acrescente o filtro de movimento aos clipes de V1), começando por um arquivo de teste com 2–3 movimentos que a pessoa abre e confere. Sem programa (`revisao.programa: nenhum`), os movimentos vão para o render.
5. **Grave** `camera.movimentos` (`--gravar camera`), com `base_cortes_versao` e `base_motions_versao` atualizados pelo `--etapa camera=aguardando_aprovacao`. Cada movimento visível (chegada rápida, aceleração antes do corte, punch, rampa) vira um evento com força e tempo para o som.
6. **Entrega** (regras comuns, §4) e resumo curto.

## Revisão e aprovação
Por número: "cam07 mais lento", "cam05 mais forte", "cam12 tira", "no s014 não precisa punch". Ajuste feito à mão no programa não volta: peça por número. Se uma animação mudar depois, a câmera é recalculada. Aprovado: `--etapa camera=concluido`, aprendizados, `/clear` e `/edicao:editar`.
