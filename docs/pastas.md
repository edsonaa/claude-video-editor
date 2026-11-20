# Pastas e arquivos

Três lugares, cada um com um dono. Saber quem grava onde explica quase tudo: por que uma atualização nunca apaga o seu estilo, por que um vídeo pode ser retomado em outra conversa e por que nada que já foi entregue some.

| Lugar | Dono | Regra |
|---|---|---|
| **Motor** (este repositório) | as atualizações | ninguém grava aqui durante o uso; é trocado a cada versão |
| **Você** (`~/.edicao`) | você | nenhuma atualização mexe; tem histórico git |
| **O vídeo** (a pasta do projeto) | você e as etapas | o Claude só grava em `_CLAUDE/` (e em `Renders/`, `Curtos/`, `Publicar/` quando você pede); nunca move, renomeia ou apaga os seus arquivos |

## O motor

```
fluxo-de-edicao/
├── .claude-plugin/          plugin.json (nome e versão) e marketplace.json
├── skills/                  uma pasta por comando /edicao:*
│   ├── montar/              /edicao:montar
│   ├── editar/              /edicao:editar e regras-comuns.md (lidas por todas as skills)
│   ├── iniciar/ … render/   uma skill por etapa (iniciar, preparar, cortes, motion-mapa, assets,
│   │                        motion-render, camera, sfx, legendas, render)
│   ├── painel/              revisão no navegador
│   ├── curtos/              cortes curtos do vídeo pronto
│   └── publicar/            preparar a publicação
├── guias/                   o ofício: princípios, decisões, referências, animação, HyperFrames,
│                            entrega no programa, legendas e áudio, curtos e publicação, e um por etapa
├── ferramentas/             os scripts prontos e testados (veja comandos.md)
│   ├── *.py                 as linhas de comando (estado.py, render.py, painel.py…)
│   ├── edicao/              os módulos que os scripts (e os seus scripts) importam
│   ├── painel_web/          a interface do painel de revisão e das boas-vindas (HTML, CSS e JS,
│                            sem dependências)
│   ├── schema/              o formato do estado do vídeo e da configuração
│   ├── modelos/             o modelo de rastreio de rosto, quando baixado (rosto.py baixar)
│   ├── testes/              os testes (clipe sintético, vídeo de demonstração)
│   └── requirements.txt     numpy e OpenCV
├── efeitos/                 a biblioteca de animações (veja efeitos.md)
│   ├── _comum/              tema.css e tema.js, a base que todo efeito usa
│   └── <efeito>/            index.html, efeito.json, previa.gif
├── estilos/                 perfis completos prontos (limpo, tech-neon, editorial, impacto)
├── transicoes/              transicoes.json: as transições (dissolver, passar pelo preto, clarão, zoom,
│                            empurrar, chicote), com o filtro do render e o efeito do XML
├── legendas/                estilos.json: os padrões de legenda (clássica, caixa, palavra a palavra,
│                            impacto, minimalista, brilho), iguais na prévia do painel e no render
├── presets/                 os pontos de partida da montagem (youtube-apresentador, reels…)
├── modelos/                 o perfil inicial, o formato do perfil e o do estado do vídeo
├── docs/                    esta documentação
├── CHANGELOG.md             o que mudou em cada versão
└── README.md
```

As skills chamam os scripts pelo caminho do motor (`${CLAUDE_PLUGIN_ROOT}/ferramentas/…`) com o Python do seu ambiente. Por isso uma atualização do motor atualiza os scripts de todo mundo.

## Você (`~/.edicao`)

Criada pelo `/edicao:montar` (`config.py criar`). Outro lugar: a variável `EDICAO_HOME`. Para ver onde está: `config.py caminho`.

```
~/.edicao/
├── config.json              as suas escolhas (veja abaixo)
├── perfis/
│   └── <perfil>/            o seu gosto; um canal ou cliente novo é um perfil novo
│       ├── identidade.md     cores com código, fontes, logo, o que nunca usar
│       ├── tema.json         o que os efeitos leem: cores, fontes, pesos, raio, material, movimento
│       ├── estilo-motion.md  como as animações se movem
│       ├── estilo-camera.md  quanto zoom, quando, com que curva
│       ├── estilo-cortes.md  ritmo, folgas, o que cortar
│       ├── estilo-som.md     densidade, níveis, sons preferidos
│       ├── catalogo.md       os efeitos e as peças que combinam com este estilo
│       └── referencias/      os vídeos de referência analisados
├── ajustes/
│   ├── geral.md             o seu jeito de trabalhar, para todas as etapas
│   └── <etapa>.md           o seu jeito numa etapa (prevalece sobre o guia do motor)
├── etapas/                  etapas que você criou (registradas em etapas_proprias)
├── scripts/                 scripts escritos para o seu fluxo, sobre os módulos do motor
├── biblioteca/              assets fixos que voltam em vários vídeos (logos, por exemplo)
├── estoque/                 as suas peças: estilos de legenda, transições, efeitos e motions
│   ├── entrada/<id>/        o que você mandou e espera o Claude (ficha.md, item.json, trecho.mp4)
│   ├── legendas/<id>/       estilo.json + ficha.md (+ o trecho de referência e a prévia)
│   ├── transicoes/<id>/     transicao.json + ficha.md
│   ├── efeitos/<id>/        index.html + efeito.json + ficha.md, como os efeitos do motor
│   └── motions/<id>/        idem, para um jeito de mover
├── venv/                    o ambiente Python do fluxo (fora do git)
└── .git/                    o histórico: toda mudança de perfil e de ajuste pode ser desfeita
```

### `config.json`
Mudado sempre campo a campo (`config.py set <caminho> <valor>`), nunca reescrito. Os blocos:

| Bloco | O que decide |
|---|---|
| `fluxo`, `etapas_proprias` | as etapas, na ordem; as que você criou |
| `revisao` | o programa (`premiere`, `resolve`, `nenhum`…) e as etapas que entregam nele |
| `video` | tipo de vídeo, formato (`16:9`, `9:16`, `1:1`, `4:5`), fps |
| `pastas` | o padrão do nome do projeto e das subpastas (`Brutos`, `Assets`, `Docs`, `Renders`) |
| `transcricao` | motor (WhisperX local ou Scribe na nuvem), idioma, modelo, termos técnicos |
| `notas_faladas` | as frases que abrem e fecham uma nota para o editor |
| `cortes`, `motion`, `camera`, `som` | o que cada etapa usa (roteiro, ferramenta de animação e densidade, seguir o rosto, a biblioteca de sons) |
| `legendas` | o estilo padrão (`estilo`, de `legendas/estilos.json`), saídas, se queima, posição; sem estilo, modo, caracteres e caixa alta valem como antes |
| `audio` | alvo de loudness e pico, redução de ruído, níveis da música |
| `perfil_padrao`, `python` | o perfil dos vídeos novos; o Python do ambiente |

`config.py mostrar` resume tudo e avisa incoerências (uma etapa de som sem biblioteca, por exemplo). O formato completo está em [`ferramentas/schema/config.schema.json`](../ferramentas/schema/config.schema.json).

## O vídeo

Uma pasta por vídeo, no padrão de `pastas.padrao_projeto` (por padrão `AAAA-MM-DD_Nome`). Você abre o Claude Code nela.

```
2026-01-15_Nome/
├── Brutos/                  as suas gravações (o Claude só lê)
├── Assets/                  logos, ícones, prints e o que você mandar para as animações; sons/ com
│                            os efeitos sonoros escolhidos na galeria do painel
├── Docs/                    roteiro e documentos de apoio
├── Renders/                 o vídeo pronto: <projeto>_final_vNN.mp4
├── _CLAUDE/                 tudo o que o Claude gera (veja abaixo)
├── Curtos/
│   └── <nome>/              cada curto é um projeto próprio, com o próprio _CLAUDE/ e Renders/
└── Publicar/
    └── <plataforma>/        o vídeo, texto.txt, legendas, capa e conferencia.md, prontos para subir
```

### `_CLAUDE/`
| Caminho | O que é | Quem grava |
|---|---|---|
| `projeto.json` | o estado do vídeo (a memória do fluxo) | todas as etapas, pelo `estado.py` |
| `briefing.md` | o que você contou sobre o vídeo, organizado | iniciar |
| `briefing_painel.md` | o que você escreveu e escolheu nas boas-vindas do painel, antes de o Claude organizar | painel (boas-vindas) |
| `aprendizados.md` | o caderno de correções que valem para outros vídeos | qualquer etapa, na revisão |
| `palavras_<id>.json` | a transcrição normalizada de cada arquivo | preparar |
| `frases_<id>.txt`, `silencios_<id>.json` | a fala em frases (o que o Claude lê) e o mapa de silêncios | preparar |
| `fala_seq.txt` | a fala no tempo da sequência, depois do corte | motion-mapa |
| `audio/` | `<id>_voz_vNN.wav` (voz tratada), `musica_vNN.wav` (música com ducking) | preparar, sfx |
| `entregas/` | `<projeto>_<etapa>_vNN.xml`, cada entrega para o programa | cortes, motion-render, câmera, sfx |
| `motion/<id>/` | o projeto HyperFrames de cada animação (com `assets/` e `eventos.json`) | motion-render |
| `motion/renders/` | `<id>_vNN.mp4` (tela cheia) e `.mov` (sobreposição com transparência) | motion-render |
| `rosto_<id>.json` | onde está o rosto ao longo de cada arquivo | câmera |
| `legendas/` | `blocos_vNN.json`, `revisao.txt`, `correcoes.json` e as saídas (`.srt`, `.vtt`, `.ass`) | legendas |
| `rascunhos/` | `<projeto>_rascunho_vNN.mp4`, para revisar | render |
| `painel/` | prévias leves para o navegador, miniaturas, o histórico do desfazer, `exemplo.jpg` (o quadro da prévia de legenda das boas-vindas) | painel |
| `curtos/` | `frases.txt` e `frases.json`: a fala do corte final, com id por frase | curtos |
| `publicar/capas/` | as candidatas a capa e a folha `candidatas.png` | publicar |
| `creditos.md` | o que pede crédito na descrição (ícones CC BY, por exemplo) | assets |
| `render_tmp/` | intermediários do render (apagados no fim) | render |

### Regras de arquivo
- **Versão nova, nunca sobrescrever.** Tudo o que é entregue ganha `_vNN` no nome; a versão anterior continua lá.
- **Caminhos.** Dentro do vídeo, o estado guarda caminhos relativos à pasta do projeto. Os brutos ficam com caminho absoluto. Um curto aponta para as mesmas mídias do longo, então mover a pasta de brutos quebra os dois.
- **O que é seu fica intacto.** Os brutos e os seus projetos de edição só são lidos. Antes de gravar fora de `_CLAUDE/` e de `~/.edicao`, o Claude diz o que vai fazer e espera o "sim".
