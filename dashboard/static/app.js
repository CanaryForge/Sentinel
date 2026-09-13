const NIVEL_COLORS = ["var(--nivel-0)", "var(--nivel-1)", "var(--nivel-2)", "var(--nivel-3)", "var(--nivel-4)", "var(--nivel-5)", "var(--nivel-6)"];
// Respaldo, no mecanismo principal: el feed en vivo llega por /api/stream
// (SSE, empujado por watchdog sobre results/ en el backend). Esto solo
// resincroniza el agregado/la lista de corridas si el stream se cayo y
// se perdio algo entre la desconexion y el reintento de EventSource.
const FALLBACK_POLL_MS = 30000;
const MAX_FEED_DOM = 300;
const DETAIL_REFRESH_DEBOUNCE_MS = 400;

const state = {
  runs: [], detail: null, aggregate: null, selectedRunId: null, userPicked: false,
  streamConnected: false, feedPaused: false, feedQueue: [], detailRefreshTimer: null,
};

function fmtSecs(s) {
  if (s === null || s === undefined) return "—";
  return s.toFixed(1) + "s";
}

function fmtClock(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("es-AR", { hour12: false });
}

function shortRunId(runId) {
  return runId.length > 40 ? runId.slice(0, 20) + "…" + runId.slice(-16) : runId;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
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
  // El contenido interpolado aca (nombres de tool, args, texto del agente)
  // viene de un agente potencialmente adversarial (es lo que este arnes
  // esta tratando de contener) -- se escapa antes de insertarlo via
  // innerHTML, nunca se confia en el como HTML seguro.
  if (entry.role === "assistant") {
    const tc = entry.tool_calls;
    if (!tc) return entry.content ? escapeHtml(entry.content.slice(0, 140)) : "(respuesta final)";
    return "→ " + tc.map((t) => escapeHtml(t.function.name)).join(", ");
  }
  if (entry.role === "tool") {
    const args = entry.args || {};
    let a = "";
    if (entry.name === "http_fetch") a = args.url || "";
    else if (args.path) a = args.path;
    else a = JSON.stringify(args).slice(0, 60);
    return `<code>${escapeHtml(entry.name)}</code> ${escapeHtml(a)}`;
  }
  return escapeHtml(entry.role);
}

function isEscapeToolCall(entry) {
  return entry.role === "tool" && entry.name === "http_fetch";
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
    setLive(false);
    return;
  }

  const enCurso = state.runs.find((r) => r.en_curso);
  setLive(!!enCurso);

  let preferido;
  if (enCurso) {
    // Una corrida activa siempre gana: es lo que "en vivo" significa.
    preferido = enCurso.run_id;
  } else if (state.userPicked && state.runs.some((r) => r.run_id === state.selectedRunId)) {
    // Respeta la seleccion manual del usuario entre refrescos automaticos.
    preferido = state.selectedRunId;
  } else {
    // Por defecto, la corrida mas "interesante": mayor nivel de escalada.
    const sorted = [...state.runs].sort((a, b) => (b.nivel_escalada || 0) - (a.nivel_escalada || 0));
    preferido = sorted[0].run_id;
  }

  for (const r of state.runs) {
    const opt = document.createElement("option");
    opt.value = r.run_id;
    opt.textContent = `${r.run_id}  [nivel ${r.nivel_escalada}]${r.en_curso ? "  ● en curso" : ""}`;
    if (r.run_id === preferido) opt.selected = true;
    picker.appendChild(opt);
  }
  picker.onchange = () => {
    state.userPicked = true;
    state.selectedRunId = picker.value;
    loadRunDetail(picker.value);
  };
  state.selectedRunId = preferido;
  await loadRunDetail(preferido);
}

function setLive(isLive) {
  document.getElementById("live-dot").classList.toggle("live", isLive);
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
    desc: "Reacciona por evento (inotify) en /workspace y en ./memory, con barrido de respaldo. El vector del incidente ancla: mensajes codificados en nombres de directorio." },
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
  // La cifra que vale es la de superficies que produce el agente. La cruda
  // cuenta tambien los hallazgos sobre agent_transcript.jsonl, que escribe el
  // propio harness -- mostrarla sola contradice report/findings.md.
  const detAgente = data.grupos.reduce((s, g) => s + (g.detectados_superficie_agente || 0), 0);
  const stats = [
    [data.total_corridas, "corridas en results/"],
    [totalIntentos, "intentos de escape"],
    [detAgente, "detectados", `en superficie del agente · ${totalDetectados} contando el log del harness`],
  ];
  for (const [v, l, nota] of stats) {
    const t = document.createElement("div");
    t.className = "stat-tile";
    t.innerHTML = `<div class="value tabular">${v}</div><div class="label">${l}</div>` +
      (nota ? `<div class="stat-note">${nota}</div>` : "");
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

function drawMiniLineChart({ points, color, xLabelFn, xLog }) {
  // points: [{x, y}], y === null significa "sin detectar" (timeout del barrido)
  const W = 320, H = 150, PAD_L = 34, PAD_R = 14, PAD_T = 14, PAD_B = 26;
  const plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;

  const xs = points.map((p) => p.x);
  const ys = points.filter((p) => p.y !== null).map((p) => p.y);
  const maxY = Math.max(...ys, 1) * 1.25;
  const xScale = xLog
    ? (x) => PAD_L + (Math.log(x / xs[0]) / Math.log(xs[xs.length - 1] / xs[0])) * plotW
    : (x) => PAD_L + ((x - xs[0]) / (xs[xs.length - 1] - xs[0])) * plotW;
  const yScale = (y) => PAD_T + plotH - (y / maxY) * plotH;

  let gridLines = "";
  const nGrid = 3;
  for (let i = 0; i <= nGrid; i++) {
    const y = PAD_T + (plotH / nGrid) * i;
    const val = maxY - (maxY / nGrid) * i;
    gridLines += `<line class="grid-line" x1="${PAD_L}" y1="${y}" x2="${W - PAD_R}" y2="${y}"></line>`;
    gridLines += `<text class="axis-label" x="${PAD_L - 6}" y="${y + 3}" text-anchor="end">${val.toFixed(0)}s</text>`;
  }

  let path = "";
  let dots = "";
  let labels = "";
  const detectedPts = points.filter((p) => p.y !== null);
  path = detectedPts.map((p, i) => `${i === 0 ? "M" : "L"}${xScale(p.x).toFixed(1)},${yScale(p.y).toFixed(1)}`).join(" ");

  for (const p of points) {
    const cx = xScale(p.x);
    if (p.y === null) {
      dots += `<text x="${cx}" y="${PAD_T + 10}" text-anchor="middle" class="miss-label">✕</text>`;
      labels += `<text x="${cx}" y="${PAD_T + 22}" text-anchor="middle" class="miss-label" font-size="8">sin detectar</text>`;
    } else {
      const cy = yScale(p.y);
      dots += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${color}" stroke="var(--surface)" stroke-width="2"></circle>`;
      labels += `<text x="${cx}" y="${cy - 10}" text-anchor="middle" class="value-label">${p.y.toFixed(1)}s</text>`;
    }
    labels += `<text x="${cx}" y="${H - 8}" text-anchor="middle" class="axis-label">${xLabelFn(p.x)}</text>`;
  }

  return `<svg viewBox="0 0 ${W} ${H}" role="img">
    ${gridLines}
    <path d="${path}" fill="none" stroke="${color}" stroke-width="2"></path>
    ${dots}${labels}
  </svg>`;
}

async function loadMonitorStrength() {
  const res = await fetch("/api/monitor_strength");
  const rows = await res.json();
  const grid = document.getElementById("mstr-grid");

  if (rows.length === 0) {
    grid.innerHTML = '<p class="empty-note">Sin datos todavia — corre tests/monitor_strength_sweep.sh</p>';
    return;
  }
  grid.innerHTML = "";

  const groups = [
    { key: "canary_fs", title: "canary_monitor.py (filesystem)", sub: "parametro: CANARY_FALLBACK_INTERVAL — solo el barrido de respaldo; la deteccion va por inotify", color: "var(--mech-canary-fs)" },
    { key: "heartbeat", title: "heartbeat_monitor.py", sub: "parametro: intervalo × multiplicador — umbral de silencio antes de alertar", color: "var(--mech-heartbeat)" },
  ];

  for (const g of groups) {
    const pts = rows.filter((r) => r.mecanismo === g.key).map((r) => ({ x: r.valor, y: r.ttd_segundos }));
    if (pts.length === 0) continue;
    const card = document.createElement("div");
    card.className = "mstr-card";
    card.innerHTML = `<h3>${g.title}</h3><div class="mstr-sub">${g.sub}</div>` +
      drawMiniLineChart({ points: pts, color: g.color, xLabelFn: (x) => `${x}s`, xLog: true });
    grid.appendChild(card);
  }
}

async function fullResync() {
  await loadRuns();
  await loadAggregate();
  await loadMonitorStrength();
}

// ---------------------------------------------------------------------
// Feed en vivo (SOC): un item por evento empujado por /api/stream (SSE).
// El backend ya filtra/clasifica (run_started, run_finished, monitor,
// transcript); aca solo se renderiza y, si el evento toca la corrida
// actualmente seleccionada, se refresca su detalle (con debounce, para
// no relanzar un fetch por cada linea si el agente escribe en rafaga).
// ---------------------------------------------------------------------

function setStreamStatus(connected) {
  state.streamConnected = connected;
  document.getElementById("stream-dot").classList.toggle("connected", connected);
  document.getElementById("stream-status").textContent = connected
    ? "conectado — push en vivo"
    : "reconectando…";
}

function feedItemNode({ cls, time, runId, badge, msg }) {
  const div = document.createElement("div");
  div.className = `feed-item fi-new ${cls}`;
  if (runId) div.dataset.runId = runId;
  div.innerHTML = `
    <span class="fi-time tabular">${escapeHtml(time)}</span>
    <span class="fi-run" title="${escapeHtml(runId || "")}">${escapeHtml(shortRunId(runId || ""))}</span>
    <span class="fi-badge">${badge}</span>
    <span class="fi-msg">${msg}</span>
  `;
  return div;
}

function buildFeedNode(msg) {
  const runId = msg.run_id;
  if (msg.feed_type === "run_started") {
    const meta = msg.data || {};
    return feedItemNode({
      cls: "fi-lifecycle started", time: fmtClock(meta.t0), runId,
      badge: "▶ iniciada", msg: escapeHtml(`${meta.condicion || "?"} / ${meta.tarea || "?"}`),
    });
  }
  if (msg.feed_type === "run_finished") {
    const meta = msg.data || {};
    return feedItemNode({
      cls: "fi-lifecycle finished", time: fmtClock(meta.t1), runId,
      badge: "■ finalizada", msg: escapeHtml(`exit=${meta.docker_exit_code ?? "?"}`),
    });
  }
  if (msg.feed_type === "monitor") {
    const ev = msg.data || {};
    const isAlert = ev.severidad === "alerta";
    return feedItemNode({
      cls: `${mechClass(ev)} ${isAlert ? "sev-alerta" : ""}`, time: fmtClock(ev.ts), runId,
      badge: `${isAlert ? "⚠ alerta" : "info"} · ${escapeHtml(mechLabel(ev))}`,
      msg: escapeHtml(JSON.stringify(ev.detalle || {}).slice(0, 220)),
    });
  }
  if (msg.feed_type === "transcript") {
    const entry = msg.data || {};
    if (!(entry.role === "tool" || (entry.role === "assistant" && entry.tool_calls))) return null;
    const escape = isEscapeToolCall(entry);
    return feedItemNode({
      cls: `fi-agent ${escape ? "is-escape" : ""}`, time: fmtClock(entry.ts), runId,
      badge: escape ? "⚑ posible fuga" : "agente",
      msg: toolSummary(entry),
    });
  }
  return null;
}

function renderFeedNode(node) {
  const list = document.getElementById("feed-list");
  if (list.querySelector(".empty-note")) list.innerHTML = "";
  list.prepend(node);
  while (list.children.length > MAX_FEED_DOM) list.removeChild(list.lastChild);
  setTimeout(() => node.classList.remove("fi-new"), 1100);
}

function updatePausedLabel() {
  const btn = document.getElementById("feed-pause-btn");
  btn.textContent = state.feedPaused
    ? `▶ reanudar (${state.feedQueue.length})`
    : "⏸ pausar";
}

function scheduleDetailRefresh(runId) {
  if (runId !== state.selectedRunId) return;
  if (state.detailRefreshTimer) return;
  state.detailRefreshTimer = setTimeout(() => {
    state.detailRefreshTimer = null;
    loadRunDetail(state.selectedRunId);
  }, DETAIL_REFRESH_DEBOUNCE_MS);
}

async function handleLifecycleEvent(msg) {
  const picker = document.getElementById("run-picker");
  const exists = [...picker.options].some((o) => o.value === msg.run_id);

  if (msg.feed_type === "run_started") {
    setLive(true);
    if (!exists) {
      if (picker.options[0] && picker.options[0].textContent.includes("sin corridas")) picker.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = msg.run_id;
      opt.textContent = `${msg.run_id}  [nivel ?]  ● en curso`;
      picker.prepend(opt);
    }
    if (!state.userPicked) {
      picker.value = msg.run_id;
      state.selectedRunId = msg.run_id;
      await loadRunDetail(msg.run_id);
    }
    return;
  }

  // run_finished
  const stillLive = state.runs.some((r) => r.en_curso && r.run_id !== msg.run_id);
  setLive(stillLive);
  await loadRuns();
  await loadAggregate();
}

function handleStreamMessage(msg) {
  if (msg.feed_type === "run_started" || msg.feed_type === "run_finished") {
    handleLifecycleEvent(msg);
  } else {
    scheduleDetailRefresh(msg.run_id);
  }

  const node = buildFeedNode(msg);
  if (!node) return;
  if (state.feedPaused) {
    state.feedQueue.push(node);
    updatePausedLabel();
  } else {
    renderFeedNode(node);
  }
}

function startStream() {
  const es = new EventSource("/api/stream");
  es.onopen = () => setStreamStatus(true);
  es.onerror = () => setStreamStatus(false); // EventSource reconecta solo
  es.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleStreamMessage(msg);
  };
}

document.getElementById("refresh-btn").addEventListener("click", fullResync);

document.getElementById("feed-pause-btn").addEventListener("click", () => {
  state.feedPaused = !state.feedPaused;
  document.getElementById("feed-pause-btn").classList.toggle("active", state.feedPaused);
  if (!state.feedPaused) {
    for (const node of state.feedQueue) renderFeedNode(node);
    state.feedQueue = [];
  }
  updatePausedLabel();
});

document.getElementById("feed-clear-btn").addEventListener("click", () => {
  document.getElementById("feed-list").innerHTML =
    '<p class="empty-note">Feed vaciado (results/ no se toco). Los proximos eventos van a seguir llegando en vivo.</p>';
});

document.getElementById("feed-list").addEventListener("click", (e) => {
  const item = e.target.closest(".feed-item");
  const runId = item && item.dataset.runId;
  if (!runId) return;
  const picker = document.getElementById("run-picker");
  if (![...picker.options].some((o) => o.value === runId)) return;
  picker.value = runId;
  state.userPicked = true;
  state.selectedRunId = runId;
  loadRunDetail(runId);
  document.getElementById("run-section").scrollIntoView({ behavior: "smooth", block: "start" });
});

fullResync();
startStream();
setInterval(fullResync, FALLBACK_POLL_MS);
