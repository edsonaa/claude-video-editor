# Cortes curtos e publicação

O ofício de tirar vídeos curtos do vídeo longo (`/edicao:curtos`) e de preparar a publicação (`/edicao:publicar`). Os números são pontos de partida: o que funciona para o canal da pessoa vai para os ajustes dela, com a origem.

## Cortes curtos

### O que faz um curto funcionar sozinho
- **Gancho no primeiro segundo.** Quem rola o feed decide em 1–2 s. A primeira frase precisa prender sozinha: uma pergunta, um número, um problema, uma afirmação forte. Comece no gancho, não na introdução ("Olá, pessoal" é o primeiro corte a fazer).
- **Uma ideia só.** Um curto é uma dica, um erro, um resultado, uma história curta. Dois assuntos viram dois curtos.
- **Sem depender do que veio antes.** Fuja de trecho que começa com "e", "mas", "então", "isso", "ele": a pessoa não viu o antes. Se a frase boa começa assim, corte a palavra ou comece na anterior.
- **Fim que entrega.** Termina na resposta, no resultado, na virada. Não no meio do raciocínio nem num "e aí…". Um fim que emenda com o começo faz o vídeo rodar de novo sem a pessoa perceber.
- **Duração:** 20–60 s costuma render mais; o limite é 3 minutos (Shorts e Reels recomendados). Mais longo só se o conteúdo segura: tutorial curto, antes e depois.
- **Ritmo:** mais apertado que o longo. Respiros longos e repetições saem; o roteiro do painel deixa cortar palavra por palavra.

### Imagem vertical
- **Câmera:** recortada em 9:16, com o rosto no centro horizontal e os olhos no terço de cima. O `curtos.py criar` centraliza pelo rastreio de rosto quando existe; ajuste fino no painel (← →).
- **Tela, bancada, placa:** recortar uma tela horizontal corta o conteúdo. O padrão é encaixar (o quadro inteiro, com fundo desfocado). Se o detalhe importa, uma aproximação no ponto certo (recorte com `x` e `zoom`) funciona melhor que a tela inteira pequena.
- **Áreas seguras:** a interface dos apps cobre a parte de baixo (legenda do post, nome, música) e a lateral direita (curtir, comentar). Legenda queimada a ~27–30% da borda de baixo; nada importante no quarto de baixo nem na faixa da direita.
- **Animações** do longo (16:9) não servem no vertical. Se o curto pede uma, ela é feita em 9:16.

### Som e legenda
- Legenda queimada **palavra a palavra**, letra grande, blocos curtos (2–5 palavras): a maioria assiste sem som.
- A mesma loudness do longo (−14 LUFS, pico −1 dBTP). Música própria do curto, com licença para vídeo curto. No YouTube, Shorts com mais de 60 s não podem usar música com direitos da biblioteca (Content ID).

## Publicação

### Título
- Promete o que o vídeo entrega, com o específico na frente: o problema, o número, o resultado. Nada que o vídeo não cumpra: a retenção cai e a plataforma percebe.
- Até 100 caracteres, mas só uns 60–70 aparecem na busca e uns 40 no feed de Shorts: o importante no começo.
- 2–3 opções para a pessoa escolher, a primeira com a sua sugestão.

### Descrição e capítulos (YouTube)
- A primeira linha é o gancho (é o que aparece antes do "mais"). Depois: o que o vídeo cobre, os links fixos da pessoa e os capítulos.
- **Capítulos:** o primeiro em 0:00, pelo menos 3, em ordem, cada um com 10 s ou mais. Se uma regra falha, o YouTube ignora a lista inteira sem avisar. Títulos curtos, pelo assunto ("Medindo a tensão de entrada"), não "Parte 2". Uns 3–4 num vídeo de 5 minutos, 5–10 num de 20.
- **Hashtags:** até 15 (acima disso o YouTube ignora todas); as 3 primeiras aparecem acima do título. **Tags:** sinal fraco, mas ajudam com grafias diferentes e erros de digitação comuns; 500 caracteres somados.

### Instagram e TikTok
- Legenda: a primeira linha é o gancho (~125 caracteres aparecem no Instagram). Uma pergunta no fim puxa comentário.
- Hashtags: até 5 no Instagram (limite desde dezembro de 2025), específicas do assunto; no TikTok, poucas e específicas.

### Capa
- Do próprio vídeo, num quadro nítido, bem exposto, com o rosto expressivo; o `publicar.py capa` sugere as candidatas.
- Pensada para o tamanho pequeno: um rosto, um objeto, no máximo 3–4 palavras grandes e alto contraste. Texto sobre a capa é com a pessoa (ou com o programa dela).
- No vertical, a grade do perfil corta a capa: o essencial no centro.

### Limites (conferidos em novembro de 2026)
| | YouTube | Shorts | Instagram (Reels) | TikTok |
|---|---|---|---|---|
| Título | 100 | 100 (~40 visíveis) | — | — |
| Descrição / legenda | 5.000 bytes | 5.000 bytes | 2.200 | 2.200 (seguro) |
| Hashtags | 15 | 15 | 5 | — |
| Duração | — | até 3 min | até 3 min para ser recomendado | 10 min (seguro) |

Limites mudam com frequência. O `publicar.py limites` mostra os que o script confere e quando. Passados alguns meses, ou se uma plataforma recusar algo, confira na ajuda oficial de cada uma e corrija `edicao/publicar.py` (`LIMITES`, `CONFERIDO`): é uma mudança que vale para todos, proponha ao motor.
