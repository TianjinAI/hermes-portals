#!/usr/bin/env python3
"""Hermes Governance Dashboard — 8-stage workflow visualization."""

import json, os, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "5056"))
GOV_DIR = Path.home() / ".hermes" / "governance"

STAGES = [
    ("critical", "Critical", "🎯"),
    ("fetch", "Fetch", "🔍"),
    ("thinking", "Thinking", "🧠"),
    ("execution", "Execution", "⚡"),
    ("review", "Review", "🔬"),
    ("meta_review", "Meta-Review", "🛡️"),
    ("verification", "Verification", "✅"),
    ("evolution", "Evolution", "🧬"),
]

CSS = """
:root {
  --bg: #0B0E11; --surface: #12161C; --surface-alt: #1A1F2B;
  --surface-hover: #222836; --border: #2A3040; --text: #E8ECF1;
  --text-secondary: #8B95A5; --text-muted: #5C6478;
  --accent: #FF6B35; --accent-bg: rgba(255,107,53,0.12);
  --green: #0ECB81; --green-bg: rgba(14,203,129,0.10);
  --amber: #FFB300; --amber-bg: rgba(255,179,0,0.10);
  --blue: #42A5F5; --blue-bg: rgba(66,165,245,0.10);
  --red: #F6465D; --purple: #AB47BC;
  --radius: 10px; --shadow: 0 2px 8px rgba(0,0,0,0.35);
  --sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
body { margin:0; background:var(--bg); color:var(--text); font-family:var(--sans); font-size:14px; line-height:1.5; }
.app { display:flex; height:100vh; overflow:hidden; }
.left { width:320px; min-width:320px; background:var(--surface); border-right:1px solid var(--border); padding:20px; overflow-y:auto; display:flex; flex-direction:column; }
.right { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.right-top { flex:1; padding:20px 24px; overflow-y:auto; }
.right-bottom { height:280px; min-height:280px; background:var(--surface); border-top:1px solid var(--border); padding:16px 24px; overflow-y:auto; }
.header { display:flex; align-items:center; gap:10px; margin-bottom:24px; }
.header-icon { width:36px; height:36px; background:var(--accent-bg); border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:18px; }
.header h1 { font-size:18px; font-weight:700; margin:0; }
.header-badge { font-size:11px; padding:3px 8px; border-radius:12px; font-weight:600; }
.badge-active { background:var(--green-bg); color:var(--green); }
.badge-idle { background:var(--surface-alt); color:var(--text-muted); }
.pipeline { display:flex; flex-direction:column; gap:0; flex:1; }
.stage { display:flex; align-items:flex-start; gap:12px; padding:8px 0; position:relative; cursor:pointer; border-radius:6px; transition:background 0.2s; }
.stage:hover { background:var(--surface-hover); }
.stage-connector { position:absolute; left:19px; top:28px; bottom:-8px; width:2px; background:var(--border); }
.stage:last-child .stage-connector { display:none; }
.stage-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; margin-top:4px; position:relative; z-index:1; }
.dot-done { background:var(--green); box-shadow:0 0 8px rgba(14,203,129,0.3); }
.dot-active { background:var(--accent); box-shadow:0 0 12px rgba(255,107,53,0.5); animation:pulse 1.5s ease-in-out infinite; }
.dot-pending { background:var(--border); }
.dot-failed { background:var(--red); }
@keyframes pulse { 0%,100% { box-shadow:0 0 8px rgba(255,107,53,0.3); } 50% { box-shadow:0 0 20px rgba(255,107,53,0.6); } }
.stage-info { flex:1; min-width:0; }
.stage-name { font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }
.stage-summary { font-size:11px; color:var(--text-muted); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.stage-active .stage-name { color:var(--accent); }
.stage-done .stage-name { color:var(--green); }
.stage-artifact { display:none; margin-top:6px; padding:8px 10px; background:var(--surface-alt); border-radius:6px; font-size:11px; color:var(--text-secondary); border:1px solid var(--border); }
.stage.expanded .stage-artifact { display:block; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 20px; margin-bottom:14px; box-shadow:var(--shadow); }
.card-title { font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); margin-bottom:10px; display:flex; align-items:center; gap:6px; }
.card-title-icon { font-size:14px; }
.info-row { display:flex; gap:8px; margin-bottom:6px; font-size:13px; }
.info-label { color:var(--text-muted); min-width:70px; }
.info-value { color:var(--text); font-weight:500; }
.task-item { padding:8px 12px; background:var(--surface-alt); border-radius:6px; margin-bottom:6px; border-left:3px solid var(--accent); }
.task-owner { font-size:11px; color:var(--text-muted); margin-top:2px; }
.log-entry { padding:6px 0; border-bottom:1px solid var(--border); font-size:12px; display:flex; gap:10px; align-items:flex-start; }
.log-time { color:var(--text-muted); font-family:var(--mono); font-size:11px; white-space:nowrap; min-width:55px; }
.log-stage { font-size:10px; padding:1px 6px; border-radius:8px; font-weight:600; white-space:nowrap; }
.log-msg { color:var(--text-secondary); flex:1; }
.empty-state { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-muted); }
.empty-icon { font-size:48px; margin-bottom:16px; }
.error { padding:20px; color:var(--red); }
"""

STAGE_COLORS = {
    "critical": "rgba(255,160,40,0.12)", "fetch": "rgba(66,165,245,0.12)",
    "thinking": "rgba(171,71,188,0.12)", "execution": "rgba(255,107,53,0.12)",
    "review": "rgba(14,203,129,0.12)", "meta_review": "rgba(171,71,188,0.12)",
    "verification": "rgba(66,165,245,0.12)", "evolution": "rgba(255,179,0,0.12)",
}

STAGE_TEXT_COLORS = {
    "critical": "#FFA028", "fetch": "#42A5F5", "thinking": "#AB47BC",
    "execution": "#FF6B35", "review": "#0ECB81", "meta_review": "#AB47BC",
    "verification": "#42A5F5", "evolution": "#FFB300",
}


def get_state():
    if not GOV_DIR.exists():
        return {"active": False}
    for proj_dir in sorted(GOV_DIR.iterdir()):
        if proj_dir.is_dir():
            sf = proj_dir / "workflow_state.json"
            if sf.exists():
                try:
                    with open(sf) as f:
                        state = json.load(f)
                    state["project_dir"] = proj_dir.name
                    return state
                except (json.JSONDecodeError, KeyError):
                    continue
    return {"active": False}


def build_html():
    state = get_state()
    active = state.get("active", False)

    # Pipeline HTML
    pipeline_html = ""
    if active:
        stages_data = state.get("stages", {})
        for sid, sname, sicon in STAGES:
            sdata = stages_data.get(sid, {"status": "pending", "summary": ""})
            status = sdata.get("status", "pending")
            summary = sdata.get("summary", "")
            artifact = sdata.get("artifact", {})
            status_class = f"stage-{status}" if status in ("done","active","failed") else ""
            dot_class = {"done":"dot-done","active":"dot-active","pending":"dot-pending","failed":"dot-failed"}.get(status,"dot-pending")

            artifact_html = ""
            if artifact:
                items = "".join(f'<div style="margin:2px 0">• <strong>{k}:</strong> {str(v)[:80]}</div>' for k,v in artifact.items())
                artifact_html = f'<div class="stage-artifact">{items}</div>'

            pipeline_html += f'''
            <div class="stage {status_class}" onclick="this.classList.toggle('expanded')">
              <div style="position:relative;width:24px;flex-shrink:0">
                <div class="stage-dot {dot_class}"></div>
                <div class="stage-connector"></div>
              </div>
              <div class="stage-info">
                <div class="stage-name">{sicon} {sname}</div>
                <div class="stage-summary">{summary or 'Waiting...'}</div>
                {artifact_html}
              </div>
            </div>'''
    else:
        pipeline_html = '<div class="empty-state"><div class="empty-icon">🛌</div><p>No active governance workflow</p></div>'

    # Right top - info
    if active:
        intent = state.get("stages",{}).get("critical",{}).get("artifact",{})
        dispatch = state.get("stages",{}).get("thinking",{}).get("artifact",{})
        tasks = dispatch.get("tasks", [])
        tasks_html = "".join(
            f'<div class="task-item"><strong>{t.get("task","?")}</strong><div class="task-owner">👤 {t.get("owner","unassigned")}</div></div>'
            for t in tasks
        ) if tasks else '<div style="color:var(--text-muted);font-size:13px">No tasks defined yet</div>'

        info_html = f'''
        <div class="card">
          <div class="card-title"><span class="card-title-icon">📋</span> Workflow Info</div>
          <div class="info-row"><span class="info-label">Project</span><span class="info-value">{state.get("project","?")}</span></div>
          <div class="info-row"><span class="info-label">Task</span><span class="info-value">{state.get("task","?")[:80]}</span></div>
          <div class="info-row"><span class="info-label">Started</span><span class="info-value">{state.get("started","?")[:19]}</span></div>
        </div>
        <div class="card">
          <div class="card-title"><span class="card-title-icon">🎯</span> Intent Packet</div>
          <div class="info-row"><span class="info-label">Scope</span><span class="info-value">{intent.get("scope","—")}</span></div>
          <div class="info-row"><span class="info-label">Goal</span><span class="info-value">{intent.get("goal","—")[:80]}</span></div>
          <div class="info-row"><span class="info-label">Constraints</span><span class="info-value">{intent.get("constraints","—")[:80]}</span></div>
        </div>
        <div class="card">
          <div class="card-title"><span class="card-title-icon">📊</span> Dispatch Plan</div>
          {tasks_html}
        </div>'''
    else:
        info_html = '<div class="empty-state"><div class="empty-icon">🚀</div><p>Send a governed-dev command to start</p></div>'

    # Log
    log_entries = state.get("log", []) if active else []
    log_html = ""
    for entry in reversed(log_entries[-50:]):
        sid = entry.get("stage","")
        bg = STAGE_COLORS.get(sid, "var(--surface-alt)")
        tc = STAGE_TEXT_COLORS.get(sid, "var(--text-muted)")
        log_html += f'''
        <div class="log-entry">
          <span class="log-time">{entry.get("time","")[11:19]}</span>
          <span class="log-stage" style="background:{bg};color:{tc}">{sid}</span>
          <span class="log-msg">{entry.get("action","")}</span>
        </div>'''
    if not log_html:
        log_html = '<div style="color:var(--text-muted);font-size:13px">No activity yet</div>'

    badge = '<span class="header-badge badge-active">● LIVE</span>' if active else '<span class="header-badge badge-idle">○ IDLE</span>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hermes Governance Dashboard</title>
<style>{CSS}</style></head>
<body>
<div class="app">
  <div class="left">
    <div class="header">
      <div class="header-icon">🔷</div>
      <h1>Governance</h1>
      {badge}
    </div>
    <div class="pipeline" id="pipeline">{pipeline_html}</div>
  </div>
  <div class="right">
    <div class="right-top" id="info">{info_html}</div>
    <div class="right-bottom" id="log">{log_html}</div>
  </div>
</div>
<script>
async function refresh() {{
  try {{
    const res = await fetch('/api/state');
    if (!res.ok) return;
    const data = await res.json();
    renderPipeline(data);
    renderInfo(data);
    renderLog(data);
  }} catch(e) {{ console.error('Refresh error:', e); }}
}}

function renderPipeline(data) {{
  if (!data.active) {{
    document.getElementById('pipeline').innerHTML = '<div class="empty-state"><div class="empty-icon">🛌</div><p>No active governance workflow</p></div>';
    return;
  }}
  const stages = {json.dumps(STAGES)};
  const sd = data.stages || {{}};
  let html = '';
  for (const [sid, sname, sicon] of stages) {{
    const sdata = sd[sid] || {{status:'pending',summary:''}};
    const status = sdata.status || 'pending';
    const summary = sdata.summary || '';
    const artifact = sdata.artifact || {{}};
    const sc = {{'done':'stage-done','active':'stage-active','pending':'','failed':''}}[status]||'';
    const dc = {{'done':'dot-done','active':'dot-active','pending':'dot-pending','failed':'dot-failed'}}[status]||'dot-pending';
    let artHtml = '';
    if (artifact && Object.keys(artifact).length) {{
      artHtml = '<div class="stage-artifact">' + Object.entries(artifact).map(([k,v]) => `<div style="margin:2px 0">• <strong>${{k}}:</strong> ${{String(v).substring(0,80)}}</div>`).join('') + '</div>';
    }}
    html += `<div class="stage ${{sc}}" onclick="this.classList.toggle('expanded')">
      <div style="position:relative;width:24px;flex-shrink:0"><div class="stage-dot ${{dc}}"></div><div class="stage-connector"></div></div>
      <div class="stage-info"><div class="stage-name">${{sicon}} ${{sname}}</div><div class="stage-summary">${{summary||'Waiting...'}}</div>${{artHtml}}</div></div>`;
  }}
  document.getElementById('pipeline').innerHTML = html;
}}

function renderInfo(data) {{
  if (!data.active) {{
    document.getElementById('info').innerHTML = '<div class="empty-state"><div class="empty-icon">🚀</div><p>Send a governed-dev command to start</p></div>';
    return;
  }}
  const intent = (data.stages||{{}}).critical?.artifact || {{}};
  const dispatch = (data.stages||{{}}).thinking?.artifact || {{}};
  const tasks = dispatch.tasks || [];
  const tasksHtml = tasks.length ? tasks.map(t => `<div class="task-item"><strong>${{t.task}}</strong><div class="task-owner">👤 ${{t.owner}}</div></div>`).join('') : '<div style="color:var(--text-muted);font-size:13px">No tasks defined yet</div>';
  document.getElementById('info').innerHTML = `
    <div class="card"><div class="card-title"><span class="card-title-icon">📋</span> Workflow Info</div>
      <div class="info-row"><span class="info-label">Project</span><span class="info-value">${{data.project||'?'}}</span></div>
      <div class="info-row"><span class="info-label">Task</span><span class="info-value">${{(data.task||'?').substring(0,80)}}</span></div>
      <div class="info-row"><span class="info-label">Started</span><span class="info-value">${{(data.started||'?').substring(0,19)}}</span></div></div>
    <div class="card"><div class="card-title"><span class="card-title-icon">🎯</span> Intent Packet</div>
      <div class="info-row"><span class="info-label">Scope</span><span class="info-value">${{intent.scope||'\u2014'}}</span></div>
      <div class="info-row"><span class="info-label">Goal</span><span class="info-value">${{(intent.goal||'\u2014').substring(0,80)}}</span></div>
      <div class="info-row"><span class="info-label">Constraints</span><span class="info-value">${{(intent.constraints||'\u2014').substring(0,80)}}</span></div></div>
    <div class="card"><div class="card-title"><span class="card-title-icon">📊</span> Dispatch Plan</div>${{tasksHtml}}</div>`;
}}

function renderLog(data) {{
  const log = data.log || [];
  if (!log.length) {{ document.getElementById('log').innerHTML = '<div style="color:var(--text-muted);font-size:13px">No activity yet</div>'; return; }}
  const bgColors = {json.dumps(STAGE_COLORS)}; const txColors = {json.dumps(STAGE_TEXT_COLORS)};
  document.getElementById('log').innerHTML = log.slice().reverse().slice(0,50).map(e => {{
    const sid = e.stage||'';
    return `<div class="log-entry"><span class="log-time">${{(e.time||'').substring(11,19)}}</span><span class="log-stage" style="background:${{bgColors[sid]||'var(--surface-alt)'}};color:${{txColors[sid]||'var(--text-muted)'}}">${{sid}}</span><span class="log-msg">${{e.action||''}}</span></div>`;
  }}).join('');
}}

setInterval(refresh, 3000);
refresh();
</script>
</body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.respond_html(build_html())
            elif path == "/api/state":
                self.respond_json(get_state())
            else:
                self.send_error(404)
        except Exception as e:
            self.send_error(500, str(e))

    def respond_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    GOV_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Governance Dashboard → http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
