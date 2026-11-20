# Transições

As transições do motor. A pessoa escolhe na galeria do painel (com prévia nas duas imagens do corte) e a escolha fica no segmento que entra: `cortes.segmentos[i].transicao = {"tipo": "dissolver", "duracao": 0.5}`.

| Id | Nome | Duração (padrão) | Render (xfade) | No Premiere e no Resolve |
|---|---|---|---|---|
| `dissolver` | Dissolver | 0,2 a 2 s (0,5) | `fade` | Cross Dissolve |
| `fade_preto` | Passar pelo preto | 0,3 a 2,5 s (0,8) | `fadeblack` | Dip to Color Dissolve, preto |
| `fade_branco` | Clarão | 0,2 a 1,2 s (0,4) | `fadewhite` | Dip to Color Dissolve, branco |
| `zoom` | Zoom | 0,25 a 1 s (0,45) | `zoomin` | Cross Dissolve + marcador |
| `empurrar` | Empurrar | 0,25 a 1 s (0,4) | `slideleft` | Cross Dissolve + marcador |
| `chicote` | Chicote | 0,15 a 0,7 s (0,3) | `hblur` | Cross Dissolve + marcador |

## Como cada caminho faz

- **Render** (`render.py`): a transição é centrada no corte, metade de cada lado, e a duração do vídeo não muda. O fim do segmento que sai continua além do corte, e o começo do que entra começa antes, com a mídia que sobra no arquivo; sem sobra, o quadro da borda fica parado. As animações e a legenda vão por cima.
- **XML** (`exportar_xml.py`): `transitionitem` em V1, alinhado ao centro, só com mídia sobrando dos dois lados (sem sobra, corte seco e aviso). As que o programa não tem entram como Cross Dissolve, com um marcador no corte dizendo qual era.
- **Volta do programa**: a transição lida volta para o segmento que entra; se o programa devolveu o equivalente da que estava (o Cross Dissolve de um zoom, por exemplo), a da biblioteca continua.
- **Painel**: ao tocar, uma prévia aproximada na troca de segmento; na galeria, a prévia com as duas imagens do corte.

As suas transições ficam no estoque (`~/.edicao/estoque/transicoes/`, pela skill `/edicao:estoque`), com os mesmos campos e mais `previa` (os quadros-chave da prévia no painel) e, se nenhum xfade serve, `"xfade": "custom"` com `expr`. Uma transição nova do motor é um bloco a mais no `transicoes.json`: `titulo`, `descricao`, `bom_para`, `evitar`, `xfade` (um dos tipos do filtro xfade do FFmpeg), `duracao` (`padrao`, `min`, `max`) e `xml` (`nome`, `effectid`, `categoria`, `cor` opcional, `aproximada` quando o programa não tem igual). A prévia da galeria e do tocador vem de `previa`: `a` e `b` são os quadros-chave (Web Animations) da imagem que sai e da que entra, com `fundo` e `a_cima` opcionais. Sem ela, o painel mostra um dissolver.
