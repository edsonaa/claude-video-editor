# Ferramentas

Os scripts que fazem as contas do fluxo, prontos e testados. O Claude decide sobre o texto; estes scripts calculam tempo, frames, bordas e o arquivo de entrega. Antes, cada pessoa escrevia os seus no primeiro vídeo, e as partes que mais dão erro (taxa 29,97, timecode, XML do Premiere) saíam diferentes em cada fluxo.

As skills do plugin chamam os scripts direto daqui (`${CLAUDE_PLUGIN_ROOT}/ferramentas/…`), com o Python do ambiente da pessoa (`~/.edicao/venv`). Assim, uma atualização do motor atualiza os scripts de todo mundo. Scripts que a pessoa escrever ficam em `~/.edicao/scripts/` e importam os módulos daqui (`edicao.*`).

## O que tem

| Script | Para quê | Etapa |
|---|---|---|
| `config.py` | A configuração da pessoa (`~/.edicao`): presets, criar, mostrar, mudar, validar, perfis, novidades do motor | montar, editar |
| `estado.py` | Lê e muda o `_CLAUDE/projeto.json` sem abrir o arquivo inteiro: status, blocos, itens, pendências, alertas de plano desatualizado | todas |
| `midia.py` | Inventário (ffprobe): fps exato, duração, áudio, data de gravação, VFR; `--estado` grava no estado | preparar |
| `silencios.py` | Mapa de silêncios e de trechos com som | preparar |
| `transcrever.py` | Roda o WhisperX ou o Scribe, normaliza num formato só, gera as frases que o Claude lê, acha takes engolidos (som sem palavra) e as notas faladas; `fala` dá a fala no tempo da sequência | preparar, motion-mapa |
| `exportar_xml.py` | FCP 7 XML para Premiere/Resolve (cortes, voz estéreo ligada, fades de 1 frame, animações em V3/V4, efeitos com ganho, marcadores) e a **volta** (lê o que a pessoa exportou) | cortes, motion-render, sfx |
| `tempo.py` | Segundos ↔ frames ↔ timecode, com drop-frame | qualquer |
| `efeitos.py` | Biblioteca de efeitos HyperFrames e estilos: listar, mostrar, criar (com tema, conteúdo, duração exata e eventos de som), prévia GIF e vitrine | motion-mapa, motion-render, montar |
| `legendas.py` | Legendas pela transcrição e pelos cortes: gerar blocos, revisar, corrigir por id, exportar SRT/VTT/ASS e os parâmetros da legenda animada | legendas |
| `audio.py` | Medir (loudness, pico real, ruído), tratar a voz sem tirar de sincronia, música com ducking, conferir a mixagem final | preparar, sfx, render |
| `contato.py` | Folha de contato (quadros lado a lado com tempo e frame) | referências, revisão |
| `sons.py` | Índice da biblioteca de sons: duração, **tempo até o pico**, nível; busca | sfx |
| `rosto.py` | Rastreio de rosto (YuNet, local, sem GPU) para a câmera seguir o rosto | câmera |
| `schema/projeto.schema.json`, `schema/config.schema.json` | O formato do estado do vídeo e da configuração | — |

Todos têm `--help` em português. Os módulos ficam em `edicao/`, para os scripts de etapa reaproveitarem (`from edicao.tempo import Taxa`).

## Instalar
- **Python 3.10+** e **FFmpeg** (com ffprobe) no PATH, ou nas variáveis `FFMPEG` e `FFPROBE`.
- `estado`, `midia`, `silencios`, `transcrever`, `exportar_xml` e `tempo` usam só a biblioteca padrão do Python.
- `contato`, `sons`, `rosto` e a prévia/vitrine do `efeitos` precisam de `numpy` e `opencv-python-headless`: `pip install -r requirements.txt`.
- `efeitos.py criar` só usa a biblioteca padrão; `previa`, `vitrine` e o `check` usam o HyperFrames (`npx --yes hyperframes@0.9.70`, ou o comando em `HYPERFRAMES_CMD`).
- Rastreio de rosto: `python rosto.py baixar` (modelo YuNet, licença MIT, ~230 KB).
- Transcrição: o WhisperX é instalado à parte (`whisperx` no PATH); o Scribe precisa de `ELEVENLABS_API_KEY`.

## Conferir que funciona no computador da pessoa
```bash
python -m pip install -r requirements.txt pytest
python -m pytest testes
```
Os testes geram um clipe sintético (vídeo com contador, "falas" em tempos conhecidos, um rosto desenhado e três efeitos) e passam o fluxo inteiro pelas linhas de comando. Sem internet e sem GPU. Leva uns 10 segundos.

`testes/esperado/estado_fixo.xml` é o **teste de regressão congelado** do XML: se uma mudança nos scripts alterar o XML sem ninguém pedir, o teste falha. Para aceitar uma mudança de propósito (depois de conferir no programa): `ATUALIZAR_ESPERADO=1 python -m pytest testes/test_xmeml.py`.

## O que está testado e o que falta conferir
- **Testado aqui:** os 13 efeitos com `criar` em todo formato e estilo e com o `check` real do HyperFrames 0.9.70 (`HYPERFRAMES_CMD=… GSAP_LOCAL=… pytest testes/test_efeitos.py`); conversões de tempo (29,97, 23,976, 59,94, drop-frame), estado (versões, alertas, conflitos, gravação concorrente), inventário, silêncios, normalização do WhisperX e do Scribe, hesitações em português, notas faladas, lacunas, estrutura e ligações do XML, a volta do XML, índice de sons e rastreio de rosto.
- **A conferir no programa de cada pessoa** (regra do fluxo: arquivo de teste primeiro, `exportar_xml.py exportar <pasta> --teste`): como o Premiere/Resolve da pessoa importa os fades (há a opção `--menos-um`, a forma da especificação FCP7, se as bordas reais não funcionarem), a cor dos marcadores (`--cores`, copiada de um XML exportado por ele) e o ganho dos efeitos.
- **Os motores de transcrição** não rodam nos testes (precisam de GPU ou de chave paga): os testes usam JSONs com o formato de saída de cada um. As opções do `whisperx` mudam entre versões; confira `whisperx --help`.

## Ainda não está aqui
Escritos na primeira vez que a etapa rodar num vídeo de verdade, como antes: sincronia por forma de onda, ajuste de bordas de corte pela energia do áudio, keyframes de câmera no XML, render final pelo FFmpeg (caminho sem programa de edição) e FCPXML para o Final Cut. Quando um deles ficar bom, ele vem para cá, com teste.
