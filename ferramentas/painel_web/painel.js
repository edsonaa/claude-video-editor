/* Painel de revisão: toca o corte a partir das mídias originais (ou das prévias),
   com animações, legenda e som por cima, e grava pedidos e ajustes no estado do
   vídeo pela API local (ferramentas/painel.py). Sem dependências. */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, props = {}, ...filhos) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(e.dataset, v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) e.append(f.nodeType ? f : String(f));
  return e;
};

const NOME_ETAPA = {
  iniciar: "Início", preparar: "Preparação", cortes: "Cortes", motion_mapa: "Plano de animação",
  assets: "Materiais", motion_render: "Animações", camera: "Câmera", sfx: "Som", legendas: "Legendas", render: "Render",
};
const nomeEtapa = (e) => NOME_ETAPA[e] || e.replace(/_/g, " ");
const nomeTransicao = (t) => ((D && D.transicoes && D.transicoes[t]) || {}).titulo || String(t || "").replace(/_/g, " ");
// a prévia de uma transição: quadros-chave do JSON dela (motor ou estoque); sem eles, um dissolver
const animTransicao = (t) => {
  const p = (D && D.transicoes && D.transicoes[t] && D.transicoes[t].previa) || { b: [{ opacity: 0 }, { opacity: 1 }] };
  return { fundo: p.fundo, a: p.a, b: p.b, aCima: !!p.a_cima };
};
const FORMATO = { tela_cheia: "tela cheia", sobreposicao: "sobreposição", sobreposicao_lateral: "lateral", enfase: "ênfase" };
const CORES_CAM = ["--cam-1", "--cam-2", "--cam-3", "--cam-4"];
const FORMATOS = { "16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350] };
// o tamanho do quadro: o formato do projeto (curto vertical) ou o do material
const dimsQuadro = () => (D && D.formato && FORMATOS[D.formato]) || (D && D.resolucao) || [16, 9];

// enquadramento de um segmento, igual ao do render: cortar (centro x/y), encaixar ou inteiro
function aplicarQuadro(v, seg) {
  if (!seg) return;
  const q = seg.quadro, m = D.midias["v:" + seg.video] || {};
  const [sw, sh] = m.resolucao || dimsQuadro();
  const [qw, qh] = dimsQuadro();
  const mesmaProporcao = Math.abs(sw / sh - qw / qh) < 0.01;
  const modo = mesmaProporcao ? "inteiro" : (q && q.modo) || (m.tipo_midia === "tela" ? "encaixar" : "cortar");
  if (modo !== "cortar") { v.style.objectFit = "contain"; v.style.objectPosition = "50% 50%"; return; }
  const box = $("#quadro"), bw = box.clientWidth, bh = box.clientHeight;
  const esc = Math.max(bw / sw, bh / sh), dw = sw * esc, dh = sh * esc;
  const pos = (c, d, b) => (d - b < 1 ? 50 : Math.min(100, Math.max(0, ((c ?? 0.5) * d - b / 2) / (d - b) * 100)));
  v.style.objectFit = "cover";
  v.style.objectPosition = `${pos(q && q.x, dw, bw)}% ${pos(q && q.y, dh, bh)}%`;
}
const ROTULO_MARCA = {
  duvida_take: "dúvida de take", hesitacao: "hesitação", nota: "nota", sugestao: "sugestão", alerta: "alerta",
  asset_faltando: "material faltando", pos: "pós", pessoa: "sua marca", nota_falada: "nota falada",
};

// ------------------------------------------------------------------ estado da interface
let D = null;                 // o que /api/dados devolveu
let fps = 30;
let pxs = 40;                 // pixels por segundo na linha do tempo
let sel = null;               // {tipo: seg|motion|leg|sfx|cam|marca|pedido, id}
let selPal = null;            // {video, i, j, ancora}
let gravando = false;
let ajusteLocal = null;       // {id, din, dout, timer}

const fmt = (t) => {
  if (t === null || t === undefined || isNaN(t)) return "–";
  const neg = t < 0; t = Math.abs(t);
  const m = Math.floor(t / 60), s = t - m * 60;
  return (neg ? "−" : "") + m + ":" + s.toFixed(2).padStart(5, "0");
};
const dbParaGanho = (db) => Math.min(1, Math.pow(10, (db || 0) / 20));
// cabeçalho de lista: cada parte vira um item próprio (o espaço entre eles vem do gap)
const cab = (...xs) => el("div", { class: "cab" }, ...xs.flat().filter((x) => x !== null && x !== undefined && x !== false).map((x) => (x.nodeType ? x : el("span", {}, x))));
const repor = (n, ...xs) => n.replaceChildren(...xs.flat().filter((x) => x !== null && x !== undefined && x !== false));
const url = (p) => p + (p.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(TOKEN);

// ------------------------------------------------------------------ API
async function api(caminho, corpo) {
  const op = { headers: { "X-Painel-Token": TOKEN } };
  if (corpo !== undefined) {
    op.method = "POST";
    op.headers["Content-Type"] = "application/json";
    op.body = JSON.stringify({ revisao: D ? D.revisao : null, ...corpo });
  }
  const r = await fetch(caminho, op);
  let j = {};
  try { j = await r.json(); } catch (_) { /* resposta vazia */ }
  if (r.status === 409 && j.dados) { aplicarDados(j.dados); throw new Error(j.erro); }
  if (!r.ok) throw new Error(j.erro || `erro ${r.status}`);
  return j;
}

async function acao(caminho, corpo, sucesso) {
  if (gravando) return;
  gravando = true;
  document.body.style.cursor = "progress";
  try {
    const j = await api(caminho, corpo);
    if (j.dados) aplicarDados(j.dados);
    if (sucesso) avisar(sucesso);
    return j;
  } catch (e) {
    avisar(e.message, true);
  } finally {
    gravando = false;
    document.body.style.cursor = "";
  }
}

function avisar(texto, erro = false) {
  const a = el("div", { class: "aviso-flutuante" + (erro ? " erro" : "") }, texto);
  const box = $("#avisos");
  while (box.children.length >= 2) box.firstElementChild.remove();
  box.append(a);
  setTimeout(() => a.remove(), erro ? 7000 : 3200);
}

// ------------------------------------------------------------------ tocador
const T = {
  v: [$("#va"), $("#vb")],
  ativo: 0,
  i: -1,               // índice do segmento atual
  t: 0,                // tempo na sequência
  tocando: false,
  relogio: null,       // para segmentos sem mídia: performance.now() de referência
  ultimoT: 0,

  segs() { return D ? D.segmentos : []; },
  dur() { return D ? D.duracao : 0; },
  indice(t) {
    const s = this.segs();
    if (!s.length) return -1;
    let a = 0, b = s.length - 1;
    if (t >= s[b].seq_fim) return b;
    while (a < b) {
      const m = (a + b) >> 1;
      if (s[m].seq_fim <= t) a = m + 1; else b = m;
    }
    return a;
  },
  midia(seg) { return D.midias["v:" + seg.video]; },
  fonte(seg) { const m = this.midia(seg); return m && m.url ? url(m.url) : null; },
  preparar(video, seg, tOrigem) {
    const src = this.fonte(seg);
    video.dataset.seg = this.segs().indexOf(seg);
    aplicarQuadro(video, seg);
    if (!src) { video.removeAttribute("src"); video.dataset.src = ""; video.load(); return false; }
    if (video.dataset.src !== src) { video.src = src; video.dataset.src = src; }
    const ir = () => { try { video.currentTime = tOrigem; } catch (_) { /* ainda sem metadados */ } };
    if (video.readyState >= 1) ir(); else video.addEventListener("loadedmetadata", ir, { once: true });
    return true;
  },
  preCarregar() {
    const s = this.segs(), prox = s[this.i + 1], outro = this.v[1 - this.ativo];
    outro.pause();
    if (prox) { this.preparar(outro, prox, prox.in); outro.dataset.seg = this.i + 1; }
    else outro.dataset.seg = "";
  },
  ir(t, manterTocando = true) {
    const s = this.segs();
    if (!s.length) return;
    t = Math.max(0, Math.min(t, this.dur() - 1e-3));
    const i = this.indice(t), seg = s[i];
    const v = this.v[this.ativo];
    Transicao.limpar();
    v.muted = !$("#ck-voz").checked;
    const tem = this.preparar(v, seg, seg.in + (t - seg.seq_ini));
    this.i = i; this.t = t; this.ultimoT = t;
    this.mostrarSemMidia(tem ? null : seg);
    this.preCarregar();
    this.relogio = tem ? null : performance.now() - (t - seg.seq_ini) * 1000;
    if (this.tocando && manterTocando && tem) v.play().catch(() => {});
    Som.sincronizar(true);
    desenharTempo();
  },
  tocar() {
    if (!this.segs().length) return;
    if (this.t >= this.dur() - 0.05) this.ir(0);
    this.tocando = true;
    document.body.classList.add("tocando");
    $("#bt-tocar").setAttribute("aria-label", "Pausar");
    const v = this.v[this.ativo];
    if (this.i < 0) this.ir(this.t);
    if (v.dataset.src) v.play().catch(() => {});
    else this.relogio = performance.now() - (this.t - this.segs()[this.i].seq_ini) * 1000;
    Som.sincronizar(true);
  },
  pausar() {
    this.tocando = false;
    document.body.classList.remove("tocando");
    $("#bt-tocar").setAttribute("aria-label", "Tocar");
    this.v.forEach((v) => v.pause());
    Som.pausar();
    Motion.pausar();
  },
  alternar() { this.tocando ? this.pausar() : this.tocar(); },
  mostrarSemMidia(seg) {
    const b = $("#sem-midia");
    if (!seg) { b.hidden = true; return; }
    const m = this.midia(seg) || {};
    repor(b, el("div", {}, el("strong", {}, `${seg.video} não toca no navegador`),
      m.motivo ? `${m.motivo}. ` : "", "Gere as prévias para assistir a este trecho."));
    b.hidden = false;
  },
  passo() {
    const s = this.segs();
    if (this.tocando && this.i >= 0) {
      const seg = s[this.i], v = this.v[this.ativo];
      let t;
      if (this.relogio !== null) t = seg.seq_ini + (performance.now() - this.relogio) / 1000;
      else t = seg.seq_ini + (v.currentTime - seg.in);
      const fimSeg = this.relogio !== null ? t >= seg.seq_fim : (v.currentTime >= seg.out - 0.02 || v.ended);
      if (fimSeg) {
        if (this.i + 1 >= s.length) { this.t = this.dur(); this.pausar(); desenharTempo(); return; }
        this.trocar();
        t = s[this.i].seq_ini;
      }
      this.t = Math.max(seg.seq_ini, Math.min(t, s[this.i].seq_fim));
      if (this.t - this.ultimoT > 0 && this.t - this.ultimoT < 0.5) Som.disparar(this.ultimoT, this.t);
      this.ultimoT = this.t;
      Som.sincronizar(false);
      desenharTempo();
    }
    Motion.atualizar(this.t, this.tocando);
    Legenda.atualizar(this.t);
  },
  trocar() {
    const s = this.segs(), velho = this.v[this.ativo], novo = this.v[1 - this.ativo], i = this.i + 1;
    const pronto = String(novo.dataset.seg) === String(i) && novo.dataset.src && novo.readyState >= 2;
    if (!pronto) { this.ir(s[i].seq_ini); return; }
    novo.muted = !$("#ck-voz").checked;
    novo.play().catch(() => {});
    novo.classList.add("ativo");
    velho.classList.remove("ativo");
    if (s[i].transicao) Transicao.tocar(velho, novo, s[i].transicao);
    velho.pause();
    velho.muted = true;
    this.ativo = 1 - this.ativo;
    this.i = i;
    this.relogio = null;
    this.mostrarSemMidia(null);
    this.preCarregar();
  },
  passoQuadro(n) {
    this.pausar();
    this.ir(Math.round((this.t + n / fps) * fps) / fps + 1e-4);
  },
};

// prévia aproximada da transição de entrada (o render faz a exata, centrada no corte)
const Transicao = {
  tocar(velho, novo, tr) {
    const an = animTransicao(tr.tipo);
    if (!$("#ck-motion").checked) return;
    this.limpar();
    const ms = Math.max(120, (tr.duracao || 0.5) * 1000 / 2);
    $("#quadro").style.background = an.fundo || "#000";
    velho.classList.add("saindo");
    velho.style.zIndex = an.aCima ? 2 : 0;
    novo.style.zIndex = an.aCima ? 0 : 1;
    const op = { duration: ms, easing: "ease-in-out" };
    const a = an.a && velho.animate(an.a.map((k) => ({ ...k })), op);
    const b = novo.animate((an.b || [{ opacity: 0 }, { opacity: 1 }]).map((k) => ({ ...k })), op);
    (b || a).finished.then(() => this.limpar()).catch(() => {});
  },
  limpar() {
    T.v.forEach((v) => { v.getAnimations().forEach((x) => x.cancel()); v.classList.remove("saindo"); v.style.zIndex = ""; });
    $("#quadro").style.background = "";
  },
};

function loop() {
  try { T.passo(); } catch (e) { console.error(e); }
  requestAnimationFrame(loop);
}

// ------------------------------------------------------------------ som (música e efeitos)
const Som = {
  musica: null, efeitos: [],
  montar() {
    this.pausar();
    this.musica = null;
    if (D.musica && D.midias.musica && D.midias.musica.url) {
      this.musica = new Audio(url(D.midias.musica.url));
      this.musica.preload = "auto";
      this.musica.volume = dbParaGanho(D.musica.ganho_db);
    }
    this.efeitos = D.sfx.filter((s) => s.status !== "riscado" && D.midias[s.chave] && D.midias[s.chave].url)
      .map((s) => { const a = new Audio(url(D.midias[s.chave].url)); a.preload = "auto"; a.volume = dbParaGanho(s.ganho_db); return { s, a }; });
  },
  sincronizar(forcar) {
    const m = this.musica;
    if (!m) return;
    const alvo = T.t - D.musica.inicio_seq;
    const dentro = alvo >= 0 && (!D.musica.duracao || alvo < D.musica.duracao);
    if (!T.tocando || !dentro || !$("#ck-musica").checked) { if (!m.paused) m.pause(); return; }
    if (forcar || m.paused || Math.abs(m.currentTime - alvo) > 0.25) m.currentTime = alvo;
    if (m.paused) m.play().catch(() => {});
  },
  disparar(de, ate) {
    if (!$("#ck-sfx").checked) return;
    for (const { s, a } of this.efeitos) {
      if (s.inicio_seq > de && s.inicio_seq <= ate) { a.currentTime = 0; a.play().catch(() => {}); }
    }
  },
  pausar() {
    if (this.musica) this.musica.pause();
    this.efeitos.forEach(({ a }) => a.pause());
  },
};

// ------------------------------------------------------------------ animações por cima
const Motion = {
  videos: new Map(),
  vivos: new Map(),            // animações da biblioteca ainda sem render: a página do efeito tocando
  caixas: new Map(),           // id -> a caixa que se move e escala (arrastada no quadro)
  chaveVivos: "",
  montar() {
    const camada = $("#camada-motion");
    repor(camada);
    this.videos.clear();
    this.caixas.clear();
    for (const m of D.motions) {
      const md = m.chave && D.midias[m.chave];
      if (!md || !md.url || m.inicio_seq === null || m.inicio_seq === undefined) continue;
      const v = el("video", { muted: true, playsinline: true, preload: "auto", src: url(md.url) });
      v.muted = true;
      const cx = el("div", { class: "mo-caixa", dataset: { id: m.id } }, v);
      camada.append(cx);
      this.videos.set(m.id, v);
      this.caixas.set(m.id, cx);
    }
    this.chaveVivos = "";
    this.vivos.clear();
    this.montarVivos();
  },
  montarVivos() {
    const lista = D.motions.filter((m) => m.efeito && !this.videos.has(m.id) && m.status !== "riscado" &&
      m.inicio_seq !== null && m.inicio_seq !== undefined);
    const chave = JSON.stringify(lista.map((m) => [m.id, m.efeito, m.params, m.inicio_seq, m.fim_seq]));
    if (chave === this.chaveVivos) return;
    this.chaveVivos = chave;
    this.vivos.forEach((fr, id) => { fr.parentElement.remove(); this.caixas.delete(id); });
    this.vivos.clear();
    const fmtEf = D.formato || (D.tema && D.tema.formato) || "16:9";
    const [w, h] = FORMATOS[fmtEf] || [1920, 1080];
    for (const m of lista) {
      const fr = el("iframe", { class: "efeito-vivo", title: `Prévia de ${m.id}`, tabindex: "-1", width: w, height: h, dataset: { w, h },
        src: Galeria.srcEfeitoPara(m.efeito, m.params, m.fim_seq !== null && m.fim_seq !== undefined ? +(m.fim_seq - m.inicio_seq).toFixed(3) : null) });
      const cx = el("div", { class: "mo-caixa", dataset: { id: m.id } }, fr);
      $("#camada-motion").append(cx);
      this.vivos.set(m.id, fr);
      this.caixas.set(m.id, cx);
    }
    Galeria.escalarIframes();
    Arrastar.aplicarPosicoes();
  },
  atualizar(t, tocando) {
    const ligado = $("#ck-motion").checked;
    const etiquetas = [];
    for (const m of D.motions) {
      if (m.inicio_seq === null || m.inicio_seq === undefined || m.status === "riscado") continue;
      const fim = m.fim_seq ?? m.inicio_seq + 2;
      const ativo = ligado && t >= m.inicio_seq && t < fim;
      const v = this.videos.get(m.id);
      if (v) {
        v.classList.toggle("visivel", ativo);
        if (ativo) {
          const alvo = t - m.inicio_seq;
          if (tocando) {
            if (v.paused) { v.currentTime = alvo; v.play().catch(() => {}); }
            else if (Math.abs(v.currentTime - alvo) > 0.15) v.currentTime = alvo;
          } else if (Math.abs(v.currentTime - alvo) > 0.5 / fps) { v.pause(); v.currentTime = alvo; }
        } else if (!v.paused) v.pause();
      } else if (this.vivos.has(m.id)) {
        const fr = this.vivos.get(m.id);
        fr.classList.toggle("visivel", ativo);
        if (ativo) {
          try { fr.contentWindow.postMessage({ cmd: "ir", t: t - m.inicio_seq }, "*"); } catch (_) { /* carregando */ }
          etiquetas.push(el("div", { class: "etiqueta" }, `${m.id} · prévia da galeria (o render vem na etapa de animações)`));
        }
      } else if (ativo) {
        const semPrevia = m.chave && D.midias[m.chave] && D.midias[m.chave].precisa_previa;
        etiquetas.push(el("div", { class: "etiqueta" }, `${m.id} · ${FORMATO[m.formato] || m.formato || "animação"} · ${semPrevia ? "gere as prévias para ver" : "ainda sem render"}`,
          m.ideia ? el("div", { class: "discreto" }, m.ideia) : null));
      }
    }
    for (const c of D.camera) {
      const ini = c.inicio_seq ?? c.tempo_seq;
      if (ini === undefined || ini === null) continue;
      const fim = c.fim_seq ?? ini + (c.duracao || 0.6);
      if (ligado && t >= ini && t < fim) etiquetas.push(el("div", { class: "etiqueta cam" }, `${c.id} · ${c.tipo || c.descricao || "movimento de câmera"}`));
    }
    const box = $("#etiquetas");
    const chave = etiquetas.map((e) => e.textContent).join("|");
    if (box.dataset.chave !== chave) { box.dataset.chave = chave; repor(box, ...etiquetas); }
  },
  pausar() { this.videos.forEach((v) => v.pause()); },
};

// ------------------------------------------------------------------ legenda por cima
const Legenda = {
  ultimo: null,
  // o estilo de legenda do vídeo (legendas/estilos.json), igual ao que o render queima
  montar() {
    const c = $("#camada-legenda"), op = D.tema.legendas || {};
    const [w, h] = dimsQuadro();
    LegendaEstilo.aplicar(c, op.estilo, D.tema, { vertical: h > w, posicao: op.posicao });
    this.ultimo = null;
  },
  atualizar(t) {
    const c = $("#camada-legenda");
    const L = D.legendas;
    if (!L || !L.blocos.length || !$("#ck-legenda").checked) { if (this.ultimo !== "") { repor(c); this.ultimo = ""; } return; }
    const b = L.blocos.find((x) => t >= x.i && t < x.f);
    const palavra = (L.opcoes || {}).modo === "palavra";
    let falada = -1;
    if (b && palavra) b.p.forEach((w, k) => { if (w[1] <= t) falada = k; });
    const chave = b ? b.id + ":" + falada : "";
    if (chave === this.ultimo) return;
    this.ultimo = chave;
    if (!b) { repor(c); return; }
    LegendaEstilo.bloco(c, b.linhas, palavra, falada);
  },
};

// ------------------------------------------------------------------ desenho geral
function aplicarDados(novo) {
  const primeira = !D;
  const tAntes = T.t;
  const mudouMidia = !D || JSON.stringify(Object.keys(novo.midias).map((k) => [k, novo.midias[k].url])) !==
    JSON.stringify(Object.keys(D.midias).map((k) => [k, D.midias[k].url]));
  D = novo;
  fps = D.fps_num || 30;
  document.title = `Revisão · ${D.projeto || ""}`;
  $("#projeto").textContent = D.projeto || "Revisão";
  $("#versao-corte").textContent = (D.cortes_versao ? `corte v${D.cortes_versao}` : "") +
    (D.origem_curto ? ` · curto de ${D.origem_curto.projeto} (${fmt(D.origem_curto.de)}–${fmt(D.origem_curto.ate)})` : "");
  $("#tc-total").textContent = fmt(D.duracao);
  desenharEtapas();
  desenharPrevias();
  if (mudouMidia || primeira) { Som.montar(); Motion.montar(); } else Motion.montarVivos();
  Legenda.montar();
  if (primeira) encaixar(); else desenharLinha();
  desenharRoteiro();
  desenharLegendas();
  desenharAnimacoes();
  desenharPedidos();
  desenharInspetor();
  $("#bt-desfazer").disabled = !D.desfazer;
  $("#bt-desfazer").title = D.desfazer ? `Desfazer: ${D.desfazer_o_que || "a última mudança feita aqui"} (Ctrl+Z)` : "Nada feito aqui para desfazer";
  ajustarQuadro();
  const eraTocando = T.tocando;
  T.ir(primeira ? 0 : Math.min(tAntes, D.duracao), eraTocando);
  Galeria.aoMudarDados();
  Arrastar.aplicarPosicoes();
}

function desenharEtapas() {
  const ol = $("#etapas");
  repor(ol, ...D.fluxo.map((e) => el("li", { class: D.etapas[e] || "pendente", title: `${nomeEtapa(e)}: ${(D.etapas[e] || "pendente").replace(/_/g, " ")}` }, nomeEtapa(e))));
  const esperando = D.fluxo.find((e) => D.etapas[e] === "aguardando_aprovacao");
  const bt = $("#bt-aprovar");
  if (esperando) {
    const abertos = D.pendencias.filter((p) => !p.resolvida_em && p.etapa === esperando).length;
    bt.hidden = false;
    bt.textContent = `Aprovar ${nomeEtapa(esperando).toLowerCase()}`;
    bt.disabled = abertos > 0;
    bt.title = abertos ? `Há ${abertos} pedido(s) aberto(s) nesta etapa` : "Fecha a etapa: o Claude segue para a próxima quando você pedir";
    bt.dataset.etapa = esperando;
  } else bt.hidden = true;
  const al = $("#bt-alertas");
  al.hidden = !D.alertas.length;
  al.textContent = D.alertas.length === 1 ? "1 aviso" : `${D.alertas.length} avisos`;
  al.classList.add("bt-alerta");
}

function desenharPrevias(fila) {
  const faixa = $("#faixa-previas"), p = $("#previas-texto"), bt = $("#bt-previas");
  if (fila && fila.rodando) {
    const atual = fila.itens.find((i) => i.status === "gerando");
    const feitas = fila.itens.filter((i) => i.status === "pronta").length;
    faixa.hidden = false;
    bt.disabled = true;
    repor(p, `Gerando prévias: ${feitas} de ${fila.itens.length}`, atual ? ` (${atual.chave})` : "",
      el("span", { class: "barra-progresso" }, el("i", { style: `width:${Math.round((atual ? atual.progresso : 1) * 100)}%` })));
    return;
  }
  const faltando = Object.entries(D.midias).filter(([, m]) => m.precisa_previa && m.usado);
  if (!faltando.length) { faixa.hidden = true; return; }
  faixa.hidden = false;
  bt.disabled = false;
  const nomes = faltando.map(([k, m]) => `${k.replace(/^(v|mo):/, "")} (${m.motivo || m.aviso})`).join(", ");
  p.textContent = faltando.length === 1 ? `Uma mídia precisa de prévia para tocar aqui: ${nomes}.`
    : `${faltando.length} mídias precisam de prévia para tocar aqui: ${nomes}.`;
}

function ajustarQuadro() {
  const palco = $("#palco"), q = $("#quadro");
  const [w, h] = dimsQuadro();
  const pw = palco.clientWidth - 24, ph = palco.clientHeight - 24;
  const esc = Math.min(pw / w, ph / h);
  const qw = Math.max(1, Math.floor(w * esc)), qh = Math.max(1, Math.floor(h * esc));
  Object.assign(q.style, { width: qw + "px", height: qh + "px", left: Math.floor((palco.clientWidth - qw) / 2) + "px", top: Math.floor((palco.clientHeight - qh) / 2) + "px" });
  T.v.forEach((v) => aplicarQuadro(v, D.segmentos[+v.dataset.seg]));
  Galeria.escalarIframes();
}

function desenharTempo() {
  $("#tc").textContent = fmt(T.t);
  const seg = D && D.segmentos[T.i];
  $("#origem").textContent = seg ? `${seg.id} · ${seg.video} em ${fmt(seg.in + (T.t - seg.seq_ini))}` : "";
  $("#cursor").style.transform = `translateX(${T.t * pxs}px)`;
  if (T.tocando) {
    const r = $("#rolagem"), x = T.t * pxs;
    if (x > r.scrollLeft + r.clientWidth - 40 || x < r.scrollLeft) r.scrollLeft = x - 60;
  }
  $("#pedido-tempo-txt").textContent = `em ${fmt(T.t)}`;
  marcarPalavraAtual();
  Galeria.atualizarCursor();
  Arrastar.desenharAlca();
}

// ------------------------------------------------------------------ linha do tempo
const TRILHAS = [
  ["corte", "Corte", "--cam-1"], ["animacoes", "Animações", "--anim"], ["legendas", "Legendas", "--leg"],
  ["camera", "Câmera", "--cam"], ["som", "Som", "--som"], ["marcas", "Pedidos", "--pedido"],
];

function corDoVideo(video) {
  const vids = [...new Set(D.segmentos.map((s) => s.video))];
  return `var(${CORES_CAM[vids.indexOf(video) % CORES_CAM.length]})`;
}

function desenharLinha() {
  const tr = $("#trilhas"), largura = Math.max($("#rolagem").clientWidth, D.duracao * pxs + 80);
  tr.style.width = largura + "px";
  $$(".trilha, .junta", tr).forEach((n) => n.remove());
  // régua
  const passos = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  const passo = passos.find((p) => p * pxs >= 70) || 600;
  const regua = $("#regua");
  repor(regua);
  const rotulo = (t) => passo >= 1 ? fmt(t).replace(/\.\d+$/, "") : fmt(t).replace(/0$/, "");
  for (let t = 0; t <= D.duracao + passo; t += passo) regua.append(el("span", { style: `left:${t * pxs}px` }, rotulo(t)));

  const vis = TRILHAS.filter(([k]) => k === "corte" || k === "marcas" ||
    (k === "animacoes" && D.motions.length) || (k === "legendas" && D.legendas && D.legendas.blocos.length) ||
    (k === "camera" && D.camera.length) || (k === "som" && (D.sfx.length || D.musica)));
  repor($("#nomes-trilhas"), ...vis.map(([, nome, cor]) => el("div", {}, el("i", { style: `background:var(${cor})` }), nome)));
  const linhaH = 22 + vis.length * 30 + 6;
  $(".linha").style.height = Math.max(150, linhaH + 14) + "px";

  const pos = (t) => t * pxs;
  const larg = (a, b) => Math.max(2, (b - a) * pxs - 1);
  for (const [k] of vis) {
    const t = el("div", { class: "trilha", dataset: { trilha: k } });
    if (k === "corte") {
      for (const s of D.segmentos) {
        const b = el("div", {
          class: "bloco seg" + (isSel("seg", s.id) ? " sel" : ""), title: `${s.id} · ${s.video} ${fmt(s.in)}–${fmt(s.out)}\n${s.texto || ""}`,
          style: `left:${pos(s.seq_ini)}px;width:${larg(s.seq_ini, s.seq_fim)}px;background-color:${corDoVideo(s.video)}`,
          dataset: { tipo: "seg", id: s.id, video: s.video, tin: s.in },
        }, el("span", {}, s.id));
        t.append(b);
      }
      for (const s of D.segmentos.slice(1)) {
        if (!s.transicao) continue;
        const d = s.transicao.duracao || 0.5;
        t.append(el("div", {
          class: "tr-marca", title: `Transição: ${nomeTransicao(s.transicao.tipo)}, ${String(d).replace(".", ",")} s (entrada de ${s.id})`,
          style: `left:${pos(s.seq_ini - d / 2)}px;width:${Math.max(8, d * pxs)}px`, dataset: { tipo: "seg", id: s.id },
        }));
      }
    } else if (k === "animacoes") {
      // animações que se sobrepõem no tempo vão para faixas (como trilhas V3, V4… no programa)
      const faixas = [], itens = D.motions.filter((m) => m.inicio_seq !== null && m.inicio_seq !== undefined)
        .map((m) => ({ m, ini: m.inicio_seq, fim: m.fim_seq ?? m.inicio_seq + 2 })).sort((a, b) => a.ini - b.ini);
      for (const it of itens) {
        let f = faixas.findIndex((fim) => fim <= it.ini + 1e-3);
        if (f < 0) { faixas.push(0); f = faixas.length - 1; }
        faixas[f] = it.fim;
        it.faixa = f;
      }
      const n = Math.max(1, faixas.length), alt = (24 - (n - 1) * 2) / n;
      for (const { m, ini, fim, faixa } of itens) {
        t.append(el("div", {
          class: `bloco motion ${m.status || ""}` + (isSel("motion", m.id) ? " sel" : "") + (n > 1 ? " fino" : ""),
          title: `${m.id} · ${m.status} · ${m.ideia || ""}`,
          style: `left:${pos(ini)}px;width:${larg(ini, fim)}px` + (n > 1 ? `;top:${3 + faixa * (alt + 2)}px;bottom:auto;height:${alt}px` : ""),
          dataset: { tipo: "motion", id: m.id },
        }, el("span", {}, m.id)));
      }
    } else if (k === "legendas") {
      for (const b of D.legendas.blocos) {
        t.append(el("div", {
          class: "bloco leg" + (isSel("leg", b.id) ? " sel" : ""), title: `${b.id}: ${b.linhas.join(" / ")}`,
          style: `left:${pos(b.i)}px;width:${larg(b.i, b.f)}px`, dataset: { tipo: "leg", id: b.id },
        }));
      }
    } else if (k === "camera") {
      for (const c of D.camera) {
        const ini = c.inicio_seq ?? c.tempo_seq;
        if (ini === undefined || ini === null) continue;
        const fim = c.fim_seq ?? ini + (c.duracao || 0.6);
        t.append(el("div", {
          class: "bloco cam" + (isSel("cam", c.id) ? " sel" : ""), title: `${c.id} · ${c.tipo || c.descricao || ""}`,
          style: `left:${pos(ini)}px;width:${larg(ini, fim)}px`, dataset: { tipo: "cam", id: c.id },
        }, el("span", {}, c.id)));
      }
    } else if (k === "som") {
      if (D.musica) {
        const fim = D.musica.duracao ? Math.min(D.duracao, D.musica.inicio_seq + D.musica.duracao) : D.duracao;
        t.append(el("div", { class: "bloco musica", style: `left:${pos(D.musica.inicio_seq)}px;width:${larg(D.musica.inicio_seq, fim)}px`, title: "Música" }, el("span", {}, "música")));
      }
      for (const s of D.sfx) {
        t.append(el("div", {
          class: "pino sfx" + (isSel("sfx", s.id) ? " sel" : ""), title: `${s.id} · ${s.nome}${s.evento ? " · " + s.evento : ""}`,
          style: `left:${pos(s.inicio_seq)}px`, dataset: { tipo: "sfx", id: s.id },
        }));
      }
    } else if (k === "marcas") {
      for (const m of D.marcadores) {
        if (m.seq === null || m.seq === undefined) continue;
        t.append(el("div", { class: "pino marca" + (isSel("marca", m.id) ? " sel" : ""), title: `${m.id} · ${ROTULO_MARCA[m.tipo] || m.tipo}: ${m.texto}`, style: `left:${pos(m.seq)}px`, dataset: { tipo: "marca", id: m.id } }));
      }
      for (const p of D.pendencias) {
        const tt = p.seq ?? p.tempo_seq;
        if (tt === undefined || tt === null) continue;
        t.append(el("div", { class: "pino pedido" + (p.resolvida_em ? " resolvido" : "") + (isSel("pedido", p.id) ? " sel" : ""), title: `${p.id} · ${p.texto}`, style: `left:${pos(tt)}px`, dataset: { tipo: "pedido", id: p.id } }));
      }
    }
    tr.append(t);
  }
  for (const s of D.segmentos.slice(1)) tr.append(el("div", { class: "junta", style: `left:${pos(s.seq_ini)}px` }));
  $("#cursor").style.transform = `translateX(${T.t * pxs}px)`;
  observarMiniaturas();
}

let observador = null;
function observarMiniaturas() {
  if (observador) observador.disconnect();
  observador = new IntersectionObserver((entradas) => {
    for (const e of entradas) {
      if (!e.isIntersecting) continue;
      const b = e.target;
      observador.unobserve(b);
      if (b.offsetWidth < 70) continue;
      const u = url(`/api/miniatura?video=${encodeURIComponent(b.dataset.video)}&tempo=${b.dataset.tin}`);
      const img = new Image();
      img.onload = () => { b.style.backgroundImage = `url("${u}")`; b.classList.add("com-miniatura"); };
      img.src = u;
    }
  }, { root: $("#rolagem") });
  $$(".bloco.seg").forEach((b) => observador.observe(b));
}

function encaixar() {
  const w = $("#rolagem").clientWidth - 40;
  pxs = D && D.duracao ? Math.max(2, Math.min(400, w / D.duracao)) : 40;
  desenharLinha();
}

function zoom(fator) {
  const r = $("#rolagem"), centro = (r.scrollLeft + r.clientWidth / 2) / pxs;
  pxs = Math.max(1, Math.min(600, pxs * fator));
  desenharLinha();
  r.scrollLeft = centro * pxs - r.clientWidth / 2;
}

// clique na linha: seleciona o que estiver embaixo e leva o cursor até lá
$("#trilhas").addEventListener("mousedown", (ev) => {
  if (Arrastar.naLinha(ev)) return;     // pegou um item: arrastar no tempo (ou clique, se não mexer)
  const r = $("#rolagem"), x = ev.clientX - r.getBoundingClientRect().left + r.scrollLeft;
  const alvo = ev.target.closest("[data-tipo]");
  if (alvo) selecionar(alvo.dataset.tipo, alvo.dataset.id, false);
  T.ir(x / pxs);
  const mover = (e2) => { const x2 = e2.clientX - r.getBoundingClientRect().left + r.scrollLeft; T.ir(x2 / pxs, false); };
  const soltar = () => { document.removeEventListener("mousemove", mover); document.removeEventListener("mouseup", soltar); if (T.tocando) T.ir(T.t); };
  document.addEventListener("mousemove", mover);
  document.addEventListener("mouseup", soltar);
});
$("#rolagem").addEventListener("wheel", (ev) => {
  if (ev.ctrlKey || ev.metaKey) { ev.preventDefault(); zoom(ev.deltaY < 0 ? 1.25 : 0.8); }
}, { passive: false });

// ------------------------------------------------------------------ seleção e inspetor
const isSel = (tipo, id) => sel && sel.tipo === tipo && sel.id === id;

function selecionar(tipo, id, ir = true) {
  sel = tipo ? { tipo, id } : null;
  if (ir && sel) {
    const t = tempoDe(tipo, id);
    if (t !== null && t !== undefined) T.ir(t + 1e-3);
  }
  desenharLinha();
  desenharInspetor();
  Arrastar.desenharAlca();
  desenharLegendas();
  desenharAnimacoes();
  desenharPedidos();
  if (tipo === "leg") rolarPara(`#aba-legendas [data-id="${id}"]`);
  if (tipo === "motion") rolarPara(`#aba-animacoes [data-id="${id}"]`);
}

function rolarPara(seletor) {
  const n = $(seletor);
  if (n && !n.closest("[hidden]")) n.scrollIntoView({ block: "nearest" });
}

function tempoDe(tipo, id) {
  const acha = (l) => l.find((x) => x.id === id);
  if (tipo === "seg") return (acha(D.segmentos) || {}).seq_ini;
  if (tipo === "motion") return (acha(D.motions) || {}).inicio_seq;
  if (tipo === "leg") return (acha(D.legendas ? D.legendas.blocos : []) || {}).i;
  if (tipo === "sfx") return (acha(D.sfx) || {}).inicio_seq;
  if (tipo === "cam") { const c = acha(D.camera) || {}; return c.inicio_seq ?? c.tempo_seq; }
  if (tipo === "marca") return (acha(D.marcadores) || {}).seq;
  if (tipo === "pedido") { const p = acha(D.pendencias) || {}; return p.seq ?? p.tempo_seq; }
  return null;
}

function itemSelecionado() {
  if (!sel || !D) return null;
  const listas = { seg: D.segmentos, motion: D.motions, leg: D.legendas ? D.legendas.blocos : [], sfx: D.sfx, cam: D.camera, marca: D.marcadores, pedido: D.pendencias };
  return (listas[sel.tipo] || []).find((x) => x.id === sel.id) || null;
}

function bt(texto, fn, extra = {}) { return el("button", { class: "insp-bt " + (extra.class || ""), onclick: fn, title: extra.title }, texto); }

function desenharInspetor() {
  const box = $("#inspetor");
  const it = itemSelecionado();
  // item do pedido acompanha a seleção
  const rot = $("#pedido-item-rotulo");
  if (it && sel.tipo !== "pedido" && sel.tipo !== "marca") { rot.hidden = false; $("#pedido-item-txt").textContent = `sobre ${sel.id}`; }
  else rot.hidden = true;
  if (!it) { repor(box); return; }
  const id = el("span", { class: "insp-id" }, sel.id);
  if (sel.tipo === "seg") {
    const s = it, quadros = (n) => n === 1 ? "1 quadro" : `${n} quadros`;
    const loc = ajusteLocal && ajusteLocal.id === s.id ? ajusteLocal : { din: 0, dout: 0 };
    const tin = (s.in_f + loc.din) / fps, tout = (s.out_f + loc.dout) / fps;
    id.prepend(el("i", { class: "bolinha", style: `background:${corDoVideo(s.video)}` }));
    const nud = (campo, n) => () => ajustarLocal(s.id, campo, n);
    repor(box, id,
      el("span", {}, `${s.video} · ${fmt(tin)} a ${fmt(tout)} · ${(tout - tin).toFixed(2).replace(".", ",")} s`),
      el("span", { class: "grupo" }, el("span", {}, "Início"), bt("−5", nud("din", -5), { title: quadros(5) }), bt("−1", nud("din", -1)), bt("+1", nud("din", 1)), bt("+5", nud("din", 5))),
      el("span", { class: "grupo" }, el("span", {}, "Fim"), bt("−5", nud("dout", -5)), bt("−1", nud("dout", -1)), bt("+1", nud("dout", 1)), bt("+5", nud("dout", 5))),
      bt("Início no cursor", () => aparar("inicio"), { title: "[" }), bt("Fim no cursor", () => aparar("fim"), { title: "]" }),
      bt("Tirar do corte", () => acao("/api/cortes", { acao: "remover_segmento", id: s.id }, `${s.id} saiu do corte`), { class: "perigo" }),
      D.formato ? controlesQuadro(s) : null,
      controlesTransicao(s),
      loc.din || loc.dout ? el("span", { class: "pendente-local" }, "aplicando…") : null,
      s.texto ? el("div", { class: "insp-texto" }, s.texto) : null);
  } else if (sel.tipo === "motion") {
    const m = it, plano = ["proposto", "aprovado", "ajustar", "riscado"].includes(m.status);
    repor(box, id, el("span", { class: "st " + m.status }, m.status),
      el("span", {}, `${FORMATO[m.formato] || m.formato || ""} · ${fmt(m.inicio_seq)} a ${fmt(m.fim_seq)}`),
      plano && m.status !== "aprovado" ? bt("Aprovar", () => acao("/api/motion", { id: m.id, status: "aprovado" }, `${m.id} aprovada`)) : null,
      plano && m.status !== "riscado" ? bt("Riscar", () => acao("/api/motion", { id: m.id, status: "riscado" }, `${m.id} riscada`), { class: "perigo" }) : null,
      plano && m.status === "riscado" ? bt("Voltar a propor", () => acao("/api/motion", { id: m.id, status: "proposto" })) : null,
      bt("Pedir ajuste…", () => pedirAjuste("motion", m.id)),
      ["sobreposicao", "sobreposicao_lateral", "enfase"].includes(m.formato)
        ? (m.posicao ? el("span", { class: "grupo" }, el("span", {}, `Na tela: ${Math.round(m.posicao.x * 100)}%, ${Math.round(m.posicao.y * 100)}%, tamanho ${Math.round(m.posicao.escala * 100)}%`),
          bt("Voltar ao lugar", () => acao("/api/posicionar", { tipo: "motion", id: m.id, x: 0, y: 0, escala: 1 }, `${m.id} voltou ao lugar original`)))
          : el("span", { class: "discreto" }, "arraste no vídeo para mover; cantos mudam o tamanho")) : null,
      m.ideia ? el("div", { class: "insp-texto" }, m.ideia) : null);
  } else if (sel.tipo === "leg") {
    const b = it;
    const entrada = el("input", { class: "insp-entrada", value: b.linhas.join(" "), "aria-label": `Texto da legenda ${b.id}` });
    const salvar = () => {
      if (entrada.value.trim() === b.linhas.join(" ")) return;
      acao("/api/legenda", { id: b.id, texto: entrada.value }, `${b.id} corrigida`);
    };
    entrada.addEventListener("keydown", (e) => { if (e.key === "Enter") salvar(); e.stopPropagation(); });
    repor(box, id, el("span", { class: "discreto" }, `${fmt(b.i)} a ${fmt(b.f)}`), entrada, bt("Salvar texto", salvar));
  } else if (sel.tipo === "sfx") {
    repor(box, id, el("span", {}, `${it.nome} · ${fmt(it.inicio_seq)} · ${it.ganho_db} dB`), it.evento ? el("span", { class: "discreto" }, it.evento) : null,
      bt("Pedir ajuste…", () => pedirAjuste("sfx", it.id)));
  } else if (sel.tipo === "cam") {
    const desc = Object.entries(it).filter(([k]) => !["id"].includes(k)).map(([k, v]) => `${k}: ${v}`).join(" · ");
    repor(box, id, el("span", { class: "discreto" }, desc), bt("Pedir ajuste…", () => pedirAjuste("cam", it.id)));
  } else if (sel.tipo === "marca") {
    repor(box, id, el("span", { class: "st" }, ROTULO_MARCA[it.tipo] || it.tipo), el("span", {}, it.texto),
      it.dentro === false ? el("span", { class: "discreto" }, "(num trecho que saiu do corte)") : null);
  } else if (sel.tipo === "pedido") {
    repor(box, id, el("span", { class: "st" }, nomeEtapa(it.etapa)), el("span", {}, it.texto),
      !it.resolvida_em ? bt("Marcar como resolvido", () => acao("/api/pedido/resolver", { id: it.id }, `${it.id} resolvido`)) : el("span", { class: "discreto" }, "resolvido"));
  }
}

function controlesTransicao(s) {
  if (D.segmentos.indexOf(s) < 1) return null;
  const abrir = () => { T.ir(s.seq_ini + 1e-3); Galeria.mostrar("transicoes"); };
  if (!s.transicao) return el("span", { class: "grupo" }, bt("Transição na entrada…", abrir, { title: "Abre a galeria de transições neste corte" }));
  return el("span", { class: "grupo" }, el("span", {}, `Entrada: ${nomeTransicao(s.transicao.tipo)} ${String(s.transicao.duracao).replace(".", ",")} s`),
    bt("Trocar…", abrir), bt("Tirar", () => acao("/api/galeria/transicao", { id: s.id, tipo: null }, `Corte seco na entrada de ${s.id}`)));
}

let quadroTimer = null;
function controlesQuadro(s) {
  const q = s.quadro || { modo: (D.midias["v:" + s.video] || {}).tipo_midia === "tela" ? "encaixar" : "cortar", x: 0.5, y: 0.5 };
  const mudar = (novo) => {
    s.quadro = novo;
    T.v.forEach((v) => { if (+v.dataset.seg === D.segmentos.indexOf(s)) aplicarQuadro(v, s); });
    clearTimeout(quadroTimer);
    quadroTimer = setTimeout(() => acao("/api/cortes", { acao: "quadro", id: s.id, quadro: novo }), 500);
    desenharInspetor();
  };
  const x = q.x ?? 0.5;
  return el("span", { class: "grupo" }, el("span", {}, "Enquadrar"),
    q.modo === "cortar" ? [bt("←", () => mudar({ ...q, x: Math.max(0, +(x - 0.05).toFixed(3)) }), { title: "mais para a esquerda" }),
      bt(`${Math.round(x * 100)}%`, () => mudar({ ...q, x: 0.5 }), { title: "centralizar" }),
      bt("→", () => mudar({ ...q, x: Math.min(1, +(x + 0.05).toFixed(3)) }), { title: "mais para a direita" }),
      bt("Encaixar inteiro", () => mudar({ modo: "encaixar" }))]
      : bt("Recortar", () => mudar({ modo: "cortar", x: 0.5, y: 0.5 })));
}

function ajustarLocal(id, campo, n) {
  if (!ajusteLocal || ajusteLocal.id !== id) ajusteLocal = { id, din: 0, dout: 0, timer: null };
  ajusteLocal[campo] += n;
  clearTimeout(ajusteLocal.timer);
  desenharInspetor();
  ajusteLocal.timer = setTimeout(async () => {
    const a = ajusteLocal, s = D.segmentos.find((x) => x.id === a.id);
    ajusteLocal = null;
    if (!s || (!a.din && !a.dout)) return desenharInspetor();
    const corpo = { acao: "ajustar", id: s.id };
    if (a.din) corpo.inicio = (s.in_f + a.din) / fps;
    if (a.dout) corpo.fim = (s.out_f + a.dout) / fps;
    await acao("/api/cortes", corpo);
    desenharInspetor();
  }, 650);
}

function aparar(qual) {
  const seg = D.segmentos[T.i];
  if (!seg) return;
  const tOrigem = seg.in + (T.t - seg.seq_ini);
  const corpo = { acao: "ajustar", id: seg.id };
  corpo[qual] = tOrigem;
  acao("/api/cortes", corpo, `${seg.id}: ${qual === "inicio" ? "início" : "fim"} em ${fmt(tOrigem)} do arquivo`);
}

// ------------------------------------------------------------------ roteiro (o corte pelo texto)
let indicePalavras = {};   // video -> [{ini, el}]

function desenharRoteiro() {
  const box = $("#roteiro");
  const vids = Object.keys(D.roteiro || {});
  indicePalavras = {};
  if (!vids.length) {
    repor(box, el("p", { class: "vazio" }, "Ainda não há transcrição. Ela aparece aqui depois da etapa de preparação."));
    return;
  }
  const usados = [...new Set(D.segmentos.map((s) => s.video))];
  vids.sort((a, b) => (usados.indexOf(a) + 1 || 99) - (usados.indexOf(b) + 1 || 99));
  const partes = [];
  for (const v of vids) {
    const ws = D.roteiro[v];
    if (vids.length > 1) partes.push(el("h3", {}, (D.midias["v:" + v] || {}).nome || v));
    indicePalavras[v] = [];
    let par = null, p = null, anterior = null;
    ws.forEach((w, k) => {
      const [texto, ini, fim, dentro, hes, idx] = w;
      if (!p || (anterior && ini - anterior[2] > 1.4)) {
        const marg = el("span", { class: "marg", title: "Ir para este ponto do arquivo", dataset: { v, t: ini } }, fmt(ini).replace(/\.\d+$/, ""));
        p = el("p");
        par = el("div", { class: "par" }, marg, p);
        partes.push(par);
      }
      const s = el("span", { class: "w" + (dentro ? "" : " fora") + (hes ? " hes" : ""), dataset: { v, k, i: idx } }, texto);
      if (selPal && selPal.video === v && k >= selPal.a && k <= selPal.b) s.classList.add("sel");
      p.append(s, " ");
      indicePalavras[v].push({ ini, fim, el: s });
      anterior = w;
    });
  }
  repor(box, ...partes);
  desenharBarraSelecao();
  ultimaPalavra = null;
  marcarPalavraAtual();
}

let ultimaPalavra = null, rolagemManual = 0;
$("#aba-roteiro").addEventListener("wheel", () => { rolagemManual = performance.now(); }, { passive: true });

function marcarPalavraAtual() {
  if (!D) return;
  const seg = D.segmentos[T.i];
  let alvo = null;
  if (seg && indicePalavras[seg.video]) {
    const t = seg.in + (T.t - seg.seq_ini), lista = indicePalavras[seg.video];
    let a = 0, b = lista.length - 1, k = -1;
    while (a <= b) { const m = (a + b) >> 1; if (lista[m].ini <= t) { k = m; a = m + 1; } else b = m - 1; }
    if (k >= 0 && t <= lista[k].fim + 0.35) alvo = lista[k].el;
  }
  if (alvo === ultimaPalavra) return;
  if (ultimaPalavra) ultimaPalavra.classList.remove("atual");
  if (alvo) {
    alvo.classList.add("atual");
    const aba = $("#aba-roteiro");
    if (T.tocando && !aba.hidden && performance.now() - rolagemManual > 4000) {
      const r = alvo.getBoundingClientRect(), ra = aba.getBoundingClientRect();
      if (r.top < ra.top + 60 || r.bottom > ra.bottom - 40) aba.scrollTop += r.top - ra.top - ra.height / 3;
    }
  }
  ultimaPalavra = alvo;
}

function tempoSeqDaOrigem(video, t) {
  for (const s of D.segmentos) if (s.video === video && t >= s.in - 1e-6 && t < s.out) return s.seq_ini + (t - s.in);
  return null;
}

// Shift+clique estende a seleção de palavras, não a seleção de texto do navegador
$("#roteiro").addEventListener("mousedown", (ev) => { if (ev.shiftKey) ev.preventDefault(); });
$("#roteiro").addEventListener("click", (ev) => {
  const m = ev.target.closest(".marg");
  if (m) {
    const t = tempoSeqDaOrigem(m.dataset.v, parseFloat(m.dataset.t));
    if (t !== null) T.ir(t + 1e-3); else avisar("Esse trecho saiu do corte.");
    return;
  }
  const w = ev.target.closest(".w");
  if (!w) return;
  const v = w.dataset.v, k = +w.dataset.k;
  if (ev.shiftKey && selPal && selPal.video === v) {
    selPal.a = Math.min(selPal.ancora, k);
    selPal.b = Math.max(selPal.ancora, k);
  } else {
    selPal = { video: v, a: k, b: k, ancora: k };
    const pal = D.roteiro[v][k];
    const t = tempoSeqDaOrigem(v, pal[1]);
    if (t !== null) T.ir(t + 1e-3);
  }
  $$("#roteiro .w.sel").forEach((n) => n.classList.remove("sel"));
  for (let i = selPal.a; i <= selPal.b; i++) indicePalavras[v][i].el.classList.add("sel");
  desenharBarraSelecao();
});

function desenharBarraSelecao() {
  const barra = $("#barra-selecao");
  if (!selPal || !D.roteiro[selPal.video]) { barra.hidden = true; return; }
  const ws = D.roteiro[selPal.video].slice(selPal.a, selPal.b + 1);
  const dentro = ws.filter((w) => w[3]).length, fora = ws.length - dentro;
  const texto = ws.map((w) => w[0]).join(" ");
  const corpo = { video: selPal.video, i: ws[0][5], j: ws[ws.length - 1][5] };
  barra.hidden = false;
  repor(barra, 
    el("span", { class: "resumo" }, `“${texto.length > 120 ? texto.slice(0, 117) + "…" : texto}”`),
    dentro ? el("button", { class: "bt-lapis", onclick: () => cortarSelecao() }, "Cortar do vídeo") : null,
    fora ? el("button", { class: "bt-devolver", onclick: () => acao("/api/cortes", { acao: "restaurar", ...corpo }, "Trecho devolvido ao corte").then(limparSelecao) }, "Devolver ao vídeo") : null,
    el("button", { class: "insp-bt", onclick: () => pedirAjuste("trecho", null, texto) }, "Pedir ajuste…"),
    el("button", { class: "insp-bt", onclick: limparSelecao }, "Limpar"),
  );
}

function cortarSelecao() {
  if (!selPal) return;
  const ws = D.roteiro[selPal.video].slice(selPal.a, selPal.b + 1);
  if (!ws.some((w) => w[3])) return;
  acao("/api/cortes", { acao: "cortar", video: selPal.video, i: ws[0][5], j: ws[ws.length - 1][5] }, "Trecho cortado (Ctrl+Z desfaz)").then(limparSelecao);
}

function limparSelecao() {
  selPal = null;
  $$("#roteiro .w.sel").forEach((n) => n.classList.remove("sel"));
  desenharBarraSelecao();
}

// ------------------------------------------------------------------ abas: legendas, animações, pedidos
function desenharLegendas() {
  const box = $("#aba-legendas"), L = D.legendas;
  if (!L) { repor(box, el("p", { class: "vazio" }, "Este vídeo ainda não tem legendas. Elas aparecem aqui depois da etapa de legendas.")); return; }
  if (L.erro) { repor(box, el("p", { class: "vazio" }, `Não deu para ler as legendas: ${L.erro}`)); return; }
  const partes = [];
  if (L.desatualizada) partes.push(el("div", { class: "aviso-bloco" }, "Estas legendas foram feitas sobre outra versão do corte: os tempos não batem mais.",
    el("div", {}, el("button", { onclick: () => enviarPedido({ etapa: "legendas", texto: "Gerar as legendas de novo sobre o corte atual" }) }, "Pedir para refazer"))));
  const cps = (b) => b.linhas.join(" ").length / Math.max(0.01, b.f - b.i);
  partes.push(el("p", { class: "subtitulo" }, `Versão ${L.versao} · ${L.blocos.length} blocos · clique para ir até a legenda; corrija o texto embaixo do vídeo`));
  partes.push(el("ul", { class: "lista" }, L.blocos.map((b) => el("li", {
    class: isSel("leg", b.id) ? "sel" : "", dataset: { id: b.id }, onclick: () => selecionar("leg", b.id),
  }, cab(el("b", {}, b.id), fmt(b.i), cps(b) > 17 ? el("span", { class: "aviso" }, `${cps(b).toFixed(0)} car/s: rápida para ler`) : null),
    el("div", { class: "corpo leg-texto" }, b.linhas.map((l, k) => [k ? el("br") : null, l]))))));
  repor(box, ...partes);
}

function desenharAnimacoes() {
  const box = $("#aba-animacoes");
  if (!D.motions.length) { repor(box, el("p", { class: "vazio" }, "Ainda não há animações planejadas para este vídeo.")); return; }
  repor(box, el("ul", { class: "lista" }, D.motions.map((m) => {
    const plano = ["proposto", "aprovado", "ajustar", "riscado"].includes(m.status);
    const parar = (fn) => (e) => { e.stopPropagation(); fn(); };
    return el("li", { class: isSel("motion", m.id) ? "sel" : "", dataset: { id: m.id }, onclick: () => selecionar("motion", m.id) },
      cab(el("b", {}, m.id), el("span", { class: "st " + m.status }, m.status), FORMATO[m.formato] || m.formato || null, fmt(m.inicio_seq),
        m.origem === "painel" ? el("span", { class: "chip-galeria" }, "da galeria") : null),
      m.ideia ? el("div", { class: "corpo" }, m.ideia) : null,
      el("div", { class: "acoes" },
        plano && m.status !== "aprovado" && m.status !== "riscado" ? el("button", { onclick: parar(() => acao("/api/motion", { id: m.id, status: "aprovado" }, `${m.id} aprovada`)) }, "Aprovar") : null,
        plano && m.status !== "riscado" ? el("button", { onclick: parar(() => acao("/api/motion", { id: m.id, status: "riscado" }, `${m.id} riscada`)) }, "Riscar") : null,
        el("button", { onclick: parar(() => pedirAjuste("motion", m.id)) }, "Pedir ajuste…")));
  })));
}

function desenharPedidos() {
  const abertos = D.pendencias.filter((p) => !p.resolvida_em);
  $("#n-pedidos").textContent = abertos.length ? abertos.length : "";
  // etapas para o pedido
  const sel_ = $("#pedido-etapa"), atual = sel_.value;
  const padrao = D.fluxo.find((e) => D.etapas[e] === "aguardando_aprovacao") || D.proxima || D.fluxo[0];
  repor(sel_, ...D.fluxo.map((e) => el("option", { value: e }, nomeEtapa(e))));
  sel_.value = atual && D.fluxo.includes(atual) ? atual : padrao;

  const box = $("#lista-pedidos");
  const item = (p) => el("li", { class: isSel("pedido", p.id) ? "sel" : "", onclick: () => selecionar("pedido", p.id) },
    cab(el("b", {}, p.id), nomeEtapa(p.etapa), p.item ? `sobre ${p.item}` : null,
      (p.seq ?? p.tempo_seq) !== undefined && (p.seq ?? p.tempo_seq) !== null ? el("span", { class: "tempo-chip" }, fmt(p.seq ?? p.tempo_seq)) : null,
      p.origem === "painel" ? null : el("span", {}, "pelo chat")),
    el("div", { class: "corpo" }, p.texto),
    !p.resolvida_em ? el("div", { class: "acoes" }, el("button", { onclick: (e) => { e.stopPropagation(); acao("/api/pedido/resolver", { id: p.id }, `${p.id} resolvido`); } }, "Marcar como resolvido")) : null);
  const partes = [];
  partes.push(el("p", { class: "subtitulo" }, abertos.length ? `Abertos (${abertos.length}): o Claude aplica quando você voltar ao chat` : "Nenhum pedido aberto"));
  if (abertos.length) partes.push(el("ul", { class: "lista" }, abertos.map(item)));
  const marcas = D.marcadores.filter((m) => m.seq !== null && m.seq !== undefined);
  if (marcas.length) {
    partes.push(el("p", { class: "subtitulo" }, "Marcações do vídeo"));
    partes.push(el("ul", { class: "lista" }, marcas.map((m) => el("li", { class: isSel("marca", m.id) ? "sel" : "", onclick: () => selecionar("marca", m.id) },
      cab(el("b", {}, m.id), ROTULO_MARCA[m.tipo] || m.tipo, el("span", { class: "tempo-chip" }, fmt(m.seq)), m.dentro === false ? "fora do corte" : null),
      el("div", { class: "corpo" }, m.texto)))));
  }
  const resolvidos = D.pendencias.filter((p) => p.resolvida_em);
  if (resolvidos.length) {
    const det = el("details", {}, el("summary", { class: "subtitulo" }, `Resolvidos (${resolvidos.length})`), el("ul", { class: "lista" }, resolvidos.map(item)));
    partes.push(det);
  }
  repor(box, ...partes);
}

async function enviarPedido(corpo, msg = "Pedido enviado") {
  return acao("/api/pedido", corpo, msg);
}

$("#form-pedido").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const texto = $("#pedido-texto").value.trim();
  if (!texto) { $("#pedido-texto").focus(); return; }
  const corpo = { texto, etapa: $("#pedido-etapa").value, aprendizado: $("#pedido-aprendizado").checked };
  if ($("#pedido-tempo").checked) corpo.tempo_seq = T.t;
  if (!$("#pedido-item-rotulo").hidden && $("#pedido-item").checked && sel) corpo.item = sel.id;
  const r = await enviarPedido(corpo, corpo.aprendizado ? "Pedido enviado e anotado como aprendizado" : "Pedido enviado");
  if (r) { $("#pedido-texto").value = ""; $("#pedido-aprendizado").checked = false; }
});

let ajustePara = null;
function pedirAjuste(tipo, id, trecho) {
  ajustePara = { tipo, id, trecho, t: T.t };
  $("#ajuste-titulo").textContent = id ? `Pedir ajuste em ${id}` : "Pedir ajuste neste trecho";
  $("#ajuste-texto").value = "";
  $("#ajuste-aprendizado").checked = false;
  $("#dlg-ajuste").showModal();
  $("#ajuste-texto").focus();
}
$("#dlg-ajuste").addEventListener("close", () => {
  if ($("#dlg-ajuste").returnValue !== "ok" || !ajustePara) return;
  const texto = $("#ajuste-texto").value.trim();
  if (!texto) return;
  const a = ajustePara, aprendizado = $("#ajuste-aprendizado").checked;
  if (a.tipo === "motion") {
    acao("/api/motion", { id: a.id, status: "ajustar", texto, aprendizado }, `Pedido de ajuste em ${a.id} enviado`);
  } else {
    const etapa = { sfx: "sfx", cam: "camera" }[a.tipo] || $("#pedido-etapa").value;
    enviarPedido({ texto: a.trecho ? `${texto} (trecho: “${a.trecho.slice(0, 140)}”)` : texto, etapa, item: a.id || undefined, tempo_seq: a.t, aprendizado });
  }
});

// ------------------------------------------------------------------ controles
$("#bt-tocar").addEventListener("click", () => T.alternar());
$("#bt-anterior").addEventListener("click", () => irCorte(-1));
$("#bt-proximo").addEventListener("click", () => irCorte(1));
$("#bt-mais").addEventListener("click", () => zoom(1.5));
$("#bt-menos").addEventListener("click", () => zoom(1 / 1.5));
$("#bt-encaixar").addEventListener("click", encaixar);
$("#bt-desfazer").addEventListener("click", async () => {
  const r = await acao("/api/desfazer", {});
  if (r && r.info) avisar(`Desfeito: ${r.info.desfeito}`);
});
$("#bt-ajuda").addEventListener("click", () => $("#dlg-ajuda").showModal());
$("#bt-alertas").addEventListener("click", () => {
  repor($("#lista-alertas"), ...D.alertas.map((a) => el("li", {}, a)));
  $("#dlg-alertas").showModal();
});
$("#bt-aprovar").addEventListener("click", (ev) => {
  const e = ev.currentTarget.dataset.etapa;
  acao("/api/etapa/aprovar", { etapa: e }, `${nomeEtapa(e)} aprovada. Volte ao chat e chame /edicao:editar para seguir.`);
});
$("#bt-previas").addEventListener("click", async () => {
  try {
    const r = await api("/api/previas", {});
    desenharPrevias(r);
  } catch (e) { avisar(e.message, true); }
});
$("#ck-voz").addEventListener("change", (e) => { T.v[T.ativo].muted = !e.target.checked; });
["#ck-musica", "#ck-legenda", "#ck-motion"].forEach((s) => $(s).addEventListener("change", () => { Som.sincronizar(true); Legenda.ultimo = null; }));

$$(".abas [role=tab]").forEach((b) => b.addEventListener("click", () => {
  $$(".abas [role=tab]").forEach((x) => x.setAttribute("aria-selected", x === b));
  $$(".aba").forEach((a) => { a.hidden = a.id !== "aba-" + b.dataset.aba; });
}));

function irCorte(dir) {
  const juntas = [0, ...D.segmentos.map((s) => s.seq_fim)];
  const t = T.t;
  const alvo = dir > 0 ? juntas.find((j) => j > t + 0.02) : [...juntas].reverse().find((j) => j < t - 0.15);
  if (alvo !== undefined) T.ir(Math.min(alvo, D.duracao - 1e-3) + 1e-4);
}

document.addEventListener("keydown", (ev) => {
  const alvo = ev.target;
  if (alvo.matches("input:not([type=checkbox]), textarea, select") || $("dialog[open]")) return;
  const k = ev.key;
  if (k === " ") { ev.preventDefault(); T.alternar(); }
  else if (k === "ArrowRight") { ev.preventDefault(); ev.shiftKey ? (T.pausar(), T.ir(T.t + 1)) : T.passoQuadro(1); }
  else if (k === "ArrowLeft") { ev.preventDefault(); ev.shiftKey ? (T.pausar(), T.ir(T.t - 1)) : T.passoQuadro(-1); }
  else if (k === "ArrowDown") { ev.preventDefault(); irCorte(1); }
  else if (k === "ArrowUp") { ev.preventDefault(); irCorte(-1); }
  else if (k === "[") aparar("inicio");
  else if (k === "]") aparar("fim");
  else if ((k === "Delete" || k === "Backspace") && selPal) { ev.preventDefault(); cortarSelecao(); }
  else if ((k === "z" || k === "Z") && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); if (D.desfazer) $("#bt-desfazer").click(); }
  else if (k === "n" || k === "N") {
    ev.preventDefault();
    $$(".abas [role=tab]").find((b) => b.dataset.aba === "pedidos").click();
    $("#pedido-tempo").checked = true;
    $("#pedido-texto").focus();
  }
  else if (k === "+" || k === "=") zoom(1.5);
  else if (k === "-") zoom(1 / 1.5);
  else if (k === "?") $("#dlg-ajuda").showModal();
  else if (k === "g" || k === "G") { ev.preventDefault(); Galeria.mostrar(); }
  else if (k === "Escape") { limparSelecao(); selecionar(null); }
});

window.addEventListener("resize", () => { if (D) { ajustarQuadro(); } });
new ResizeObserver(() => { if (D) ajustarQuadro(); }).observe($("#palco"));

// ------------------------------------------------------------------ acompanhar o Claude
async function vigiar() {
  try {
    const r = await api("/api/revisao");
    if (r.previas && (r.previas.rodando || r.previas.itens.length)) {
      if (r.previas.rodando) desenharPrevias(r.previas);
      else if (vigiar.rodava) {
        vigiar.rodava = false;
        const falhas = r.previas.itens.filter((i) => i.status === "falhou");
        avisar(falhas.length ? `Prévia falhou: ${falhas.map((f) => f.erro).join("; ")}` : "Prévias prontas", !!falhas.length);
        aplicarDados((await api("/api/dados")));
      }
      vigiar.rodava = vigiar.rodava || r.previas.rodando;
    }
    if (D && r.revisao !== D.revisao && !gravando && !ajusteLocal) {
      aplicarDados(await api("/api/dados"));
      avisar("Atualizado com as mudanças do Claude");
    }
  } catch (e) {
    if (!vigiar.offline) avisar("O painel parou de responder. Ele ainda está rodando no terminal?", true);
    vigiar.offline = true;
    return setTimeout(vigiar, 5000);
  }
  vigiar.offline = false;
  setTimeout(vigiar, 2000);
}

// ------------------------------------------------------------------ início
(async function iniciar() {
  if (!TOKEN) {
    repor(document.body, el("p", { class: "vazio" }, "Abra o endereço completo que o painel mostrou no terminal (com ?t=…)."));
    return;
  }
  Galeria.iniciar();
  Arrastar.iniciar();
  try {
    aplicarDados(await api("/api/dados"));
  } catch (e) {
    repor(document.body, el("p", { class: "vazio" }, `Não deu para abrir o painel: ${e.message}`));
    return;
  }
  requestAnimationFrame(loop);
  setTimeout(vigiar, 2000);
})();
