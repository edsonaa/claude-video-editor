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
  let est = null;               // /api/estoque
  let filtroAnim = "todos";     // todos | efeito | motion | estoque
  let novaPeca = null;          // o formulário de "adicionar ao estoque", aberto

  const SECOES = { legendas: "Legendas", animacoes: "Animações", transicoes: "Transições", sons: "Sons", estoque: "Estoque" };
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
    if (secao === "estoque" && !est) { carregarEstoque().then(desenhar); return; }
    const f = { legendas: secaoLegendas, animacoes: secaoAnimacoes, transicoes: secaoTransicoes, sons: secaoSons, estoque: secaoEstoque }[secao];
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
        el("div", { class: "gcab" }, el("h3", {}, e.titulo), seu(e), atual.estilo === e.id ? el("span", { class: "gselo" }, "em uso") : null),
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
    const lista = cat.animacoes.filter((e) => filtroAnim === "todos" || (filtroAnim === "estoque" ? e.estoque : e.categoria === filtroAnim));
    const chips = el("div", { class: "gchips" }, ...[["todos", "Todas"], ["efeito", "Efeitos"], ["motion", "Motion"], ["estoque", "Do seu estoque"]]
      .map(([k, nome]) => el("button", { "aria-pressed": filtroAnim === k, onclick: () => { filtroAnim = k; aberto = null; desenhar(); } }, nome)));
    const cards = lista.map((e) => {
      const box = caixaPrevia(e.formato === "tela_cheia" ? "cheia" : "");
      const fr = iframeEfeito(e);
      box.append(fr);
      box.addEventListener("mouseenter", () => mandar(fr, { cmd: "tocar" }));
      box.addEventListener("mouseleave", () => { if (aberto !== e.id) mandar(fr, { cmd: "parar" }); });
      const card = el("article", { class: "gcard" + (aberto === e.id ? " aberto" : ""), dataset: { efeito: e.id } },
        box,
        el("div", { class: "gcab" }, el("h3", {}, e.titulo), seu(e), el("span", { class: "gfmt" }, FORMATOS_EF[e.formato] || e.formato),
          el("span", { class: "discreto" }, `${virgula(e.duracao.padrao, 1)} s`)),
        el("p", { class: "gdesc" }, e.descricao),
        e.bom_para ? el("p", { class: "gbom" }, `Bom para ${e.bom_para}`) : null,
        aberto === e.id ? formularioEfeito(e, fr) : el("div", { class: "gacoes" },
          el("button", { class: "gbt", onclick: () => { aberto = e.id; desenhar(); } }, "Escolher o conteúdo e inserir…"),
          botaoSugerir("animacao", e)));
      return card;
    });
    const usadas = D.motions.filter((m) => m.origem === "painel").length;
    return [el("div", { class: "gintro" }, el("p", {}, "Passe o mouse para tocar. Inserir põe a animação aprovada no plano, no ponto do cursor; Sugerir deixa um pedido ali para o Claude decidir como usar."),
      usadas ? el("p", { class: "gnota" }, `${usadas} animação(ões) já escolhida(s) aqui: veja na aba Animações.`) : null, chips),
      ...(cards.length ? cards : [el("p", { class: "vazio" }, filtroAnim === "estoque" ? "Nenhuma animação sua ainda: adicione pela seção Estoque." : "Nada nesse filtro.")])];
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

  // a prévia de cada tipo (os quadros-chave do JSON da transição), uma aproximação do xfade do render
  function animarTransicao(box, tipo, dur) { animarTransicaoCom(box, animTransicaoCat(tipo), dur); }
  function animTransicaoCat(tipo) {
    const t = (cat && cat.transicoes.find((x) => x.id === tipo)) || {};
    const p = t.previa || null;
    return p ? { fundo: p.fundo, a: p.a, b: p.b, aCima: !!p.a_cima } : animTransicao(tipo);
  }
  function animarTransicaoCom(box, an, dur) {
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
        el("div", { class: "gcab" }, el("h3", {}, t.titulo), seu(t), el("span", { class: "gselo", hidden: true }, "neste corte")),
        el("p", { class: "gdesc" }, t.descricao),
        el("p", { class: "gbom" }, `Bom para ${t.bom_para}`),
        t.aproximada_xml ? el("p", { class: "gnota" }, "No Premiere e no Resolve entra como dissolver, com um marcador no corte; o render faz esta.") : null,
        el("div", { class: "glinha" }, el("span", {}, "Duração"), faixa, rotDur),
        el("div", { class: "gacoes" }, el("button", { class: "gbt primario", disabled: !c, onclick: () => mudarTransicao(corteAtual(), { tipo: t.id, duracao: durTr[t.id] }) }, "Aplicar neste corte"),
          botaoSugerir("transicao", t)));
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

  // ---------------------------------------------------------------- peças da pessoa e sugestões
  function seu(x) {
    return x.estoque ? el("span", { class: "gseu", title: x.estoque.gostei ? `O que você gostou: ${x.estoque.gostei}` : "Do seu estoque" }, "seu") : null;
  }

  // a etapa do pedido: a primeira ainda aberta entre as que cuidam disso
  function etapaPara(tipo) {
    const cand = tipo === "transicao" ? ["cortes", "render"] : ["motion_mapa", "motion_render"];
    return cand.find((e) => D.fluxo.includes(e) && D.etapas[e] !== "concluido") || D.proxima || cand[0];
  }

  function botaoSugerir(tipo, x) {
    return el("button", { class: "gbt fantasma", dataset: { emCursor: "Sugerir" }, title: "Deixa um pedido no ponto do cursor para o Claude usar esta peça ali",
      onclick: async () => {
        const nome = tipo === "transicao" ? `a transição ${x.titulo}` : `a animação ${x.titulo}`;
        const r = await acao("/api/pedido", { etapa: etapaPara(tipo), tempo_seq: T.t,
          texto: `Usar ${nome} (${x.id}) aqui${x.estoque ? ", do meu estoque" : ""} (sugerido pela galeria)` });
        if (r) avisar(`Sugestão deixada em ${fmt(T.t)}: aparece em Pedidos e para o Claude`);
      } }, `Sugerir em ${fmt(T.t)}`);
  }

  // ---------------------------------------------------------------- o estoque
  const ROT_TIPO = { legenda: "Legenda", transicao: "Transição", efeito: "Efeito", motion: "Motion" };
  const DICA_TIPO = {
    legenda: "Um jeito de mostrar a legenda: fonte, cor, contorno, caixa, palavra a palavra.",
    transicao: "Uma passagem de um plano para o outro.",
    efeito: "Um elemento animado: tarja, título, card, contador, chamada.",
    motion: "Um jeito de mover: como algo entra, assenta e sai, ou um movimento de câmera.",
  };

  async function carregarEstoque() {
    try { est = await api("/api/estoque"); } catch (e) { est = { itens: [], resumo: {}, bases: {}, erro: e.message }; }
    return est;
  }

  async function recarregarTudo() {
    await Promise.all([carregarEstoque(), carregar(true)]);
    desenhar();
  }

  const arqEstoque = (id, qual) => url(`/api/estoque/arquivo?id=${encodeURIComponent(id)}&qual=${qual}`);

  function secaoEstoque() {
    const r = est.resumo || {};
    const intro = el("div", { class: "gintro" },
      el("p", {}, "Peças suas, guardadas fora do plugin. Mande um trecho de referência e conte o que gostou: o Claude analisa, constrói e te mostra a prévia aqui. Aprovada, a peça aparece na galeria, nas boas-vindas e no plano dos próximos vídeos."),
      est.erro ? el("p", { class: "gnota" }, est.erro) : null,
      novaPeca ? null : el("div", { class: "gacoes" }, el("button", { class: "gbt primario", onclick: () => { novaPeca = { tipo: "efeito", origem: "arquivo", de: null, ate: null }; desenhar(); } }, "Adicionar ao estoque")));
    const out = [intro];
    if (novaPeca) out.push(formNovaPeca());
    const por = (st) => est.itens.filter((i) => i.status === st);
    const rasc = por("rascunho"), entr = por("entrada"), ativos = por("ativo"), arq = por("arquivado");
    if (rasc.length) out.push(el("h3", { class: "gsub" }, `Para você aprovar (${rasc.length})`), ...rasc.map(cardRascunho));
    if (entr.length) {
      out.push(el("h3", { class: "gsub" }, `Esperando o Claude (${entr.length})`),
        el("p", { class: "gnota" }, "Peça no chat: “analise o estoque” (ou /edicao:estoque). O Claude mede o trecho, constrói a peça e ela volta aqui para você aprovar."),
        ...entr.map(cardEntrada));
    }
    if (ativos.length) {
      out.push(el("h3", { class: "gsub" }, `No seu estoque (${ativos.length})`));
      for (const t of Object.keys(ROT_TIPO)) {
        const g = ativos.filter((i) => i.tipo === t);
        if (g.length) out.push(el("p", { class: "gsom-cat" }, ROT_TIPO[t]), ...g.map(cardAtivo));
      }
    }
    if (arq.length) out.push(el("details", { class: "garq" }, el("summary", {}, `Arquivados (${arq.length})`),
      ...arq.map((i) => el("div", { class: "glinha-est" }, el("span", {}, `${ROT_TIPO[i.tipo]} · ${i.nome}`),
        el("button", { class: "gbt fantasma", onclick: () => agirEstoque("aprovar", i, `${i.nome} voltou ao estoque`) }, "Voltar ao estoque")))));
    if (!rasc.length && !entr.length && !ativos.length && !novaPeca) out.push(el("p", { class: "vazio" }, "O estoque está vazio. Comece por uma legenda, transição, efeito ou motion de que você gosta."));
    return out;
  }

  function campoTexto(id, rotulo, valor, onIn, area = false, dica = null) {
    const e = el(area ? "textarea" : "input", { id, rows: area ? 3 : undefined, value: area ? undefined : valor || "", oninput: (ev) => onIn(ev.target.value) }, area ? valor || "" : null);
    e.addEventListener("keydown", (ev) => ev.stopPropagation());
    return el("div", { class: "gcampo" }, el("label", { for: id }, rotulo), e, dica ? el("small", { class: "discreto" }, dica) : null);
  }

  function formNovaPeca() {
    const n = novaPeca;
    const tipos = el("div", { class: "gsegmentado", role: "group", "aria-label": "Tipo da peça" },
      ...Object.entries(ROT_TIPO).map(([k, nome]) => el("button", { "aria-pressed": n.tipo === k, onclick: () => { n.tipo = k; n.parecido = ""; desenhar(); } }, nome)));
    const bases = (est.bases || {})[n.tipo] || [];
    const parecido = el("select", { id: "np-parecido", onchange: (ev) => { n.parecido = ev.target.value; } },
      el("option", { value: "" }, "nenhuma em especial"), ...bases.map((b) => el("option", { value: b.id, selected: b.id === n.parecido }, b.titulo)));
    const origens = el("div", { class: "gsegmentado", role: "group", "aria-label": "De onde vem a referência" },
      ...[["arquivo", "Um arquivo"], ["video", "Um trecho deste vídeo"], ["nenhum", "Só a descrição"]]
        .map(([k, nome]) => el("button", { "aria-pressed": n.origem === k, onclick: () => { n.origem = k; if (k === "video" && n.de === null) { n.de = T.t; n.ate = Math.min(D.duracao, T.t + 3); } desenhar(); } }, nome)));
    const faixa = () => (n.de !== null && n.ate !== null ? `de ${fmt(n.de)} a ${fmt(n.ate)} (${virgula(Math.max(0, n.ate - n.de), 1)} s)` : "o arquivo inteiro (até 90 s)");
    const rotFaixa = el("span", { class: "discreto" }, faixa());
    let blocoOrigem = null;
    if (n.origem === "arquivo") {
      const prev = el("video", { class: "np-video", controls: true, muted: true, playsinline: true, hidden: !n.urlLocal, src: n.urlLocal || undefined });
      const entrada = el("input", { type: "file", accept: "video/*,image/*,.gif", onchange: (ev) => {
        const f = ev.target.files[0];
        if (!f) return;
        if (n.urlLocal) URL.revokeObjectURL(n.urlLocal);
        n.arquivo = f; n.urlLocal = URL.createObjectURL(f); n.de = null; n.ate = null;
        if (!n.nome) n.nome = f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
        desenhar();
      } });
      const ehVideo = n.arquivo && n.arquivo.type.startsWith("video/");
      entrada.hidden = true;
      const escolher = el("button", { class: "gbt", onclick: () => entrada.click() }, n.arquivo ? "Trocar o arquivo" : "Escolher o arquivo");
      blocoOrigem = el("div", { class: "gcampo" }, el("label", {}, "O arquivo (vídeo, GIF ou imagem)"), entrada, el("div", { class: "gacoes" }, escolher),
        n.arquivo ? el("small", { class: "discreto" }, `${n.arquivo.name} · ${(n.arquivo.size / 1048576).toFixed(1).replace(".", ",")} MB`) : null,
        ehVideo ? prev : null,
        ehVideo ? el("div", { class: "gacoes" },
          el("button", { class: "gbt", onclick: () => { n.de = prev.currentTime; if (n.ate !== null && n.ate <= n.de) n.ate = null; rotFaixa.textContent = faixa(); } }, "Início aqui"),
          el("button", { class: "gbt", onclick: () => { n.ate = prev.currentTime; if (n.de === null) n.de = 0; rotFaixa.textContent = faixa(); } }, "Fim aqui"),
          rotFaixa) : null);
      if (ehVideo && n.urlLocal) prev.hidden = false;
    } else if (n.origem === "video") {
      blocoOrigem = el("div", { class: "gcampo" }, el("label", {}, "O trecho da sequência (use o cursor do vídeo)"),
        el("div", { class: "gacoes" },
          el("button", { class: "gbt", onclick: () => { n.de = T.t; if (n.ate <= n.de) n.ate = Math.min(D.duracao, n.de + 3); desenhar(); } }, `Início no cursor (${fmt(T.t)})`),
          el("button", { class: "gbt", onclick: () => { n.ate = T.t; if (n.de >= n.ate) n.de = Math.max(0, n.ate - 3); desenhar(); } }, `Fim no cursor (${fmt(T.t)})`)),
        rotFaixa, el("small", { class: "discreto" }, "Sai da gravação de origem; se o trecho passar de um corte, vai até o fim do segmento."));
    }
    const enviar = el("button", { class: "gbt primario", onclick: () => mandarPeca(enviar) }, "Mandar para o estoque");
    return el("div", { class: "gform np" },
      el("div", { class: "gcampo" }, el("label", {}, "O que é"), tipos, el("small", { class: "discreto" }, DICA_TIPO[n.tipo])),
      campoTexto("np-nome", "Nome", n.nome, (v) => { n.nome = v; }),
      campoTexto("np-gostei", "O que você gostou", n.gostei, (v) => { n.gostei = v; }, true,
        "O detalhe que importa: “a letra entra pulando”, “o fundo desfoca antes do texto”. É o que guia a análise."),
      el("div", { class: "gcampo" }, el("label", { for: "np-parecido" }, "Parecida com alguma que já existe?"), parecido),
      el("div", { class: "gcampo" }, el("label", {}, "A referência"), origens), blocoOrigem,
      el("div", { class: "gacoes" }, enviar, el("button", { class: "gbt fantasma", onclick: () => { if (novaPeca && novaPeca.urlLocal) URL.revokeObjectURL(novaPeca.urlLocal); novaPeca = null; desenhar(); } }, "Cancelar")));
  }

  function enviarArquivo(arquivo, aoProgresso) {
    return new Promise((ok, falha) => {
      const x = new XMLHttpRequest();
      x.open("POST", url("/api/estoque/envio"));
      x.setRequestHeader("X-Painel-Token", TOKEN);
      x.setRequestHeader("X-Nome-Arquivo", encodeURIComponent(arquivo.name));
      x.upload.onprogress = (e) => { if (e.lengthComputable) aoProgresso(e.loaded / e.total); };
      x.onload = () => {
        let j = {};
        try { j = JSON.parse(x.responseText); } catch (_) { /* vazio */ }
        x.status === 200 ? ok(j) : falha(new Error(j.erro || `erro ${x.status}`));
      };
      x.onerror = () => falha(new Error("o envio caiu"));
      x.send(arquivo);
    });
  }

  async function mandarPeca(botao) {
    const n = novaPeca;
    if (!(n.nome || "").trim()) return avisar("Dê um nome para a peça", true);
    if (!(n.gostei || "").trim()) return avisar("Conte o que você gostou: é o que guia a análise", true);
    if (n.origem === "arquivo" && !n.arquivo) return avisar("Escolha o arquivo de referência (ou mude para “Só a descrição”)", true);
    botao.disabled = true;
    try {
      let origem = { tipo: n.origem };
      if (n.origem === "arquivo") {
        const r = await enviarArquivo(n.arquivo, (p) => { botao.textContent = `Enviando… ${Math.round(p * 100)}%`; });
        origem = { tipo: "arquivo", envio: r.envio, nome: n.arquivo.name, de: n.de, ate: n.ate };
        botao.textContent = "Cortando o trecho…";
      } else if (n.origem === "video") origem = { tipo: "video", de: n.de, ate: n.ate };
      const r = await api("/api/estoque/novo", { tipo: n.tipo, nome: n.nome, gostei: n.gostei, parecido: n.parecido || null, origem });
      if (n.urlLocal) URL.revokeObjectURL(n.urlLocal);
      novaPeca = null;
      avisar(`${r.info.nome} está no estoque, esperando o Claude analisar`);
      await recarregarTudo();
    } catch (e) {
      avisar(e.message, true);
      botao.disabled = false;
      botao.textContent = "Mandar para o estoque";
    }
  }

  async function agirEstoque(qual, it, msg, extra = {}) {
    try {
      await api(`/api/estoque/${qual}`, { id: it.id, ...extra });
      avisar(msg);
      await recarregarTudo();
    } catch (e) { avisar(e.message, true); }
  }

  // a prévia de uma peça (rascunho ou ativa): a mesma tecnologia de cada seção da galeria
  function previaPeca(it) {
    const box = caixaPrevia(it.tipo === "transicao" ? "gtr" : "");
    if (it.tipo === "legenda" && it.dados) {
      const [w, h] = dimsQuadro(), camada = el("div", { class: "glegenda" });
      box.append(camada);
      LegendaEstilo.aplicar(camada, it.dados, D.tema, { vertical: h > w });
      LegendaEstilo.bloco(camada, it.dados.modo === "palavra" ? ["vinte placas"] : ["vinte placas com", "o mesmo defeito"], it.dados.modo === "palavra", 1);
    } else if (it.tipo === "transicao") {
      if (it.arquivos.previa) { box.replaceChildren(el("img", { class: "gimg", src: arqEstoque(it.id, "previa") + `&v=${Date.now()}`, alt: `Prévia de ${it.nome}` })); }
      else {
        box.replaceChildren(el("div", { class: "gtr-a" }), el("div", { class: "gtr-b" }));
        const c = corteAtual();
        if (c) { $(".gtr-a", box).style.backgroundImage = `url("${quadroDe(c.de.video, c.de.out - 0.08)}")`; $(".gtr-b", box).style.backgroundImage = `url("${quadroDe(c.para.video, c.para.in + 0.08)}")`; }
        const p = (it.dados && it.dados.previa) || {};
        setTimeout(() => animarTransicaoCom(box, { fundo: p.fundo, a: p.a, b: p.b, aCima: !!p.a_cima }, (it.dados && it.dados.duracao && it.dados.duracao.padrao) || 0.5), 30);
      }
    } else if (it.dados) {
      const fr = iframeEfeito({ id: it.id, titulo: it.nome });
      box.append(fr);
      box.addEventListener("mouseenter", () => mandar(fr, { cmd: "tocar" }));
      box.addEventListener("mouseleave", () => mandar(fr, { cmd: "parar" }));
    }
    return box;
  }

  function referencia(it) {
    if (it.arquivos.trecho) return el("video", { class: "np-video", controls: true, muted: true, preload: "metadata", src: arqEstoque(it.id, "trecho") });
    if (it.arquivos.referencia) return el("img", { class: "gimg-ref", src: arqEstoque(it.id, "referencia"), alt: `Referência de ${it.nome}` });
    return null;
  }

  function cardRascunho(it) {
    const ajustes = (it.ajustes || []).filter((a) => !a.feito);
    let pedindo = false;
    const caixaAjuste = el("div", { class: "gform", hidden: true });
    const texto = el("textarea", { rows: 2, "aria-label": `O que ajustar em ${it.nome}` });
    texto.addEventListener("keydown", (ev) => ev.stopPropagation());
    caixaAjuste.append(texto, el("div", { class: "gacoes" },
      el("button", { class: "gbt primario", onclick: () => agirEstoque("ajuste", it, "Ajuste anotado: o Claude refaz e te mostra de novo", { texto: texto.value }) }, "Mandar o ajuste")));
    return el("article", { class: "gcard" }, previaPeca(it),
      el("div", { class: "gcab" }, el("h3", {}, it.nome), el("span", { class: "gfmt" }, ROT_TIPO[it.tipo])),
      el("p", { class: "gdesc" }, `O que você gostou: ${it.gostei}`),
      it.analise ? el("details", {}, el("summary", { class: "gbom" }, "O que o Claude mediu e fez"), el("p", { class: "gbom" }, it.analise)) : null,
      ajustes.length ? el("p", { class: "gnota" }, `Ajuste pedido: ${ajustes[ajustes.length - 1].texto} (esperando o Claude)`) : null,
      el("div", { class: "gacoes" },
        el("button", { class: "gbt primario", onclick: () => agirEstoque("aprovar", it, `${it.nome} entrou no seu estoque`) }, "Aprovar"),
        el("button", { class: "gbt", onclick: () => { pedindo = !pedindo; caixaAjuste.hidden = !pedindo; if (pedindo) texto.focus(); } }, "Pedir ajuste…"),
        el("button", { class: "gbt fantasma perigo", onclick: () => agirEstoque("recusar", it, `${it.nome} recusada`) }, "Recusar")),
      caixaAjuste);
  }

  function cardEntrada(it) {
    return el("article", { class: "gcard compacto" },
      el("div", { class: "gcab" }, el("h3", {}, it.nome), el("span", { class: "gfmt" }, ROT_TIPO[it.tipo]),
        el("span", { class: "discreto" }, it.por === "painel" ? "pelo painel" : "pelo Claude")),
      el("p", { class: "gdesc" }, it.gostei), it.parecido_com ? el("p", { class: "gbom" }, `Parecida com ${it.parecido_com}`) : null,
      referencia(it),
      el("div", { class: "gacoes" }, el("button", { class: "gbt fantasma perigo", onclick: () => agirEstoque("recusar", it, `${it.nome} saiu da entrada`) }, "Tirar")));
  }

  function cardAtivo(it) {
    let pedindo = false;
    const texto = el("textarea", { rows: 2, "aria-label": `O que ajustar em ${it.nome}` });
    texto.addEventListener("keydown", (ev) => ev.stopPropagation());
    const caixa = el("div", { class: "gform", hidden: true }, texto, el("div", { class: "gacoes" },
      el("button", { class: "gbt primario", onclick: () => agirEstoque("ajuste", it, "Ajuste anotado: a peça volta para o Claude", { texto: texto.value }) }, "Mandar o ajuste")));
    const ver = { legenda: "legendas", transicao: "transicoes", efeito: "animacoes", motion: "animacoes" }[it.tipo];
    return el("div", { class: "gativo" },
      el("div", { class: "gativo-txt" }, el("b", {}, it.nome), el("span", { class: "discreto" }, it.gostei)),
      el("div", { class: "gacoes" },
        el("button", { class: "gbt", onclick: () => { secao = ver; if (ver === "animacoes") filtroAnim = "estoque"; desenhar(); } }, "Ver na galeria"),
        el("button", { class: "gbt fantasma", onclick: () => { pedindo = !pedindo; caixa.hidden = !pedindo; } }, "Pedir ajuste…"),
        el("button", { class: "gbt fantasma", onclick: () => agirEstoque("arquivar", it, `${it.nome} arquivada`) }, "Arquivar")),
      caixa);
  }

  // ---------------------------------------------------------------- ganchos do painel
  function aoMudarDados() {
    if (!cat || !visivel()) return;
    if (secao === "transicoes") { const b = $("#gal-corte"); if (b) delete b.dataset.chave; desenharCorte(); }
  }

  return { iniciar, mostrar, desenhar, atualizarCursor, aoMudarDados, escalarIframes, carregar, srcEfeitoPara: (id, params, dur) => {
    const p = params && Object.keys(params).length ? "&p=" + encodeURIComponent(JSON.stringify(params)) : "";
    return url(`/api/efeito?nome=${encodeURIComponent(id)}&formato=${encodeURIComponent((D && D.formato) || "")}${p}${dur ? `&d=${dur}` : ""}`);
  } };
})();
