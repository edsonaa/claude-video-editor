---
name: iniciar
description: "Abre um vídeo novo no fluxo de edição: confere a pasta do projeto, cria o estado do vídeo com as etapas da pessoa e organiza o briefing ditado por ela, sem analisar nenhum arquivo. Use em /edicao:iniciar, quando a pessoa começar um vídeo novo, ou quando a /edicao:editar não achar o projeto."
---

# iniciar

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

Abre o projeto e organiza o briefing. Não analisa mídia: isso é da `preparar`.

- **Lê:** a configuração (pastas, perfil padrão, fluxo), `<pessoa>/ajustes/iniciar.md` e `geral.md`, se existirem.
- **Escreve:** `_CLAUDE/projeto.json` (pelo `estado.py --init`) e `_CLAUDE/briefing.md`.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-iniciar-preparar.md`, parte "Iniciar".

## Passo a passo
1. **A pasta.** O Claude Code foi aberto na raiz de um projeto, no padrão do config (`pastas.padrao_projeto`, subpastas `pastas.brutos`, `assets`, `docs`, `renders`)? Se faltar subpasta, pergunte se pode criar (vazia). Se não parecer um projeto, pergunte se foi aberto no lugar certo.
2. **Já iniciado** (`_CLAUDE/projeto.json` existe): não sobrescreva; mostre `estado.py . status` e pergunte se é só para atualizar o briefing.
3. **Perfil:** com um perfil só em `<pessoa>/perfis/`, o padrão do config; com mais de um, pergunte de quem é o vídeo.
4. **Estado:** `<py> <f>/estado.py . --init <nome da pasta> --perfil <perfil>` (o fluxo vem da configuração; um vídeo diferente pode pedir `--fluxo iniciar,preparar,cortes`).
5. **Briefing:** peça numa mensagem curta, sem formulário: "Me conta, do jeito que vier, sobre o que é esse vídeo e qualquer direcionamento que você já tenha." Organize sem inventar (as palavras e a intenção dela, nada de tom, público ou ideia que ela não disse), em seções: sobre o vídeo, direcionamentos gerais, observações por etapa. Omita as vazias. Grave em `_CLAUDE/briefing.md` e mostre.
   - Nomes próprios e termos técnicos do briefing: anote numa seção "Termos" (a `preparar` passa para a transcrição, junto com os do config).
6. **Fechar:** `estado.py . --etapa iniciar=concluido` e diga o que falta para a próxima etapa (brutos na pasta, proxies, roteiro em `Docs/` se `cortes.usa_roteiro`). Sugira `/clear` e `/edicao:editar`.

## Regras
- Não abrir nem analisar arquivos de mídia.
- Nunca mover, renomear ou apagar arquivos do projeto.
