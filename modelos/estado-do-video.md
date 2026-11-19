# Modelo: estado do vídeo e o script de estado

Cada vídeo tem um arquivo de estado em `_CLAUDE/projeto.json`. É a memória do fluxo: sobrevive ao `/clear` e a qualquer conversa nova. O formato completo está em `ferramentas/schema/projeto.schema.json`, e quem lê e grava é o `ferramentas/estado.py` (pronto e testado).

## Esqueleto (cresce a cada etapa)

```json
{
  "schema": 1,
  "revisao": 12,
  "projeto": "2026-01-15_Nome",
  "perfil": "<nome do perfil>",
  "fluxo": ["iniciar", "preparar", "cortes", "motion_mapa", "assets", "motion_render", "camera", "sfx"],
  "etapas": {
    "iniciar": "concluido",
    "preparar": "concluido",
    "cortes": "aguardando_aprovacao",
    "motion_mapa": "pendente"
  },
  "ferramentas": { "hyperframes": "<versão fixa deste vídeo>" },
  "midia": { "fps": "30000/1001", "resolucao": [3840, 2160], "principal": "cam01",
             "arquivos": [ { "id": "cam01", "caminho": "<absoluto>", "tipo": "camera", "duracao": 812.4 } ],
             "sync": [ { "id": "tela01", "referencia": "cam01", "offset": 12.48, "confianca": 0.93 } ] },
  "transcricao": { "motor": "whisperx", "palavras": { "cam01": "_CLAUDE/palavras_cam01.json" },
                   "lacunas": [ { "video": "cam01", "inicio": 48.1, "fim": 51.0 } ] },
  "notas_edicao": [ { "id": "n01", "video": "cam01", "inicio": 60.2, "fim": 64.9, "texto": "usa esse take", "etapa": "cortes" } ],
  "cortes": { "versao": 1, "segmentos": [ { "id": "s001", "video": "cam01", "inicio": 3.10, "fim": 15.62, "texto": "..." } ] },
  "marcadores": [ { "id": "m001", "video": "cam01", "tempo": 48.3, "tipo": "duvida_take", "texto": "..." } ],
  "motions": { "versao": 1, "base_cortes_versao": 1, "trechos": {},
               "itens": [ { "id": "mo01", "status": "aprovado", "inicio_seq": 0.5, "fim_seq": 4.0, "formato": "tela_cheia",
                            "render": { "arquivo": "...", "versao": 1 } } ] },
  "camera": { "base_cortes_versao": 1, "base_motions_versao": 1, "movimentos": [], "recortes": [] },
  "sfx": { "itens": [ { "id": "sfx01", "arquivo": "...", "inicio_seq": 0.42, "ganho_db": -14 } ], "recortes": [] },
  "pendencias": [ { "id": "p01", "etapa": "motion_render", "texto": "mo05 mais lento", "item": "mo05" } ],
  "entregas": [ { "etapa": "cortes", "arquivo": "...", "versao": 1 } ]
}
```

- **`fluxo`** é a lista de etapas *deste* fluxo, na ordem: cada pessoa tem o seu (reels pode ter 4 etapas). Nomes com `_`; o script aceita `motion-mapa` e grava `motion_mapa`.
- Status de etapa: `pendente`, `em_andamento`, `aguardando_aprovacao`, `aguardando_<pessoa>`, `concluido`, `nao_precisa`.
- Tempos de corte, marcadores e notas ficam no **tempo do arquivo de origem**, em segundos (não da sequência): sobrevivem a novas versões do corte. Animações e efeitos ficam no tempo da sequência (`inicio_seq`).
- Ids estáveis (`s001`, `mo04`, `cam07`, `sfx12`, `p03`): é por eles que a pessoa pede ajustes.
- **`cortes.versao` e `motions.versao` sobem sozinhas** quando o conteúdo muda. Cada etapa guarda a versão sobre a qual foi feita (`base_cortes_versao`…), e é assim que o status avisa "o corte mudou depois do plano de animação".
- **`revisao`** sobe a cada gravação. Quem leu a revisão N e tenta gravar quando o arquivo já está na N+1 recebe um conflito, em vez de apagar a mudança do outro (importa quando um painel e o Claude gravam no mesmo arquivo).
- Itens aceitam campos extras: cada fluxo acrescenta o que precisar. Os campos do schema têm sempre o formato do schema.

## O script de estado (`estado.py`)
Já vem pronto. Na skill de cada etapa, use o caminho na pasta de ferramentas da pessoa:
- `estado.py <pasta> status`: as etapas, o que foi feito por trecho, as pendências e os alertas;
- `estado.py <pasta> <bloco>`: um resumo legível de um bloco; com `--json`, o bloco completo;
- `estado.py <pasta> --item <id>`: um item inteiro;
- `--set <caminho> <valor>` e `--etapa <etapa>=<status>`;
- `--pendencia <etapa> "<texto>" [--de <id>]` e `--resolver <id>`;
- `--gravar <bloco> <arquivo.json|->`: um bloco inteiro (é assim que os scripts de etapa gravam);
- `--validar` e `--init <nome> [--perfil P] [--fluxo a,b,c]`.

Toda gravação é atômica e validada: estado inválido não é gravado. Ele economiza muito limite: num vídeo longo, o estado inteiro tem dezenas de milhares de tokens.
