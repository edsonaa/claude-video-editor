---
name: motion-render
description: "Constrói e renderiza cada animação aprovada no plano (HyperFrames ou a ferramenta da pessoa), confere os arquivos, anota os eventos para o som e entrega as animações nas trilhas certas do programa de edição. Funciona por trecho (\"renders até 3:00\", \"o gancho\"). Use em /edicao:motion-render, depois do plano de animação aprovado."
---

# motion-render

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

A etapa mais longa e a que mais depende do ofício.

- **Lê:** o plano (`estado.py . motions`, e `--item moNN` para cada um), os assets, o perfil (`identidade.md`, `estilo-motion.md`, `catalogo.md`, peças-base), a configuração (`motion.ferramenta`, `video.formato`, `video.fps`), `<pessoa>/ajustes/motion-render.md` e `geral.md`.
- **Escreve:** os projetos em `_CLAUDE/motion/<id>/`, os renders em `_CLAUDE/motion/renders/<id>_vNN.<mp4|mov>`, os eventos em `_CLAUDE/motion/eventos.json`, o `render` de cada item no plano, a entrega.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-motion-render.md`, `${CLAUDE_PLUGIN_ROOT}/guias/oficio-motion.md` e, com HyperFrames, `${CLAUDE_PLUGIN_ROOT}/guias/hyperframes.md` (as armadilhas custaram rodadas inteiras). Outra ferramenta: pesquise a documentação atual e anote o que aprender em `<pessoa>/ajustes/motion-render.md`.

## Passo a passo
1. `<py> <f>/estado.py . status`: o plano aprovado e o trecho pedido (só os itens que **começam** nele).
2. **Versão da ferramenta fixa no vídeo:** na primeira animação, anote `--set ferramentas.hyperframes <versão>` (a mais nova); todo comando usa essa versão.
3. **Item com efeito da biblioteca** (`"efeito"` no plano): comece por ele em vez de uma página em branco:
   `<py> <f>/efeitos.py criar <efeito> _CLAUDE/motion/<id> --perfil <pessoa>/perfis/<perfil> --params <params.json> --duracao <fim_seq − inicio_seq> --fps <midia.fps> --formato <video.formato>`
   Ele copia a composição com o tema do perfil e o conteúdo nas variáveis, a duração exata em frames e o tamanho do formato, e grava os eventos de som em `eventos.json`. Daí em diante é um projeto HyperFrames comum: ajuste o que o item pedir (o storyboard manda), sem mexer na biblioteca. Imagens de parâmetros (`imagem`) são copiadas para `assets/`; sem o arquivo, o efeito mostra o marcador de ASSET FALTANDO no lugar.
   Um efeito que ficou bom e é novo vira peça do perfil (catálogo); se serve para qualquer pessoa, sugira propô-lo à biblioteca do motor.
4. **Item sem efeito**, o ciclo do guia: tempo (gatilho = tempo da palavra − início do item), construir (storyboard é especificação; tela cheia com fundo e câmera virtual; sobreposição transparente, do lado oposto ao rosto; saída marcada com a direção), anotar os eventos para o som, `check`, snapshots dos momentos-chave e **olhar**.
5. **Renderizar** em fila, em segundo plano, com versão no nome. Duração em frames pela taxa do vídeo (`edicao.tempo`; ver a conta em `hyperframes.md`).
6. **Conferir o arquivo:** `<py> <f>/midia.py <render>` (resolução, fps, frames = duração do item), transparência na sobreposição, um ou dois quadros (`<py> <f>/contato.py <render> _CLAUDE/motion/<id>_folha.png --cada 6`), a última letra de toda palavra com gradiente.
7. **Registrar** no plano: `status: "renderizado"`, `render: {"arquivo": "<absoluto>", "versao": N, "duracao": <s>}`, a direção da saída e os eventos (os do `eventos.json` do efeito, somados ao `inicio_seq` do item). Grave o bloco `motions` inteiro (`--gravar motions`); mudar só status e render não muda a versão do plano.
8. **Entrega** (regras comuns, §4): `exportar_xml.py exportar . --etapa motion_render` põe as telas cheias em V3 e as sobreposições em V4, cada uma no seu tempo. Marcadores de pós ("desfoque do fundo aqui") e de asset faltando.
9. **Resumo** e `--etapa motion_render=aguardando_aprovacao` (ou `em_andamento`, se faltam trechos).

## Revisão e aprovação
- Por número: "mo04 mais lento", "mo07 tira". Só os citados, versão nova, entrega nova.
- **Crítica de qualidade geral** ("básico", "sem vida") pede **refazer**, não retocar: releia as referências, diga em uma frase a nova direção de cada uma e construa de novo.
- Mudou a duração de um item: mude no plano e na composição, registre de novo (o status vai avisar a câmera e o som).
- Aprovado: um padrão que se repetiu vira item do `catalogo.md` do perfil; um elemento que ficou bom vira peça-base (com o "sim" da pessoa). `--etapa motion_render=concluido`, sugerir `/clear` e `/edicao:editar`.
