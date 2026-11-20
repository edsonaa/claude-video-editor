# Novidades do motor

Cada versão nova do motor (skills, guias e ferramentas) entra aqui, a mais nova em cima. A skill `/edicao:editar` mostra o que mudou desde a última vez que a pessoa viu. Ao lançar uma versão, suba o `version` em `.claude-plugin/plugin.json` para o mesmo número (um teste confere).

## 0.8.0
- **Galeria no painel** (aba Galeria, tecla G): o que dá para pôr no vídeo, com prévia sobre o quadro do ponto do cursor, e um botão que põe ali.
  - **Legendas:** os seis estilos com o texto do ponto do cursor, nas medidas do render, e a posição. A escolha vale para o vídeo (`video.legendas`); se a divisão em blocos muda, fica um pedido para gerar de novo.
  - **Animações:** os 14 efeitos tocando no navegador com o tema do seu perfil. Você preenche o conteúdo vendo a prévia e insere no cursor: o item entra aprovado no plano, com `efeito` e `params`, e já toca por cima do vídeo no painel antes do render.
  - **Transições:** dissolver, passar pelo preto, clarão, zoom, empurrar e chicote, com prévia nas duas imagens do corte mais perto e a duração num controle.
  - **Sons:** a sua biblioteca por categoria, para ouvir e inserir com o pico no cursor (o arquivo vai para `Assets/sons/`). Sem biblioteca, um botão cria o pacote inicial.
  - Tudo entra com `origem: painel`, e as skills tratam como escolha da pessoa: o plano de animação e a etapa de som mantêm esses itens.
- **Transições** (`transicoes/transicoes.json`, no segmento que entra):
  - no render, centradas no corte com o xfade do FFmpeg e a mídia que sobra de cada lado, sem mudar a duração do vídeo;
  - no XML, Cross Dissolve ou Dip to Color (as que o programa não tem entram como dissolver, com um marcador);
  - na volta do programa, voltam para o segmento certo;
  - no painel, aparecem na linha do tempo e no inspetor do segmento, e com uma prévia aproximada ao tocar.
- **Pacote inicial de sons** (`sons.py pacote`): 12 sons sintetizados pelo próprio motor, livres de direitos: whoosh, impacto, pop, clique, sino, subida e falha digital.
- Painel: animações que se sobrepõem no tempo ficam em faixas na trilha, e as miniaturas aceitam largura (`/api/miniatura?largura=`).

## 0.7.0
- **Boas-vindas pelo painel:** a `/edicao:iniciar` pergunta se o briefing vai pela conversa ou pelo painel. Pelo painel (`painel.py boas-vindas`), num só lugar:
  - a verificação do que está pronto (pasta, subpastas, gravações, FFmpeg, transcrição, Node e sons quando o fluxo pede), com o que fazer no que falta;
  - o briefing livre e os termos para a transcrição;
  - o tipo de vídeo (preset), o estilo das animações (com prévia e aviso de fonte que falta) e o padrão de legenda tocando sobre um quadro da sua gravação, no formato do vídeo;
  - "Enviar para o Claude" grava as escolhas só neste vídeo (ou também como padrão, se marcado), fecha o painel e o Claude segue dali, a partir de `_CLAUDE/briefing_painel.md`.
- **Estilos de legenda** (`legendas/estilos.json`): clássica, caixa, palavra a palavra, impacto, minimalista e brilho. Cada um define a divisão (frase ou palavra, caracteres, caixa alta) e o visual queimado (contorno, sombra, faixa, brilho, cor e tamanho da palavra falada).
  - Escolha em camadas: `legendas.estilo` na configuração, `video.legendas` no vídeo, opções da linha de comando. Configuração antiga sem estilo continua igual.
  - O painel desenha a legenda com as mesmas medidas do ASS do render (`painel_web/legenda-estilo.js`).

## 0.6.0
- **Render pronto** (`render.py plano|rascunho|final`): antes, a etapa de render pedia para escrever o script no primeiro vídeo.
  - Cortes com quadros exatos (a mesma conversão da entrega em XML) e voz com amostras exatas, com fades curtos nas junções e a voz tratada quando houver.
  - Enquadramento por segmento (inteiro, recortado com centro e zoom, ou encaixado sobre fundo desfocado), o que tira vídeo vertical do horizontal.
  - Animações por cima (tela cheia e com transparência), legenda queimada (ASS ou a animada), música, efeitos com ganho e loudness final no alvo, em duas passadas (`edicao.audio.normalizar`).
  - Recusa legenda feita sobre outro corte antes de gastar tempo. Confere duração, loudness e pico e registra a entrega (final ou rascunho).
- **Cortes curtos** (`/edicao:curtos`, `curtos.py`):
  - a fala do corte final em frases com id;
  - sugestões de trecho com motivos (começo que se sustenta, fim fechado, gancho, pausa natural);
  - cada curto vira um projeto em `Curtos/<nome>/`, com os mesmos quadros do longo, recortado em vertical centrado no rosto (pelo rastreio) e a tela encaixada, com fluxo cortes → legendas → render.
- **Publicação** (`/edicao:publicar`, `publicar.py`):
  - capítulos conferidos pelas regras do YouTube (0:00, pelo menos 3, 10 s cada), escritos por tempo, frase, segmento ou animação, ou tirados dos marcadores de capítulo do plano;
  - candidatas a capa (nitidez, exposição, rosto) já no formato do vídeo;
  - textos por plataforma conferidos contra os limites (título, descrição em bytes, tags com vírgulas e aspas, hashtags: 15 no YouTube, 5 no Instagram; duração e formato de Shorts, Reels e TikTok);
  - pasta `Publicar/<plataforma>/` com o vídeo, o texto para colar, as legendas, a capa e a conferência.
- **Painel:** mostra o curto em 9:16 com o enquadramento de cada segmento, que se ajusta ali (← →, encaixar). Enquadrar ou mudar o texto de um segmento não conta como corte novo (nada fica desatualizado à toa).
- `guias/curtos-e-publicacao.md`: o ofício de curtos (gancho, uma ideia, áreas seguras do vertical) e de publicação (título, descrição, capítulos, capa), com a tabela de limites e a data em que foram conferidos.

## 0.5.0
- **Painel de revisão** (`/edicao:painel`, `painel.py`): um servidor local (só desta máquina, com token) que abre o vídeo no navegador já cortado, a partir das mídias originais, com as animações (inclusive com transparência), a legenda palavra a palavra, a música e os efeitos por cima. Sem render.
  - **Roteiro:** a transcrição com o que saiu do corte riscado; selecionar palavras e cortar ou devolver ao vídeo (com respiro nas bordas e desfazer).
  - **Linha do tempo** com trilhas (corte com miniaturas, animações, legendas, câmera, som, pedidos) e ajuste fino de cada segmento quadro a quadro.
  - **Pedidos** presos ao ponto do vídeo (guardam o tempo da origem, então sobrevivem a mudanças no corte), com opção de anotar no caderno de aprendizados; aprovar ou riscar animações do plano; corrigir legendas; aprovar a etapa.
  - **Prévias** leves para o que o navegador não toca (ProRes, HEVC 10 bits, áudio PCM em MOV, a voz tratada e animações com transparência em WebM), geradas pelo próprio painel com progresso.
  - Toda gravação passa pelo estado com a revisão lida: se o Claude gravou no meio, a mudança é recusada e a tela se atualiza, sem apagar a dele. O painel acompanha as mudanças do Claude sozinho.
- `estado.py status` mostra, em cada pendência, o item, o ponto na sequência e na origem e se veio do painel.
- `edicao.legendas`: ler, gravar versão e corrigir bloco viraram funções do módulo (o script e o painel usam as mesmas).

## 0.4.0
- **Legendas** (etapa nova `legendas`, `legendas.py`): blocos pela transcrição e pelos cortes, no tempo da sequência, com as regras de leitura (até 2 linhas, ~42 caracteres, ~17 caracteres por segundo, sem terminar linha em artigo ou preposição), correções de grafia e revisão por id (`l014`). Saídas: SRT e VTT (programa, YouTube, plataformas de curso), ASS para queimar no render (no modo palavra, a palavra falada acende) e o efeito novo `legenda-animada` (HyperFrames), que entra no XML em V5.
- **Áudio** (`audio.py`): medição (loudness, pico real, ruído de fundo, fala/ruído, clipping) com recomendações; tratamento da voz (passa-alta, redução de ruído pelo piso medido, compressão leve, loudness em duas passadas) com **a mesma duração e o mesmo início do original** (o atraso dos filtros é medido e compensado), e a voz tratada entra no XML no lugar do áudio da câmera; música de fundo com ducking sob a fala e fades, numa trilha própria; conferência da mixagem final.
- Configuração: blocos `legendas` e `audio`; presets com legendas (reels: queimada palavra a palavra; aula técnica: SRT e VTT).
- `guias/legendas-e-audio.md`: o ofício de legendas, alvos de loudness por plataforma, a ordem do tratamento de voz e a música.

## 0.3.0
- **Biblioteca de efeitos** (`efeitos/`): 13 composições HyperFrames prontas e parametrizadas, com prévia animada: título de impacto, ênfase de frase, contador, gráfico de barras, lista de passos, comparação lado a lado, card lateral, revelação de logo, print com destaque, marcador de capítulo, transição com rampa, cursor e clique, tarja de nome. Funcionam em 16:9, 9:16, 1:1 e 4:5, pegam cores, fontes e curvas do perfil e mostram ASSET FALTANDO quando falta uma imagem.
- `efeitos.py`: `listar`, `mostrar`, `criar` (copia o efeito para o item do plano com o tema, o conteúdo, a duração exata em frames e os eventos de som), `previa` e `vitrine`.
- **Estilos prontos** (`estilos/`): limpo, tech-neon, editorial e impacto, cada um um perfil completo com `tema.json` e vitrine. A montagem sugere um por preset; `config.py perfil-novo <nome> --estilo <estilo>`.
- `motion-mapa` consulta o repertório (o conteúdo continua decidindo); `motion-render` parte do efeito quando o plano indica um; `sfx` usa os eventos de cada efeito.
- `guias/hyperframes.md`: três armadilhas novas (variável com nome de variável CSS, `transform` do CSS sobrescrito pelo GSAP, render lento sem chrome-headless-shell) e a versão testada (0.9.70).

## 0.2.0
- **Motor separado da configuração.** O repositório virou um plugin (`edicao`): as skills de cada etapa vêm prontas e se atualizam. As escolhas, o estilo e os ajustes de cada pessoa ficam em `~/.edicao/` e nenhuma atualização mexe neles.
- **Comandos novos:** `/edicao:montar` (montagem e mudanças no fluxo) e `/edicao:editar` (o dia a dia), mais uma skill por etapa (`/edicao:cortes`, `/edicao:camera`…) e a etapa `render` para quem não usa programa de edição.
- **Presets:** YouTube com apresentador, tutorial com tela, aula técnica, reels, narrado e só os cortes. A montagem parte de um deles e pergunta só o que falta.
- **Ajustes pessoais** (`~/.edicao/ajustes/<etapa>.md`): os aprendizados de ofício entram ali, sem editar o motor.
- `config.py` (escolhas, perfis, novidades) e `estado.py --init` lendo o fluxo da configuração.

## 0.1.0
- Ferramentas prontas e testadas em `ferramentas/`: estado do vídeo, inventário, silêncios, transcrição (WhisperX e Scribe), XML para Premiere/Resolve com a volta, tempo e timecode, folha de contato, índice de sons e rastreio de rosto.
