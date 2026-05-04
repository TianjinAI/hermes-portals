// Governance Dashboard — live pipeline viewer

const STAGE_NAMES = {
  critical:    "① Critical",
  fetch:       "② Fetch",
  thinking:    "③ Thinking",
  implement:   "④ Implement",
  review:      "⑤ Review",
  meta_review: "⑥ Meta-Review",
  verify:      "⑦ Verify",
  evolve:      "⑧ Evolve",
};

const STAGE_ICONS = {
  done:    "✅",
  active:  "🔄",
  failed:  "❌",
  pending: "⏳",
};

let lastLogCount = 0;

function iconFor(status) {
  return STAGE_ICONS[status] || "⏳";
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function formatElapsed(started, completed) {
  if (!started) return "";
  const start = new Date(started);
  const end = completed ? new Date(completed) : new Date();
  const ms = end - start;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms/1000).toFixed(1)}s`;
  return `${(ms/60000).toFixed(1)}m`;
}

// --- Render Pipeline ---
function renderPipeline(stages) {
  const container = document.getElementById("stagesContainer");
  const entries = Object.entries(stages);
  let html = "";

  entries.forEach(([key, stage], i) => {
    if (i > 0) {
      const flowing = stage.status === "active" || (entries[i - 1][1].status === "done");
      html += `<div class="stage-connector${flowing ? ' flowing' : ''}"></div>`;
    }
    html += `
      <div class="stage-node ${stage.status === 'active' ? 'active' : ''} ${stage.status === 'done' ? 'done' : ''} ${stage.status === 'failed' ? 'failed' : ''}">
        <div class="stage-icon">${iconFor(stage.status)}</div>
        <div class="stage-info">
          <div class="stage-name">${STAGE_NAMES[key] || key}</div>
          <div class="stage-output">${stage.output || '—'}</div>
        </div>
        <div class="stage-num">${i + 1}</div>
      </div>`;
  });

  container.innerHTML = html;
}

// --- Render Intent Packet ---
function renderIntent(packet) {
  const body = document.getElementById("intentBody");
  if (!packet || !packet.goal) {
    body.innerHTML = '<div class="placeholder">No active pipeline run.</div>';
    return;
  }
  const constraints = packet.constraints || [];
  const nonGoals = packet.non_goals || [];
  const success = packet.success_criteria || [];
  body.innerHTML = `
    <div class="intent-field">
      <div class="label">Goal</div>
      <div class="value">${esc(packet.goal)}</div>
    </div>
    ${constraints.length ? `
    <div class="intent-field">
      <div class="label">Constraints (${constraints.length})</div>
      <div>${constraints.map(c => `<span class="constraint-tag">${esc(c)}</span>`).join('')}</div>
    </div>` : ''}
    ${nonGoals.length ? `
    <div class="intent-field">
      <div class="label">Non-Goals (${nonGoals.length})</div>
      <div>${nonGoals.map(n => `<span class="constraint-tag" style="opacity:.6">${esc(n)}</span>`).join('')}</div>
    </div>` : ''}
    ${success.length ? `
    <div class="intent-field">
      <div class="label">Success Criteria (${success.length})</div>
      <div>${success.map(s => `<div style="font-size:12px;margin:3px 0">✓ ${esc(s)}</div>`).join('')}</div>
    </div>` : ''}
  `;
}

// --- Render Dispatch Plan ---
function renderPlan(plan) {
  const body = document.getElementById("planBody");
  if (!plan || !plan.tasks || !plan.tasks.length) {
    body.innerHTML = '<div class="placeholder">Waiting for Stage 3 (Thinking).</div>';
    return;
  }
  body.innerHTML = `
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">${plan.tasks.length} tasks · ${plan.architecture || 'No architecture summary'}</div>
    ${plan.tasks.map((t, i) => `
      <div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px">
        <span style="color:var(--accent);flex-shrink:0">${i + 1}.</span>
        <span>${esc(typeof t === 'string' ? t : t.content || t.goal || JSON.stringify(t))}</span>
      </div>
    `).join('')}
  `;
}

// --- Render Active Task ---
function renderTask(taskName, stages) {
  const body = document.getElementById("taskBody");
  const activeStage = Object.entries(stages).find(([_, s]) => s.status === "active");
  const stageName = activeStage ? STAGE_NAMES[activeStage[0]] : "—";
  if (!taskName) {
    body.innerHTML = '<div class="placeholder">No task active.</div>';
    return;
  }
  body.innerHTML = `
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">
      <div style="width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);animation:pulse 1.5s infinite"></div>
      <span style="font-weight:600">${esc(taskName)}</span>
    </div>
    <div style="font-size:11px;color:var(--text-muted)">Current stage: ${stageName}</div>
    <style>@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }</style>
  `;
}

// --- Render Activity Log ---
function renderLog(log, activeStage) {
  const feed = document.getElementById("logFeed");
  if (!log || !log.length) {
    feed.innerHTML = '<div class="log-entry muted">Waiting for pipeline to start...</div>';
    lastLogCount = 0;
    return;
  }
  // Only append new entries
  let html = "";
  const newEntries = log.slice(lastLogCount);
  newEntries.forEach(entry => {
    const time = formatTime(entry.time);
    const cls = entry.level || "info";
    html += `<div class="log-entry ${cls}"><span class="log-time">${time}</span> ${esc(entry.message)}</div>`;
  });
  if (newEntries.length > 0) {
    // Append without replacing existing
    const existing = feed.innerHTML;
    const wasAtBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
    feed.innerHTML = existing + html;
    if (wasAtBottom) feed.scrollTop = feed.scrollHeight;
    lastLogCount = log.length;
  }

  // If feed was empty placeholder, replace entirely
  if (lastLogCount === 0 && log.length > 0) {
    let fullHtml = "";
    log.forEach(entry => {
      const time = formatTime(entry.time);
      const cls = entry.level || "info";
      fullHtml += `<div class="log-entry ${cls}"><span class="log-time">${time}</span> ${esc(entry.message)}</div>`;
    });
    feed.innerHTML = fullHtml;
    lastLogCount = log.length;
  }
}

// --- Status bar ---
function renderStatus(state) {
  const stages = state.stages || {};
  const activeEntry = Object.entries(stages).find(([_, s]) => s.status === "active");
  document.getElementById("activeStage").textContent = activeEntry
    ? `${STAGE_NAMES[activeEntry[0]]}`
    : "idle";

  const dot = document.getElementById("connectionDot");
  dot.className = "status-dot live";
  document.getElementById("connectionLabel").textContent = "live";
}

// --- Poll loop ---
async function poll() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) throw new Error("bad response");
    const state = await res.json();
    renderPipeline(state.stages);
    renderIntent(state.intent_packet);
    renderPlan(state.dispatch_plan);
    renderTask(state.active_task, state.stages);
    renderLog(state.activity_log);
    renderStatus(state);
  } catch (err) {
    document.getElementById("connectionDot").className = "status-dot";
    document.getElementById("connectionLabel").textContent = "offline";
    console.warn("Poll error:", err.message);
  }
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- Init ---
poll();
setInterval(poll, 2000);
