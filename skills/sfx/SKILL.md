---
name: sfx
description: "Coloca os efeitos sonoros de um vídeo depois de corte, animações e câmera travados: junta os eventos visíveis, escolhe os sons da biblioteca por camada (principal, grave, apoio), alinha pelo pico, nivela pela voz e entrega cada som numa trilha. Funciona por trecho. Use em /edicao:sfx, depois da câmera (ou da última etapa visual do fluxo)."
---

# sfx

Motor: `${CLAUDE_PLUGIN_ROOT}`. Ferramentas: `<f>` = `${CLAUDE_PLUGIN_ROOT}/ferramentas`. Uma vez por sessão: leia `${CLAUDE_PLUGIN_ROOT}/skills/editar/regras-comuns.md` e rode `<py> <f>/config.py mostrar`.

- **Lê:** os eventos (cortes, câmera, animações, eventos anotados no render), o índice da biblioteca, o perfil (`estilo-som.md`: densidade, níveis, preferidos), a configuração (`som.biblioteca`, `som.musica`), `<pessoa>/ajustes/sfx.md` e `geral.md`.
- **Escreve:** o bloco `sfx` (`itens` numerados `sfx01`…), os sons usados copiados para a pasta de assets do projeto, a entrega.
- **Ofício:** `${CLAUDE_PLUGIN_ROOT}/guias/etapa-sfx.md`. Leia antes: o som segue o que se vê, um protagonista por momento, camadas, antecipação e resolução, escalada.

## Passo a passo
1. `<py> <f>/estado.py . status`: as etapas visuais aprovadas, sem alerta de desatualizado.
2. **Biblioteca:** `<py> <f>/sons.py indexar <som.biblioteca>` (incremental) e `sons.py categorias <índice>`. Para escolher: `sons.py buscar <índice> --categoria whoosh --dur-max 1.5`.
3. **Eventos no tempo da sequência** (os das animações da biblioteca já vêm em `_CLAUDE/motion/<id>/eventos.json`, em segundos desde o início do item): o script que junta tudo (cortes com e sem mudança de plano, movimentos de câmera, entradas, saídas e gatilhos das animações, eventos do render), com id estável, e mede a loudness da voz (LUFS), ainda não vem pronto. Na primeira vez, escreva `<pessoa>/scripts/eventos_som.py` sobre `edicao.estado` e `edicao.linha`, como o guia descreve.
4. **Rascunho:** para cada som, o evento, a camada, o arquivo e o alinhamento. Pelo pico: `inicio_seq = tempo do evento − pico` (o índice traz o `pico`). Nível pela voz, com os alvos por categoria do perfil e o teto de pico.
5. **Grave** `{"itens": [{"id": "sfx01", "evento": "…", "camada": "principal", "arquivo": "<absoluto>", "inicio_seq": 12.34, "duracao": 0.8, "canais": 2, "ganho_db": -14}]}` com `--gravar sfx`. A entrega põe cada som numa trilha abaixo da voz, sem sobrepor, com o ganho no clipe.
   Sons que a pessoa pôs pela galeria do painel (`origem: painel`) já estão no bloco: **mantenha-os** no que gravar (o `--gravar` troca o bloco inteiro), conte-os na densidade e não ponha outro som no mesmo evento sem perguntar.
6. **Música de fundo:** só se `som.musica` for `fluxo`; com `manual`, deixe para a pessoa.
   - A pessoa escolhe a faixa (licença dela; nunca uma música comercial sem licença). `<py> <f>/audio.py musica . <faixa>` estende a faixa até o fim do vídeo, abaixa sob a fala (antecipa ~0,3 s e volta em ~0,8 s, pelos tempos da transcrição já cortada) e faz os fades. Os níveis vêm de `audio.musica_nivel_livre` e `musica_nivel_fala`; ajuste com `--nivel-livre`/`--nivel-fala` se a pessoa achar alta ou baixa.
   - O arquivo entra numa trilha própria, acima dos efeitos, na próxima entrega (anotado em `sfx.musica`).
7. **Entrega** (regras comuns, §4) e resumo. `--etapa sfx=aguardando_aprovacao`.

## Revisão e aprovação
Por número: "sfx12 mais baixo" (−3 dB), "sfx05 outro som", "menos som no corpo". Se a pessoa ajustar níveis no programa e aprovar assim, a diferença é aprendizado para o perfil. Aprovado: `--etapa sfx=concluido`, aprendizados, `/clear` e `/edicao:editar`.
