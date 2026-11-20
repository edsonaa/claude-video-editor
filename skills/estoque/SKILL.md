---
name: estoque
description: "O estoque de peças da pessoa: estilos de legenda, transições, efeitos e motions dela, guardados fora do motor. Recebe uma referência (trecho de vídeo, GIF, imagem ou só a descrição) com o que ela gostou, analisa, constrói a peça, mostra a prévia e, aprovada, a peça passa a aparecer na galeria do painel, nas boas-vindas, no plano de animação, no render e no XML. Use em /edicao:estoque, quando a pessoa quiser guardar ou criar um estilo de legenda, uma transição, um efeito ou um motion, mandar uma referência de que gostou, ou quando o status mostrar peças do estoque esperando análise ou ajuste."
---

# estoque

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md`.

Não é uma etapa do vídeo: é o arsenal da pessoa, que vale para todos os vídeos. Cada peça tem uma **ficha** (`ficha.md`) com o nome, o tipo e **o que ela gostou**: essa frase é a régua de tudo o que você constrói.

- **Lê:** `<pessoa>/estoque/` (`estoque.py listar`), a ficha e o trecho de cada peça, o perfil dela (tema, estilo de motion) e as peças do motor (para partir de uma parecida).
- **Escreve:** só dentro de `<pessoa>/estoque/` (nunca no motor): o rascunho de cada peça, a análise na ficha, a prévia, o status.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/referencias.md` (olhar e medir uma referência), `${CLAUDE_PLUGIN_ROOT}/docs/efeitos.md` ("Criar um efeito novo") e `${CLAUDE_PLUGIN_ROOT}/guias/hyperframes.md` (efeitos e motions), `${CLAUDE_PLUGIN_ROOT}/legendas/README.md` (campos de um estilo de legenda), `${CLAUDE_PLUGIN_ROOT}/transicoes/README.md` (campos de uma transição).

Os tipos:
- **legenda:** um jeito de mostrar a legenda (fonte, cor, contorno, caixa, palavra a palavra). Vira `estilo.json`.
- **transição:** uma passagem entre dois planos. Vira `transicao.json` (o xfade do render, o equivalente no XML e a prévia do painel).
- **efeito:** um elemento animado (tarja, título, card, contador, chamada). Vira um efeito HyperFrames (`index.html` + `efeito.json`), igual aos do motor.
- **motion:** um jeito de mover (como algo entra, assenta e sai; um movimento de câmera). Também vira um efeito HyperFrames, com o conteúdo como parâmetro e o movimento como o ponto.

## Receber uma peça
- **Pelo painel:** Galeria → Estoque → "Adicionar ao estoque": a pessoa escolhe o tipo, escreve o nome e o que gostou, diz se parece com alguma peça que já existe e manda a referência (um arquivo, marcando início e fim, um trecho do vídeo aberto ou só a descrição). Chega como "esperando análise".
- **Pelo chat:** pergunte o que faltar, uma coisa por vez: o tipo (se não estiver claro), o nome, **o que ela gostou** (obrigatório) e a referência (caminho do arquivo e o trecho, até 90 s). Depois:
  `<py> <f>/estoque.py novo --tipo efeito --nome "…" --gostei "…" [--arquivo <caminho> --de S --ate S] [--parecido <id>]`
- **De um vídeo:** uma animação que ficou boa (`_CLAUDE/motion/mo04`) pode virar peça: `novo` com o render dela como referência, `construir` e leve o `index.html` do projeto para o rascunho, no formato da biblioteca (variáveis da composição, `efeito.json`).

## Analisar e construir (uma peça de cada vez)
1. `<py> <f>/estoque.py listar` e `estoque.py mostrar <id>`: a ficha, o que ela gostou, a peça parecida.
2. **Olhar:** `estoque.py folha <id> --cada 2` e leia a `folha.png` da pasta da peça. Para movimento, meça como em `guias/referencias.md` (seção 3): a duração em quadros, a curva mais parecida do GSAP, se passa do ponto e quanto, o que entra primeiro.
   - Foque no que ela disse que gostou. O resto do trecho é contexto.
   - Meça o **jeito**, nunca copie o desenho de outra pessoa (marca, logotipo, ilustração). As cores e as fontes vêm do tema do perfil dela; numa legenda, se ela quiser a cor exata da referência, pergunte.
3. `estoque.py construir <id> [--base <id parecido>]`: abre o rascunho na pasta do tipo, copiando a base (a peça parecida ou um modelo).
4. **Construa** a partir da base, pelo tipo:
   - **legenda:** edite `estilo.json` (os campos em `legendas/README.md`): `modo`, `caixa_alta`, `max_caracteres` e `max_caracteres_vertical`, `linhas`, `fonte` (`titulo`, `texto` ou o nome de uma fonte instalada), `peso`, `tamanho`, `cor` e `cor_destaque` (hex ou uma cor do tema), `contorno`, `cor_contorno`, `opacidade_contorno`, `sombra`, `caixa`, `brilho`, `escala_destaque`, `posicao`; e `titulo`, `descricao`, `bom_para`.
   - **transição:** edite `transicao.json` (os campos em `transicoes/README.md`):
     - `xfade`: um dos tipos do FFmpeg (`ffmpeg -hide_banner -h filter=xfade` lista; ex.: `circleopen`, `radial`, `pixelize`, `smoothleft`, `squeezeh`, `wipetl`, `fadegrays`), ou `custom` com `expr` (a expressão do xfade, com A, B, P, X, Y, W, H) quando nenhum serve;
     - `duracao` (`padrao`, `min`, `max`, em segundos);
     - `xml`: `nome` e `effectid` do equivalente no programa (Cross Dissolve; Dip to Color Dissolve com `cor`); `aproximada: true` quando o programa não tem igual;
     - `previa`: os quadros-chave da prévia no painel (`a` para a imagem que sai, `b` para a que entra, com `opacity`, `transform`, `filter`, `clipPath`; `fundo`; `a_cima`). Sem ela, o painel mostra um dissolver;
     - `titulo`, `descricao`, `bom_para`, `evitar`.
   - **efeito ou motion:** edite `index.html` e `efeito.json` como em "Criar um efeito novo" (`docs/efeitos.md`): as variáveis do tema (`--t-*`), as funções `HF.*`, a linha do tempo pausada com `HF.pronto(tl)`, os parâmetros com `exemplo`, os `eventos_som`, e as armadilhas do guia do HyperFrames. Num motion, o conteúdo (texto, imagem) é parâmetro e o movimento medido é o que a peça guarda; ponha `"motion"` nas `tags`.
5. `estoque.py verificar <id>` e `estoque.py previa <id> --perfil <pessoa>/perfis/<perfil>`. Leia a prévia (PNG ou GIF) e compare com a folha da referência. Não ficou com o que ela gostou: ajuste e gere de novo.
6. `estoque.py analise <id> "…"`: o que mediu e como construiu, com números ("entrada em 14 quadros, back.out(1.6), passa 8% do ponto; base: titulo-impacto").
7. Diga à pessoa, em 2–3 linhas, o que fez e onde aprovar: no painel (Galeria → Estoque → "Para você aprovar": prévia, Aprovar, Pedir ajuste, Recusar) ou aqui no chat (`estoque.py aprovar <id>`).

## Ajustes e manutenção
- Ajuste pedido (pelo painel ou no chat, `estoque.py ajuste <id> "…"`): aparece em `estoque.py listar` e no status do vídeo. Aplique, gere a prévia, atualize a análise; a pessoa aprova de novo. Uma peça ativa com ajuste pedido continua valendo até a aprovação.
- `estoque.py arquivar <id>` tira da galeria sem apagar; `aprovar` traz de volta. `recusar` encerra uma entrada ou um rascunho.

## Onde a peça aparece, depois de aprovada
- **Legenda:** a galeria (Legendas, com o selo "seu"), as boas-vindas, `legendas.estilo` na configuração e `video.legendas.estilo` no vídeo; o render e o ASS queimam igual.
- **Transição:** a galeria (Transições), o render (xfade centrado no corte), o XML (o efeito do `xml`) e a prévia ao tocar no painel.
- **Efeito e motion:** a galeria (Animações, filtro "Do seu estoque"), o plano (`/edicao:motion-mapa`) e a construção (`efeitos.py criar <id>` funciona igual aos do motor).
- **Boas-vindas:** a pessoa marca as peças que quer naquele vídeo; elas vão para o briefing e para `boas_vindas.estoque` no estado.
- **Revisões:** "Sugerir" na galeria deixa um pedido no ponto do cursor com o id da peça.

## Regras
- O estoque fica em `<pessoa>/estoque/` (sobrevive às atualizações do plugin). Nunca escreva peças na pasta do motor.
- Uma peça por vez, com a prévia mostrada antes de dizer que está pronta. Só a pessoa aprova.
- O que ela gostou é a régua. Na dúvida entre duas leituras, pergunte qual era.
