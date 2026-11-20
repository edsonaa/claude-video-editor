# Regras comuns das skills de edição

Lidas uma vez por sessão por todas as skills `/edicao:*`. O que vale para todas as etapas fica aqui; o que é de uma etapa fica na skill dela.

## 0. Onde está cada coisa
- **`<motor>`**: a pasta do plugin, que cada skill informa no topo (o `${CLAUDE_PLUGIN_ROOT}` dela). Skills, guias e ferramentas. **Nunca grave nada no motor**: ele é trocado a cada atualização.
- **`<f>`** = `<motor>/ferramentas`: os scripts prontos (`--help` em cada um).
- **`<pessoa>`**: a pasta da pessoa, por padrão `~/.edicao` (ou a de `EDICAO_HOME`); `<py> <f>/config.py caminho` mostra. Nela:
  - `config.json`: as escolhas (leia com `<py> <f>/config.py mostrar`, uma vez por sessão);
  - `perfis/<nome>/`: o gosto. O perfil do vídeo está no estado (`perfil`);
  - `ajustes/<etapa>.md` e `ajustes/geral.md`: o ofício pessoal. **Prevalece sobre os guias do motor**;
  - `etapas/`: etapas que a pessoa criou; `scripts/`: scripts que ela (ou você, por ela) escreveu.
- **`<py>`**: o `python` do config; sem ele, `python3` (ou `python` no Windows).
- **Pasta do vídeo**: onde o Claude Code foi aberto. Tudo o que o Claude gera fica em `_CLAUDE/`.

Ordem de quem manda, do mais geral ao mais específico: guia do motor → `ajustes/geral.md` → `ajustes/<etapa>.md` → perfil (gosto) → briefing e notas faladas do vídeo → o que a pessoa pediu agora.

## 1. Conversa e segurança
- Falar com a pessoa (o `nome` do config) em português, de forma curta. Uma pergunta por vez, sempre com a sua sugestão.
- Nunca mover, renomear ou apagar arquivos do projeto. Nunca sobrescrever um arquivo já entregue: versão nova (`_v02`).
- Antes de instalar algo ou gravar fora de `_CLAUDE/` e de `<pessoa>`, diga o que vai fazer e espere o "sim".

## 2. Estado do vídeo sem ler inteiro
O `_CLAUDE/projeto.json` cresce muito. Ler e mudar sempre pelo `<py> <f>/estado.py`, nunca abrindo nem editando à mão:
- `estado.py . status` mostra onde o vídeo está; `estado.py . <bloco>` resume um bloco (`--json` para o bloco inteiro); `--item <id>` mostra um item;
- `--set <caminho> <valor>`, `--etapa <etapa>=<status>`, `--pendencia <etapa> "<texto>" [--de <id>]`, `--resolver <id>`;
- `--gravar <bloco> <arquivo.json>` grava um bloco inteiro (é assim que você grava o resultado de uma etapa).

Estado inválido não é gravado: leia o erro e corrija. Conflito de revisão: outro processo gravou no meio; leia de novo e refaça.

## 3. Scripts
- Prontos em `<f>` (ver `<f>/README.md`). Segundos viram frames **só** por `edicao.tempo`.
- Falta um script (sincronia, bordas pela energia, keyframes de câmera, render, FCPXML…)? Na primeira vez que a etapa precisar, escreva-o em `<pessoa>/scripts/`, importando os módulos do motor (`sys.path.insert(0, "<f>")`, `from edicao import tempo, estado, ff`), teste num trecho curto e anote o uso em `<pessoa>/ajustes/<etapa>.md` ("script: `scripts/sync.py <args>` — o que faz"). Nos próximos vídeos, reaproveite.
- Um script desses ficou bom e vale para qualquer pessoa? Sugira, numa linha, propô-lo ao motor (issue ou PR no repositório do plugin).

## 4. Entrega, conforme `revisao.programa` do config
- **premiere / resolve:** `<py> <f>/exportar_xml.py exportar . --etapa <etapa>`. **Na primeira entrega de todas** (sem registro em `<pessoa>/ajustes/geral.md` de que o formato foi validado), gere antes `--teste`, peça para a pessoa abrir no programa e conferir clipes, áudio, marcadores e tempos, e anote o resultado em `ajustes/geral.md` ("XML validado no Premiere 2026 em dd/mm; fades OK"). O que não funcionou vira opção anotada ali (ex.: `--menos-um`, `--cores cores.json`).
- **finalcut / outro:** o motor ainda não gera esse formato: escreva o exportador na primeira entrega (regra 3), começando por um arquivo de teste e copiando o que o próprio programa exporta (`guias/entrega-no-editor.md`).
- **painel (qualquer programa):** ao entregar cortes, plano de animação, animações, som ou legendas para revisão, ofereça `/edicao:painel`: a pessoa assiste já cortado, com animações, legenda e som, corta ou devolve frases pelo roteiro e deixa pedidos no ponto exato. Os pedidos voltam como pendências (`pelo painel`) no status.
- **nenhum:** a pessoa revisa assistindo. No painel, cortes, animações, som e legendas já dão para revisar sem render; o **rascunho** em resolução baixa fica para o que o painel não mostra (movimentos de câmera, o vídeo inteiro montado). Rascunho: (o script de render da etapa `render`, com `--rascunho`; se ainda não existir, escreva-o agora seguindo `guias/entrega-no-editor.md`, caminho C). O final sai na etapa `render`.
- A volta pelo programa: `exportar_xml.py volta . <exportado.xml>` (sem `--aplicar` mostra a diferença; os ajustes da pessoa valem mais).
- Trilhas da entrega: V1 câmera, V3 animações em tela cheia, V4 sobreposições, V5 legenda animada; A1 voz (a tratada, quando houver), A2 música (quando houver), efeitos sonoros abaixo.
- O vídeo final exportado do programa: confira a loudness com `<py> <f>/audio.py final <arquivo>` (alvo do config).

## 5. Caderno de aprendizados (`_CLAUDE/aprendizados.md`)
Durante a revisão de qualquer etapa, anote na hora toda correção, elogio ou preferência que vale **para outros vídeos**:
- "zoom mais sutil", "esse som ficou ótimo": **anota**; "tira essa frase": **não anota** (só deste vídeo); na dúvida, anota com "(talvez só deste vídeo)".
- Formato: `- [ ] <etapa> · <o que foi pedido, com contexto> · <dd/mm>`. Nunca apagar linhas. Anotar não é mudar.

## 6. Trechos, ponto salvo e fechar uma etapa
- Cortes e plano de animação olham o vídeo inteiro. Render, câmera e som podem ir por trecho ("até 3:00", "o gancho"). Um item pertence ao trecho em que começa; cada trecho lê o que os anteriores fizeram.
- **Ponto salvo:** trecho ou etapa terminado, revisões aplicadas, entrega gerada. Só aí sugerir `/clear` e `/edicao:editar`.
- **Pendência:** pedido ainda não aplicado é anotado na hora (`--pendencia`) e aparece no status.
- **Resumo no chat** ao entregar: curto, com o que precisa da atenção da pessoa e o caminho do arquivo. Status `aguardando_aprovacao`.
- **Revisão:** pela citação de número (`mo04 mais lento`), pelo tempo da sequência (`estado.py` converte pela lista de cortes; `edicao.linha.Linha.seq_para_origem`), pelos pedidos do painel (pendências com o ponto) ou pela volta do programa. Ajustar só o que foi citado, versão nova, anotar aprendizados.
- **Fechar a etapa** (aprovada inteira): `--etapa <etapa>=concluido`, dizer quantos aprendizados ficaram anotados, sugerir `/clear` e `/edicao:editar`. Nunca encadear a próxima etapa sozinho.

## 7. Aplicar os aprendizados (quando a pessoa pedir: `/edicao:editar aprendizados`)
1. Ler as linhas `- [ ]` do caderno do vídeo atual (e de outros vídeos, se ela indicar).
2. Propor o destino de cada uma:
   - **gosto** (cores, quanto zoom, quanto som, curvas preferidas) → o perfil (`<pessoa>/perfis/<perfil>/estilo-*.md`, `identidade.md`, `catalogo.md`), com número e origem;
   - **ofício pessoal** (jeito de trabalhar que vale para todos os vídeos dela) → `<pessoa>/ajustes/<etapa>.md` ou `geral.md`, com origem;
   - **ofício universal** (vale para qualquer pessoa, corrige um erro do motor) → mesmo destino, e sugerir propor ao motor (issue/PR);
   - **só daquele vídeo** → nada.
3. A pessoa filtra. Gravar só o aprovado, mostrando antes o texto das mudanças maiores. Marcar cada linha: `[x] → <onde entrou>` ou `[-]`.
4. Se `<pessoa>` tem git (`git -C <pessoa> status`), fazer um commit com o resumo ("aprendizados de <vídeo>").

## 8. Economia de limite
- `/clear` entre etapas; ler resumos (frases, `estado.py`), não arquivos inteiros; um quadro só quando há dúvida real; render em segundo plano.
- Modelo sugerido: o mais leve para `editar`, `iniciar` e `assets`; intermediário para `preparar` e `legendas`; o mais capaz para `cortes`, `motion-mapa`, `motion-render`, `camera`, `sfx` e `render`. Trocar logo depois do `/clear` não custa nada.
