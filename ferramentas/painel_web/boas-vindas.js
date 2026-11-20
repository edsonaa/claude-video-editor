/* Boas-vindas de um vídeo novo: verificação, briefing, tipo de vídeo, estilo e legenda.
   Tudo fica na página até "Enviar para o Claude", que grava pelo servidor (painel.py
   boas-vindas) e encerra o processo; o Claude é avisado pelo fim do comando. */
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
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) e.append(f.nodeType ? f : String(f));
  return e;
};
const url = (p) => p + (p.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(TOKEN);

const PASSOS = [
  ["verificar", "O que está pronto"], ["briefing", "Sobre o vídeo"], ["tipo", "Tipo de vídeo"],
  ["estilo", "Estilo das animações"], ["legenda", "Legenda"], ["enviar", "Revisar e enviar"],
];
const NOME_ETAPA = {
  iniciar: "início", preparar: "preparação", cortes: "cortes", motion_mapa: "plano de animação", assets: "materiais",
  motion_render: "animações", camera: "câmera", sfx: "som", legendas: "legendas", render: "render",
};
const FORMATO_DIM = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:5": [4, 5] };
const EXEMPLO = "Esse é o padrão de legenda que vai aparecer no seu vídeo enquanto você fala";

let O = null;               // opções vindas do servidor
let passo = 0;
const E = { briefing: "", termos: [], preset: null, tema: null, legenda: null, padrao: false };
let tocouTema = false, tocouLegenda = false;

// ------------------------------------------------------------------ navegação
function irPara(i) {
  passo = Math.max(0, Math.min(PASSOS.length - 1, i));
  const id = PASSOS[passo][0];
  $$("section[data-passo]").forEach((s) => { s.hidden = s.dataset.passo !== id; });
  $$("#passos li").forEach((li, k) => {
    li.className = k === passo ? "atual" : k < passo ? "feito" : "";
    $("button", li).disabled = k > maiorVisitado;
    if (k === passo) $("button", li).setAttribute("aria-current", "step"); else $("button", li).removeAttribute("aria-current");
  });
  $("#voltar").style.visibility = passo === 0 ? "hidden" : "visible";
  const ultimo = id === "enviar";
  $("#avancar").textContent = ultimo ? "Enviar para o Claude" : "Continuar";
  $("#avancar").classList.toggle("enviar", ultimo);
  if (id === "legenda") montarPreviaLegenda();
  if (id === "enviar") desenharResumo();
  $("#conteudo").scrollTo?.(0, 0);
  window.scrollTo(0, 0);
  const h = $(`section[data-passo=${id}] h2`);
  if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
}
let maiorVisitado = 0;

$("#avancar").addEventListener("click", () => {
  if (PASSOS[passo][0] === "enviar") return enviar();
  maiorVisitado = Math.max(maiorVisitado, passo + 1);
  irPara(passo + 1);
});
$("#voltar").addEventListener("click", () => irPara(passo - 1));

// ------------------------------------------------------------------ 1. verificação
function desenharVerificacao() {
  const ic = (ok) => ok === true ? ["sim", "✓"] : ok === false ? ["nao", "✗"] : ["aviso", "!"];
  $("#verificacao").replaceChildren(...O.verificacao.map((v) => {
    const [cls, s] = ic(v.ok);
    return el("li", {}, el("span", { class: `ic ${cls}`, "aria-label": cls === "sim" ? "pronto" : cls === "nao" ? "falta" : "atenção" }, s),
      el("span", {}, v.titulo), el("span", { class: "det" }, v.detalhe));
  }));
}

// ------------------------------------------------------------------ 2. briefing
function desenharTermos() {
  $("#lista-termos").replaceChildren(...E.termos.map((t, i) => el("span", { class: "chip" }, t,
    el("button", { "aria-label": `Tirar ${t}`, onclick: () => { E.termos.splice(i, 1); desenharTermos(); } }, "×"))));
}
$("#termo").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== ",") return;
  ev.preventDefault();
  for (const t of ev.target.value.split(",").map((x) => x.trim()).filter(Boolean)) if (!E.termos.includes(t)) E.termos.push(t);
  ev.target.value = "";
  desenharTermos();
});
$("#briefing").addEventListener("input", (ev) => { E.briefing = ev.target.value; });

// ------------------------------------------------------------------ 3. tipo de vídeo
function iconeFormato(f) {
  const [w, h] = FORMATO_DIM[f] || [16, 9];
  const k = 18 / Math.max(w, h);
  return el("span", { class: "formato" }, el("i", { style: `width:${w * k}px;height:${h * k}px` }), f === "9:16" ? "vertical 9:16" : f === "16:9" ? "horizontal 16:9" : f);
}
function cardRadio(selecionado, conteudo, aoEscolher, extra = {}) {
  const c = el("button", { class: "card " + (extra.class || ""), role: "radio", "aria-checked": String(selecionado) }, conteudo);
  c.addEventListener("click", aoEscolher);
  return c;
}
function desenharPresets() {
  $("#presets").replaceChildren(...O.presets.map((p) => cardRadio(E.preset === p.id, [
    el("h3", {}, p.titulo), iconeFormato(p.formato), el("p", {}, p.descricao),
    el("div", { class: "etapas-chips", "aria-label": "Etapas" }, p.fluxo.filter((e) => e !== "iniciar").map((e) => el("span", {}, NOME_ETAPA[e] || e))),
  ], () => escolherPreset(p.id))));
}
function escolherPreset(id) {
  E.preset = id;
  const p = preset();
  if (!tocouTema && !O.perfis.some((x) => x.id === O.atual.perfil)) {
    const sug = [...O.perfis, ...O.estilos].find((x) => x.id === p.estilo_sugerido);
    if (sug) E.tema = { tipo: sug.tipo, id: sug.id };
  }
  if (!tocouLegenda) E.legenda = { ...E.legenda, estilo: p.legenda.estilo, queimar: p.legenda.queimar || p.formato === "9:16", ativas: true };
  desenharPresets();
  desenharEstilos();
}
const preset = () => O.presets.find((p) => p.id === E.preset) || O.presets[0];

// ------------------------------------------------------------------ 4. estilo
function temaEscolhido() {
  const t = [...O.perfis, ...O.estilos].find((x) => x.tipo === (E.tema || {}).tipo && x.id === (E.tema || {}).id);
  return t || O.perfis[0] || O.estilos[0];
}
function cardEstilo(t) {
  const sel = E.tema && E.tema.tipo === t.tipo && E.tema.id === t.id;
  const img = t.previa ? el("img", { src: url(`/api/previa-tema/${t.tipo}/${encodeURIComponent(t.id)}`), alt: `Vitrine do estilo ${t.titulo || t.id}`, loading: "lazy" })
    : el("div", { class: "sem-previa", "aria-hidden": "true" }, ["fundo", "superficie", "destaque", "apoio", "texto"].map((k) => el("i", { style: `background:${t.cores[k]}` })));
  const falta = t.fontes_faltando && t.fontes_faltando.length ? el("span", { class: "aviso-fonte" }, `Fonte não instalada neste computador: ${t.fontes_faltando.join(", ")}`) : null;
  return cardRadio(sel, [img, el("div", { class: "txt" }, el("h3", {}, t.titulo || t.id, t.tipo === "perfil" ? el("span", { class: "discreto" }, ` · seu perfil “${t.id}”`) : null),
    t.descricao ? el("p", {}, t.descricao) : null, falta)], () => { tocouTema = true; E.tema = { tipo: t.tipo, id: t.id }; desenharEstilos(); }, { class: "estilo" });
}
function desenharEstilos() {
  const partes = [];
  if (O.perfis.length) partes.push(el("p", { class: "subtitulo" }, "Seus perfis"), el("div", { class: "grade-estilos", role: "radiogroup", "aria-label": "Seus perfis" }, O.perfis.map(cardEstilo)));
  if (O.estilos.length) partes.push(el("p", { class: "subtitulo" }, O.perfis.length ? "Estilos do motor (viram um perfil seu ao escolher)" : "Estilos"),
    el("div", { class: "grade-estilos", role: "radiogroup", "aria-label": "Estilos do motor" }, O.estilos.map(cardEstilo)));
  if (preset() && !preset().fluxo.includes("motion_render")) partes.unshift(el("p", { class: "intro" }, "Este tipo de vídeo não tem etapa de animação: o estilo vale para as cores da legenda e para quando você ligar animações."));
  $("#estilos").replaceChildren(...partes);
}

// ------------------------------------------------------------------ 5. legenda
let animacao = null;
function estiloLegenda() { return O.legendas.find((l) => l.id === E.legenda.estilo) || O.legendas[0]; }

function desenharOpcoesLegenda() {
  const ops = [el("button", { class: "opcao", role: "radio", "aria-checked": String(!E.legenda.ativas), onclick: () => mudarLegenda({ ativas: false }) },
    el("b", {}, "Sem legenda"), el("span", { class: "modo" }, ""), el("span", { class: "desc" }, "Este vídeo não leva legenda."))];
  for (const l of O.legendas) {
    ops.push(el("button", { class: "opcao", role: "radio", "aria-checked": String(E.legenda.ativas && E.legenda.estilo === l.id),
      onclick: () => mudarLegenda({ ativas: true, estilo: l.id, queimar: l.modo === "palavra" ? true : E.legenda.queimar }) },
    el("b", {}, l.titulo), el("span", { class: "modo" }, l.modo === "palavra" ? "palavra a palavra" : "frase"), el("span", { class: "desc" }, `${l.descricao} Bom para ${l.bom_para}.`)));
  }
  $("#estilos-legenda").replaceChildren(...ops);
  $$("#posicao input").forEach((i) => { i.checked = i.value === (E.legenda.posicao || "baixo"); i.disabled = !E.legenda.ativas; });
  const palavra = estiloLegenda().modo === "palavra";
  $$("input[name=queimar]").forEach((i) => { i.checked = (i.value === "1") === !!E.legenda.queimar; i.disabled = !E.legenda.ativas || palavra; });
  $("#nota-queimar").hidden = !palavra || !E.legenda.ativas;
}
function mudarLegenda(m) {
  tocouLegenda = true;
  E.legenda = { ...E.legenda, ...m };
  if (estiloLegenda().modo === "palavra") E.legenda.queimar = true;
  desenharOpcoesLegenda();
  montarPreviaLegenda();
}
$$("#posicao input").forEach((i) => i.addEventListener("change", () => mudarLegenda({ posicao: i.value })));
$$("input[name=queimar]").forEach((i) => i.addEventListener("change", () => mudarLegenda({ queimar: i.value === "1" })));

function montarPreviaLegenda() {
  desenharOpcoesLegenda();
  const f = preset().formato;
  const [w, h] = FORMATO_DIM[f] || [16, 9];
  const q = $("#quadro-legenda");
  q.style.aspectRatio = `${w} / ${h}`;
  const vertical = h > w;
  const t = temaEscolhido();
  const c = $("#camada-legenda");
  clearInterval(animacao);
  if (!E.legenda.ativas) { c.replaceChildren(); return; }
  const est = estiloLegenda();
  LegendaEstilo.aplicar(c, est, t, { vertical, posicao: E.legenda.posicao || est.posicao });
  const max = vertical ? est.max_caracteres_vertical : est.max_caracteres;
  const blocos = LegendaEstilo.quebrar(est.caixa_alta ? EXEMPLO.toUpperCase() : EXEMPLO, max, est.linhas);
  const palavra = est.modo === "palavra";
  let b = 0, k = 0;
  const tique = () => {
    const bl = blocos[b];
    const n = bl.join(" ").split(/\s+/).length;
    LegendaEstilo.bloco(c, bl, palavra, k);
    k++;
    if (!palavra || k >= n) { if (k >= (palavra ? n : 4)) { b = (b + 1) % blocos.length; k = 0; } }
  };
  tique();
  animacao = setInterval(tique, palavra ? 330 : 420);
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) clearInterval(animacao);
}

// ------------------------------------------------------------------ 6. enviar
function desenharResumo() {
  const p = preset(), t = temaEscolhido(), l = estiloLegenda();
  const leg = !E.legenda.ativas ? "Sem legenda" : `${l.titulo}, ${E.legenda.queimar ? "queimada no vídeo" : "em arquivo (SRT)"}, ${{ baixo: "embaixo", centro: "no centro", topo: "em cima" }[E.legenda.posicao || "baixo"]}`;
  const linhas = [
    ["Sobre o vídeo", E.briefing.trim() || "(nada escrito: o Claude pergunta na conversa)", "briefing"],
    ["Termos", E.termos.length ? E.termos.join(", ") : "nenhum"],
    ["Tipo de vídeo", `${p.titulo} · ${p.formato}`],
    ["Estilo", `${t.titulo || t.id}${t.tipo === "estilo" ? " (vira um perfil seu)" : ""}`],
    ["Legenda", leg],
  ];
  $("#resumo").replaceChildren(...linhas.flatMap(([k, v, cls]) => [el("dt", {}, k), el("dd", { class: cls || "" }, v)]));
}

async function enviar() {
  const bt = $("#avancar");
  bt.disabled = true;
  bt.textContent = "Enviando…";
  $("#erro").hidden = true;
  const corpo = {
    briefing: E.briefing, termos: E.termos, preset: E.preset, tema: E.tema || { tipo: temaEscolhido().tipo, id: temaEscolhido().id },
    legenda: { estilo: E.legenda.estilo, queimar: !!E.legenda.queimar, posicao: E.legenda.posicao || "baixo", ativas: !!E.legenda.ativas },
    padrao: $("#padrao").checked,
  };
  try {
    const r = await fetch("/api/boas-vindas", { method: "POST", headers: { "X-Painel-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || `erro ${r.status}`);
    clearInterval(animacao);
    $$("section[data-passo]").forEach((s) => { s.hidden = s.dataset.passo !== "pronto"; });
    $("#navegacao").hidden = true;
    $$("#passos li").forEach((li) => { li.className = "feito"; $("button", li).disabled = true; });
    $("section[data-passo=pronto] h2").focus?.();
  } catch (e) {
    $("#erro").textContent = `Não deu para enviar: ${e.message}`;
    $("#erro").hidden = false;
    bt.disabled = false;
    bt.textContent = "Enviar para o Claude";
  }
}

// ------------------------------------------------------------------ início
(async function iniciar() {
  if (!TOKEN) { document.body.replaceChildren(el("p", { style: "padding:24px" }, "Abra o endereço completo que o Claude mostrou (com ?t=…).")); return; }
  try {
    const r = await fetch(url("/api/boas-vindas"));
    if (!r.ok) throw new Error((await r.json()).erro);
    O = await r.json();
  } catch (e) {
    document.body.replaceChildren(el("p", { style: "padding:24px" }, `Não deu para abrir: ${e.message}`));
    return;
  }
  $("#projeto").textContent = O.projeto ? `· ${O.projeto}` : "";
  $("#saudacao").textContent = O.nome ? `Olá, ${O.nome}.` : "";
  document.title = `Novo vídeo · ${O.projeto || ""}`;
  $("#passos").replaceChildren(...PASSOS.map(([, nome], i) => el("li", {}, el("button", { onclick: () => irPara(i), disabled: i > 0 }, nome))));
  E.preset = O.presets.some((p) => p.id === O.atual.preset) ? O.atual.preset : O.presets[0].id;
  const atual = [...O.perfis, ...O.estilos].find((x) => x.id === O.atual.perfil);
  E.tema = atual ? { tipo: atual.tipo, id: atual.id } : null;
  E.legenda = { ...O.atual.legenda };
  if (!E.tema) escolherPreset(E.preset); else { desenharPresets(); desenharEstilos(); }
  if (!O.atual.legenda.ativas) E.legenda = { ...E.legenda, ...preset().legenda };
  desenharVerificacao();
  const img = $("#exemplo");
  if (O.tem_exemplo) {
    img.src = url("/api/exemplo.jpg");
    $("#nota-exemplo").textContent = "Prévia sobre um quadro das suas gravações. As fontes aparecem como no render quando estão instaladas neste computador.";
    img.onerror = () => { img.hidden = true; $("#quadro-legenda").classList.add("sem-exemplo"); };
  } else {
    img.hidden = true;
    $("#quadro-legenda").classList.add("sem-exemplo");
    $("#nota-exemplo").textContent = "Sem gravações na pasta ainda: a prévia usa um fundo neutro.";
  }
  irPara(0);
})();
