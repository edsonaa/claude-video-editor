# Novidades do motor

Cada versão nova do motor (skills, guias e ferramentas) entra aqui, a mais nova em cima. A skill `/edicao:editar` mostra o que mudou desde a última vez que a pessoa viu. Ao lançar uma versão, suba o `version` em `.claude-plugin/plugin.json` para o mesmo número (um teste confere).

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
