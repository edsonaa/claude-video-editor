# Novidades do motor

Cada versão nova do motor (skills, guias e ferramentas) entra aqui, a mais nova em cima. A skill `/edicao:editar` mostra o que mudou desde a última vez que a pessoa viu. Ao lançar uma versão, suba o `version` em `.claude-plugin/plugin.json` para o mesmo número (um teste confere).

## 0.2.0
- **Motor separado da configuração.** O repositório virou um plugin (`edicao`): as skills de cada etapa vêm prontas e se atualizam. As escolhas, o estilo e os ajustes de cada pessoa ficam em `~/.edicao/` e nenhuma atualização mexe neles.
- **Comandos novos:** `/edicao:montar` (montagem e mudanças no fluxo) e `/edicao:editar` (o dia a dia), mais uma skill por etapa (`/edicao:cortes`, `/edicao:camera`…) e a etapa `render` para quem não usa programa de edição.
- **Presets:** YouTube com apresentador, tutorial com tela, aula técnica, reels, narrado e só os cortes. A montagem parte de um deles e pergunta só o que falta.
- **Ajustes pessoais** (`~/.edicao/ajustes/<etapa>.md`): os aprendizados de ofício entram ali, sem editar o motor.
- `config.py` (escolhas, perfis, novidades) e `estado.py --init` lendo o fluxo da configuração.

## 0.1.0
- Ferramentas prontas e testadas em `ferramentas/`: estado do vídeo, inventário, silêncios, transcrição (WhisperX e Scribe), XML para Premiere/Resolve com a volta, tempo e timecode, folha de contato, índice de sons e rastreio de rosto.
