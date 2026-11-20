/* Arrastar e soltar, como num programa de edição.
   No tempo (linha do tempo): mover animações e sons, esticar animações e legendas pelas bordas,
   aparar a entrada e a saída de um segmento (as bordas) e mudar a ordem dos segmentos (o meio).
   Na tela (o quadro): mover e redimensionar a animação selecionada, arrastar a legenda e o
   enquadramento de um segmento recortado. Ímã nos cortes, no cursor e nas bordas dos outros
   itens (Alt desliga). Cada soltura vira uma mudança gravada, com desfazer (Ctrl+Z) e registro
   para o Claude. Usa as funções do painel.js; nada roda antes de Arrastar.iniciar(). */
"use strict";

const Arrastar = (() => {
  const LIMIAR = 4;          // px antes de virar arrasto (menos que isso é clique)
  const BORDA = 7;           // px da borda de um bloco que puxam a borda
  const IMA = 8;             // px do ímã
  const MOVEIS = ["sobreposicao", "sobreposicao_lateral", "enfase"];
  let ativo = null;          // arrasto em andamento
  let ultimoClique = 0;

  const virg = (x, c = 2) => Number(x).toFixed(c).replace(".", ",");
  const sinal = (x) => (x >= 0 ? "+" : "−") + virg(Math.abs(x)) + " s";
  const quadroDeT = (t) => Math.round(t * fps) / fps;

  // ---------------------------------------------------------------- no tempo
  function itemDe(tipo, id) {
    if (tipo === "motion") { const m = D.motions.find((x) => x.id === id); return m && { m, ini: m.inicio_seq, fim: m.fim_seq ?? m.inicio_seq + 2 }; }
    if (tipo === "sfx") { const s = D.sfx.find((x) => x.id === id); return s && { m: s, ini: s.inicio_seq, fim: s.inicio_seq }; }
    if (tipo === "leg") { const b = (D.legendas ? D.legendas.blocos : []).find((x) => x.id === id); return b && { m: b, ini: b.i, fim: b.f }; }
    if (tipo === "seg") { const s = D.segmentos.find((x) => x.id === id); return s && { m: s, ini: s.seq_ini, fim: s.seq_fim }; }
    return null;
  }

  const pronta = (m) => !!m.chave;   // animação com render: só move

  // o que acontece se arrastar a partir deste ponto do bloco
  function modoDe(alvo, clientX) {
    const tipo = alvo.dataset.tipo;
    if (!["motion", "sfx", "leg", "seg"].includes(tipo) || alvo.classList.contains("tr-marca")) return null;
    const r = alvo.getBoundingClientRect(), largo = r.width > BORDA * 2.5;
    const naEsq = largo && clientX - r.left < BORDA, naDir = largo && r.right - clientX < BORDA;
    if (tipo === "sfx") return "mover";
    if (tipo === "motion") {
      const it = itemDe("motion", alvo.dataset.id);
      if (!it || !pronta(it.m)) { if (naEsq) return "ini"; if (naDir) return "fim"; }
      return "mover";
    }
    if (tipo === "leg") return naEsq ? "ini" : naDir ? "fim" : null;
    if (tipo === "seg") return naEsq ? "ini" : naDir ? "fim" : D.segmentos.length > 1 ? "ordem" : null;
    return null;
  }

  function alvos(tipo, id) {
    const ts = [0, D.duracao, T.t];
    D.segmentos.forEach((s) => ts.push(s.seq_ini, s.seq_fim));
    if (tipo !== "seg") {
      D.motions.forEach((m) => { if (m.id !== id && m.inicio_seq != null) ts.push(m.inicio_seq, m.fim_seq ?? m.inicio_seq + 2); });
      D.sfx.forEach((s) => { if (s.id !== id) ts.push(s.inicio_seq); });
      if (D.legendas) D.legendas.blocos.forEach((b) => { if (b.id !== id) ts.push(b.i, b.f); });
    }
    return ts.filter((x) => x !== null && x !== undefined && isFinite(x));
  }

  function ima(t, lista, livre) {
    if (livre) return { t, em: null };
    let melhor = null;
    for (const a of lista) {
      const dpx = Math.abs(a - t) * pxs;
      if (dpx <= IMA && (!melhor || dpx < melhor.d)) melhor = { d: dpx, a };
    }
    return melhor ? { t: melhor.a, em: melhor.a } : { t, em: null };
  }

  function guia(t) {
    let g = $("#guia-ima");
    if (t === null || t === undefined) { if (g) g.hidden = true; return; }
    if (!g) { g = el("div", { id: "guia-ima", class: "guia-ima" }); $("#trilhas").append(g); }
    g.hidden = false;
    g.style.left = `${t * pxs}px`;
  }

  function dica(texto, x, y) {
    let d = $("#dica-arrasto");
    if (!texto) { if (d) d.hidden = true; return; }
    if (!d) { d = el("div", { id: "dica-arrasto", class: "dica-arrasto", role: "status" }); document.body.append(d); }
    d.hidden = false;
    d.textContent = texto;
    d.style.left = `${x + 14}px`;
    d.style.top = `${y - 34}px`;
  }

  function noBloco(tipo, id) { return $(`#trilhas [data-tipo="${tipo}"][data-id="${id}"]:not(.tr-marca)`); }

  // chamado pelo mousedown da linha do tempo; true = o arrasto cuida (não rolar o cursor)
  function naLinha(ev) {
    const alvo = ev.target.closest("[data-tipo]");
    if (!alvo || ev.button !== 0) return false;
    const modo = modoDe(alvo, ev.clientX);
    if (!modo) return false;
    const tipo = alvo.dataset.tipo, id = alvo.dataset.id, it = itemDe(tipo, id);
    if (!it) return false;
    ev.preventDefault();
    const x0 = ev.clientX, r = $("#rolagem");
    const tClique = (ev.clientX - r.getBoundingClientRect().left + r.scrollLeft) / pxs;
    const est = { tipo, id, modo, it, x0, comecou: false, lista: alvos(tipo, id), novo: null };
    const mover = (e2) => {
      if (!est.comecou) {
        if (Math.abs(e2.clientX - x0) < LIMIAR) return;
        est.comecou = true;
        ativo = est;
        if (T.tocando) T.pausar();
        document.body.classList.add("arrastando-" + (modo === "mover" || modo === "ordem" ? "mover" : "borda"));
        const b = noBloco(tipo, id);
        if (b) b.classList.add("arrastado");
      }
      atualizarLinha(est, (e2.clientX - x0) / pxs, e2.altKey, e2);
    };
    const soltar = async (e3) => {
      document.removeEventListener("mousemove", mover);
      document.removeEventListener("mouseup", soltar);
      document.body.classList.remove("arrastando-mover", "arrastando-borda");
      guia(null); dica(null); marcaOrdem(null);
      ativo = null;
      if (!est.comecou) {      // foi clique: o comportamento de sempre
        selecionar(tipo, id, false);
        T.ir(tClique);
        return;
      }
      await soltarLinha(est, e3);
    };
    document.addEventListener("mousemove", mover);
    document.addEventListener("mouseup", soltar);
    return true;
  }

  function atualizarLinha(est, delta, livre, ev) {
    const { tipo, id, modo, it } = est, b = noBloco(tipo, id);
    const dur = it.fim - it.ini;
    if (modo === "ordem") {
      const t = it.ini + dur / 2 + delta;
      const outros = D.segmentos.filter((s) => s.id !== id);
      let para = outros.filter((s) => (s.seq_ini + s.seq_fim) / 2 < t).length;
      const juntaT = para < outros.length ? outros[para].seq_ini - (outros[para].seq_ini > it.ini ? dur : 0) : D.duracao - dur;
      const atual = D.segmentos.findIndex((s) => s.id === id);
      est.novo = { para };
      if (b) b.style.transform = `translateX(${delta * pxs}px)`;
      const xMarca = para === 0 ? 0 : (para >= outros.length ? D.duracao : outros[para].seq_ini);
      marcaOrdem(para === atual ? null : xMarca);
      dica(para === atual ? `${id}: solte em outro lugar para mudar a ordem` :
        `${id} vai ${para < outros.length ? "antes de " + outros[para].id : "para o fim"}`, ev.clientX, ev.clientY);
      return;
    }
    let ini = it.ini, fim = it.fim, em = null;
    if (modo === "mover") {
      ini = it.ini + delta;
      const a = ima(ini, est.lista, livre), z = ima(ini + dur, est.lista, livre);
      if (a.em !== null && (z.em === null || Math.abs(a.t - ini) <= Math.abs(z.t - (ini + dur)))) { ini = a.t; em = a.em; }
      else if (z.em !== null) { ini = z.t - dur; em = z.em; }
      ini = Math.max(0, Math.min(ini, D.duracao - Math.max(dur, 1 / fps)));
      fim = ini + dur;
    } else if (modo === "ini") {
      const a = ima(it.ini + delta, est.lista, livre);
      ini = Math.min(a.t, it.fim - (tipo === "seg" ? 1 / fps : 0.2));
      if (tipo === "seg") ini = Math.max(ini, it.ini - it.m.in);        // não antes do começo do arquivo
      ini = Math.max(0, ini); em = a.em;
    } else {
      const z = ima(it.fim + delta, est.lista, livre);
      fim = Math.max(z.t, it.ini + (tipo === "seg" ? 1 / fps : 0.2));
      fim = Math.min(fim, tipo === "seg" ? Infinity : D.duracao); em = z.em;
    }
    // só a borda que se mexe vai para o quadro; a outra fica exatamente como estava
    if (modo !== "fim") ini = quadroDeT(ini);
    if (modo === "fim") fim = quadroDeT(fim); else if (modo === "mover") fim = ini + dur;
    est.novo = { ini, fim };
    guia(em);
    if (b) {
      if (tipo === "sfx") b.style.left = `${ini * pxs}px`;
      else { b.style.left = `${ini * pxs}px`; b.style.width = `${Math.max(2, (fim - ini) * pxs - 1)}px`; }
    }
    // o quadro do ponto que está sendo mexido aparece no vídeo
    if (tipo === "seg") {
      const s = it.m;
      const tOrigem = modo === "ini" ? s.in + (ini - it.ini) : s.out + (fim - it.fim);
      mostrarOrigem(s, tOrigem);
      dica(`${id} · ${modo === "ini" ? "entrada" : "saída"} ${sinal(modo === "ini" ? ini - it.ini : fim - it.fim)} · ${Math.round(((modo === "ini" ? ini - it.ini : fim - it.fim)) * fps)} quadros`, ev.clientX, ev.clientY);
    } else {
      T.ir((modo === "fim" ? fim - 1 / fps : ini) + 1e-4, false);
      const txt = tipo === "sfx" ? `${id} em ${fmt(ini)} (${sinal(ini - it.ini)})`
        : modo === "mover" ? `${id} em ${fmt(ini)}–${fmt(fim)} (${sinal(ini - it.ini)})`
          : `${id}: ${fmt(ini)}–${fmt(fim)} · ${virg(fim - ini)} s`;
      dica(txt, ev.clientX, ev.clientY);
    }
  }

  // aparando: mostra o quadro da origem no vídeo (fora do corte atual, então direto no elemento)
  function mostrarOrigem(seg, tOrigem) {
    const v = T.v[T.ativo];
    const m = D.midias["v:" + seg.video];
    if (!m || !m.url) return;
    if (!v.src.includes(m.url.split("?")[0])) { v.src = url(m.url); }
    v.pause();
    try { v.currentTime = Math.max(0, tOrigem); } catch (_) { /* carregando */ }
  }

  function marcaOrdem(t) {
    let m = $("#marca-ordem");
    if (t === null || t === undefined) { if (m) m.hidden = true; return; }
    if (!m) { m = el("div", { id: "marca-ordem", class: "marca-ordem" }); $("#trilhas").append(m); }
    m.hidden = false;
    m.style.left = `${t * pxs}px`;
  }

  async function soltarLinha(est) {
    const { tipo, id, modo, it, novo } = est;
    if (!novo) return desenharLinha();
    let r = null;
    if (modo === "ordem") {
      const atual = D.segmentos.findIndex((s) => s.id === id);
      if (novo.para === atual) return desenharLinha();
      r = await acao("/api/cortes", { acao: "mover", id, para: novo.para }, `${id} mudou de lugar no corte`);
    } else if (tipo === "seg") {
      const s = it.m, corpo = { acao: "ajustar", id };
      if (modo === "ini") corpo.inicio = s.in + (novo.ini - it.ini); else corpo.fim = s.out + (novo.fim - it.fim);
      const dq = Math.round(((modo === "ini" ? novo.ini - it.ini : novo.fim - it.fim)) * fps);
      if (!dq) return T.ir(T.t), desenharLinha();
      r = await acao("/api/cortes", corpo, `${id}: ${modo === "ini" ? "entrada" : "saída"} ${dq > 0 ? "+" : ""}${dq} quadros`);
      T.ir(modo === "ini" ? s.seq_ini + 1e-4 : Math.max(0, (D.segmentos.find((x) => x.id === id) || s).seq_fim - 1 / fps));
    } else {
      if (Math.abs(novo.ini - it.ini) < 0.5 / fps && Math.abs(novo.fim - it.fim) < 0.5 / fps) return desenharLinha();
      const corpo = { tipo, id, inicio: novo.ini };
      if (tipo !== "sfx" && modo !== "mover") corpo.fim = novo.fim;
      if (tipo === "leg") corpo.fim = novo.fim;
      r = await acao("/api/mover", corpo, tipo === "sfx" ? `${id} em ${fmt(novo.ini)}` : `${id}: ${fmt(novo.ini)}–${fmt(novo.fim)}`);
    }
    if (!r) desenharLinha();     // recusado: volta ao que estava
  }

  // cursor certo antes de clicar (borda puxa, meio move)
  function pairar(ev) {
    if (ativo) return;
    const alvo = ev.target.closest("[data-tipo]");
    const modo = alvo ? modoDe(alvo, ev.clientX) : null;
    $("#trilhas").dataset.pairar = modo || "";
  }

  // ---------------------------------------------------------------- na tela
  function motionSel() {
    if (!sel || sel.tipo !== "motion" || !$("#ck-motion").checked) return null;
    const m = D.motions.find((x) => x.id === sel.id);
    if (!m || !MOVEIS.includes(m.formato) || m.status === "riscado") return null;
    const fim = m.fim_seq ?? m.inicio_seq + 2;
    return T.t >= m.inicio_seq && T.t < fim ? m : null;
  }

  function segSel() {
    if (!sel || sel.tipo !== "seg" || !D.formato) return null;
    const i = D.segmentos.findIndex((s) => s.id === sel.id);
    if (i !== T.i) return null;
    const s = D.segmentos[i], v = T.v[T.ativo];
    return v && v.style.objectFit === "cover" ? s : null;
  }

  function caixaLegenda() {
    const c = $("#camada-legenda");
    const partes = $$(".txt", c);
    if (!partes.length || !$("#ck-legenda").checked) return null;
    let r = null;
    for (const p of partes) {
      const b = p.getBoundingClientRect();
      r = r ? { left: Math.min(r.left, b.left), top: Math.min(r.top, b.top), right: Math.max(r.right, b.right), bottom: Math.max(r.bottom, b.bottom) }
        : { left: b.left, top: b.top, right: b.right, bottom: b.bottom };
    }
    return r;
  }
  const dentro = (r, x, y, folga = 6) => r && x >= r.left - folga && x <= r.right + folga && y >= r.top - folga && y <= r.bottom + folga;

  const posDe = (m) => ({ x: 0, y: 0, escala: 1, ...(m.posicao || {}) });

  function aplicarPosicoes() {
    for (const [id, cx] of Motion.caixas) {
      const m = D.motions.find((x) => x.id === id);
      const p = m ? posDe(m) : { x: 0, y: 0, escala: 1 };
      cx.style.transform = p.x || p.y || p.escala !== 1 ? `translate(${p.x * 100}%, ${p.y * 100}%) scale(${p.escala})` : "";
    }
    const dl = (D.tema.legendas || {}).deslocamento || { x: 0, y: 0 };
    $("#camada-legenda").style.translate = dl.x || dl.y ? `${dl.x * 100}cqw ${dl.y * 100}cqh` : "";
    desenharAlca();
  }

  function desenharAlca() {
    const a = $("#alca"), m = motionSel();
    if (!m) { a.hidden = true; return; }
    const p = posDe(m);
    a.hidden = false;
    a.style.left = `${(0.5 + p.x - p.escala / 2) * 100}%`;
    a.style.top = `${(0.5 + p.y - p.escala / 2) * 100}%`;
    a.style.width = `${p.escala * 100}%`;
    a.style.height = `${p.escala * 100}%`;
    $(".alca-rotulo", a).textContent = `${m.id} · arraste para mover · cantos ou roda do mouse: tamanho · duplo clique: volta ao lugar`;
    // o rótulo fica dentro do quadro mesmo com a animação puxada para cima
    $(".alca-rotulo", a).classList.toggle("dentro", 0.5 + p.y - p.escala / 2 < 0.06);
  }

  function naTela(ev) {
    if (ev.button !== 0) return;
    const q = $("#quadro"), r = q.getBoundingClientRect();
    const x0 = ev.clientX, y0 = ev.clientY;
    const canto = ev.target.closest(".alca-canto");
    let alvo = null;
    const leg = caixaLegenda();
    if (canto && motionSel()) alvo = { tipo: "escala", m: motionSel(), canto };
    else if (dentro(leg, x0, y0)) alvo = { tipo: "legenda" };
    else if (motionSel()) alvo = { tipo: "motion", m: motionSel() };
    else if (segSel()) alvo = { tipo: "quadro", s: segSel() };
    if (!alvo) return;
    ev.preventDefault();
    if (T.tocando) T.pausar();
    const agora = Date.now();
    if (agora - ultimoClique < 320) { ultimoClique = 0; return restaurar(alvo); }
    ultimoClique = agora;
    const W = r.width, H = r.height;
    const p0 = alvo.m ? posDe(alvo.m) : null;
    const dl0 = { x: 0, y: 0, ...((D.tema.legendas || {}).deslocamento || {}) };
    const q0 = alvo.s ? { x: 0.5, y: 0.5, ...(alvo.s.quadro || {}) } : null;
    const centro = alvo.m ? { x: r.left + (0.5 + p0.x) * W, y: r.top + (0.5 + p0.y) * H } : null;
    const dist0 = centro ? Math.hypot(x0 - centro.x, y0 - centro.y) || 1 : 1;
    let mudou = false, final = null;
    q.classList.add("movendo");
    const mover = (e) => {
      const dx = (e.clientX - x0) / W, dy = (e.clientY - y0) / H;
      if (!mudou && Math.hypot(e.clientX - x0, e.clientY - y0) < LIMIAR) return;
      mudou = true;
      const ima2 = (v) => (e.altKey || Math.abs(v) > 0.012 ? v : 0);   // ímã no centro
      if (alvo.tipo === "motion") {
        final = { ...p0, x: ima2(clamp(p0.x + dx, -0.5, 0.5)), y: ima2(clamp(p0.y + dy, -0.5, 0.5)) };
        alvo.m.posicao = final;
        dica(`${alvo.m.id}: ${pct(final.x)} na horizontal, ${pct(final.y)} na vertical`, e.clientX, e.clientY);
      } else if (alvo.tipo === "escala") {
        const d = Math.hypot(e.clientX - centro.x, e.clientY - centro.y);
        final = { ...p0, escala: +clamp(p0.escala * d / dist0, 0.25, 2).toFixed(3) };
        alvo.m.posicao = final;
        dica(`${alvo.m.id}: tamanho ${Math.round(final.escala * 100)}%`, e.clientX, e.clientY);
      } else if (alvo.tipo === "legenda") {
        final = { x: ima2(clamp(dl0.x + dx, -0.45, 0.45)), y: ima2(clamp(dl0.y + dy, -0.45, 0.45)) };
        D.tema.legendas = { ...(D.tema.legendas || {}), deslocamento: final };
        dica(`legenda: ${pct(final.x)} na horizontal, ${pct(final.y)} na vertical`, e.clientX, e.clientY);
      } else if (alvo.tipo === "quadro") {
        // arrastar a imagem: o recorte anda para o outro lado
        const s = alvo.s, md = D.midias["v:" + s.video] || {};
        const [sw, sh] = md.resolucao || dimsQuadro();
        // o centro do recorte anda o contrário do arrasto, sem sair da imagem
        const esc = Math.max(W / sw, H / sh), dw = sw * esc, dh = sh * esc;
        const lx = W / (2 * dw), ly = H / (2 * dh);
        const cx = clamp(q0.x, lx, 1 - lx), cy = clamp(q0.y, ly, 1 - ly);
        final = { modo: "cortar", x: +clamp(cx - (e.clientX - x0) / dw, lx, 1 - lx).toFixed(4),
          y: +clamp(cy - (e.clientY - y0) / dh, ly, 1 - ly).toFixed(4) };
        s.quadro = final;
        T.v.forEach((v) => { if (+v.dataset.seg === D.segmentos.indexOf(s)) aplicarQuadro(v, s); });
        dica(`${s.id}: enquadramento ${Math.round(final.x * 100)}% × ${Math.round(final.y * 100)}%`, e.clientX, e.clientY);
      }
      aplicarPosicoes();
    };
    const soltar = async () => {
      document.removeEventListener("pointermove", mover);
      document.removeEventListener("pointerup", soltar);
      q.classList.remove("movendo");
      dica(null);
      if (!mudou || !final) return;
      if (alvo.tipo === "motion" || alvo.tipo === "escala") {
        await acao("/api/posicionar", { tipo: "motion", id: alvo.m.id, ...final }, `${alvo.m.id}: posição na tela gravada`);
      } else if (alvo.tipo === "legenda") {
        await acao("/api/posicionar", { tipo: "legenda", ...final }, "Posição da legenda gravada (vale para o vídeo todo)");
      } else if (alvo.tipo === "quadro") {
        await acao("/api/cortes", { acao: "quadro", id: alvo.s.id, quadro: final }, `${alvo.s.id}: enquadramento gravado`);
      }
      aplicarPosicoes();
    };
    document.addEventListener("pointermove", mover);
    document.addEventListener("pointerup", soltar);
  }

  async function restaurar(alvo) {
    if (alvo.tipo === "motion" || alvo.tipo === "escala") {
      if (!alvo.m.posicao) return;
      await acao("/api/posicionar", { tipo: "motion", id: alvo.m.id, x: 0, y: 0, escala: 1 }, `${alvo.m.id} voltou ao lugar original`);
    } else if (alvo.tipo === "legenda") {
      await acao("/api/posicionar", { tipo: "legenda", x: 0, y: 0 }, "Legenda de volta à posição do estilo");
    } else if (alvo.tipo === "quadro") {
      await acao("/api/cortes", { acao: "quadro", id: alvo.s.id, quadro: { modo: "cortar", x: 0.5, y: 0.5 } }, `${alvo.s.id}: enquadramento centralizado`);
    }
    aplicarPosicoes();
  }

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const pct = (v) => `${v >= 0 ? "+" : "−"}${Math.round(Math.abs(v) * 100)}%`;

  function pairarTela(ev) {
    const q = $("#quadro");
    if (q.classList.contains("movendo")) return;
    const leg = caixaLegenda();
    const sobre = dentro(leg, ev.clientX, ev.clientY) ? "legenda"
      : ev.target.closest(".alca-canto") ? "canto" : motionSel() ? "motion" : segSel() ? "quadro" : "";
    q.dataset.pairar = sobre;
  }

  // roda do mouse sobre o vídeo, com uma animação selecionada: o tamanho (os cantos podem sair do quadro)
  let rodaTimer = null;
  function roda(ev) {
    const m = motionSel();
    if (!m) return;
    ev.preventDefault();
    const p = posDe(m);
    const e = +clamp(p.escala * (ev.deltaY < 0 ? 1.05 : 1 / 1.05), 0.25, 2).toFixed(3);
    m.posicao = { ...p, escala: e };
    aplicarPosicoes();
    dica(`${m.id}: tamanho ${Math.round(e * 100)}%`, ev.clientX, ev.clientY);
    clearTimeout(rodaTimer);
    rodaTimer = setTimeout(async () => {
      dica(null);
      await acao("/api/posicionar", { tipo: "motion", id: m.id, ...m.posicao }, `${m.id}: tamanho ${Math.round(e * 100)}%`);
      aplicarPosicoes();
    }, 450);
  }

  function iniciar() {
    $("#trilhas").addEventListener("mousemove", pairar);
    $("#trilhas").addEventListener("mouseleave", () => { $("#trilhas").dataset.pairar = ""; });
    const q = $("#quadro");
    q.append(el("div", { id: "alca", class: "alca", hidden: true },
      ...["ne", "no", "se", "so"].map((c) => el("i", { class: "alca-canto " + c })), el("span", { class: "alca-rotulo" })));
    q.addEventListener("pointerdown", naTela);
    q.addEventListener("pointermove", pairarTela);
    q.addEventListener("wheel", roda, { passive: false });
  }

  return { iniciar, naLinha, aplicarPosicoes, desenharAlca, ativo: () => ativo };
})();
