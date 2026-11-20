---
name: editar
description: "Ponto de entrada da edição de vídeo: mostra em que pé o vídeo está (etapas, pendências, alertas, aprendizados anotados) e abre a etapa certa. Também aplica os aprendizados, mostra as novidades do motor, atualiza o motor e muda a configuração. Use em /edicao:editar, ao abrir ou retomar um vídeo, depois de um /clear, ou quando a pessoa perguntar em que pé está o vídeo."
---

# editar

Motor: `${CLAUDE_PLUGIN_ROOT}` (o `<motor>` das regras). Ferramentas: `<f>` = `<motor>/ferramentas`.

É a recepcionista: não edita nada, mostra onde o vídeo está e abre a skill da etapa certa. A pessoa só precisa lembrar dela.

Antes de tudo, uma vez por sessão, leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md`.

## Configuração
Rode `python3 ${CLAUDE_PLUGIN_ROOT}/ferramentas/config.py mostrar` (no Windows, `python`). Daí em diante use o `python` que ele mostra como `<py>`.
- **Não existe configuração:** a montagem ainda não foi feita. Diga isso em uma linha e ofereça `/edicao:montar` (leva uns 10 minutos com um preset).
- **"novidades no motor":** antes do status, mostre em 2–4 linhas o que mudou (`<py> <f>/config.py novidades`) e marque como lido (`novidades --marcar-lido`).
- **Avisos** de incoerência: mostre e pergunte se quer ajustar agora.

## /edicao:editar
1. **Sem projeto:** se não existe `_CLAUDE/projeto.json` na pasta atual, o vídeo ainda não foi iniciado: ofereça `/edicao:iniciar`. Se a pasta não parecer um projeto (sem brutos, sem padrão de pasta), pergunte se o Claude Code foi aberto no lugar certo.
2. **Status:** `<py> <f>/estado.py . status`. Mostre de forma curta: etapas, trechos feitos, pendências, alertas e aprendizados anotados.
3. **Próximo passo:** diga qual é e pergunte se segue. Com o "sim", abra a skill da etapa (`/edicao:<etapa>`, com `-` no lugar de `_`: `motion_mapa` → `/edicao:motion-mapa`) e siga as instruções dela.
   - Etapa própria da pessoa (está em `etapas_proprias` no config): leia o arquivo indicado em `<pessoa>/` e siga-o, com as regras comuns.
   - Etapa `aguardando_aprovacao`: o próximo passo é continuar essa mesma etapa (a revisão), nunca pular. Ofereça revisar assistindo pelo `/edicao:painel`; pendências `pelo painel` no status são pedidos que a pessoa deixou lá.
   - Alerta de algo desatualizado (o corte mudou depois do plano de animação): mostre primeiro e espere a decisão.
   - Linha `estoque:` no status (peças esperando análise ou ajuste): mencione numa linha e ofereça `/edicao:estoque` (não trava o vídeo).
   - A pessoa pediu outra etapa ou um trecho ("sim, até 3:00"): abra essa etapa e passe o trecho.
4. **Depois da última etapa:** o vídeo está pronto. Ofereça, numa linha, `/edicao:publicar` (títulos, descrição, capítulos, capa, pacote por plataforma) e `/edicao:curtos` (cortes curtos verticais do vídeo).
5. **Uma etapa por vez.** Não encadear etapas sozinho e não dar `/clear` (isso é sempre da pessoa).
6. **Modelo:** lembre, numa linha, o modelo sugerido para a etapa (regras comuns, §8).

## /edicao:editar aprendizados
Siga a §7 das regras comuns.

## /edicao:editar atualizar
1. Descubra como o motor foi instalado:
   - `${CLAUDE_PLUGIN_ROOT}` é um clone git (`git -C ${CLAUDE_PLUGIN_ROOT} status`): mostre os commits novos (`git -C ${CLAUDE_PLUGIN_ROOT} fetch` e `git log --oneline HEAD..@{u}`), peça o "sim" e rode `git -C ${CLAUDE_PLUGIN_ROOT} pull --ff-only`;
   - instalado pelo marketplace: diga para rodar `/plugin update edicao@edicao-de-video` (ou ligar a atualização automática em `/plugin`).
2. Depois: `/reload-plugins`, `<py> <f>/config.py novidades` e os testes (`<py> -m pytest <f>/testes -q`). A pasta da pessoa nunca é tocada.

## /edicao:editar config
Mostre `config.py mostrar` e mude o que a pessoa pedir com `config.py set <caminho> <valor>` (ex.: `revisao.programa resolve`, `transcricao.termos '["VRM","BIOS"]'`). Para mudar o fluxo inteiro ou trocar de preset, ofereça `/edicao:montar`.

## Regras
- Não editar vídeo nem rodar scripts de etapa: isso é das skills de cada etapa.
- Nunca mover, renomear ou apagar arquivos do projeto.
