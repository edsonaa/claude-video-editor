---
name: publicar
description: "Prepara a publicação do vídeo pronto: título, descrição, capítulos, tags, hashtags e legenda de post para YouTube, Shorts, Instagram e TikTok, conferidos contra os limites de cada plataforma; candidatas a capa tiradas do vídeo; e a pasta Publicar/ com tudo pronto para subir. Use em /edicao:publicar, depois do render final, ou quando a pessoa pedir título, descrição, capítulos ou capa."
---

# publicar

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** o estado (cortes, frases, animações de capítulo, legendas exportadas, a entrega final do render), o briefing e o perfil (tom de voz), `<pessoa>/ajustes/publicar.md` e `geral.md` (fórmulas de título que funcionam, hashtags fixas, links da descrição).
- **Escreve:** o bloco `publicacao` do estado (textos, capítulos, capa), `_CLAUDE/publicar/capas/`, `<vídeo>/Publicar/<plataforma>/`.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/curtos-e-publicacao.md`, parte "Publicação". Leia antes.

## Passo a passo
1. `<py> <f>/estado.py . status`: precisa de um render final do vídeo inteiro (`render.py final`). A pessoa revisa num programa? Peça o caminho do arquivo exportado e registre-o em `entregas` (`etapa: render`, `tipo: final`).
2. **Plataformas:** horizontal vai para o YouTube; vertical vai para Shorts, Instagram e TikTok. Confirme com a pessoa em uma linha.
3. **Capítulos** (YouTube, vídeos de uns 3 minutos para cima): leia `_CLAUDE/curtos/frases.txt` (gere com `<py> <f>/curtos.py frases .` se não houver) e proponha os capítulos pela virada de assunto. Escreva as linhas `f012 Título` num arquivo e rode `<py> <f>/publicar.py capitulos . capitulos.txt --gravar`. A ferramenta confere as regras (0:00, pelo menos 3, 10 s cada). Se o plano de animação tem marcadores de capítulo, comece por `--das-animacoes`.
4. **Textos:** proponha 2–3 títulos (o primeiro com a sua escolha), a descrição (a primeira linha é o gancho; depois o que o vídeo entrega, os links fixos da pessoa e os capítulos) e as tags; para Instagram e TikTok, a legenda e as hashtags. Tudo pelo conteúdo real do vídeo e no tom da pessoa: nada que o vídeo não cumpra. Com o aprovado, grave um JSON e rode `<py> <f>/publicar.py definir . textos.json`. A conferência sai junto; corrija o que der ✗.
5. **Capa:** `<py> <f>/publicar.py capa . -n 6` gera as candidatas (nítidas, bem expostas, com rosto) já no formato do vídeo, e a folha `_CLAUDE/publicar/capas/candidatas.png`. Mostre a folha. A pessoa escolhe: `publicar.py capa . --escolher <n>`. Texto ou arte sobre a capa é com a pessoa ou com o programa dela; diga isso numa linha se ela pedir.
6. **Pacote:** `<py> <f>/publicar.py pacote .` cria `Publicar/<plataforma>/` com o vídeo (link, sem duplicar quando dá), `texto.txt` pronto para colar, as legendas SRT/VTT, a capa e `conferencia.md`. O pacote recusa se a conferência tiver erro.
7. Resumo curto: onde está cada pasta e o que ficou como aviso. O envio é da pessoa: o pacote só deixa tudo pronto para subir.

## Cuidados
- Os limites mudam. `publicar.py limites` mostra os que o script confere e quando foram conferidos. Passados alguns meses, ou se uma plataforma recusar algo, confira na ajuda oficial e avise a pessoa; se mudou, proponha a correção ao motor.
- Legenda do vídeo (SRT) ajuda acessibilidade e busca: o YouTube aceita no upload. Se o vídeo não tem, ofereça `/edicao:legendas`.
- Preferências que valem para os próximos vídeos (hashtags fixas, fórmula de título, links) vão para o caderno de aprendizados.
