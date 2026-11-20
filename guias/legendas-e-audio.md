# Legendas e áudio

O ofício das legendas (etapa `legendas`) e do tratamento de voz e música (etapas `preparar` e `sfx`). Os números são pontos de partida: o que a pessoa preferir vai para o perfil ou para os ajustes, com a origem.

## Legendas

### Para quê
- Muita gente assiste sem som, principalmente no celular. Em vídeo curto, legenda queimada é quase obrigatória.
- Acessibilidade: quem não ouve, ou não entende bem o idioma.
- Busca: o arquivo de legenda (SRT/VTT) enviado à plataforma vira texto indexável.

### Arquivo ou queimada
- **Arquivo** (SRT, VTT): a pessoa liga ou desliga, a plataforma traduz, dá para corrigir depois sem renderizar. É o padrão para vídeo longo e para aula.
- **Queimada** (dentro da imagem): sempre visível, com o estilo do vídeo. É o padrão para reels e shorts. Errou uma palavra? É render de novo, então a revisão vem antes.
- **Palavra a palavra** (a palavra falada acende na cor de destaque) só existe queimada; em arquivo, vira frase.

### Regras de leitura
- **Até 2 linhas**; **até ~42 caracteres por linha** em 16:9. Em 9:16, blocos curtos: 2–5 palavras, ~20 caracteres por linha, letra grande.
- **Velocidade de leitura:** até ~17 caracteres por segundo. Acima disso, a pessoa não termina de ler (o `legendas.py` avisa).
- **Duração:** no mínimo ~1 s, no máximo ~6 s por bloco; entre dois blocos, pelo menos 2 quadros, para o olho perceber a troca.
- **Tempo:** o bloco entra junto com a primeira palavra e sai ~0,25 s depois da última (ou antes do próximo).
- **Quebra de linha:** de preferência depois de pontuação; nunca terminar linha em artigo, preposição ou conjunção ("de", "a", "que", "e"); linhas equilibradas, a de cima um pouco maior.
- **Quebra de bloco:** em pausa (≥ ~0,5 s), em ponto final, quando não couber. Opcional: em cada corte de câmera (`quebrar_no_corte`), para a legenda não atravessar a troca de plano.

### Fidelidade
- A legenda é a **fala limpa**: sem hesitações (ééé, hum), sem falsa largada que o corte deixou, com a grafia certa dos nomes e termos. Não resume nem reescreve, a não ser que a pessoa peça.
- **Grafia primeiro:** antes de dividir em blocos, conferir nomes, marcas e termos técnicos (termos do config, briefing, roteiro) e escrever o `correcoes.json`. Uma palavra corrigida que volta em outros vídeos vai para `transcricao.termos` do config, e a próxima transcrição já acerta.
- Números: como a pessoa falou ("vinte placas" ou "20 placas"); escolha um jeito por vídeo e mantenha.

### Posição e convivência
- 16:9: embaixo, centralizada, a ~8% da borda. **9:16: mais alta**, a ~27–30% da borda de baixo; a interface do app (legenda do post, botões) cobre a parte de baixo e a lateral direita.
- Não colidir com animação: tarja de nome, ênfase de frase e cards embaixo disputam o mesmo lugar. Nesses trechos, a legenda sobe para o centro (`posicao: centro`) ou o efeito vai para cima. Confira por folha de contato.
- Legível sobre qualquer imagem: contorno escuro e sombra (já nos estilos ASS e no efeito `legenda-animada`), nunca texto fino sem contorno.

## Áudio

### Alvos de loudness
- **YouTube, TikTok, Instagram, Facebook, Spotify (podcast):** −14 LUFS integrados, pico real até −1 dBTP. É o padrão do config (`audio.alvo_lufs`, `audio.pico_dbtp`).
- **Apple Podcasts:** −16 LUFS. **TV (EBU R128):** −23 LUFS.
- TikTok e Instagram: há quem recomende mais alto (−12 a −10 LUFS); outros lembram que essas plataformas não normalizam, então o arquivo toca como foi enviado. −14 é seguro; mais alto só se a pessoa pedir, e sempre com o pico real abaixo de −1.
- Alvos mudam: confira os atuais antes de recomendar um diferente do config.

### Tratar a voz (nesta ordem)
1. **Passa-alta** (~80 Hz): tira o ronco grave (ar-condicionado, mesa, vento) sem mexer na voz.
2. **Redução de ruído**, pelo **piso de ruído medido** no próprio arquivo. Pouca é melhor que muita: redução forte demais deixa a voz metálica, "embaixo d'água", com artefatos nas pausas. Sempre um trecho de teste primeiro, para a pessoa ouvir.
3. **Compressão leve:** a voz oscila menos entre frases e entre takes. Pesada demais, soa "esmagada" e sobe o ruído nas pausas.
4. **Loudness em duas passadas** (mede, depois aplica o ganho exato até o alvo, com o teto de pico real). Normalização linear quando dá; o script avisa quando teve que cair para o modo dinâmico.
- O que o tratamento **não** conserta: clipping (a gravação estourou), eco forte de sala, voz longe do microfone. O `audio.py medir` avisa; a solução é na próxima gravação (anote no caderno).
- **Sincronia:** filtros de redução de ruído atrasam o sinal. O `audio.py tratar` mede o atraso real e compensa, e a voz tratada tem exatamente a duração e o início do original. Um script novo de áudio precisa garantir o mesmo (medir por correlação, como `edicao.audio.atraso`).
- Dois microfones (lapela e câmera) em canais separados: trate o canal da lapela (`--canal 0`) e use o da câmera só de reserva.

### Música de fundo
- Sempre com licença: biblioteca da plataforma, bancos com licença clara ou música própria. Música comercial sem licença derruba o vídeo ou o monetiza para outra pessoa.
- **Sob a fala, bem baixa:** a fala precisa ficar ~15–20 LU acima da música. Sem fala (abertura, transições), a música pode subir.
- **Ducking:** abaixa um pouco **antes** da fala começar (~0,3 s) e volta devagar depois (~0,8 s). Abaixar e subir rápido demais "bombeia" e chama atenção.
- Fade de entrada (~1 s) e de saída (~2–3 s); a música acaba junto com o vídeo, não no meio de uma frase musical se der para escolher o ponto.
- Efeitos sonoros por cima da música: o protagonista do momento continua sendo um só (`guias/etapa-sfx.md`).

### Conferir a mixagem final
- No render: `audio.py final <vídeo>` falha se a loudness passar de ±1 LU do alvo ou o pico real passar do teto.
- No programa: a pessoa exporta com a normalização de loudness do programa ligada no alvo do config; depois, o mesmo `audio.py final` no arquivo exportado.
