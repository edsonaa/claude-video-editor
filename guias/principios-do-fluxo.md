# Princípios do fluxo

Os bons costumes que fazem um fluxo de edição com o Claude funcionar vídeo após vídeo. Valem para qualquer tipo de vídeo e qualquer programa. Escreva-os nas regras comuns e nas skills da pessoa.

## 1. Uma skill por etapa, uma etapa por vez
- Uma skill que tenta fazer tudo de uma vez entrega um vídeo médio. Etapas pequenas, cada uma com um trabalho só, entregam muito mais.
- Cada etapa parte da anterior **travada** (aprovada). Se algo aprovado mudar depois (um corte muda depois das animações), a etapa avisa o que precisa ser refeito, em vez de seguir com um plano velho.
- Nada de encadear etapas sozinho. A pessoa aprova uma e diz "sim" para a próxima.

## 2. Planejar inteiro, executar por partes
- O que pede visão do todo (cortes, plano das animações) olha o vídeo inteiro: história, variedade, ritmo do começo ao fim.
- O que é pesado de executar (render, câmera, som) pode ir **por trecho**, escolhido pela pessoa na hora: "render até 3:00", "o hook", "o resto". Um item pertence ao trecho em que começa.
- Cada trecho lê o que os anteriores já fizeram, para não repetir a mesma fórmula.

## 3. A memória fica nos arquivos, não na conversa
- Cada vídeo tem uma pasta de trabalho do Claude (ex.: `_CLAUDE/`) com um **arquivo de estado** (ex.: `projeto.json`): o que cada etapa decidiu, o status de cada uma e as pendências.
- Por isso dá para limpar o chat (`/clear`) entre as etapas sem perder nada. A `/edicao:editar` lê o estado e diz onde o vídeo parou.
- O arquivo de estado cresce muito. Um script pequeno lê e muda só o pedaço que cada etapa precisa (`estado.py <pasta> status`, `estado.py <pasta> cortes`, já pronto em `ferramentas/`). Ler o arquivo inteiro a cada passo gasta limite à toa.

## 4. O Claude decide, os scripts calculam
- O Claude decide sobre o **texto**: qual take, onde entra uma animação, qual som. Ele lê a transcrição por frase, não por palavra.
- Os **scripts** fazem as contas: tempo por palavra, frames, bordas de corte, keyframes, níveis de áudio e o arquivo para o programa de edição. Script erra menos que conta feita à mão e gasta menos limite.
- Os scripts das contas mais delicadas já vêm prontos e testados (`ferramentas/`): estado, inventário, silêncios, transcrição, XML, tempo, folha de contato, sons e rosto. Um script novo, escrito para um vídeo, fica em `~/.edicao/scripts/` e é reaproveitado nos próximos; se servir para qualquer pessoa, vai para o motor.
- Uma conversão de segundos para frames só, para todos os scripts (`edicao.tempo`). Duas conversões diferentes geram um descompasso de 1 frame que ninguém acha.

## 5. Ponto salvo, pendência e `/clear`
- **Ponto salvo:** a etapa (ou o trecho) terminou, as revisões foram aplicadas e o arquivo de entrega foi gerado. Só aí a skill sugere `/clear` e `/edicao:editar`.
- **Pendência:** algo que a pessoa pediu e ainda não foi aplicado fica anotado no estado e aparece no status até ser resolvido.
- Nunca sugerir `/clear` com uma revisão que não foi aplicada nem anotada.

## 6. O caderno de aprendizados
- Durante a revisão, toda correção, elogio ou preferência que vale **para outros vídeos** vira uma linha num caderno na pasta do vídeo: `- [ ] <etapa> · <o que foi pedido> · <data>`.
- Ajuste só de conteúdo daquele vídeo ("tira essa frase") não entra. Na dúvida, entra com "(talvez só deste vídeo)".
- Anotar não é mudar. O fluxo só muda quando a pessoa pede (`/edicao:editar aprendizados`): o Claude propõe onde cada linha entra (perfil, ajustes da etapa ou, se vale para todo mundo, uma proposta ao motor), ela filtra, ele grava e marca (`[x] → onde entrou`, ou `[-]` se era só daquele vídeo).
- É isso que faz cada vídeo sair melhor que o anterior.

## 7. Motor, ajustes e gosto: três camadas
- **Motor** (este repositório, atualizável): o ofício que vale para qualquer pessoa e qualquer vídeo (como escolher um take, como uma curva fica fluida, como alinhar um som), nas skills, nos guias e nas ferramentas. Ninguém edita o motor para personalizar.
- **Ajustes** (`~/.edicao/ajustes/<etapa>.md`): o ofício pessoal, o jeito de trabalhar que vale para todos os vídeos *desta* pessoa. As skills leem depois das próprias instruções, e o ajuste prevalece.
- **Gosto** (`~/.edicao/perfis/<nome>/`): cores, fontes, quanto zoom, quanta animação, que tipo de som. Mais de um estilo (um canal, um cliente) é um perfil novo, sem copiar o fluxo.
- **Configuração** (`~/.edicao/config.json`): as escolhas de fluxo (programa, formato, etapas, transcrição).
- Assim o motor se atualiza (`/edicao:editar atualizar`) sem apagar nada do que é da pessoa, e uma melhoria que vale para todos sobe para o motor e chega a todo mundo.

## 8. Tendência, não regra
- Nas decisões criativas, o que está nas skills e no perfil é ponto de partida. Regra absoluta faz todo vídeo sair igual.
- Regras técnicas (sincronia, nível de áudio, formato do arquivo) podem ser firmes.

## 9. Segurança
- Nunca mover, renomear ou apagar os arquivos do projeto da pessoa. Tudo o que o Claude gera fica na pasta de trabalho dele.
- Nunca sobrescrever um arquivo já entregue (XML, render): sempre uma versão nova (`_v02`, `_v03`).
- Apagar, quando precisar, é mover para uma pasta de espera e deixar a pessoa apagar depois. Mandar para a lixeira por script pode apagar de vez sem avisar.
- Mudança no próprio fluxo (skills, scripts, perfil): com o "sim" da pessoa, e de preferência com um histórico de versões (git local) para poder voltar.

## 10. Conferir antes de confiar
- Todo formato de entrega novo começa por um **arquivo de teste curto** que a pessoa abre no programa dela e confere. Só depois de ela confirmar, o fluxo usa aquilo de verdade.
- Quando não souber como o programa representa algo, peça à pessoa para exportar um exemplo do próprio programa e copie o formato, em vez de chutar.
- Depois de mexer em scripts que já funcionam, compare o resultado novo com o de antes num vídeo de teste congelado (um "teste de regressão"). Mudança que ninguém pediu é bug. As ferramentas prontas já têm o seu: `python -m pytest <motor>/ferramentas/testes`.

## 11. Economia de limite
- `/clear` entre as etapas. O histórico longo é reprocessado a cada mensagem.
- Ler resumos e recortes, não arquivos inteiros: a transcrição por frase, o estado pelo script, um frame só quando há dúvida real.
- Render e tarefas longas em segundo plano: esperar não gasta limite.
- Modelo por etapa (sugestão; ajuste ao plano da pessoa):

| Etapa | Modelo | Esforço | Por quê |
|---|---|---|---|
| editar, iniciar, assets | o mais leve que funcione bem | baixo | Organizar e encaminhar |
| preparar | intermediário | médio | Quase tudo é script |
| cortes, motion-mapa, motion-render, câmera | o mais capaz | alto | Erro aqui custa uma rodada inteira de revisão |
| sfx, aplicar aprendizados | o mais capaz | médio | Gosto dentro de regras claras |

- Trocar de modelo logo depois do `/clear` não custa nada. No meio de uma conversa longa, a troca reprocessa tudo.
