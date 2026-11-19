---
name: assets
description: "Busca os arquivos reais que as animações planejadas precisam e que não dá para desenhar em código: logos oficiais, ícones de coleções abertas e prints de páginas públicas, com licença conferida, mostrados numa folha numerada para a pessoa escolher. Use em /edicao:assets, depois do motion-mapa, ou avulso (\"busca o logo do Notion\")."
---

# assets

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

Pula sozinha se nada faltar.

- **Lê:** os `assets` de cada item do plano (`estado.py . motions --json`), a pasta de assets do projeto, a biblioteca fixa da pessoa (`<pessoa>/biblioteca/`), `<pessoa>/ajustes/assets.md` e `geral.md`.
- **Escreve:** os arquivos na pasta de assets do projeto, o status de cada asset no plano, `_CLAUDE/creditos.md` (o que pede crédito na descrição).
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-assets.md` (o que é de quem, fontes, licenças). Leia antes.

## Passo a passo
1. Liste o que falta: assets do plano que não estão na pasta do projeto nem na biblioteca (procure também por nomes parecidos).
2. **Busque** pelas fontes do guia. Pesquise as fontes e as licenças atuais antes; o script de busca (e o de print, com navegador sem interface) é escrito na primeira vez em `<pessoa>/scripts/`. Descarte o claramente errado (marca errada, logo antigo, print com banner de cookies).
3. **Mostre uma folha numerada por rodada**: uma imagem com as opções lado a lado sobre o fundo do vídeo (`identidade.md`). A opção 1 é a recomendação. A pessoa responde por número ("a1 1, a3 2, a4 eu mando").
4. **Grave** com a extensão da opção escolhida (SVG é melhor que PNG), atualize o plano (`assets[].arquivo`, `status: "ok" | "pessoa_manda"`) e o `creditos.md`. Pergunte quais vão para a biblioteca fixa.
5. **Resumo:** o que entrou (arquivo, fonte, licença), o que ficou faltando e o que a pessoa precisa gravar ou mandar, com o nome de arquivo esperado. O render constrói com um marcador visível no lugar do que faltar, então não bloqueia.
6. `--etapa assets=concluido` (ou `nao_precisa`), sugerir `/clear` e `/edicao:editar`.

## Regras
- Logo é marca: só a oficial, sem redesenhar; sem a oficial, fica faltando, nunca um "parecido".
- Imagem sem licença clara não entra: vira "a pessoa manda". Nada de tela logada nem de conta de terceiros.
