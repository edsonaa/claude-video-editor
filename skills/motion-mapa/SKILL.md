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
5. **Corpo e fechamento**, na densidade do perfil e do config. Formato de cada item: `tela_cheia`, `sobreposicao`, `sobreposicao_lateral` (diga o lado do rosto) ou `enfase`. Com `video.formato` vertical, pense na área segura e no rosto ocupando o quadro.
6. **Câmera em volta** (se `camera.ativa`): a intenção em palavras (antes, durante, depois) e as batidas fora das animações. Sob tela cheia, nada.
7. **Assets:** liste a pasta de assets antes (o arquivo pode estar lá com outro nome); cada asset que falta ganha tipo e termo de busca. Desenho, forma e diagrama não são asset.
8. **Mostre o plano numerado**, uma linha por item: tempo, formato, ideia, câmera. Num vídeo longo, aprove por trecho, começando pelo gancho.
9. **Grave** `{"itens": [{"id": "mo01", "status": "proposto", "inicio_seq": 0.5, "fim_seq": 4.2, "formato": "tela_cheia", "ideia": "…", "gatilhos": [{"palavra": "…", "tempo_seq": 1.2}], "storyboard": {…}, "camera": "…", "assets": [{"id": "a1", "tipo": "logo", "busca": "Notion"}]}], "trechos": {"gancho_fim": 48.0}}` com `estado.py . --gravar motions <arquivo>`. Ao gravar de novo, **preserve o status** do que já foi aprovado.

## Revisão e aprovação
Pelo chat, por número ("mo04 tira", "mo07 mais simples"). A aprovação aqui é só no chat. Aprovado: status dos itens `aprovado`, `--etapa motion_mapa=concluido` (o estado guarda sobre qual versão do corte o plano foi feito). Anote aprendizados. Próxima etapa: a seguinte no fluxo (`assets` ou `motion-render`). Sugira `/clear` e `/edicao:editar`.
