---
name: montar
description: "Monta (ou muda) o fluxo de edição de vídeo da pessoa: confere o ambiente, parte de um preset (YouTube com apresentador, tutorial com tela, aula técnica, reels, narrado, só cortes), pergunta só o que falta, cria a configuração e o perfil em ~/.edicao, instala as dependências e testa. Use em /edicao:montar, na primeira vez, ou quando a pessoa quiser mudar o fluxo, trocar de preset, criar um perfil ou uma etapa própria."
---

# montar

Motor: `${CLAUDE_PLUGIN_ROOT}` (o `<motor>`). Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Leia também `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` (§0 e §1).

Esta skill não edita vídeo: ela deixa tudo pronto para a `/edicao:editar`. O motor (skills, guias, ferramentas) já vem pronto e se atualiza; o que é da pessoa fica em `~/.edicao` (`<pessoa>`): as escolhas (`config.json`), o estilo (`perfis/`) e os ajustes de ofício (`ajustes/`). Nenhuma atualização mexe lá.

## Como falar
- Português, frases curtas, sem jargão sem explicar. Muita gente aqui nunca editou com código.
- Uma pergunta por vez, sempre com a sua sugestão já dita ("Eu sugiro X, porque Y. Prefere outra coisa?"). Use o AskUserQuestion quando houver opções claras.
- Antes de instalar algo, diga o que é, para que serve e espere o "sim".

## 0. Já existe uma montagem?
`python3 <f>/config.py mostrar` (no Windows, `python`).
- **Existe:** mostre o resumo e pergunte o que mudar. Caminhos:
  - mudar uma escolha → `config.py set <caminho> <valor>`;
  - ligar ou desligar etapas → `config.py set fluxo '[...]'`, mostrando os avisos;
  - trocar de preset → mostre as diferenças entre o atual e o novo (`config.py presets`) e aplique campo a campo com `set`; o perfil e os ajustes continuam;
  - perfil novo (outro canal, um cliente) → `config.py perfil-novo <nome> [--de <perfil>]`;
  - etapa própria → escreva `<pessoa>/etapas/<nome>.md` com a pessoa (o que lê, o que faz, como entrega, como revisa, seguindo as regras comuns) e registre em `etapas_proprias` (`config.py set etapas_proprias.<nome> etapas/<nome>.md`) e no `fluxo`.
- **Montagem antiga** (skills geradas pela versão anterior desta skill, em `~/.claude/skills/<prefixo>*/` com `regras-comuns.md` e um `montagem.md`): ofereça migrar. Leia o `montagem.md` para as escolhas, copie o perfil para `<pessoa>/perfis/`, e leve para `<pessoa>/ajustes/<etapa>.md` só o que as skills antigas tinham **a mais** que os guias do motor (o ofício pessoal). Não apague as skills antigas: diga quais são e peça para a pessoa removê-las (senão os dois fluxos aparecem).
- **Não existe:** siga.

## 1. Ambiente
Confira, sem instalar nada: sistema, Python (3.10+), FFmpeg/ffprobe, Git, Node.js (só se for usar o HyperFrames) e a placa de vídeo (uma GPU NVIDIA acelera muito a transcrição local; sem ela, funciona mais devagar, ou com transcrição na nuvem). Mostre o que existe e o que falta.

## 2. Preset
`<py> <f>/config.py presets`. Pergunte que tipo de vídeo ela faz e sugira o preset que mais encaixa (os presets estão em `${CLAUDE_PLUGIN_ROOT}/presets/`). Explique em uma linha o fluxo dele. Depois faça **só as perguntas do preset** (campo `perguntas` do JSON), uma por vez, e as de ambiente que faltarem:
- nome (como chamar a pessoa);
- transcrição: local (WhisperX, grátis, precisa de máquina boa) ou nuvem (Scribe, paga por hora de áudio). Pesquise o preço e a versão atuais antes de recomendar;
- notas faladas: sugira o costume ("nota de edição … fim da nota") e combine as frases;
- biblioteca de sons, se o fluxo tiver `sfx`: onde está, ou montar uma básica depois.

Quer decidir tudo em detalhe (outro programa, outro formato, ordem das etapas)? Siga `${CLAUDE_PLUGIN_ROOT}/guias/decisoes.md` e grave as respostas pelo `--json` do passo 3.

## 3. Criar
1. **Ambiente Python** em `<pessoa>/venv` (explique: isola as bibliotecas do fluxo): `python3 -m venv ~/.edicao/venv`, depois `<venv>/bin/python -m pip install -r <f>/requirements.txt pytest` (no Windows, `<venv>\Scripts\python.exe`). Daí em diante, `<py>` é esse python.
2. **Configuração:** `<py> <f>/config.py criar --nome "<nome>" --preset <preset> --estilo <estilo> --python <py> --json '<respostas>'` (o estilo é escolhido no passo 4; pode fazer o 4 antes), com as respostas no formato do config (ex.: `{"revisao":{"programa":"resolve"},"transcricao":{"termos":["VRM","BIOS"]},"som":{"biblioteca":"D:/Sons"}}`). Mostre o resumo e os avisos.
3. **Histórico:** `git init` em `<pessoa>` e um primeiro commit ("montagem: preset <preset>"). Assim toda mudança de perfil e de ajuste pode ser desfeita.
4. **Testes das ferramentas:** `<py> -m pytest <f>/testes -q`. Geram um clipe sintético e passam o fluxo inteiro pelos scripts (1–3 minutos). Passou: Python, FFmpeg e os scripts funcionam neste computador. Falhou: resolva antes de seguir.
5. **Só o que o fluxo usa**, uma instalação por vez, explicada:
   - transcrição local: WhisperX no venv. Com GPU NVIDIA, confirme que o PyTorch enxerga a placa antes de transcrever;
   - Scribe: a chave em `ELEVENLABS_API_KEY` (nunca no config);
   - câmera que segue o rosto: `<py> <f>/rosto.py baixar`;
   - sons: `<py> <f>/sons.py indexar <biblioteca>`;
   - HyperFrames roda por `npx`, sem instalar; a versão fica fixa por vídeo (ver `guias/hyperframes.md`).

## 4. Perfil
**Estilo de partida.** A biblioteca tem estilos prontos, perfis completos com cores, fontes, curvas, câmera, cortes e som (`<py> <f>/config.py estilos`). Mostre a prévia de cada um: `${CLAUDE_PLUGIN_ROOT}/estilos/<estilo>/previa.png` (os mesmos seis efeitos em cada estilo). Sugira o `estilo_sugerido` do preset e pergunte. O escolhido entra no `config.py criar ... --estilo <estilo>` (ou, depois, `config.py perfil-novo <nome> --estilo <estilo>`); sem estilo, fica o perfil inicial neutro. As fontes do estilo precisam estar instaladas no computador que renderiza (são livres, licença OFL): confira e, se faltar, explique como instalar.

Para ele virar o estilo **dela**:
- **identidade** (cores com código, fontes, logotipo, o que nunca usar): pergunte agora, leva 2 minutos, e grave em `identidade.md`. Sem animação no fluxo, pule;
- **referências:** ofereça analisar 5–10 trechos de vídeos de que ela gosta (`${CLAUDE_PLUGIN_ROOT}/guias/referencias.md`). Recomendado antes do primeiro vídeo de verdade com animação, mas não trava: dá para fazer depois, com `/edicao:montar` de novo. As referências medem o jeito geral (o perfil); uma peça específica que ela queira ter (um estilo de legenda, uma transição, um efeito, um motion) vai para o estoque (`/edicao:estoque`).

## 5. Teste num clipe curto
Peça um vídeo de 1–3 minutos (pode ser gravado só para isso) e rode o fluxo inteiro com a pessoa pela `/edicao:editar`, etapa por etapa. A primeira entrega no programa é o arquivo de teste (regras comuns, §4). É aqui que nascem os scripts que ainda faltam e os primeiros aprendizados.

## 6. Fechamento
Mostre, em destaque e antes de tudo, **o comando do dia a dia**: "Para editar, abra o Claude Code na pasta do vídeo e digite `/edicao:editar`. Ela vê em que etapa o vídeo está e te guia." Depois, curto:
- o ciclo: `/clear` e `/edicao:editar` a cada etapa; o caderno de aprendizados e o `/edicao:editar aprendizados`;
- onde está o que é dela (`<pessoa>`) e que as atualizações do motor (`/edicao:editar atualizar`) nunca mexem lá;
- para mudar o fluxo depois: `/edicao:montar`.
Faça um commit em `<pessoa>` ("montagem concluída").

## Regras
- Nunca mover, renomear ou apagar arquivos de vídeo ou de projeto da pessoa, nem as skills antigas dela.
- Nunca sobrescrever a configuração: mudanças são campo a campo, com `config.py set`.
- Nunca gravar no motor (`${CLAUDE_PLUGIN_ROOT}`): ele é trocado a cada atualização.
- Instalar só depois de explicar e de a pessoa confirmar. Não prometer resultado de uma ferramenta sem testar no computador dela.
