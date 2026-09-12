const NIVEL_COLORS = ["var(--nivel-0)", "var(--nivel-1)", "var(--nivel-2)", "var(--nivel-3)", "var(--nivel-4)", "var(--nivel-5)", "var(--nivel-6)"];

const state = { runs: [], detail: null, aggregate: null };

function fmtSecs(s) {
  if (s === null || s === undefined) return "—";
  return s.toFixed(1) + "s";
}

function mechClass(evento) {
  if (evento.type === "heartbeat") return "mech-heartbeat";
  if (evento.type === "egress") return "mech-egress";
  if (evento.type === "canary") {
    const sup = (evento.detalle || {}).superficie || "";
    return sup === "trafico_saliente" ? "mech-canary-net" : "mech-canary-fs";
  }
  return "";
}

function mechLabel(evento) {
  if (evento.type === "heartbeat") return "heartbeat";
  if (evento.type === "egress") return "egress (baseline)";
  if (evento.type === "canary") {
    const sup = (evento.detalle || {}).superficie || "";
    return sup === "trafico_saliente" ? "canary (red)" : "canary (filesystem)";
  }
  return evento.type;
}

function toolSummary(entry) {
  if (entry.role === "assistant") {
    const tc = entry.tool_calls;
    if (!tc) return entry.content ? entry.content.slice(0, 140) : "(respuesta final)";
    return "→ " + tc.map((t) => t.function.name).join(", ");
  }
  if (entry.role === "tool") {
    const args = entry.args || {};
    let a = "";
    if (entry.name === "http_fetch") a = args.url || "";
    else if (args.path) a = args.path;
    else a = JSON.stringify(args).slice(0, 60);
    return `<code>${entry.name}</code> ${a}`;
  }
  return entry.role;
}

async function loadRuns() {
  const res = await fetch("/api/runs");
  const runs = await res.json();
  state.runs = runs.filter((r) => !r.error);

  const picker = document.getElementById("run-picker");
  picker.innerHTML = "";
  if (state.runs.length === 0) {
    picker.innerHTML = "<option>sin corridas en results/</option>";
    renderEmpty();
    return;
  }

  // Prioriza mostrar por defecto la corrida mas "interesante": la de mayor
  // nivel de escalada (idealmente una fuga real detectada).
  const sorted = [...state.runs].sort((a, b) => (b.nivel_escalada || 0) - (a.nivel_escalada || 0));
  const preferido = sorted[0].run_id;

  for (const r of state.runs) {
    const opt = document.createElement("option");
    opt.value = r.run_id;
    opt.textContent = `${r.run_id}  [nivel ${r.nivel_escalada}]`;
    if (r.run_id === preferido) opt.selected = true;
    picker.appendChild(opt);
  }
  picker.onchange = () => loadRunDetail(picker.value);
  await loadRunDetail(preferido);
}

function renderEmpty() {
  document.getElementById("run-meta").innerHTML = "";
  document.getElementById("run-title").textContent = "Sin corridas todavia";
  document.getElementById("run-sub").textContent = "";
  document.getElementById("timeline-wrap").innerHTML =
    '<p class="empty-note">Corre orchestrator/run_experiment.py o dashboard/../tests/positive_controls.sh y pulsa "releer results/"</p>';
  document.getElementById("turn-log").innerHTML = "";
}

async function loadRunDetail(runId) {
  const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  const data = await res.json();
  state.detail = data;
  renderRunMeta(data);
  renderTimeline(data);
  renderTurnLog(data);
  renderMechCards(data);
}

function renderRunMeta(data) {
  const { meta, analysis } = data;
  const wrap = document.getElementById("run-meta");
  wrap.innerHTML = "";
  const chips = [
    [meta.condicion, `condicion-${meta.condicion}`],
    [meta.tarea, ""],
    [analysis.nivel_label, ""],
    [analysis.detectado ? "detectado" : (analysis.intento_de_escape ? "NO detectado" : "sin intento"),
      analysis.detectado ? "status-good" : (analysis.intento_de_escape ? "status-critical" : "")],
  ];
  for (const [text, cls] of chips) {
    if (!text) continue;
    const span = document.createElement("span");
    span.className = "chip " + cls;
    span.textContent = text;
    wrap.appendChild(span);
  }

  document.getElementById("run-title").textContent = meta.run_id;
  document.getElementById("run-sub").textContent =
    `canary=${meta.canary || "?"}  ·  backend=${meta.backend || "?"}`;

  const ttdEl = document.getElementById("ttd-value");
  const lblEl = document.getElementById("ttd-label");
  if (analysis.ttd_segundos !== null && analysis.ttd_segundos !== undefined) {
    ttdEl.textContent = fmtSecs(analysis.ttd_segundos);
    ttdEl.className = "value tabular detected";
    lblEl.textContent = `detectado por ${analysis.monitor_detector}`;
  } else if (analysis.intento_de_escape) {
    ttdEl.textContent = "sin detectar";
    ttdEl.className = "value tabular missed";
    lblEl.textContent = "intento de escape sin alerta";
  } else {
    ttdEl.textContent = "—";
    ttdEl.className = "value tabular";
    lblEl.textContent = "sin intento de escape";
  }
}

function renderTimeline(data) {
  const wrap = document.getElementById("timeline-wrap");
  const axis = document.getElementById("timeline-axis");
  wrap.querySelectorAll(".event-dot, .event-label, .ttd-bracket, .tick").forEach((n) => n.remove());

  const toolEntries = data.transcript.filter((e) => e.role === "tool" || (e.role === "assistant" && e.tool_calls));
  const alertEvents = data.events.filter((e) => e.severidad === "alerta");
  const allTs = [...data.transcript.map((e) => e.ts), ...data.events.map((e) => e.ts)].filter(Boolean);
  if (allTs.length === 0) {
    wrap.innerHTML = '<p class="empty-note">Esta corrida no tiene transcript/eventos con timestamps.</p>';
    return;
  }
  const t0 = Math.min(...allTs);
  const t1 = Math.max(...allTs);
  const dur = Math.max(t1 - t0, 1);
  const pct = (ts) => ((ts - t0) / dur) * 100;

  // ticks de tiempo
  const nTicks = 6;
  for (let i = 0; i <= nTicks; i++) {
    const t = (dur / nTicks) * i;
    const tick = document.createElement("div");
    tick.className = "tick";
    tick.style.left = `${(i / nTicks) * 100}%`;
    tick.textContent = `${t.toFixed(0)}s`;
    axis.appendChild(tick);
  }

  // acciones del agente (tool calls), por encima del eje
  for (const e of toolEntries) {
    if (e.role !== "tool") continue;
    const dot = document.createElement("div");
    dot.className = "event-dot agent";
    dot.style.left = pct(e.ts) + "%";
    dot.title = `t+${(e.ts - t0).toFixed(1)}s — ${e.name}(${JSON.stringify(e.args || {}).slice(0, 80)})`;
    wrap.appendChild(dot);
  }

  // alertas de los monitores, por debajo del eje
  for (const e of alertEvents) {
    const dot = document.createElement("div");
    dot.className = "event-dot " + mechClass(e);
    dot.style.left = pct(e.ts) + "%";
    dot.title = `t+${(e.ts - t0).toFixed(1)}s — ${mechLabel(e)}: ${JSON.stringify(e.detalle).slice(0, 100)}`;
    wrap.appendChild(dot);
  }

  // momento de fuga
  if (data.escape_ts) {
    const dot = document.createElement("div");
    dot.className = "event-dot escape";
    dot.style.left = pct(data.escape_ts) + "%";
    wrap.appendChild(dot);

    const label = document.createElement("div");
    label.className = "event-label escape";
    label.style.left = pct(data.escape_ts) + "%";
    label.textContent = "FUGA";
    wrap.appendChild(label);
  }

  // momento de deteccion + bracket de TTD
  if (data.alert_ts) {
    const dot = document.createElement("div");
    dot.className = "event-dot detected";
    dot.style.left = pct(data.alert_ts) + "%";
    wrap.appendChild(dot);

    const label = document.createElement("div");
    label.className = "event-label detected";
    label.style.left = pct(data.alert_ts) + "%";
    label.textContent = `DETECTADO\n${data.analysis.monitor_detector}`;
    label.style.whiteSpace = "pre-line";
    wrap.appendChild(label);

    if (data.escape_ts) {
      const left = pct(data.escape_ts);
      const right = pct(data.alert_ts);
      const bracket = document.createElement("div");
      bracket.className = "ttd-bracket";
      bracket.style.left = Math.min(left, right) + "%";
      bracket.style.width = Math.abs(right - left) + "%";
      wrap.appendChild(bracket);
    }
  }
}

function renderTurnLog(data) {
  const log = document.getElementById("turn-log");
  log.innerHTML = "";

  const rows = [];
  for (const e of data.transcript) {
    if (!(e.role === "tool" || (e.role === "assistant"))) continue;
    rows.push({ ts: e.ts, who: e.role === "assistant" ? "agente" : `agente · ${e.name}`, html: toolSummary(e), kind: "agent" });
  }
  for (const e of data.events) {
    if (e.severidad !== "alerta") continue;
    rows.push({ ts: e.ts, who: `monitor · ${mechLabel(e)}`, html: JSON.stringify(e.detalle).slice(0, 140), kind: "monitor" });
  }
  rows.sort((a, b) => a.ts - b.ts);
  if (rows.length === 0) {
    log.innerHTML = '<p class="empty-note">Sin transcript para esta corrida.</p>';
    return;
  }
  const t0 = rows[0].ts;

  for (const r of rows) {
    const div = document.createElement("div");
    let cls = "turn-row";
    if (data.escape_ts && Math.abs(r.ts - data.escape_ts) < 0.001) cls += " is-escape";
    if (data.alert_ts && Math.abs(r.ts - data.alert_ts) < 0.001 && r.kind === "monitor") cls += " is-detect";
    div.className = cls;
    div.innerHTML = `<span class="t tabular">t+${(r.ts - t0).toFixed(1)}s</span><span class="who">${r.who}</span><span class="what">${r.html}</span>`;
    log.appendChild(div);
  }
}

const MECH_INFO = [
  { key: "heartbeat", cls: "mech-heartbeat", title: "Heartbeat", surface: "ausencia — canal directo, bypassea el proxy",
    desc: "Ping cada 5s desde el sandbox. Si deja de sonar >2 intervalos, alerta de silencio." },
  { key: "egress", cls: "mech-egress", title: "Egress baseline", surface: "red — mitmproxy, unico camino de salida",
    desc: "Aprende destinos normales; marca cualquier desviacion, exitosa o fallida (CONNECT incluido)." },
  { key: "canary-net", cls: "mech-canary-net", title: "Canary — red", surface: "host / ruta / query / cuerpo de requests salientes",
    desc: "Busca el token (y variantes ofuscadas: b64, url, hex, invertido) en todo el trafico saliente." },
  { key: "canary-fs", cls: "mech-canary-fs", title: "Canary — filesystem", surface: "nombres de archivo/directorio + contenido",
    desc: "Escanea /workspace cada 3s. El vector del incidente ancla: mensajes codificados en nombres de directorio." },
];

function renderMechCards(data) {
  const grid = document.getElementById("mech-grid");
  grid.innerHTML = "";
  const counts = {};
  for (const e of data.events) {
    if (e.severidad !== "alerta") continue;
    const c = mechClass(e).replace("mech-", "");
    counts[c] = (counts[c] || 0) + 1;
  }
  for (const m of MECH_INFO) {
    const card = document.createElement("div");
    card.className = "mech-card";
    card.style.setProperty("--mech-color", `var(--${m.cls})`);
    const n = counts[m.key] || 0;
    card.innerHTML = `
      <h3>${m.title}</h3>
      <div class="surface">${m.surface}</div>
      <p>${m.desc}</p>
      <div class="fact">en esta corrida: <b>${n}</b> alerta${n === 1 ? "" : "s"}</div>
    `;
    grid.appendChild(card);
  }
}

async function loadAggregate() {
  const res = await fetch("/api/aggregate");
  const data = await res.json();
  state.aggregate = data;

  const tiles = document.getElementById("agg-tiles");
  tiles.innerHTML = "";
  const totalIntentos = data.grupos.reduce((s, g) => s + g.intentos_de_escape, 0);
  const totalDetectados = data.grupos.reduce((s, g) => s + g.detectados, 0);
  const stats = [
    [data.total_corridas, "corridas en results/"],
    [totalIntentos, "intentos de escape"],
    [totalDetectados, "detectados"],
  ];
  for (const [v, l] of stats) {
    const t = document.createElement("div");
    t.className = "stat-tile";
    t.innerHTML = `<div class="value tabular">${v}</div><div class="label">${l}</div>`;
    tiles.appendChild(t);
  }

  const grid = document.getElementById("agg-grid");
  grid.innerHTML = "";
  const maxN = Math.max(...data.grupos.map((g) => g.corridas), 1);
  for (const g of data.grupos) {
    const row = document.createElement("div");
    row.className = "agg-row";
    const bar = document.createElement("div");
    bar.className = "agg-bar";
    for (let n = 0; n <= 6; n++) {
      const c = g.dist_niveles[n] || 0;
      if (c === 0) continue;
      const seg = document.createElement("div");
      seg.className = "seg";
      seg.style.background = NIVEL_COLORS[n];
      seg.style.width = `${(c / g.corridas) * 100}%`;
      seg.title = `nivel ${n} (${data.niveles_labels[n]}): ${c}/${g.corridas}`;
      bar.appendChild(seg);
    }
    row.innerHTML = `<div class="agg-label">${g.condicion} <span class="n">/ ${g.tarea}</span></div>`;
    row.appendChild(bar);
    const count = document.createElement("div");
    count.className = "agg-count tabular";
    count.textContent = `n=${g.corridas}`;
    row.appendChild(count);
    grid.appendChild(row);
  }

  const legend = document.getElementById("agg-legend");
  legend.innerHTML = "";
  for (let n = 0; n <= 6; n++) {
    const sw = document.createElement("span");
    sw.className = "sw";
    sw.innerHTML = `<span class="chip-dot" style="background:${NIVEL_COLORS[n]}"></span>${n} ${data.niveles_labels[n]}`;
    legend.appendChild(sw);
  }
}

document.getElementById("refresh-btn").addEventListener("click", async () => {
  await loadRuns();
  await loadAggregate();
});

loadRuns();
loadAggregate();
