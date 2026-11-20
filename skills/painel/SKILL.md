---
name: painel
description: "Abre o painel de revisão no navegador: o vídeo já cortado, com animações, legenda e som; o roteiro com o que saiu do corte riscado (dá para cortar ou devolver frases), ajuste fino dos cortes, a galeria (legendas, animações, transições e sons com prévia, postos no ponto do cursor), pedidos marcados no ponto exato e aprovação da etapa. Depois, aplica o que a pessoa pediu e escolheu lá. Use em /edicao:painel, quando a pessoa quiser revisar assistindo ou ao entregar uma etapa para revisão."
---

# painel

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md`.

Não é uma etapa: é um jeito de revisar qualquer etapa. A pessoa assiste ao corte como ele vai ficar e aponta o que mudar no ponto exato, em vez de descrever tempos no chat.

- **Lê:** o estado do vídeo inteiro (cortes, transcrição, animações, câmera, som, legendas, marcadores, pendências).
- **Escreve (pela pessoa, no painel):** cortes (versão nova a cada mudança, com desfazer), pendências com `origem: painel` e o ponto (tempo da sequência e da origem), status das animações do plano (aprovar, riscar), texto das legendas (versão nova), etapa aprovada, linhas no caderno de aprendizados (`(pelo painel)`). Prévias leves em `_CLAUDE/painel/`.
- **Escreve arrastando** (como num programa de edição): o tempo de animações e sons (`inicio_seq`/`fim_seq`), a entrada e a saída de blocos de legenda (versão nova do arquivo de blocos), a entrada e a saída dos segmentos (aparar pelas bordas) e a ordem deles (o meio), a posição e o tamanho das animações por cima do vídeo (`motions.itens[i].posicao` = `{x, y, escala}`, frações do quadro em volta do centro), o deslocamento da legenda (`video.legendas.deslocamento`) e o enquadramento de segmentos recortados. Tudo vai para o registro `painel.mudancas`, em palavras.
- **Escreve pela galeria** (tudo com `origem: painel`): animações da biblioteca como itens `aprovado` do plano (`efeito` e `params`), transições na entrada de um segmento (`cortes.segmentos[i].transicao`, sem mudar a versão do corte), sons da biblioteca em `sfx.itens` (pico no cursor, arquivo copiado para `Assets/sons/`) e o estilo de legenda do vídeo (`video.legendas`), com um pedido para refazer os blocos quando a divisão muda. Pode criar o pacote inicial de sons e ligar `som.biblioteca`.

## Abrir
1. `<py> <f>/painel.py verificar .`: o que o navegador toca direto. ProRes, HEVC 10 bits, áudio PCM dentro de MOV e animações com transparência precisam de **prévia** (H.264 leve; animações em WebM com transparência). A voz tratada também só toca pela prévia. Diga quais faltam: a pessoa gera pelo botão do próprio painel, ou você gera antes com `<py> <f>/painel.py previas .` (em vídeo longo, alguns minutos).
2. Rode **em segundo plano** (o comando não termina sozinho): `<py> <f>/painel.py abrir . --navegador`. A primeira linha da saída é o endereço com o token (`http://127.0.0.1:8765/?t=…`): passe-o inteiro para a pessoa. Porta ocupada (outro painel aberto): `--porta 0` escolhe uma livre.
3. Em 2–3 linhas, diga o que dá para fazer e o atalho principal:
   - assistir já cortado (espaço toca e pausa; ↑ ↓ pulam de corte em corte);
   - no **roteiro**, o que está riscado saiu do corte: selecionar palavras (clique, Shift+clique) e cortar ou devolver; Ctrl+Z desfaz;
   - ajustar a entrada ou a saída de um segmento quadro a quadro; aprovar ou riscar animações do plano; corrigir o texto de uma legenda;
   - **arrastar**, como num programa de edição: na linha do tempo, animações e sons mudam de lugar, as bordas esticam animações e legendas e aparam segmentos, o meio de um segmento muda a ordem (ímã nos cortes e no cursor; Alt desliga); no vídeo, a legenda se arrasta, a animação selecionada se move e muda de tamanho (cantos ou roda do mouse) e o segmento recortado se enquadra; Ctrl+Z desfaz qualquer uma;
   - **galeria** (tecla G): legendas, animações, transições e sons com prévia sobre o quadro do vídeo; cada um entra no ponto do cursor (a animação escolhida já toca por cima do vídeo, antes do render);
   - **pedidos** (tecla N): ficam presos ao ponto do vídeo; "vale para os próximos vídeos" também anota no caderno;
   - "Aprovar <etapa>" fecha a etapa (só sem pedidos abertos nela).
   Quando terminar, a pessoa diz "pronto" aqui no chat.

## Depois da revisão
1. `<py> <f>/painel.py mudancas . --marcar-lidas`: o que ela arrastou, inseriu e desfez, em palavras. Já está gravado: não refaça, e leve em conta no que for fazer (o status avisa quando há mudanças não lidas).
   `<py> <f>/estado.py . status`. Os pedidos do painel aparecem com o item, o ponto na sequência e na origem, e "pelo painel". O tempo da origem é o que vale: se o corte mudou depois do pedido, o status já mostra o ponto novo.
2. **Cortes mudados no painel já estão gravados** (versão nova): não refaça. O que dependia do corte ficou desatualizado e o status avisa (plano de animação, legendas, câmera, som): mostre e combine o que refazer, seguindo a skill de cada etapa.
3. **Pedidos:** aplique na etapa de cada um (a que está `aguardando_aprovacao` é a de agora; pedidos de etapas futuras ficam para quando ela chegar). Aplicou: `--resolver <id>`. Pedido ambíguo: pergunte, citando o id e o ponto.
4. Animações riscadas ou aprovadas no painel já mudaram de status. "Pedir ajuste" numa animação pronta virou pendência e ela continua no XML até a versão nova.
   **O que veio da galeria** é escolha da pessoa, já gravada: não proponha de novo nem troque sem perguntar. Animações (`origem: painel`, `aprovado`) seguem para a `motion-render` com o `efeito` e os `params` dela; sons entram na `sfx` como estão (ajuste de nível só se a pessoa pedir ou se passar do teto); transições valem no render e no XML; o estilo de legenda vale no painel e no render, e o pedido de refazer os blocos (se houver) vai para a etapa de legendas. Diga o que entrou: `estado.py . status` mostra.
5. Etapa aprovada no painel: o status já está `concluido`. Diga quantos aprendizados ficaram anotados e sugira `/clear` e `/edicao:editar`.
6. A pessoa terminou de revisar: encerre o processo em segundo plano. Sem a página aberta, ele fecha sozinho depois de 2 horas.

## Limites (diga quando importar)
- Movimentos de câmera aparecem como etiqueta, não aplicados na imagem: para vê-los, o rascunho do render ou o programa.
- Correção de cor e mixagem fina não aparecem: são do programa ou do render. Transições aparecem aproximadas ao tocar (o render faz a exata, centrada no corte). A música toca como foi gerada (já com o ducking).
- Posição arrastada: o render e o XML aplicam (no XML, um Basic Motion no clipe da animação; confira no programa na primeira vez). A legenda deslocada vale na legenda queimada e no ASS; a legenda animada (HyperFrames) e o SRT seguem a posição do estilo.
- Animação escolhida na galeria toca a página do efeito no navegador (com GSAP do CDN, ou de `GSAP_LOCAL`): sem internet e sem `GSAP_LOCAL`, a prévia fica parada.
- Prévias em resolução reduzida (até 1280 px no lado maior). Animações com transparência: Chrome, Edge ou Firefox (o Safari mostra o fundo preto).
- Só aceita conexões desta máquina. Para revisar em outro computador, a pessoa abre o painel lá.
