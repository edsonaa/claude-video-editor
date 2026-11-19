/* Tema e utilidades dos efeitos. Copiado para cada projeto pelo efeitos.py.
   Lê as variáveis da composição (o tema do perfil + o conteúdo do item), aplica as cores
   e fontes como variáveis CSS e oferece funções de tempo com a curva e a velocidade do estilo.
   Regras do HyperFrames (guias/hyperframes.md): fromTo com partida explícita, lazy:false,
   immediateRender:false quando o "from" já é visível; nada de Date.now/Math.random. */
(function () {
  const v = window.__hyperframes.getVariables();
  const raiz = document.getElementById("root");
  const css = document.documentElement.style;
  const cor = (k, padrao) => v[k] || padrao;
  css.setProperty("--t-fundo", cor("cor_fundo", "#0F172A"));
  css.setProperty("--t-superficie", cor("cor_superficie", "#1E293B"));
  css.setProperty("--t-texto", cor("cor_texto", "#F8FAFC"));
  css.setProperty("--t-texto-suave", cor("cor_texto_suave", "#94A3B8"));
  css.setProperty("--t-destaque", cor("cor_destaque", "#3B82F6"));
  css.setProperty("--t-apoio", cor("cor_apoio", "#22D3EE"));
  css.setProperty("--t-fonte-titulo", JSON.stringify(v.fonte_titulo || "Inter"));
  css.setProperty("--t-fonte-texto", JSON.stringify(v.fonte_texto || "Inter"));
  css.setProperty("--t-fonte-numeros", JSON.stringify(v.fonte_numeros || v.fonte_titulo || "Inter"));
  css.setProperty("--t-peso-titulo", String(v.peso_titulo || 800));
  css.setProperty("--t-peso-texto", String(v.peso_texto || 500));
  css.setProperty("--t-tracking-titulo", (v.tracking_titulo ?? -0.02) + "em");
  css.setProperty("--t-caixa", v.caixa_titulo === "alta" ? "uppercase" : "none");
  css.setProperty("--t-raio", (v.raio ?? 18) + "px");
  raiz.classList.add("material-" + (v.material || "plano"));
  const W = parseFloat(raiz.dataset.width), H = parseFloat(raiz.dataset.height);
  const vertical = H > W;
  if (vertical) raiz.classList.add("vertical");

  const fps = Number(v.fps) || 30;
  const D = parseFloat(raiz.dataset.duration);
  // "f" é sempre 1/30 s (a unidade dos guias), seja qual for o fps do vídeo.
  const f = (n) => n / 30;
  const os = Number(v.overshoot) || 0;            // 0 = sem passar do ponto
  const easeIn = v.ease_entrada || "expo.out";
  const easeOut = v.ease_saida || "power3.in";
  const entradaF = Number(v.entrada_f) || 15;
  const saidaF = Number(v.saida_f) || 8;
  const veloc = Number(v.velocidade) || 1;        // >1 mais rápido, <1 mais lento

  const HF = {
    v, raiz, W, H, vertical, fps, D, f,
    /** duração em segundos de `n` frames na velocidade do estilo */
    df: (n) => f(n) / veloc,
    entradaD: () => f(entradaF) / veloc,
    saidaD: () => f(saidaF) / veloc,
    easeEntrada: () => (os > 0 ? `back.out(${os})` : easeIn),
    easeSaida: () => easeOut,
    /** entrada padrão: de `de` até o estado natural, com a curva do estilo */
    entrada(tl, alvo, de, t, extra = {}) {
      const para = {};
      const neutro = (k) => (k === "opacity" || k === "autoAlpha" || k.startsWith("scale")) ? 1 : (k === "filter" ? "blur(0px)" : 0);
      for (const k of Object.keys(de)) para[k] = neutro(k);
      Object.assign(para, extra.para || {});
      tl.fromTo(alvo, de, Object.assign({ duration: extra.duracao || HF.entradaD(), ease: extra.ease || HF.easeEntrada(),
        lazy: false, immediateRender: extra.imediato !== false }, para), t);
      return tl;
    },
    /** saída padrão: um movimento só, mais rápido que a entrada */
    saida(tl, alvo, para, t, extra = {}) {
      tl.to(alvo, Object.assign({ duration: extra.duracao || HF.saidaD(), ease: extra.ease || HF.easeSaida(), lazy: false }, para), t);
      return tl;
    },
    /** texto com quebra em palavras (span.palavra), para animar palavra por palavra */
    palavras(el, texto) {
      el.textContent = "";
      const out = [];
      String(texto).split(/\s+/).filter(Boolean).forEach((p, i, arr) => {
        const s = document.createElement("span");
        s.className = "palavra"; s.style.display = "inline-block"; s.textContent = p;
        el.appendChild(s); out.push(s);
        if (i < arr.length - 1) el.appendChild(document.createTextNode(" "));
      });
      return out;
    },
    lista(nome) {
      const x = v[nome];
      if (Array.isArray(x)) return x;
      try { return JSON.parse(x || "[]"); } catch (e) { return String(x || "").split("|").map((s) => s.trim()).filter(Boolean); }
    },
    /** câmera virtual da cena: aproximação lenta e contínua do começo ao fim (linear) */
    camera(tl, alvo, intensidade = 0.05, deriva = 0) {
      tl.fromTo(alvo, { scale: 1, xPercent: 0 }, { scale: 1 + intensidade, xPercent: deriva, duration: D, ease: "none",
        lazy: false, immediateRender: true }, 0);
      return tl;
    },
    /** número formatado em pt-BR */
    numero(x, casas = 0, prefixo = "", sufixo = "") {
      return prefixo + Number(x).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + sufixo;
    },
    /** contador determinístico: anima um objeto e escreve o texto a cada quadro */
    contar(tl, el, de, ate, t, duracao, op = {}) {
      const o = { n: de };
      el.textContent = HF.numero(de, op.casas || 0, op.prefixo || "", op.sufixo || "");
      tl.fromTo(o, { n: de }, { n: ate, duration: duracao, ease: op.ease || "power2.out", lazy: false, immediateRender: true,
        onUpdate: () => { el.textContent = HF.numero(o.n, op.casas || 0, op.prefixo || "", op.sufixo || ""); } }, t);
      return tl;
    },
    /** imagem do parâmetro, ou um marcador visível de ASSET FALTANDO no mesmo lugar e tamanho */
    imagem(el, caminho, descricao) {
      if (caminho) {
        const img = document.createElement("img");
        img.src = caminho; img.alt = ""; img.style.width = "100%"; img.style.height = "100%"; img.style.objectFit = "contain";
        el.appendChild(img);
      } else {
        el.classList.add("faltando");
        el.textContent = "ASSET FALTANDO" + (descricao ? ": " + descricao : "");
      }
      return el;
    },
    /** timeline raiz, já registrada; chame HF.pronto(tl) no fim */
    timeline() { return gsap.timeline({ paused: true }); },
    pronto(tl) {
      window.__timelines = window.__timelines || {};
      window.__timelines[raiz.dataset.compositionId] = tl;
      tl.seek(0);
    },
  };
  window.HF = HF;
})();
