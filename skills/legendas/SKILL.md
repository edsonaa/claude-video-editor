---
name: legendas
description: "Faz as legendas do vídeo pela transcrição e pelos cortes: blocos numerados (l001…) revisados com a pessoa, entregues como arquivo (SRT/VTT para o programa, YouTube e plataformas de curso) ou queimadas na imagem, inclusive palavra a palavra no estilo de vídeo curto. Use em /edicao:legendas, depois do corte travado."
---

# legendas

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** os cortes e a transcrição (pelo estado), o **estilo de legenda** do vídeo (`video.legendas` no estado, escolhido nas boas-vindas; senão `legendas.estilo` da configuração), a configuração (`legendas`: saídas, queimar, posição; `video.formato`), o perfil (cores e fontes, para a queimada), `<pessoa>/ajustes/legendas.md` e `geral.md`.
- **Estilos:** `legendas/estilos.json` no motor (clássica, caixa, palavra a palavra, impacto, minimalista, brilho) e os estilos do estoque da pessoa (`estoque.py listar --tipo legenda`), que valem igual. O estilo define modo, caixa alta, caracteres por linha e o visual da queimada; o painel mostra a legenda no mesmo estilo que o render queima. Para trocar só neste vídeo: `estado.py . --set video.legendas.estilo <id>` e gere de novo. A pessoa pode arrastar a legenda no painel (`video.legendas.deslocamento`) e ajustar a entrada e a saída de blocos (versão nova do arquivo de blocos): ao gerar de novo, avise que esses ajustes de tempo se perdem e pergunte antes.
- **Escreve:** `_CLAUDE/legendas/blocos_vNN.json` (os blocos, editáveis), `revisao.txt`, os arquivos exportados, o bloco `legendas` do estado.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/legendas-e-audio.md`, parte "Legendas". Leia antes.

## Passo a passo
1. `<py> <f>/estado.py . status`: o corte precisa estar aprovado. Legenda feita sobre um corte que ainda muda vai ter os tempos errados (o status avisa).
2. **Grafia antes de dividir.** Leia as frases (`_CLAUDE/frases_<id>.txt`) atrás de nomes, marcas e termos técnicos que a transcrição errou. Confira pelos termos do config, pelo briefing e pelo roteiro, se houver. Escreva `_CLAUDE/legendas/correcoes.json` (`{"errado": "certo"}`, palavras inteiras). Na dúvida sobre um termo, pergunte.
3. **Gerar:** `<py> <f>/legendas.py gerar . --correcoes _CLAUDE/legendas/correcoes.json` (o modo e os limites vêm do estilo de legenda do vídeo; `--modo`, `--max-caracteres` e `--linhas` mudam só desta vez). Leia `_CLAUDE/legendas/revisao.txt` e os avisos (bloco rápido demais para ler, linha comprida).
4. **Ajustar** o que ler mal: `legendas.py corrigir . l014 "<texto certo>"` mantém os tempos. Para juntar ou separar blocos, gere de novo com outros limites, ou edite o JSON (cada bloco tem `inicio`, `fim`, `linhas` e `palavras`) e gere a versão com o próximo número.
5. **Entregar**, conforme o config:
   - **arquivo** (`saidas`: srt, vtt): `legendas.py exportar . --formatos srt,vtt`. No Premiere e no Resolve, a pessoa importa o SRT como trilha de legenda; o YouTube e as plataformas de curso aceitam o SRT ou o VTT direto no upload.
   - **queimada sem programa** (`queimar`, `revisao.programa: nenhum`): `legendas.py exportar . --formatos ass --perfil <pessoa>/perfis/<perfil>`; o render queima o ASS (no modo palavra, a palavra falada acende na cor de destaque).
   - **queimada animada** (reels, ou queimada com programa): `legendas.py exportar . --formatos hyperframes --de <s> --ate <s>` por trecho e
     `<py> <f>/efeitos.py criar legenda-animada _CLAUDE/motion/legendas_<trecho> --perfil <pessoa>/perfis/<perfil> --params <json exportado> --duracao <ate − de> --fps <midia.fps> --formato <video.formato>`;
     `check`, `snapshot`, render em MOV com alpha. Anote `estado.py . --set legendas.render '{"arquivo": "<mov>", "inicio_seq": <de>, "duracao": <s>}'` (com um trecho só; com vários, junte os MOVs antes): o XML põe a legenda em V5.
6. **Resumo:** quantos blocos, o que foi corrigido, os avisos que ficaram e onde está cada arquivo. `--etapa legendas=aguardando_aprovacao`.

## Revisão e aprovação
Por id: "l014 está escrito errado", "l020 quebra depois de 'placa'". Pelo tempo do vídeo: converta pela lista de cortes. Corrigiu uma palavra que vai voltar em outros vídeos? Anote no caderno (a grafia vai para `transcricao.termos` do config). Se o corte mudar depois, as legendas são geradas de novo (as correções do `correcoes.json` continuam valendo). Aprovado: `--etapa legendas=concluido`, `/clear` e `/edicao:editar`.
