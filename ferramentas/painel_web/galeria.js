/* Galeria do painel: legendas, animações, transições e sons, com prévia sobre o quadro
   do vídeo no ponto do cursor e um botão para pôr no vídeo ali. Usa as funções do
   painel.js (D, T, el, api, acao…), que é carregado depois: nada aqui roda antes de
   Galeria.iniciar(). */
"use strict";

const Galeria = (() => {
  let cat = null;               // /api/galeria
  let secao = "legendas";
  let posLeg = null;            // posição escolhida na prévia das legendas
  let aberto = null;            // animação com o formulário aberto
  let valores = {};             // parâmetros digitados, por efeito
  let duracoes = {};            // duração escolhida, por efeito
  let durTr = {};               // duração escolhida, por transição
  let ganho = -12;              // volume dos sons inseridos
  let catSom = null;            // categoria de som filtrada
  let tique = null, palavraK = 0;
  let ultimoQuadro = "";
  let tocandoSom = null;
  let observador = null;

  const SECOES = { legendas: "Legendas", animacoes: "Animações", transicoes: "Transições", sons: "Sons" };
  const FORMATOS_EF = { tela_cheia: "tela cheia", sobreposicao: "sobreposição", sobreposicao_lateral: "lateral", enfase: "ênfase" };
  const AMOSTRA = "vinte placas chegaram com o mesmo defeito";

  const visivel = () => !$("#aba-galeria").hidden;
  const virgula = (x, c = 2) => Number(x).toFixed(c).replace(".", ",");

  // ---------------------------------------------------------------- o quadro do cursor
  function quadroUrl(largura = 480) {
    const seg = D && D.segmentos[T.i];
    if (!seg || !(D.midias["v:" + seg.video] || {}).url) return null;
    const t = seg.in + (T.t - seg.seq_ini);
    return url(`/api/miniatura?video=${encodeURIComponent(seg.video)}&tempo=${t.toFixed(3)}&largura=${largura}`);
  }
  function quadroDe(video, tempo, largura = 480) {
    return url(`/api/miniatura?video=${encodeURIComponent(video)}&tempo=${Math.max(0, tempo).toFixed(3)}&largura=${largura}`);
  }
  function caixaPrevia(extra = "") {
    const [w, h] = dimsQuadro();
    const box = el("div", { class: "gprev " + extra, style: `aspect-ratio:${w}/${h};${h > w ? "max-width:190px" : ""}` });
    const u = quadroUrl();
    box.append(el("div", { class: "gfundo", style: u ? `background-image:url("${u}")` : "" }));
    return box;
  }
  function trocarFundos() {
    const u = quadroUrl();
    if (!u || u === ultimoQuadro) return;
    ultimoQuadro = u;
    $$("#gal-corpo .gfundo").forEach((f) => { f.style.backgroundImage = `url("${u}")`; });
  }

  // ---------------------------------------------------------------- estrutura
  function iniciar() {
    const seg = $("#gal-secoes");
    repor(seg, ...Object.entries(SECOES).map(([k, nome]) => el("button", {
      role: "tab", "aria-selected": k === secao, dataset: { secao: k }, onclick: () => { secao = k; aberto = null; desenhar(); },
    }, nome)));
    $$(".abas [role=tab]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.aba === "galeria") mostrar(); else parar(); }));
  }

  async function carregar(forcar = false) {
    if (cat && !forcar) return cat;
    cat = await api("/api/galeria");
    return cat;
  }

  async function mostrar(nova) {
    if (nova) secao = nova;
    if (!visivel()) { $$(".abas [role=tab]").find((b) => b.dataset.aba === "galeria").click(); return; }
    try { await carregar(); } catch (e) { repor($("#gal-corpo"), el("p", { class: "vazio" }, `Não deu para abrir a galeria: ${e.message}`)); return; }
    desenhar();
  }

  function parar() {
    clearInterval(tique); tique = null;
    if (tocandoSom) { tocandoSom.pause(); tocandoSom = null; }
  }

  function desenhar() {
    if (!cat || !D) return;
    parar();
    $$("#gal-secoes button").forEach((b) => b.setAttribute("aria-selected", b.dataset.secao === secao));
    $("#aba-galeria").dataset.secao = secao;
    const corpo = $("#gal-corpo");
    const f = { legendas: secaoLegendas, animacoes: secaoAnimacoes, transicoes: secaoTransicoes, sons: secaoSons }[secao];
    repor(corpo, ...f());
    observarIframes();
    atualizarCursor(true);
  }

  // o texto de "no cursor" e dos botões acompanha o tempo, sem redesenhar
  let ultimoCursor = "";
  function atualizarCursor(forcar = false) {
    if (!visivel() || !D) return;
    const chave = `${secao}:${T.t.toFixed(2)}`;
    if (!forcar && chave === ultimoCursor) return;
    ultimoCursor = chave;
    $$("#gal-corpo [data-em-cursor]").forEach((b) => { b.textContent = `${b.dataset.emCursor} em ${fmt(T.t)}`; });
    if (secao === "transicoes") desenharCorte();
    if (!T.tocando) { clearTimeout(atualizarCursor.t); atualizarCursor.t = setTimeout(trocarFundos, 350); }
  }

  // ---------------------------------------------------------------- legendas
  function textoAmostra() {
    const L = D.legendas;
    if (L && L.blocos.length) {
      const b = L.blocos.find((x) => T.t >= x.i && T.t < x.f) || L.blocos.find((x) => x.i >= T.t) || L.blocos[0];
      return b.linhas.join(" ");
    }
    const seg = D.segmentos[T.i];
    const ws = seg && D.roteiro[seg.video];
    if (ws) {
      const t = seg.in + (T.t - seg.seq_ini);
      const k = ws.findIndex((w) => w[1] >= t - 0.2);
      if (k >= 0) return ws.slice(k, k + 8).map((w) => w[0]).join(" ");
    }
    return AMOSTRA;
  }

  function secaoLegendas() {
    const atual = cat.legenda_atual, [w, h] = dimsQuadro(), vertical = h > w;
    const pos = posLeg || atual.posicao;
    const texto = textoAmostra();
    const cards = cat.legendas.map((e) => {
      const box = caixaPrevia();
      const camada = el("div", { class: "glegenda" });
      box.append(camada);
      LegendaEstilo.aplicar(camada, e, D.tema, { vertical, posicao: pos });
      const max = vertical ? e.max_caracteres_vertical : e.max_caracteres;
      const blocos = LegendaEstilo.quebrar(texto, e.modo === "palavra" ? Math.min(max, 18) : max, e.modo === "palavra" ? 1 : e.linhas);
      camada.dataset.modo = e.modo;
      camada._blocos = blocos;
      LegendaEstilo.bloco(camada, blocos[0] || [AMOSTRA], e.modo === "palavra", 0);
      const emUso = atual.estilo === e.id && pos === atual.posicao;
      return el("article", { class: "gcard" + (atual.estilo === e.id ? " em-uso" : "") },
        box,
        el("div", { class: "gcab" }, el("h3", {}, e.titulo), atual.estilo === e.id ? el("span", { class: "gselo" }, "em uso") : null),
        el("p", { class: "gdesc" }, e.descricao),
        el("p", { class: "gbom" }, `Bom para ${e.bom_para}`),
        el("div", { class: "gacoes" }, emUso ? null : el("button", { class: "gbt", onclick: () => usarLegenda(e) },
          atual.estilo === e.id ? `Usar na posição ${pos}` : "Usar neste vídeo")));
    });
    tique = setInterval(() => {
      palavraK++;
      $$("#gal-corpo .glegenda[data-modo=palavra]").forEach((c) => {
        const bl = c._blocos || [];
        const n = bl.reduce((s, b) => s + b.join(" ").split(/\s+/).length, 0) || 1;
        let k = palavraK % n, i = 0;
        while (i < bl.length && k >= bl[i].join(" ").split(/\s+/).length) { k -= bl[i].join(" ").split(/\s+/).length; i++; }
        LegendaEstilo.bloco(c, bl[i] || [AMOSTRA], true, k);
      });
    }, 380);
    const seg = el("div", { class: "gsegmentado", role: "group", "aria-label": "Posição da legenda" },
      ...["baixo", "centro", "topo"].map((p) => el("button", { "aria-pressed": p === pos, onclick: () => { posLeg = p; desenhar(); } }, p)));
    const aviso = cat.legenda_atual.ativas || (D.legendas && D.legendas.blocos.length) ? null
      : el("p", { class: "gnota" }, "Este vídeo ainda não tem legendas: o estilo escolhido vale quando a etapa de legendas rodar.");
    return [el("div", { class: "gintro" }, el("p", {}, "A prévia usa o texto e o quadro do ponto do cursor, com as medidas que o render queima."),
      el("div", { class: "glinha" }, el("span", {}, "Posição"), seg)), aviso, ...cards];
  }

  async function usarLegenda(e) {
    const r = await acao("/api/galeria/legenda", { estilo: e.id, posicao: posLeg || undefined });
    if (!r) return;
    avisar(r.info && r.info.refazer ? `${e.titulo} neste vídeo. A divisão em blocos mudou: ficou um pedido para o Claude gerar as legendas de novo.`
      : `${e.titulo} neste vídeo`);
    await carregar(true);
    posLeg = null;
    desenhar();
  }

  // ---------------------------------------------------------------- animações
  function srcEfeito(e) {
    const p = valores[e.id] ? JSON.stringify(valores[e.id]) : "";
    const d = duracoes[e.id] ? `&d=${duracoes[e.id]}` : "";
    return url(`/api/efeito?nome=${encodeURIComponent(e.id)}&formato=${encodeURIComponent(cat.formato)}${p ? "&p=" + encodeURIComponent(p) : ""}${d}`);
  }

  function iframeEfeito(e) {
    const [w, h] = (FORMATOS[cat.formato] || [1920, 1080]);
    const fr = el("iframe", { class: "gefeito", title: `Prévia: ${e.titulo}`, loading: "lazy", tabindex: "-1",
      width: w, height: h, dataset: { src: srcEfeito(e), w, h } });
    return fr;
  }

  function escalarIframes() {
    $$("#gal-corpo .gprev iframe, .camada-motion iframe").forEach((fr) => {
      const box = fr.parentElement, w = +fr.dataset.w, h = +fr.dataset.h;
      if (!box.clientWidth) return;
      fr.style.transform = `scale(${box.clientWidth / w}, ${box.clientHeight / h})`;
    });
  }

  function observarIframes() {
    if (observador) observador.disconnect();
    observador = new IntersectionObserver((es) => {
      for (const e of es) {
        if (!e.isIntersecting) continue;
        const fr = e.target;
        observador.unobserve(fr);
        if (!fr.src) fr.src = fr.dataset.src;
      }
    }, { root: $("#aba-galeria") });
    $$("#gal-corpo iframe[data-src]").forEach((f) => observador.observe(f));
    requestAnimationFrame(escalarIframes);
  }

  const mandar = (fr, msg) => { try { fr.contentWindow.postMessage(msg, "*"); } catch (_) { /* ainda carregando */ } };

  function secaoAnimacoes() {
    const cards = cat.animacoes.map((e) => {
      const box = caixaPrevia(e.formato === "tela_cheia" ? "cheia" : "");
      const fr = iframeEfeito(e);
      box.append(fr);
      box.addEventListener("mouseenter", () => mandar(fr, { cmd: "tocar" }));
      box.addEventListener("mouseleave", () => { if (aberto !== e.id) mandar(fr, { cmd: "parar" }); });
      const card = el("article", { class: "gcard" + (aberto === e.id ? " aberto" : ""), dataset: { efeito: e.id } },
        box,
        el("div", { class: "gcab" }, el("h3", {}, e.titulo), el("span", { class: "gfmt" }, FORMATOS_EF[e.formato] || e.formato),
          el("span", { class: "discreto" }, `${virgula(e.duracao.padrao, 1)} s`)),
        el("p", { class: "gdesc" }, e.descricao),
        e.bom_para ? el("p", { class: "gbom" }, `Bom para ${e.bom_para}`) : null,
        aberto === e.id ? formularioEfeito(e, fr) : el("div", { class: "gacoes" },
          el("button", { class: "gbt", onclick: () => { aberto = e.id; desenhar(); } }, "Escolher o conteúdo e inserir…")));
      return card;
    });
    const usadas = D.motions.filter((m) => m.origem === "painel").length;
    return [el("div", { class: "gintro" }, el("p", {}, "Passe o mouse para tocar. A animação entra como item aprovado do plano, no ponto do cursor; o Claude constrói e renderiza na etapa de animações."),
      usadas ? el("p", { class: "gnota" }, `${usadas} animação(ões) já escolhida(s) aqui: veja na aba Animações.`) : null), ...cards];
  }

  function formularioEfeito(e, fr) {
    const v = valores[e.id] || (valores[e.id] = { ...e.exemplo });
    let timer = null;
    const recarregar = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        fr.src = srcEfeito(e);
        fr.addEventListener("load", () => setTimeout(() => mandar(fr, { cmd: "tocar" }), 150), { once: true });
      }, 650);
    };
    const campos = e.parametros.map((p) => {
      const id = `gp-${e.id}-${p.id}`;
      let entrada;
      const val = v[p.id] ?? p.padrao ?? "";
      const mudar = (x) => { if (x === "" || x === null) delete v[p.id]; else v[p.id] = x; recarregar(); };
      if (p.tipo === "opcao") {
        entrada = el("select", { id, onchange: (ev) => mudar(ev.target.value) }, ...p.opcoes.map((o) => el("option", { value: o, selected: o === val }, o)));
      } else if (p.tipo === "booleano") {
        entrada = el("input", { id, type: "checkbox", checked: !!val, onchange: (ev) => mudar(ev.target.checked) });
      } else if (p.tipo === "numero") {
        entrada = el("input", { id, type: "number", step: "any", value: val, oninput: (ev) => mudar(ev.target.value === "" ? "" : +ev.target.value) });
      } else if (p.tipo === "cor") {
        entrada = el("input", { id, type: "color", value: val || "#ffffff", oninput: (ev) => mudar(ev.target.value) });
      } else if (p.tipo === "imagem") {
        entrada = el("select", { id, onchange: (ev) => mudar(ev.target.value) }, el("option", { value: "" }, cat.imagens.length ? "sem imagem (marcador)" : "nenhuma imagem em Assets/"),
          ...cat.imagens.map((i) => el("option", { value: i, selected: i === val }, i)));
      } else if (p.tipo === "lista") {
        const linhas = Array.isArray(val) ? val.map((x) => (typeof x === "object" ? JSON.stringify(x) : x)).join("\n") : String(val || "");
        entrada = el("textarea", { id, rows: 3, oninput: (ev) => {
          const ls = ev.target.value.split("\n").map((s) => s.trim()).filter(Boolean)
            .map((s) => { try { return s.startsWith("{") ? JSON.parse(s) : s; } catch (_) { return s; } });
          mudar(ls.length ? ls : "");
        } }, linhas);
      } else {
        entrada = el("input", { id, type: "text", value: val, oninput: (ev) => mudar(ev.target.value) });
      }
      entrada.addEventListener("keydown", (ev) => ev.stopPropagation());
      return el("div", { class: "gcampo" + (p.tipo === "booleano" ? " linha" : "") },
        el("label", { for: id }, p.rotulo, p.obrigatorio ? el("span", { class: "gobrig", title: "obrigatório" }, " *") : null),
        entrada, p.tipo === "lista" ? el("small", { class: "discreto" }, "um item por linha") : null,
        p.descricao ? el("small", { class: "discreto" }, p.descricao) : null);
    });
    const dm = e.duracao, dur = duracoes[e.id] ?? dm.padrao;
    const durId = `gd-${e.id}`;
    const durEnt = el("input", { id: durId, type: "number", min: dm.min, max: dm.max, step: 0.1, value: dur,
      oninput: (ev) => { const x = +ev.target.value; if (x >= dm.min && x <= dm.max) { duracoes[e.id] = x; recarregar(); } } });
    durEnt.addEventListener("keydown", (ev) => ev.stopPropagation());
    return el("div", { class: "gform" }, ...campos,
      el("div", { class: "gcampo" }, el("label", { for: durId }, `Duração (${virgula(dm.min, 1)} a ${virgula(dm.max, 1)} s)`), durEnt),
      el("div", { class: "gacoes" },
        el("button", { class: "gbt primario", dataset: { emCursor: "Inserir" }, onclick: () => inserirEfeito(e) }, `Inserir em ${fmt(T.t)}`),
        el("button", { class: "gbt fantasma", onclick: () => { aberto = null; desenhar(); } }, "Fechar")));
  }

  async function inserirEfeito(e) {
    const corpo = { efeito: e.id, params: valores[e.id] || {}, inicio_seq: T.t, duracao: duracoes[e.id] ?? e.duracao.padrao };
    const r = await acao("/api/galeria/animacao", corpo);
    if (!r) return;
    const id = r.info && r.info.id;
    avisar(`${e.titulo} entrou como ${id} em ${fmt(T.t)}. Arraste o cursor para conferir.`);
    aberto = null;
    desenhar();
  }

  // ---------------------------------------------------------------- transições
  function corteAtual() {
    const segs = D.segmentos;
    if (segs.length < 2) return null;
    let melhor = null;
    for (let i = 1; i < segs.length; i++) {
      const dist = Math.abs(segs[i].seq_ini - T.t);
      if (!melhor || dist < melhor.dist) melhor = { i, dist, de: segs[i - 1], para: segs[i], tempo: segs[i].seq_ini };
    }
    return melhor;
  }

  function desenharCorte() {
    const c = corteAtual(), box = $("#gal-corte");
    if (!box) return;
    const chave = c ? `${c.para.id}:${JSON.stringify(c.para.transicao || null)}` : "";
    if (box.dataset.chave === chave) return;
    box.dataset.chave = chave;
    if (!c) { repor(box, el("p", {}, "O corte ainda tem um segmento só: não há onde pôr transição.")); return; }
    const tr = c.para.transicao;
    const meta = tr && cat.transicoes.find((t) => t.id === tr.tipo);
    repor(box, el("p", {}, el("strong", {}, `Corte em ${fmt(c.tempo)}`), ` · de ${c.de.id} para ${c.para.id}`),
      el("p", { class: "discreto" }, meta ? `Agora: ${meta.titulo}, ${virgula(tr.duracao, 2)} s` : "Agora: corte seco"),
      el("div", { class: "gacoes" },
        el("button", { class: "gbt fantasma", onclick: () => { irCorte(-1); } }, "← Corte anterior"),
        el("button", { class: "gbt fantasma", onclick: () => { irCorte(1); } }, "Próximo corte →"),
        meta ? el("button", { class: "gbt fantasma perigo", onclick: () => mudarTransicao(c, null) }, "Voltar ao corte seco") : null));
    // marca o card em uso e troca as imagens das prévias
    $$("#gal-corpo .gcard[data-tr]").forEach((card) => {
      const usa = tr && tr.tipo === card.dataset.tr;
      card.classList.toggle("em-uso", !!usa);
      const sel = $(".gselo", card);
      if (sel) sel.hidden = !usa;
      const bt = $(".gbt.primario", card);
      if (bt) bt.textContent = usa ? "Atualizar a duração" : "Aplicar neste corte";
    });
    const a = quadroDe(c.de.video, c.de.out - 0.08), b = quadroDe(c.para.video, c.para.in + 0.08);
    $$("#gal-corpo .gtr-a").forEach((x) => { x.style.backgroundImage = `url("${a}")`; });
    $$("#gal-corpo .gtr-b").forEach((x) => { x.style.backgroundImage = `url("${b}")`; });
  }

  // a prévia de cada tipo, com animações do navegador (uma aproximação do xfade do render)
  const ANIM = {
    dissolver: { b: [{ opacity: 0 }, { opacity: 1 }] },
    fade_preto: { fundo: "#000", a: [{ opacity: 1 }, { opacity: 0, offset: 0.5 }, { opacity: 0 }], b: [{ opacity: 0 }, { opacity: 0, offset: 0.5 }, { opacity: 1 }] },
    fade_branco: { fundo: "#fff", a: [{ opacity: 1 }, { opacity: 0, offset: 0.5 }, { opacity: 0 }], b: [{ opacity: 0 }, { opacity: 0, offset: 0.5 }, { opacity: 1 }] },
    zoom: { a: [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(2.2)", opacity: 0 }], b: [{ transform: "scale(1.04)", opacity: 1 }, { transform: "scale(1)", opacity: 1 }], aCima: true },
    empurrar: { a: [{ transform: "translateX(0)" }, { transform: "translateX(-100%)" }], b: [{ transform: "translateX(100%)" }, { transform: "translateX(0)" }] },
    chicote: { a: [{ transform: "translateX(0)", filter: "blur(0)", opacity: 1 }, { transform: "translateX(-55%)", filter: "blur(14px)", opacity: 0 }],
      b: [{ transform: "translateX(55%)", filter: "blur(14px)", opacity: 0 }, { transform: "translateX(0)", filter: "blur(0)", opacity: 1 }] },
  };
  function animarTransicao(box, tipo, dur) {
    const an = ANIM[tipo] || ANIM.dissolver;
    const a = $(".gtr-a", box), b = $(".gtr-b", box);
    box.style.background = an.fundo || "#000";
    a.style.zIndex = an.aCima ? 2 : 1;
    b.style.zIndex = an.aCima ? 1 : 2;
    const ms = Math.max(150, dur * 1000), total = ms + 1600, ini = 700 / total, fim = (700 + ms) / total;
    const esticar = (kf) => kf && [{ ...kf[0], offset: 0 }, { ...kf[0], offset: ini },
      ...kf.slice(1, -1).map((k) => ({ ...k, offset: ini + (k.offset ?? 0.5) * (fim - ini) })),
      { ...kf[kf.length - 1], offset: fim }, { ...kf[kf.length - 1], offset: 1 }];
    const op = { duration: total, iterations: Infinity, easing: "linear" };
    box.getAnimations({ subtree: true }).forEach((x) => x.cancel());
    if (an.a) a.animate(esticar(an.a), op);
    if (an.b) b.animate(esticar(an.b), op); else b.animate(esticar([{ opacity: 0 }, { opacity: 1 }]), op);
  }

  function secaoTransicoes() {
    const c = corteAtual();
    const cards = cat.transicoes.map((t) => {
      const box = caixaPrevia("gtr");
      box.replaceChildren(el("div", { class: "gtr-a" }), el("div", { class: "gtr-b" }));
      const d = durTr[t.id] ?? (c && c.para.transicao && c.para.transicao.tipo === t.id ? c.para.transicao.duracao : t.duracao.padrao);
      durTr[t.id] = d;
      const rotDur = el("output", {}, `${virgula(d, 2)} s`);
      const faixa = el("input", { type: "range", min: t.duracao.min, max: t.duracao.max, step: 0.05, value: d, "aria-label": `Duração de ${t.titulo}`,
        oninput: (ev) => { durTr[t.id] = +ev.target.value; rotDur.textContent = `${virgula(durTr[t.id], 2)} s`; animarTransicao(box, t.id, durTr[t.id]); } });
      faixa.addEventListener("keydown", (ev) => ev.stopPropagation());
      setTimeout(() => animarTransicao(box, t.id, d), 30);
      return el("article", { class: "gcard", dataset: { tr: t.id } }, box,
        el("div", { class: "gcab" }, el("h3", {}, t.titulo), el("span", { class: "gselo", hidden: true }, "neste corte")),
        el("p", { class: "gdesc" }, t.descricao),
        el("p", { class: "gbom" }, `Bom para ${t.bom_para}`),
        t.aproximada_xml ? el("p", { class: "gnota" }, "No Premiere e no Resolve entra como dissolver, com um marcador no corte; o render faz esta.") : null,
        el("div", { class: "glinha" }, el("span", {}, "Duração"), faixa, rotDur),
        el("div", { class: "gacoes" }, el("button", { class: "gbt primario", disabled: !c, onclick: () => mudarTransicao(corteAtual(), { tipo: t.id, duracao: durTr[t.id] }) }, "Aplicar neste corte")));
    });
    return [el("div", { class: "gintro" }, el("div", { id: "gal-corte", class: "gcorte" }),
      el("p", { class: "discreto" }, "A transição fica centrada no corte, metade de cada lado; a duração do vídeo não muda. No painel ela aparece aproximada ao tocar.")), ...cards];
  }

  async function mudarTransicao(c, tr) {
    if (!c) return;
    const r = await acao("/api/galeria/transicao", { id: c.para.id, tipo: tr ? tr.tipo : null, duracao: tr ? tr.duracao : null });
    if (!r) return;
    const meta = tr && cat.transicoes.find((t) => t.id === tr.tipo);
    avisar(meta ? `${meta.titulo} no corte de ${fmt(c.tempo)} (${c.de.id} → ${c.para.id})` : `Corte seco em ${fmt(c.tempo)}`);
    $("#gal-corte") && delete $("#gal-corte").dataset.chave;
    desenharCorte();
  }

  // ---------------------------------------------------------------- sons
  function secaoSons() {
    const s = cat.sons, cats = Object.keys(s.categorias);
    if (!s.biblioteca || !cats.length) {
      return [el("div", { class: "gvazio" },
        el("h3", {}, s.biblioteca ? "A biblioteca de sons está vazia" : "Você ainda não tem uma biblioteca de sons"),
        s.erro ? el("p", { class: "gnota" }, s.erro) : null,
        el("p", {}, "O pacote inicial tem 12 sons feitos pelo próprio motor, livres para usar: whoosh, impacto, pop, clique, sino, subida e falha digital. Depois você junta os seus na mesma pasta."),
        el("button", { class: "gbt primario", onclick: criarPacote }, s.biblioteca ? "Pôr o pacote inicial na biblioteca" : "Criar o pacote inicial"))];
    }
    if (catSom && !cats.includes(catSom)) catSom = null;
    const chips = el("div", { class: "gchips" }, el("button", { "aria-pressed": !catSom, onclick: () => { catSom = null; desenhar(); } }, "Todos"),
      ...cats.map((k) => el("button", { "aria-pressed": catSom === k, onclick: () => { catSom = k; desenhar(); } }, k)));
    const vol = el("div", { class: "gsegmentado", role: "group", "aria-label": "Volume ao inserir" },
      ...[[-6, "alto"], [-12, "médio"], [-18, "baixo"]].map(([g, nome]) => el("button", { "aria-pressed": ganho === g, onclick: () => { ganho = g; desenhar(); } }, nome)));
    const lista = el("ul", { class: "gsons" });
    for (const k of cats) {
      if (catSom && k !== catSom) continue;
      if (!catSom) lista.append(el("li", { class: "gsom-cat" }, k));
      for (const som of s.categorias[k]) {
        const bt = el("button", { class: "gplay", "aria-label": `Ouvir ${som.nome}`, title: "Ouvir" }, el("i"));
        bt.addEventListener("click", () => ouvir(som, bt));
        lista.append(el("li", { class: "gsom" }, bt,
          el("div", { class: "gsom-txt" }, el("b", {}, som.nome), el("span", { class: "discreto" }, `${virgula(som.duracao, 2)} s${som.nota ? " · " + som.nota : ""}`)),
          el("button", { class: "gbt", dataset: { emCursor: "Inserir" }, title: "O pico do som cai no cursor", onclick: () => inserirSom(som) }, `Inserir em ${fmt(T.t)}`)));
      }
    }
    return [el("div", { class: "gintro" }, el("p", {}, "O pico de cada som cai no ponto do cursor. O arquivo é copiado para os assets do projeto."),
      el("div", { class: "glinha" }, el("span", {}, "Volume"), vol), chips), lista];
  }

  function ouvir(som, bt) {
    if (tocandoSom) { tocandoSom.pause(); $$(".gplay.tocando").forEach((b) => b.classList.remove("tocando")); if (tocandoSom._id === som.id) { tocandoSom = null; return; } }
    const a = new Audio(url(`/api/som?id=${encodeURIComponent(som.id)}`));
    a._id = som.id;
    a.volume = Math.min(1, Math.pow(10, (ganho + 6) / 20));
    a.play().catch((e) => avisar(`Não tocou: ${e.message}`, true));
    a.addEventListener("ended", () => { bt.classList.remove("tocando"); tocandoSom = null; });
    bt.classList.add("tocando");
    tocandoSom = a;
  }

  async function inserirSom(som) {
    const r = await acao("/api/galeria/som", { id: som.id, tempo_seq: T.t, ganho_db: ganho });
    if (r) avisar(`${som.nome} entrou como ${r.info.id}, com o pico em ${fmt(T.t)}`);
  }

  async function criarPacote() {
    avisar("Criando os sons…");
    try {
      const r = await api("/api/galeria/pacote-sons", {});
      const info = r.info || {};
      avisar(info.configurada ? `Pacote criado em ${info.pasta} e ligado como a sua biblioteca de sons` : `${info.feitos.length} sons novos na biblioteca`);
      if (r.dados) aplicarDados(r.dados);
      await carregar(true);
      desenhar();
    } catch (e) { avisar(e.message, true); }
  }

  // ---------------------------------------------------------------- ganchos do painel
  function aoMudarDados() {
    if (!cat || !visivel()) return;
    if (secao === "transicoes") { const b = $("#gal-corte"); if (b) delete b.dataset.chave; desenharCorte(); }
  }

  return { iniciar, mostrar, desenhar, atualizarCursor, aoMudarDados, escalarIframes, carregar, ANIM, srcEfeitoPara: (id, params, dur) => {
    const p = params && Object.keys(params).length ? "&p=" + encodeURIComponent(JSON.stringify(params)) : "";
    return url(`/api/efeito?nome=${encodeURIComponent(id)}&formato=${encodeURIComponent((D && D.formato) || "")}${p}${dur ? `&d=${dur}` : ""}`);
  } };
})();
