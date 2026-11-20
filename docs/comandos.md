# Comandos

Os scripts do motor, em `ferramentas/`. As skills chamam todos eles por você; esta página serve para entender o que cada um faz, ou para rodar à mão. Todos têm `--help` em português, e o texto abaixo é o mesmo do `--help`.

Para rodar à mão, use o Python do seu ambiente (`~/.edicao/venv/bin/python`, ou `~/.edicao/venv/Scripts/python.exe` no Windows) e o caminho do motor (`config.py motor` mostra onde ele está). Nos exemplos, `<pasta>` é a pasta do vídeo; dentro dela, use `.`.

| Grupo | Scripts |
|---|---|
| Configuração e estado | [`config.py`](#configpy), [`estado.py`](#estadopy) |
| Preparar o material | [`midia.py`](#midiapy), [`silencios.py`](#silenciospy), [`transcrever.py`](#transcreverpy), [`audio.py`](#audiopy), [`tempo.py`](#tempopy) |
| Entregar e revisar | [`exportar_xml.py`](#exportar_xmlpy), [`painel.py`](#painelpy), [`render.py`](#renderpy), [`contato.py`](#contatopy) |
| Animação, câmera, som e legendas | [`efeitos.py`](#efeitospy), [`rosto.py`](#rostopy), [`sons.py`](#sonspy), [`legendas.py`](#legendaspy) |
| Depois do vídeo | [`curtos.py`](#curtospy), [`publicar.py`](#publicarpy) |

## Configuração e estado

### config.py
A sua configuração (`~/.edicao`).

```text
A configuração da pessoa (~/.edicao, ou EDICAO_HOME): as escolhas que o motor lê.

Uso:
  config.py presets                          os pontos de partida, com o que cada um faz
  config.py criar --nome N --preset P [--perfil padrao] [--estilo limpo] [--python caminho] [--json '{"video":{…}}']
                                             cria ~/.edicao (config, perfil inicial, pastas); nunca sobrescreve
  config.py mostrar [--json]                 resumo das escolhas + avisos de incoerência
  config.py set <caminho> <valor>            muda um campo (valor em JSON ou texto); valida antes de gravar
  config.py validar
  config.py perfil-novo <nome> [--de <perfil existente> | --estilo <estilo da biblioteca>]
  config.py estilos                          os estilos prontos (veja estilos/<nome>/previa.png)
  config.py novidades [--marcar-lido]        o que mudou no motor desde a última vez
  config.py caminho                          onde fica a pasta da pessoa
  config.py motor                            onde fica o motor (para os comandos das skills)
```

### estado.py
O estado do vídeo (`_CLAUDE/projeto.json`).

```text
Lê e muda o estado do vídeo sem abrir o arquivo inteiro.

Uso (sempre com a pasta do vídeo primeiro):
  estado.py <pasta> status                      onde o vídeo está
  estado.py <pasta> <bloco> [--json]            resumo de um bloco (cortes, motions, marcadores, pendencias, midia…)
  estado.py <pasta> --item <id>                 um item inteiro (s003, mo04, cam07, p02…)
  estado.py <pasta> --set <caminho> <valor>     muda um campo (valor em JSON ou texto)
  estado.py <pasta> --etapa <etapa>=<status>    muda o status de uma etapa
  estado.py <pasta> --pendencia <etapa> "<texto>" [--de <id>]
  estado.py <pasta> --resolver <id>
  estado.py <pasta> --gravar <bloco> <arquivo.json|->   grava um bloco inteiro (scripts de etapa)
  estado.py <pasta> --validar
  estado.py <pasta> --init <nome> [--perfil P] [--fluxo iniciar,preparar,…]

Status de etapa: pendente, em_andamento, aguardando_aprovacao, aguardando_<quem>, concluido, nao_precisa.
```

## Preparar o material

### midia.py
Inventário da mídia.

```text
Inventário da mídia (ffprobe): duração, fps exato, resolução, áudio, data de gravação e alertas.

Uso:
  midia.py <arquivos ou pastas…> [--json] [--saida inventario.json] [--contar-frames]
  midia.py <arquivos ou pastas…> --estado <pasta do vídeo>
      grava o bloco `midia` do estado (ids pelo nome do arquivo; mantém ids,
      tipos e proxies já decididos). Confira o tipo de cada um (camera, tela, audio).

Ordem: data de gravação (metadado); sem data, nome em ordem natural.
Alertas: arquivo ilegível, vídeo sem áudio, fps diferente entre vídeos, taxa variável (VFR).
```

### silencios.py
Mapa de silêncios.

```text
Mapa de silêncios e de trechos com som de um arquivo (silencedetect do FFmpeg).

Uso:
  silencios.py <arquivo> [--limiar -35] [--minimo 0.3] [--inicio S] [--duracao S] [--saida silencios.json]

Esta ferramenta só mapeia: quem decide o corte é a etapa de cortes.
O limiar depende do ambiente da gravação; confira num trecho antes de confiar.
```

### transcrever.py
Transcrição e o que o Claude lê.

```text
Transcrição: roda o motor, normaliza, e gera o que o Claude lê.

Uso:
  transcrever.py rodar <video|audio> <saida.json> [--motor whisperx|scribe] [--idioma pt]
                 [--termos "Nome, Termo"] [--offset S] [--modelo M]
      extrai o WAV 16 kHz mono, transcreve e grava já normalizado (palavras/1).
      --offset: soma S segundos (áudio externo → tempo da câmera).

  transcrever.py normalizar <bruto.json> <saida.json> [--offset S] [--origem arquivo]
      converte uma transcrição do WhisperX ou do Scribe para o formato único.

  transcrever.py frases <palavras.json> [--silencios silencios.json] [--video cam01] [--saida frases.txt]
      uma frase por linha, com tempo, pausas e ⟨som sem palavra⟩ (lacunas).

  transcrever.py lacunas <palavras.json> <silencios.json> [--minimo 0.6] [--json]
      trechos com som e sem palavra: retranscreva SEM termos/contexto.

  transcrever.py notas <palavras.json> [--abertura "nota de edição"] [--fechamento "fim da nota"]
      acha as notas faladas para o editor.

  transcrever.py fala <pasta do vídeo> [--saida fala_seq.txt]
      a fala no tempo da sequência (pelos cortes do estado), com o tempo exato de cada corte.

Sempre confira trechos com som e sem palavra: com contexto inicial o motor às
vezes inventa frases ou engole takes repetidos.
```

### audio.py
Medir e tratar a voz, música com ducking.

```text
Áudio do vídeo: medir, tratar a voz e montar a música de fundo com ducking.

Uso (os padrões vêm do bloco `audio` da configuração):
  audio.py medir <arquivo> [--inicio S --duracao S] [--canal N] [--json]
      loudness (LUFS), pico real (dBTP), piso de ruído, fala/ruído, clipping, com recomendações
  audio.py tratar <arquivo> [<saida.wav>] [--estado <pasta> --id cam01] [--alvo -14] [--pico -1]
                  [--ruido auto|nenhuma|leve|media|forte] [--passa-alta 80] [--compressao nenhuma|leve|media]
                  [--canal N] [--inicio S --duracao S]
      passa-alta → redução de ruído (pelo piso medido) → compressão → loudness em duas passadas.
      A saída tem a mesma duração e o mesmo início do original (o atraso dos filtros é medido e
      compensado). Com --estado/--id, grava em _CLAUDE/audio/<id>_voz_vNN.wav e anota no estado
      (midia.arquivos[].audio_tratado): o XML passa a usar a voz tratada. Para ouvir antes de tratar
      o arquivo inteiro: --inicio/--duracao num trecho de 20–30 s.
  audio.py musica <pasta> <musica> [--nivel-livre -20] [--nivel-fala -32] [--ataque 0.3] [--liberacao 0.8]
                  [--fade-in 1] [--fade-out 2.5] [--inicio-musica S]
      a música do tamanho do vídeo, abaixando sob a fala (pelos cortes e pela transcrição);
      grava _CLAUDE/audio/musica_vNN.wav e anota em sfx.musica (o XML a põe numa trilha própria)
  audio.py final <arquivo> [--alvo -14] [--pico -1]
      confere a mixagem final contra o alvo (para o render e para o que a pessoa exporta do programa)
```

### tempo.py
Segundos, quadros e timecode.

```text
Converte entre segundos, frames e timecode, com a taxa exata.

Uso:
  tempo.py --fps 29.97 12.5            segundos → frame e timecode
  tempo.py --fps 29.97 --frame 375     frame → segundos e timecode
  tempo.py --fps 29.97 00:00:12;15     timecode → frame e segundos (';' = drop-frame)

--df mostra o timecode em drop-frame (só 29,97 e 59,94).
```

## Entregar e revisar

### exportar_xml.py
FCP 7 XML para Premiere e Resolve, e a volta.

```text
Entrega em FCP 7 XML (Premiere, Resolve) e leitura da volta.

Uso:
  exportar_xml.py exportar <pasta do vídeo> [--etapa cortes] [--teste] [--cores cores.json]
                  [--fade 1] [--menos-um] [--saida arquivo.xml]
      Gera _CLAUDE/entregas/<projeto>_<etapa>_vNN.xml, sempre numa versão nova,
      e anota a entrega no estado. --teste: 3–4 clipes, para conferir o formato
      no programa ANTES de usar de verdade.

  exportar_xml.py volta <pasta do vídeo> <exportado.xml> [--aplicar]
      Lê a sequência que a pessoa exportou do programa e reconstrói os cortes de V1.
      Sem --aplicar só mostra a diferença; com --aplicar grava os cortes no estado
      (os ajustes da pessoa valem mais). Avisa o que estiver fora do modelo.

cores.json: {"duvida_take": 4294741314, …} com os valores de <pproColor>
copiados de um XML exportado pelo Premiere com marcadores daquela cor.
```

### painel.py
O painel de revisão no navegador e as boas-vindas de um vídeo novo (a `/edicao:iniciar` oferece o briefing por ali).

```text
Painel de revisão no navegador: assistir ao corte, apontar ajustes e aprovar.

Uso (a pasta do vídeo primeiro):
  painel.py abrir <pasta> [--porta 8765] [--navegador] [--ocioso 120]
      sobe o painel em http://127.0.0.1:<porta>/?t=<token> e fica rodando até Ctrl+C
      (ou até --ocioso minutos sem a página aberta). Só aceita conexões desta máquina.
  painel.py previas <pasta> [--todas]
      gera as prévias leves das mídias que o navegador não toca (ProRes, HEVC, áudio
      PCM em MOV), da voz tratada e das animações com transparência
  painel.py verificar <pasta>
      o que o navegador toca direto e o que precisa de prévia (sem gerar nada)
  painel.py boas-vindas <pasta> [--porta 8765] [--navegador] [--ocioso 60]
      o começo de um vídeo novo pelo navegador: verificação, briefing, tipo de vídeo, estilo e
      padrão de legenda (com prévia). Ao enviar, grava no estado e em _CLAUDE/briefing_painel.md,
      mostra o resumo em JSON e termina (código 0). Fechado sem enviar: código 3.

No painel: o vídeo toca já cortado, com as animações, a legenda e o som; o roteiro
mostra o que saiu do corte (riscado) e deixa cortar ou devolver frases; os pedidos
viram pendências no estado (_CLAUDE/projeto.json), que o Claude aplica na etapa.
```

### render.py
O vídeo pronto pelo FFmpeg.

```text
Render do vídeo pelo FFmpeg, a partir do estado: para quem não revisa num programa de edição.

Uso (a pasta do vídeo primeiro):
  render.py plano <pasta> [--formato 9:16] [--de S --ate S]
      o que vai entrar (pedaços com quadros exatos, enquadramento, animações, som), sem renderizar
  render.py rascunho <pasta> [--de S --ate S] [--legenda auto|ass|animada|nao]
      resolução baixa e rápido, para revisar (_CLAUDE/rascunhos/<projeto>_rascunho_vNN.mp4)
  render.py final <pasta> [--de S --ate S] [--formato F] [--legenda …] [--perfil <pasta do perfil>]
      na resolução do formato (16:9 1920x1080, 9:16 1080x1920, 1:1, 4:5), em <pastas.renders>/<projeto>_final_vNN.mp4

O que entra: os cortes (frames exatos, a mesma conversão da entrega em XML), a voz (a tratada,
quando houver) com fades curtos nas junções, as animações renderizadas por cima (tela cheia e com
transparência), a legenda queimada (ASS das legendas atuais, ou a legenda animada), a música e os
efeitos sonoros com o ganho de cada um, e a loudness no alvo do config (audio.alvo_lufs, pico_dbtp).

Enquadramento por segmento (cortes.segmentos[].quadro): {"modo": "inteiro"}, {"modo": "cortar",
"x": 0.42, "y": 0.5, "zoom": 1.0} (x/y: o centro, de 0 a 1) ou {"modo": "encaixar"} (o quadro inteiro
sobre um fundo desfocado). Sem quadro: inteiro se a proporção bate; câmera recortada no centro; tela encaixada.
Movimentos de câmera não são aplicados (o render avisa). Cada render é uma versão nova; o original nunca muda.
```

### contato.py
Folha de contato.

```text
Folha de contato: um quadro a cada N frames, lado a lado, com o tempo e o frame em cada um.

Uso:
  contato.py <video> <saida.png> [--inicio S] [--fim S] [--cada 4] [--colunas 6] [--largura 320] [--maximo 60]

Tempos aceitam segundos (75.2) ou mm:ss (1:15.2). Precisa de numpy e OpenCV.
```

## Animação, câmera, som e legendas

### efeitos.py
A biblioteca de efeitos e de estilos.

```text
Biblioteca de efeitos (HyperFrames) e de estilos.

Uso:
  efeitos.py listar [--formato tela_cheia|sobreposicao|...] [--json]
  efeitos.py mostrar <efeito>                 parâmetros, duração, eventos de som, quando usar
  efeitos.py estilos                          os estilos prontos (perfis completos)
  efeitos.py criar <efeito> <destino> [--perfil <pasta do perfil> | --estilo <nome> | --tema tema.json]
                   [--param chave=valor …] [--params arquivo.json] [--duracao S] [--fps 30000/1001]
                   [--formato 16:9|9:16|1:1|4:5] [--gsap gsap.min.js]
      copia o efeito para <destino> (ex.: _CLAUDE/motion/mo04) com o tema e o conteúdo nas variáveis
      da composição, a duração exata em frames e o tamanho do formato. Depois: `npx hyperframes check`,
      `snapshot` e `render` (sobreposição: --format mov). Os eventos de som ficam em eventos.json.
  efeitos.py vitrine <saida.png> [--estilo E | --perfil P] [--efeitos a,b,c] [--formato 16:9]
      uma imagem com vários efeitos no mesmo estilo, para ver como o estilo fica
  efeitos.py previa <efeito> <saida.gif> [--estilo E | --perfil P] [--formato 16:9] [--quadros 36]
      GIF de prévia pelos snapshots do HyperFrames (precisa do HyperFrames; HYPERFRAMES_CMD muda o comando).

Valores de --param são JSON quando possível (listas: --param itens='["a","b"]').
```

### rosto.py
Rastreio de rosto.

```text
Rastreio de rosto (YuNet, OpenCV): onde está o rosto ao longo do vídeo.

Uso:
  rosto.py baixar [--pasta modelos/]
      baixa o modelo YuNet (licença MIT, ~230 KB) para a pasta de ferramentas.
  rosto.py rastrear <video> <saida.json> [--modelo caminho.onnx] [--amostras 5]
                    [--inicio S] [--fim S] [--confianca 0.7]

Saída: amostras (centro cx/cy e largura w do maior rosto, de 0 a 1, ou null) e
uma trilha suavizada, sem buracos. Roda local e leve; não precisa de GPU.
```

### sons.py
A biblioteca de sons e o pacote inicial.

```text
Biblioteca de sons: índice e busca.

Uso:
  sons.py indexar <pasta da biblioteca> [--indice indice.json]
      Mede cada som (duração, tempo até o pico, nível) e grava o índice
      (padrão: <biblioteca>/indice.json). Incremental; mantém licenca/tags/nota.
  sons.py buscar <indice.json> [--categoria whoosh] [--texto "vidro"] [--dur-max 1.5] [--json]
  sons.py categorias <indice.json>
  sons.py pacote <pasta> [--sobrescrever]
      Cria o pacote inicial: 12 sons sintetizados pelo motor (whoosh, impacto, pop,
      clique, sino, subida, falha), livres de direitos, em pastas por categoria, e o índice.

Para alinhar: um som com pico em P segundos entra em (tempo do evento − P).
Confira sempre a licença de uso de cada som (campo "licenca", escrito à mão).
```

### legendas.py
Legendas.

```text
Legendas do vídeo, a partir da transcrição e dos cortes (tempo da sequência).

Uso (a pasta do vídeo primeiro; os padrões vêm do bloco `legendas` da configuração):
  legendas.py gerar <pasta> [--modo frase|palavra] [--max-caracteres 42] [--linhas 2]
                    [--correcoes correcoes.json] [--manter-hesitacoes] [--quebrar-no-corte]
      divide a fala em blocos (l001, l002…) e grava _CLAUDE/legendas/blocos_vNN.json e revisao.txt
  legendas.py ver <pasta>                      os blocos atuais, com caracteres por segundo e avisos
  legendas.py corrigir <pasta> <id> "<texto>"  troca o texto de um bloco (mantém os tempos), versão nova
  legendas.py exportar <pasta> [--formatos srt,vtt,ass,hyperframes] [--perfil <pasta do perfil>]
                       [--formato 16:9] [--de S --ate S]
      srt/vtt: para o programa de edição, o YouTube e plataformas de curso
      ass: para queimar no render (FFmpeg: -vf "ass=arquivo.ass"); no modo palavra, a palavra
           falada fica na cor de destaque do perfil
      hyperframes: parâmetros do efeito legenda-animada para o trecho [de, ate)

correcoes.json: {"palavra errada": "palavra certa", …} (palavras inteiras, sem diferenciar maiúsculas).
```

## Depois do vídeo

### curtos.py
Cortes curtos.

```text
Cortes curtos (Shorts, Reels, TikTok) a partir do vídeo longo já cortado.

Uso (a pasta do vídeo longo primeiro):
  curtos.py frases <pasta>
      a fala do corte final em frases com id (f001…) e tempo da sequência:
      _CLAUDE/curtos/frases.txt (para ler) e frases.json
  curtos.py sugerir <pasta> [--min 20] [--max 60] [-n 8]
      janelas de frases na duração pedida, com nota e motivos (pontos de partida, não decisão)
  curtos.py criar <pasta> <nome> --de f012 --ate f019 [--formato 9:16] [--titulo "…"]
      cria <pasta>/Curtos/<nome>/ como um projeto próprio: os cortes do trecho (os mesmos
      quadros do longo), o enquadramento vertical de cada segmento (centrado no rosto se
      houver _CLAUDE/rosto_<id>.json; tela encaixada) e o fluxo cortes → legendas → render.
      --de/--ate também aceitam segundos da sequência.
  curtos.py listar <pasta>
      os curtos criados e em que pé está cada um

Depois de criar: revisar no painel (painel.py abrir <pasta do curto>), legendas e render no
projeto do curto, como em qualquer vídeo.
```

### publicar.py
Publicação.

```text
Publicação: capítulos, capa, textos por plataforma (validados) e a pasta pronta para subir.

Uso (a pasta do vídeo primeiro):
  publicar.py limites
      os limites de cada plataforma que o script confere (e quando foram conferidos)
  publicar.py capitulos <pasta> [<arquivo.txt>|-] [--das-animacoes] [--gravar]
      cada linha: "<onde> <título>", onde = 1:23 (tempo do vídeo), f012 (frase do curtos.py frases),
      s003 (segmento) ou mo04 (animação). --das-animacoes usa os marcadores de capítulo do plano.
      Confere as regras do YouTube (0:00, pelo menos 3, 10 s cada) e mostra a lista pronta.
  publicar.py capa <pasta> [-n 6]
      candidatas a capa do corte final (nítidas, bem expostas, com rosto): _CLAUDE/publicar/capas/
  publicar.py capa <pasta> --escolher 3
  publicar.py definir <pasta> <textos.json>
      {"youtube": {"titulo", "descricao", "tags": [], "hashtags": []},
       "instagram": {"legenda", "hashtags": []}, "tiktok": {"legenda", "hashtags": []}}
      (Shorts usam os textos de "youtube", ou "shorts" se existir)
  publicar.py conferir <pasta> [--plataformas youtube,shorts,instagram,tiktok]
  publicar.py pacote <pasta> [--plataformas …] [--forcar]
      Publicar/<plataforma>/: o vídeo final (link, sem duplicar quando dá), texto.txt, legendas
      SRT/VTT, a capa e conferencia.md. Recusa se a conferência tiver erro (sem --forcar).

O envio para as plataformas é da pessoa: o pacote deixa tudo pronto para colar e subir.
```

## Módulos para os seus scripts

Os scripts acima são finos: o trabalho está nos módulos de `ferramentas/edicao/`, que os seus scripts (em `~/.edicao/scripts/`) podem importar:

```python
import sys
sys.path.insert(0, "<motor>/ferramentas")
from edicao import estado, tempo, linha, ff
```

| Módulo | Para quê |
|---|---|
| `edicao.tempo` | a única conversão de segundos para quadros e timecode (`Taxa`, drop-frame) |
| `edicao.linha` | origem ↔ sequência pelos cortes (`Linha`: `seq_para_origem`, `origem_para_seq`) |
| `edicao.estado` | ler, editar e gravar o estado com validação, versões e conflito (`ler`, `editar`, `gravar`) |
| `edicao.ff` | chamar o FFmpeg e o ffprobe, ler áudio |
| `edicao.midia`, `edicao.silencios`, `edicao.transcricao` | inventário, silêncios, transcrição normalizada e frases |
| `edicao.audio` | loudness, tratamento da voz, música com ducking, normalização da mixagem |
| `edicao.legendas` | blocos, SRT, VTT, ASS, versões das legendas |
| `edicao.xmeml` | o FCP 7 XML |
| `edicao.efeitos` | os efeitos e o tema |
| `edicao.render` | o render (plano, enquadramento, montagem) |
| `edicao.painel` | os dados e as mudanças do painel |
| `edicao.curtos`, `edicao.publicar` | curtos e publicação |
| `edicao.contato`, `edicao.sons`, `edicao.rosto` | folha de contato, índice de sons, rastreio de rosto |
| `edicao.config` | a configuração e os presets |

Regra de ouro: segundos viram quadros **só** pelo `edicao.tempo`, e o estado muda **só** pelo `edicao.estado`.

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `EDICAO_HOME` | outra pasta para o que é seu (o padrão é `~/.edicao`) |
| `FFMPEG`, `FFPROBE` | o caminho do FFmpeg e do ffprobe, se não estiverem no PATH |
| `WHISPERX` | o caminho do `whisperx`, se não estiver no PATH |
| `ELEVENLABS_API_KEY` | a chave do Scribe (transcrição na nuvem); nunca no config |
| `HYPERFRAMES_CMD` | outro comando para o HyperFrames (o padrão é `npx --yes hyperframes@<versão>`) |
| `GSAP_LOCAL` | uma cópia local do GSAP para os testes rodarem sem internet |
| `ATUALIZAR_ESPERADO` | `1` aceita uma mudança de propósito no XML de referência dos testes |

## Testes

```bash
<py> -m pip install -r ferramentas/requirements.txt pytest
<py> -m pytest ferramentas/testes -q
```
Geram um clipe sintético e um vídeo de demonstração e passam o fluxo pelos scripts. Sem internet e sem GPU. Com o HyperFrames instalado (`HYPERFRAMES_CMD`), também conferem cada efeito com o `check` real.
