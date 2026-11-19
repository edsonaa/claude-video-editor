# Estilo de motion — Impacto

Origem: estilo `impacto` da biblioteca do motor (ponto de partida). Tendência, não regra: ajuste com referências e com o caderno de aprendizados, anotando a origem de cada mudança.
Mesma numeração do `guias/oficio-motion.md`. Os números de entrada/saída e a curva estão no `tema.json` (`movimento`) e os efeitos já os usam.

## §1 Velocidade
- Entrada de elemento ~10 f; saída ~6 f (a 30 fps). Velocidade geral ×1.35.

## §2 Curvas
- Entrada: `expo.out`, chegando com overshoot 1.7 (`back.out(1.7)`).
- Saída: `power4.in`, um movimento só.

## §8 Movimento secundário
- Pouco: a energia vem dos cortes e das batidas, não de partículas.

## Densidade por trecho
- Gancho: muito densa: algo novo a cada 1,5–3 s.
- Corpo: densa: ênfase de frase frequente.
- Fechamento: rápido, com chamada.

## Efeitos que combinam (repertório, nunca obrigação)
- `enfase-frase`, `titulo-impacto`, `contador`, `transicao-rampa`, `comparacao`, `cursor-clique`
