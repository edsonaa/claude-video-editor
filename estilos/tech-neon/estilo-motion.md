# Estilo de motion — Tech neon

Origem: estilo `tech-neon` da biblioteca do motor (ponto de partida). Tendência, não regra: ajuste com referências e com o caderno de aprendizados, anotando a origem de cada mudança.
Mesma numeração do `guias/oficio-motion.md`. Os números de entrada/saída e a curva estão no `tema.json` (`movimento`) e os efeitos já os usam.

## §1 Velocidade
- Entrada de elemento ~13 f; saída ~7 f (a 30 fps). Velocidade geral ×1.1.

## §2 Curvas
- Entrada: `expo.out`, chegando com overshoot 1.2 (`back.out(1.2)`).
- Saída: `power3.in`, um movimento só.

## §8 Movimento secundário
- Deriva da câmera virtual e brilho pulsando de leve nos elementos de destaque.

## Densidade por trecho
- Gancho: densa: uma ideia visual a cada 3–5 s.
- Corpo: média: ênfases e conceitos.
- Fechamento: leve.

## Efeitos que combinam (repertório, nunca obrigação)
- `titulo-impacto`, `contador`, `logo-revela`, `transicao-rampa`, `card-lateral`, `barras`, `enfase-frase`
