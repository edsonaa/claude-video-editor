---
name: motion-mapa
description: "Planeja as animações de um vídeo cortado: onde entra animação, o que mostra, em que formato, com storyboard no gancho, a intenção da câmera em volta de cada uma e os assets que faltam. Não anima nada: propõe no chat, ajusta com a pessoa e grava o plano numerado (mo01, mo02…). Use em /edicao:motion-mapa, depois dos cortes aprovados."
---

# motion-mapa

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

A etapa que mais decide a qualidade do vídeo. Mudar aqui é barato; depois do render, um conceito fraco custa uma rodada inteira.

- **Lê:** a fala no tempo da sequência, o briefing, as notas de edição sobre animação, o perfil (`identidade.md`, `estilo-motion.md`, `estilo-camera.md`, `catalogo.md`), a configuração (`motion.densidade`, `camera.ativa`, `video.formato`), `<pessoa>/ajustes/motion-mapa.md` e `geral.md`.
- **Escreve:** o bloco `motions` no estado (o plano). Nada é renderizado.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-motion-mapa.md` e `${CLAUDE_PLUGIN_ROOT}/guias/oficio-motion.md`. Leia os dois antes de propor.

## Passo a passo
1. `<py> <f>/estado.py . status`: os cortes precisam estar `concluido`.
2. **A fala no tempo da sequência:** `<py> <f>/transcrever.py fala . --saida _CLAUDE/fala_seq.txt`. Uma frase por linha, com o tempo exato de cada corte. Animação que começa ou termina junto com um corte usa o **tempo do corte**, não o da palavra.
3. **Trechos:** fim do gancho, tipo de vídeo, começo do fechamento. Confirme numa mensagem curta, já com a proposta.
4. **Gancho primeiro**, quase frase a frase, com storyboard (conceito, camadas, câmera, batidas, herói, vida, saída). Antes de mostrar, releia com as perguntas do guia (o conceito nasce desta fala? a energia combina? estou repetindo a fórmula?).
5. **Repertório:** `<py> <f>/efeitos.py listar` mostra os efeitos prontos da biblioteca (título, contador, barras, lista, comparação, card lateral, print com destaque, cursor, capítulo, transição, tarja, logo, ênfase), e `efeitos.py mostrar <efeito>` os parâmetros e quando usar; o `catalogo.md` do perfil diz quais combinam com o estilo. **O conteúdo decide**: use um efeito quando ele for a melhor forma *daquela* ideia, e proponha algo próprio sempre que servir melhor (no gancho, de preferência um conceito do assunto). Quando usar um, anote no item `"efeito": "<nome>"` e `"params": {…}` (os do `mostrar`).
6. **Corpo e fechamento**, na densidade do perfil e do config. Formato de cada item: `tela_cheia`, `sobreposicao`, `sobreposicao_lateral` (diga o lado do rosto) ou `enfase`. Com `video.formato` vertical, pense na área segura e no rosto ocupando o quadro.
7. **Câmera em volta** (se `camera.ativa`): a intenção em palavras (antes, durante, depois) e as batidas fora das animações. Sob tela cheia, nada.
8. **Assets:** liste a pasta de assets antes (o arquivo pode estar lá com outro nome); cada asset que falta ganha tipo e termo de busca. Desenho, forma e diagrama não são asset.
9. **Mostre o plano numerado**, uma linha por item: tempo, formato, ideia, câmera. Num vídeo longo, aprove por trecho, começando pelo gancho.
10. **Grave** `{"itens": [{"id": "mo01", "status": "proposto", "inicio_seq": 0.5, "fim_seq": 4.2, "formato": "tela_cheia", "ideia": "…", "gatilhos": [{"palavra": "…", "tempo_seq": 1.2}], "storyboard": {…}, "camera": "…", "assets": [{"id": "a1", "tipo": "logo", "busca": "Notion"}]}], "trechos": {"gancho_fim": 48.0}}` com `estado.py . --gravar motions <arquivo>`. Ao gravar de novo, **preserve o status** do que já foi aprovado e mantenha os itens que a pessoa pôs pela galeria do painel (`origem: painel`, já `aprovado`, com `efeito` e `params`): eles entram no plano como estão, e você planeja o resto em volta deles.

## Revisão e aprovação
Pelo chat, por número ("mo04 tira", "mo07 mais simples"). A aprovação aqui é só no chat. Aprovado: status dos itens `aprovado`, `--etapa motion_mapa=concluido` (o estado guarda sobre qual versão do corte o plano foi feito). Anote aprendizados. Próxima etapa: a seguinte no fluxo (`assets` ou `motion-render`). Sugira `/clear` e `/edicao:editar`.
