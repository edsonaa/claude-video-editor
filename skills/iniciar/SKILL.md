---
name: iniciar
description: "Abre um vídeo novo no fluxo de edição: confere a pasta do projeto, cria o estado do vídeo e faz o briefing, pela conversa ou pelo painel no navegador (boas-vindas com verificação, briefing, tipo de vídeo, estilo e padrão de legenda com prévia), sem analisar nenhum arquivo. Use em /edicao:iniciar, quando a pessoa começar um vídeo novo, ou quando a /edicao:editar não achar o projeto."
---

# iniciar

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

Abre o projeto e organiza o briefing. Não analisa mídia: isso é da `preparar`.

- **Lê:** a configuração (pastas, perfil padrão, fluxo), `<pessoa>/ajustes/iniciar.md` e `geral.md`, se existirem.
- **Escreve:** `_CLAUDE/projeto.json` (pelo `estado.py --init`) e `_CLAUDE/briefing.md`. Pelo painel, também o que a pessoa escolheu lá: o fluxo e o formato do tipo de vídeo, o perfil e `video.legendas` no estado, e `_CLAUDE/briefing_painel.md`.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-iniciar-preparar.md`, parte "Iniciar".

## Passo a passo
1. **A pasta.** O Claude Code foi aberto na raiz de um projeto, no padrão do config (`pastas.padrao_projeto`, subpastas `pastas.brutos`, `assets`, `docs`, `renders`)? Se faltar subpasta, pergunte se pode criar (vazia). Se não parecer um projeto, pergunte se foi aberto no lugar certo.
2. **Já iniciado** (`_CLAUDE/projeto.json` existe): não sobrescreva; mostre `estado.py . status` e pergunte se é só para atualizar o briefing.
3. **Perfil:** com um perfil só em `<pessoa>/perfis/`, o padrão do config; com mais de um, pergunte de quem é o vídeo.
4. **Estado:** `<py> <f>/estado.py . --init <nome da pasta> --perfil <perfil>` (o fluxo vem da configuração; um vídeo diferente pode pedir `--fluxo iniciar,preparar,cortes`).
5. **Como fazer o briefing.** Pergunte com o AskUserQuestion: "Como quer fazer o briefing inicial?"
   - **Pelo Claude** (a conversa, como sempre);
   - **Pelo painel** (no navegador: conferir o que está pronto, contar sobre o vídeo, escolher o tipo de vídeo, o estilo das animações e o padrão de legenda, vendo a prévia).

   **Pelo Claude:** peça numa mensagem curta, sem formulário: "Me conta, do jeito que vier, sobre o que é esse vídeo e qualquer direcionamento que você já tenha." Organize sem inventar (as palavras e a intenção dela, nada de tom, público ou ideia que ela não disse), em seções: sobre o vídeo, direcionamentos gerais, observações por etapa. Omita as vazias. Grave em `_CLAUDE/briefing.md` e mostre.
   - Nomes próprios e termos técnicos do briefing: anote numa seção "Termos" (a `preparar` passa para a transcrição, junto com os do config).

   **Pelo painel:**
   1. Rode **em segundo plano** `<py> <f>/painel.py boas-vindas . --navegador` e passe à pessoa o endereço da primeira linha da saída (com o `?t=`), dizendo que é só seguir os passos e clicar em "Enviar para o Claude". Porta ocupada: `--porta 0`.
   2. Espere. Quando ela enviar, o comando termina sozinho (você é avisado pelo fim do processo em segundo plano) com uma linha `ENVIADO {…}` (o resumo em JSON). Código 3 = fechou sem enviar: pergunte se quer continuar pela conversa.
   3. Leia `_CLAUDE/briefing_painel.md` e organize o `briefing.md` com as mesmas regras de cima (sem inventar; os termos na seção "Termos"). As escolhas já estão gravadas no estado (`estado.py . status` mostra o fluxo novo) e, se ela marcou "usar como padrão", na configuração.
   4. Mostre o briefing organizado e as escolhas numa lista curta. Se o resumo trouxe observações (ex.: o tipo de vídeo costuma revisar sem programa e a configuração usa o Premiere), pergunte uma de cada vez.
   5. Faltaram subpastas na verificação? Pergunte se pode criar (vazias), como no passo 1.
6. **Fechar:** `estado.py . --etapa iniciar=concluido` e diga o que falta para a próxima etapa (brutos na pasta, proxies, roteiro em `Docs/` se `cortes.usa_roteiro`). Sugira `/clear` e `/edicao:editar`.

## Regras
- Não abrir nem analisar arquivos de mídia (o painel de boas-vindas só tira um quadro das gravações para a prévia da legenda).
- Nunca mover, renomear ou apagar arquivos do projeto.
