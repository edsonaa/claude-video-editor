# Estilo de motion — Limpo

Origem: estilo `limpo` da biblioteca do motor (ponto de partida). Tendência, não regra: ajuste com referências e com o caderno de aprendizados, anotando a origem de cada mudança.
Mesma numeração do `guias/oficio-motion.md`. Os números de entrada/saída e a curva estão no `tema.json` (`movimento`) e os efeitos já os usam.

## §1 Velocidade
- Entrada de elemento ~15 f; saída ~8 f (a 30 fps). Velocidade geral ×1.

## §2 Curvas
- Entrada: `expo.out`, sem passar do ponto.
- Saída: `power3.in`, um movimento só.

## §8 Movimento secundário
- Quase nenhum: deriva lenta da câmera virtual e só.

## Densidade por trecho
- Gancho: média: um conceito visual a cada ~6 s.
- Corpo: leve: só onde a fala sozinha não explica.
- Fechamento: mínima.

## Efeitos que combinam (repertório, nunca obrigação)
- `lista-passos`, `print-destaque`, `cursor-clique`, `comparacao`, `barras`, `capitulo`, `tarja-nome`
