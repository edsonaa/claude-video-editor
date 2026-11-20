---
name: curtos
description: "Tira cortes curtos (Shorts, Reels, TikTok) do vídeo longo já cortado: lê a fala em frases, propõe os trechos que se sustentam sozinhos, cria cada curto como um projeto próprio em Curtos/<nome> (mesmos quadros do longo, enquadramento vertical pelo rosto) e leva cada um até o vídeo pronto. Use em /edicao:curtos, quando a pessoa quiser reaproveitar o vídeo longo em vídeos curtos."
---

# curtos

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** o estado do vídeo longo (cortes aprovados, transcrição, animações, rastreio de rosto `_CLAUDE/rosto_<id>.json` se a etapa de câmera rodou), o perfil, `<pessoa>/ajustes/curtos.md` e `geral.md`.
- **Escreve:** `_CLAUDE/curtos/frases.txt|json` no longo, o bloco `curtos` do estado do longo, e um projeto novo por curto em `<vídeo>/Curtos/<nome>/` (com o próprio `_CLAUDE/projeto.json`).
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/curtos-e-publicacao.md`, parte "Cortes curtos". Leia antes.

## Passo a passo
1. `<py> <f>/estado.py . status`: o corte do longo precisa estar aprovado (curto feito sobre um corte que ainda muda fica velho).
2. **Frases:** `<py> <f>/curtos.py frases .` e leia `_CLAUDE/curtos/frases.txt` inteiro. Cada frase tem id (`f012`) e tempo do vídeo.
3. **Pontos de partida:** `<py> <f>/curtos.py sugerir . --min 20 --max 60` (a faixa vem do pedido da pessoa e do guia). As notas medem só a forma: começo que se sustenta, fim fechado, pausa natural. Quem escolhe é você, pelo conteúdo: um gancho nos primeiros segundos, uma ideia só, um fim que entrega.
4. **Proposta** à pessoa: 3–6 curtos, cada um com nome curto, `de`–`ate` (ids de frase), duração, o gancho (a primeira frase) e por que funciona sozinho. Uma pergunta só: quais fazer.
5. **Criar** os aprovados: `<py> <f>/curtos.py criar . <nome> --de f012 --ate f019 --titulo "<título>"`. Cada um vira `Curtos/<nome>/`: mesmos quadros do longo; câmera recortada em 9:16, centrada no rosto quando há rastreio; tela encaixada sobre fundo desfocado. Sem rastreio e com a pessoa fora do centro: rode `<py> <f>/rosto.py rastrear` no trecho antes (ou ajuste o enquadramento no painel).
6. **Revisar** cada curto no painel: `<py> <f>/painel.py abrir Curtos/<nome> --navegador` (veja `/edicao:painel`). Lá a pessoa vê o vertical, ajusta o enquadramento de cada segmento (← →, encaixar), corta ou devolve palavras pelo roteiro e aprova os cortes.
7. **Terminar** cada curto no projeto dele, com o Claude Code aberto em `Curtos/<nome>` (ou passando a pasta aos scripts):
   - legendas queimadas palavra a palavra: `<py> <f>/legendas.py gerar Curtos/<nome> --modo palavra --max-caracteres 20`, depois revisar (`/edicao:legendas`);
   - o vídeo: `<py> <f>/render.py final Curtos/<nome>` (vertical 1080x1920, legenda queimada, loudness no alvo);
   - publicar: `/edicao:publicar` na pasta do curto.
8. `<py> <f>/curtos.py listar .`: o pé de cada curto. Resumo curto à pessoa.

## Cuidados
- Animações do longo em 16:9 não entram no vertical (o render avisa). Se o curto pede uma, é um item novo no plano do curto, em 9:16.
- Música do longo não vem junto: o curto pede uma faixa própria (`audio.py musica` no projeto do curto), com licença para vídeo curto.
- O curto aponta para as mesmas mídias do longo (caminhos absolutos): mover a pasta de brutos quebra os dois.
