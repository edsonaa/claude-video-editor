/* Desenha uma legenda no navegador num estilo da biblioteca (legendas/estilos.json),
   com as mesmas medidas do ASS que o render queima (edicao/legendas.py: ass):
   tamanho = 5,2% da altura (6,2% da largura no vertical) × estilo.tamanho; contorno =
   estilo.contorno × tamanho / 14; sombra = estilo.sombra × tamanho / 28; caixa por linha;
   palavra falada na cor de destaque, crescendo pela escala do estilo. Usado pelo painel e
   pelas boas-vindas. Sem dependências. */
"use strict";

const LegendaEstilo = (() => {
  let injetado = false;
  function injetar() {
    if (injetado) return;
    injetado = true;
    const css = document.createElement("style");
    css.textContent = `
.leg-estilo { position: absolute; left: 8%; right: 8%; text-align: center; pointer-events: none; line-height: 1.18; }
.leg-estilo .lin { display: block; }
.leg-estilo .txt { -webkit-text-stroke: var(--leg-traco, 0) var(--leg-traco-cor, transparent); paint-order: stroke fill;
  text-shadow: var(--leg-sombra, none); background: var(--leg-caixa, none); padding: var(--leg-caixa-pad, 0);
  -webkit-box-decoration-break: clone; box-decoration-break: clone; border-radius: .08em; }
.leg-estilo .w { display: inline; }
.leg-estilo .w.falada { color: var(--leg-dest); font-size: calc(1em * var(--leg-escala, 1)); }`;
    document.head.append(css);
  }

  const hexRgb = (h) => {
    const x = (h || "#000000").replace("#", "");
    return [parseInt(x.slice(0, 2), 16), parseInt(x.slice(2, 4), 16), parseInt(x.slice(4, 6), 16)];
  };
  const rgba = (h, a) => `rgba(${hexRgb(h).join(",")},${a})`;
  const cor = (valor, tema) => (valor && valor.startsWith("#") ? valor : (tema.cores || {})[valor || "destaque"] || "#FFFFFF");

  /* Prepara a camada: fonte, tamanho, cores, contorno, sombra, caixa, posição. */
  function aplicar(camada, estilo, tema, op = {}) {
    injetar();
    const e = estilo || {};
    const vertical = !!op.vertical;
    const posicao = op.posicao || e.posicao || "baixo";
    camada.classList.add("leg-estilo");
    const fk = e.fonte || "texto";
    const fonte = ["titulo", "texto", "numeros"].includes(fk) ? (tema.fontes || {})[fk] || "Inter" : fk;
    const s = camada.style;
    s.fontFamily = `"${fonte}", system-ui, sans-serif`;
    s.fontWeight = e.peso || 700;
    s.fontSize = `${(vertical ? 6.2 : 5.2) * (e.tamanho || 1)}${vertical ? "cqw" : "cqh"}`;
    s.textTransform = e.caixa_alta ? "uppercase" : "none";
    s.color = cor(e.cor || "#FFFFFF", tema);
    s.setProperty("--leg-dest", cor(e.cor_destaque || "destaque", tema));
    s.setProperty("--leg-escala", e.escala_destaque || 1);
    const sombras = [];
    if (e.caixa) {
      s.setProperty("--leg-traco", "0");
      s.setProperty("--leg-caixa", rgba(e.caixa.cor || "#000000", e.caixa.opacidade ?? 0.6));
      s.setProperty("--leg-caixa-pad", ".06em .28em");
    } else {
      const r = (e.contorno ?? 1) / 14;
      s.setProperty("--leg-traco", r > 0 ? `${(2 * r).toFixed(3)}em` : "0");
      s.setProperty("--leg-traco-cor", rgba(cor(e.cor_contorno || "#000000", tema), e.opacidade_contorno ?? 1));
      s.setProperty("--leg-caixa", "none");
      s.setProperty("--leg-caixa-pad", "0");
      const sh = (e.sombra ?? 1) / 28;
      if (sh > 0) sombras.push(`${sh.toFixed(3)}em ${sh.toFixed(3)}em 0 rgba(0,0,0,.5)`);
    }
    if (e.brilho) {
      const d = cor(e.cor_destaque || "destaque", tema);
      sombras.push(`0 0 .22em ${rgba(d, 0.85)}`, `0 0 .5em ${rgba(d, 0.55)}`);
    }
    s.setProperty("--leg-sombra", sombras.length ? sombras.join(",") : "none");
    s.top = s.bottom = s.transform = "";
    if (posicao === "centro") { s.top = "50%"; s.transform = "translateY(-50%)"; }
    else if (posicao === "topo") s.top = "8%";
    else s.bottom = vertical ? "30%" : "8%";
  }

  /* Escreve um bloco: as linhas; no modo palavra, a palavra `falada` (índice) acende. */
  function bloco(camada, linhas, palavra = false, falada = -1) {
    camada.replaceChildren();
    let k = 0;
    for (const l of linhas) {
      const lin = document.createElement("span");
      lin.className = "lin";
      const txt = document.createElement("span");
      txt.className = "txt";
      if (!palavra) txt.textContent = l;
      else {
        l.split(/\s+/).filter(Boolean).forEach((w, j) => {
          if (j) txt.append(" ");
          const sp = document.createElement("span");
          sp.className = "w" + (k === falada ? " falada" : "");
          sp.textContent = w;
          txt.append(sp);
          k++;
        });
      }
      lin.append(txt);
      camada.append(lin);
    }
  }

  /* Quebra um texto em blocos de até `linhas` × `max` caracteres (para as prévias). */
  function quebrar(texto, max, linhas = 2) {
    const ws = texto.split(/\s+/).filter(Boolean), blocos = [];
    let atual = [[]];
    const tam = (ls) => ls.join(" ").length;
    for (const w of ws) {
      const lin = atual[atual.length - 1];
      if (tam([...lin, w]) <= max) lin.push(w);
      else if (atual.length < linhas) atual.push([w]);
      else { blocos.push(atual.map((l) => l.join(" "))); atual = [[w]]; }
    }
    if (atual[0].length) blocos.push(atual.map((l) => l.join(" ")).filter(Boolean));
    return blocos;
  }

  return { aplicar, bloco, quebrar, cor };
})();
