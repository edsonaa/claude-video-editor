# Assets

**Asset** é todo material real que entra no vídeo e não dá para desenhar em código: o logo de uma ferramenta, um ícone, o print de uma página, uma foto, um som, uma música. O que dá para desenhar (formas, diagramas, bonecos, cenas) não é asset: a animação constrói no código.

O fluxo cuida dos assets em três frentes: os **visuais** das animações (a etapa `assets`), os **sons** (a biblioteca da etapa de som) e os **materiais de apoio** (fontes dos estilos, música, capa).

## Assets das animações

### O que é de quem
| Precisa de… | Quem resolve |
|---|---|
| logo de marca ou de ferramenta, ícone, print de página pública | a etapa `assets` (`/edicao:assets`) |
| boneco, forma, cena montada, diagrama | o render da animação, desenhando no código |
| tela logada, gravação sua, foto sua | você: o fluxo só lembra o que falta |
| foto ou vídeo de banco | depende de ter uma fonte com licença; senão, você manda |

### Onde ficam
| Lugar | O que guarda |
|---|---|
| `<vídeo>/Assets/` (`pastas.assets`) | os assets deste vídeo: o que a etapa achou e o que você mandou |
| `~/.edicao/biblioteca/` | os assets fixos, que voltam em vários vídeos (os logos que você sempre usa) |
| `<vídeo>/_CLAUDE/motion/<id>/assets/` | a cópia que cada animação usa (o `efeitos.py criar` copia para lá) |
| `<vídeo>/_CLAUDE/creditos.md` | o que pede crédito na descrição do vídeo |

### Do plano ao arquivo
1. **No plano** (`/edicao:motion-mapa`), cada item lista os assets que precisa, com tipo e termo de busca:
   ```json
   "assets": [{"id": "a1", "tipo": "logo", "busca": "Notion"},
              {"id": "a2", "tipo": "print", "busca": "página de preços do Notion"}]
   ```
   Antes de pedir, o plano olha a pasta `Assets/`: o arquivo pode já estar lá com outro nome.
2. **Na etapa `assets`** (pula sozinha se nada faltar):
   - lista o que falta: o que não está em `Assets/` nem na biblioteca fixa (procurando também nomes parecidos);
   - busca nas fontes do guia e descarta o claramente errado: marca errada (a empresa-mãe no lugar do produto), logo antigo, print com banner de cookies ou página que não carregou;
   - mostra **uma folha numerada por rodada**, com as opções lado a lado sobre o fundo do vídeo. A opção 1 é a recomendação;
   - você responde por número: `a1 1, a3 2, a4 eu mando`.
3. **Gravado**, cada asset ganha `arquivo` e `status` no plano (`ok` ou `pessoa_manda`). Os que pedem crédito vão para o `creditos.md`, e o Claude pergunta quais entram na biblioteca fixa.
4. **No render da animação**, o asset entra por um parâmetro `imagem` do efeito (o `logo-revela`, o `print-destaque`, o `card-lateral`) ou direto no projeto da animação. Se ainda faltar, a animação é construída do mesmo jeito, com um marcador vermelho **ASSET FALTANDO** no lugar, e a entrega no programa ganha um marcador de asset faltando. Nada trava o fluxo.

O resumo da etapa diz o que entrou (arquivo, fonte, licença), o que ficou faltando e o que **você** precisa gravar ou mandar, com o nome de arquivo esperado.

### Fontes que funcionam bem
- **Logo:** primeiro a biblioteca fixa; depois fontes de logos oficiais em SVG e o Iconify (coleções como `logos` e `devicon`).
- **Ícone:** o Iconify, com uma opção de cada coleção para dar variedade (Lucide, Phosphor, Tabler…). Vêm em SVG de uma cor, e o render recolore com as cores do perfil.
- **Print de site:** um navegador sem interface, na resolução do vídeo, com a página como ela abre.
- **SVG é melhor que PNG:** escala sem perder nitidez. Se a opção escolhida vier em SVG no lugar do PNG esperado, ela é gravada como SVG.

As fontes e as licenças mudam: a etapa pesquisa as atuais antes de escrever o script de busca. O script fica em `~/.edicao/scripts/` e é reaproveitado nos próximos vídeos.

### Licenças
- **Logos** são marcas registradas. Só a oficial, sem redesenhar nem distorcer, para falar da ferramenta. Sem a oficial, o asset fica faltando; nunca entra um "parecido".
- **Ícones** de coleções abertas (MIT, ISC, Apache, CC BY). CC BY pede crédito: vai para o `creditos.md`, que você cola na descrição.
- **Print de site:** só página pública, para comentar o produto. Nada de tela logada nem de conta de terceiros.
- **Imagem sem licença clara não entra**: vira "você manda".

## Sons

A etapa de som (`/edicao:sfx`) escolhe os efeitos sonoros na **sua biblioteca**, uma pasta no seu computador (`som.biblioteca` na configuração).

- **Organização:** uma pasta por categoria (`whoosh`, `impacto`, `grave`, `riser`, `pop`, `clique`, `glitch`, `interface`, `ding`, `papel`…). A categoria de cada som é a primeira pasta do caminho.
- **Índice:** `sons.py indexar <biblioteca>` mede cada som e grava `<biblioteca>/indice.json`. Ele é incremental: rodar de novo só mede o que é novo. O índice guarda:
  - a duração;
  - o **tempo até o pico**, que alinha o som ao que se vê: um impacto com pico em 0,4 s começa 0,4 s antes do quadro do impacto;
  - o nível e a categoria;
  - os campos escritos à mão, que nunca são apagados: `licenca`, `tags`, `nota` e `favorito`.
- **Busca:** `sons.py buscar <índice> --categoria whoosh --dur-max 1.5` ou `--texto "vidro"`; `sons.py categorias <índice>` mostra o que existe.
- **Licença:** confira a de cada som e escreva no campo `licenca` do índice. Som sem licença clara não entra no vídeo.
- **Faltou som?** Não force um ruim: o melhor possível, ou nenhum, e o que faltou vai para uma lista de sons para buscar.

Os efeitos da biblioteca de animações já dizem onde pedem som (os eventos em `eventos.json`, veja [efeitos.md](efeitos.md)), e a etapa de som parte deles.

## Outros materiais

| Material | Onde entra | O que cuidar |
|---|---|---|
| **Música de fundo** | `audio.py musica` monta a faixa do tamanho do vídeo, abaixando sob a fala, em `_CLAUDE/audio/musica_vNN.wav` | sempre com licença (biblioteca da plataforma, banco com licença clara ou música própria); música comercial sem licença derruba o vídeo ou o monetiza para outra pessoa. Num curto, uma faixa própria, com licença para vídeo curto |
| **Fontes** | os estilos usam fontes livres (licença OFL): Inter, Montserrat, Lora, DM Sans, Anton | instaladas no computador que renderiza as animações; sem elas, o navegador usa uma substituta e o desenho muda |
| **Capa** | `publicar.py capa` sugere quadros do próprio vídeo, já no formato certo | texto ou arte sobre a capa é com você (ou com o seu programa) |
| **Roteiro** | `<vídeo>/Docs/`, quando `cortes.usa_roteiro` está ligado | a etapa de cortes lê o roteiro junto com a fala |
| **Brutos** | `<vídeo>/Brutos/` | só leitura; o Claude nunca move nem renomeia |

A etapa `assets` anota no `_CLAUDE/creditos.md` o que pede crédito na descrição. Vale juntar ali também os sons e as músicas com licença de atribuição, para colar tudo de uma vez na descrição do vídeo.
