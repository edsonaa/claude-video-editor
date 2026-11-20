---
name: render
description: "Monta e exporta o vídeo pronto pelo FFmpeg, para quem não revisa num programa de edição: cortes com quadros exatos, enquadramento (vertical a partir do horizontal), animações por cima, legenda queimada, voz tratada, música, efeitos sonoros e a loudness da plataforma, com conferência final. Também gera os rascunhos em resolução baixa para revisão. Use em /edicao:render, ou quando a pessoa pedir o vídeo final ou um rascunho."
---

# render

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** todos os blocos do estado (cortes com o enquadramento de cada segmento, motions com os renders, legendas, sfx com a música, a voz tratada em `midia.arquivos`), a configuração (`video.formato`, `legendas`, `audio`, `pastas.renders`), `<pessoa>/ajustes/render.md` e `geral.md`.
- **Escreve:** `<pastas.renders>/<projeto>_final_vNN.mp4` e `_CLAUDE/rascunhos/<projeto>_rascunho_vNN.mp4`, sempre em versão nova; a entrega no estado (`entregas`, com `tipo` final ou rascunho).
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/entrega-no-editor.md` (caminho C) e `${CLAUDE_PLUGIN_ROOT}/guias/legendas-e-audio.md`.

## O script (pronto)
`<py> <f>/render.py plano|rascunho|final . [--de S --ate S] [--formato F] [--legenda auto|ass|animada|nao] [--perfil <pessoa>/perfis/<perfil>]`
- **plano:** mostra o que vai entrar, sem renderizar: cada segmento com quadro de entrada e quantidade de quadros, o enquadramento, as animações, a música e os efeitos, e os avisos. Rode antes do primeiro render de cada vídeo.
- Os cortes saem com **quadros exatos** (a mesma conversão da entrega em XML). A voz sai com **amostras exatas** e fades curtos nas junções, e é a tratada quando houver.
- **Enquadramento:** em cada segmento (`cortes.segmentos[].quadro`) vale `inteiro`, `cortar` (com o centro `x`/`y` de 0 a 1 e `zoom`) ou `encaixar` (o quadro inteiro sobre fundo desfocado). Sem `quadro`, o padrão é inteiro quando a proporção bate, câmera recortada no centro e tela encaixada. Animações em outra proporção ficam de fora, com aviso.
- **Legenda:** no `auto`, queima quando o config pede (`legendas.queimar`) ou quando o formato é vertical. A legenda animada (`legendas.render`) tem prioridade quando existe. Legenda feita sobre outro corte faz o render recusar antes de gastar tempo.
- **Som:** a voz, a música (`sfx.musica`, já com o ducking), os efeitos com o ganho de cada um, e a loudness final no alvo (`audio.alvo_lufs`, `audio.pico_dbtp`) em duas passadas.
- **Não aplica** movimentos de câmera (o formato deles é de cada fluxo; o render avisa). Se a pessoa usa câmera sem programa, estenda o render em `<pessoa>/scripts/` sobre `edicao.render` (regras comuns, §3) e sugira propor ao motor.

## Passo a passo
1. `<py> <f>/estado.py . status`: as etapas anteriores aprovadas (ou a pessoa pediu um rascunho).
2. `render.py plano .` e os avisos. Rascunho para revisar (`render.py rascunho .`, em segundo plano se o vídeo for longo); um trecho com `--de/--ate`.
3. Final: `render.py final .`. Cada ajuste é um render novo: agrupe vários pedidos antes.
4. **Conferir** antes de entregar: o script já confere duração, loudness e pico e mostra os avisos. Olhe também uma folha de contato dos pontos de animação e da legenda queimada (`<py> <f>/contato.py <arquivo> folha.png --inicio … --fim …`).
5. Resumo curto com o caminho. `--etapa render=aguardando_aprovacao`. Para revisar assistindo, ofereça também `/edicao:painel`.

## Revisão e aprovação
A pessoa assiste e pede pelo chat, citando o tempo do vídeo ("em 01:12 tira essa frase") ou o número do item, ou deixa pedidos no painel. Converta o tempo do vídeo para o de origem pela lista de cortes (`Linha.seq_para_origem`) e mande o pedido para a etapa certa (um corte volta para `cortes`, um som para `sfx`). Aprovado: `--etapa render=concluido`, aprendizados. Depois, se a pessoa publica: `/edicao:publicar`; se quer cortes curtos do vídeo: `/edicao:curtos`.
