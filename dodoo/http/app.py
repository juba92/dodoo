from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from dodoo.http.jsonrpc import jsonrpc_handler
from dodoo.http.middleware import CorrelationMiddleware
from dodoo.http.routing import MountRegistry, RouteRegistry

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dodoo ERP</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    header { background: #1e293b; padding: 1.25rem 2rem; border-bottom: 1px solid #334155;
             display: flex; align-items: center; gap: 1rem; }
    header h1 { font-size: 1.4rem; font-weight: 700; color: #f8fafc; }
    header .badge { font-size: 0.75rem; background: #0ea5e9; color: #fff;
                    padding: 0.2rem 0.6rem; border-radius: 9999px; }
    nav { margin-left: auto; display: flex; gap: 1rem; }
    nav a { color: #94a3b8; text-decoration: none; font-size: 0.875rem; }
    nav a:hover { color: #e2e8f0; }
    main { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }
    .grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 1.5rem; margin-bottom: 1.5rem; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 0.75rem; padding: 1.25rem; }
    .card h2 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
               color: #64748b; margin-bottom: 0.75rem; }
    .stat { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
    .stat-label { font-size: 0.8rem; color: #94a3b8; margin-top: 0.2rem; }
    .status-row { display: flex; align-items: center; gap: 0.5rem; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; flex-shrink: 0;
           animation: pulse 2s infinite; }
    .dot.red { background: #ef4444; animation: none; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
    .tag { display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem;
           border-radius: 4px; font-weight: 600; }
    .tag-green { background: #064e3b; color: #6ee7b7; }
    .tag-blue  { background: #1e3a5f; color: #93c5fd; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th { text-align: left; color: #64748b; font-size: 0.7rem; text-transform: uppercase;
         letter-spacing: 0.05em; padding: 0 0 0.5rem; border-bottom: 1px solid #334155; }
    td { padding: 0.6rem 0; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
    tr:last-child td { border-bottom: none; }
    td:first-child { color: #f1f5f9; font-family: monospace; }
    .model-grid { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .model-tag { background: #0f172a; border: 1px solid #334155; border-radius: 0.3rem;
                 font-size: 0.75rem; padding: 0.2rem 0.5rem; font-family: monospace; color: #94a3b8; }
    .login-form { display: flex; flex-direction: column; gap: 0.6rem; }
    .login-form input { background: #0f172a; border: 1px solid #475569; border-radius: 0.4rem;
                        padding: 0.5rem 0.75rem; color: #e2e8f0; font-size: 0.875rem; width: 100%; }
    .login-form input:focus { outline: none; border-color: #0ea5e9; }
    .btn { padding: 0.55rem 1rem; border-radius: 0.4rem; border: none; font-weight: 600;
           font-size: 0.875rem; cursor: pointer; transition: opacity 0.15s; }
    .btn-primary { background: #0ea5e9; color: #fff; }
    .btn:hover { opacity: 0.85; }
    pre#result { background: #0f172a; border: 1px solid #334155; border-radius: 0.5rem;
                 padding: 0.75rem; font-size: 0.8rem; white-space: pre-wrap; color: #6ee7b7;
                 margin-top: 0.75rem; display: none; max-height: 160px; overflow: auto; }
    #token-box { margin-top: 0.5rem; font-size: 0.75rem; color: #94a3b8;
                 word-break: break-all; display: none; }
    .rpc-form textarea { background: #0f172a; border: 1px solid #475569; border-radius: 0.4rem;
                         padding: 0.5rem 0.75rem; color: #e2e8f0; font-size: 0.8rem;
                         font-family: monospace; width: 100%; resize: vertical; }
    .rpc-form textarea:focus { outline: none; border-color: #0ea5e9; }
    pre#rpc-result { background: #0f172a; border: 1px solid #334155; border-radius: 0.5rem;
                     padding: 0.75rem; font-size: 0.8rem; white-space: pre-wrap; color: #6ee7b7;
                     margin-top: 0.75rem; display: none; max-height: 200px; overflow: auto; }
  </style>
</head>
<body>
<header>
  <h1>Dodoo ERP</h1>
  <span class="badge">v0.1.0</span>
  <nav>
    <a href="/docs">API Docs</a>
    <a href="/redoc">ReDoc</a>
    <a href="/web/health">Health</a>
    <a href="/web/core/info">Core Info</a>
  </nav>
</header>
<main>

  <!-- Stats row -->
  <div class="grid-4">
    <div class="card">
      <h2>Server</h2>
      <div class="status-row" id="srv-status"><div class="dot"></div><span>Checking…</span></div>
      <div class="stat-label" id="srv-db" style="margin-top:.5rem"></div>
    </div>
    <div class="card">
      <h2>Installed Modules</h2>
      <div class="stat" id="stat-modules">—</div>
      <div class="stat-label">addon packages</div>
    </div>
    <div class="card">
      <h2>Registered Models</h2>
      <div class="stat" id="stat-models">—</div>
      <div class="stat-label">ORM models</div>
    </div>
    <div class="card">
      <h2>Users / Groups</h2>
      <div class="stat" id="stat-users">—</div>
      <div class="stat-label">users · groups</div>
    </div>
  </div>

  <div class="grid-2">
    <!-- Modules table -->
    <div class="card">
      <h2>Installed Modules</h2>
      <table>
        <thead><tr><th>Name</th><th>Version</th><th>State</th></tr></thead>
        <tbody id="modules-table"><tr><td colspan="3" style="color:#475569">Loading…</td></tr></tbody>
      </table>
    </div>

    <!-- Registered models -->
    <div class="card">
      <h2>Registered ORM Models</h2>
      <div class="model-grid" id="models-grid"><span style="color:#475569;font-size:.85rem">Loading…</span></div>
    </div>
  </div>

  <div class="grid-2">
    <!-- Login -->
    <div class="card">
      <h2>Authenticate</h2>
      <div class="login-form">
        <input id="login" type="text" placeholder="Login" value="admin">
        <input id="password" type="password" placeholder="Password" value="admin">
        <button class="btn btn-primary" onclick="doLogin()">Sign In</button>
      </div>
      <div id="token-box"></div>
      <pre id="result"></pre>
    </div>

    <!-- JSON-RPC playground -->
    <div class="card">
      <h2>JSON-RPC Playground</h2>
      <div class="rpc-form" style="display:flex;flex-direction:column;gap:.6rem">
        <textarea id="rpc-body" rows="6">{
  "jsonrpc": "2.0",
  "method": "call",
  "id": 1,
  "params": {
    "service": "common",
    "method": "version",
    "args": [], "kwargs": {}
  }
}</textarea>
        <button class="btn btn-primary" onclick="doRpc()">Send Request</button>
      </div>
      <pre id="rpc-result"></pre>
    </div>
  </div>

</main>
<script>
  let _token = '';

  async function loadCoreInfo() {
    try {
      const r = await fetch('/web/core/info');
      const d = await r.json();

      document.getElementById('stat-modules').textContent = d.modules.length;
      document.getElementById('stat-models').textContent = d.models.length;
      document.getElementById('stat-users').textContent = d.users + ' · ' + d.groups;

      const tbody = document.getElementById('modules-table');
      tbody.innerHTML = d.modules.map(m =>
        `<tr><td>${m.name}</td><td>${m.version||'—'}</td>
         <td><span class="tag tag-green">${m.state}</span></td></tr>`
      ).join('') || '<tr><td colspan="3" style="color:#475569">No modules</td></tr>';

      const mgrid = document.getElementById('models-grid');
      mgrid.innerHTML = d.models.map(m =>
        `<span class="model-tag">${m}</span>`
      ).join('');
    } catch(e) {}
  }

  async function checkHealth() {
    try {
      const r = await fetch('/web/health');
      const d = await r.json();
      const ok = d.status === 'ok';
      document.getElementById('srv-status').innerHTML =
        `<div class="dot${ok?'':' red'}"></div><span>${ok ? 'Running' : 'Degraded'}</span>`;
      document.getElementById('srv-db').textContent = 'DB: ' + (d.db||'unknown');
    } catch(e) {
      document.getElementById('srv-status').innerHTML = '<div class="dot red"></div><span>Unreachable</span>';
    }
  }

  async function doLogin() {
    const el = document.getElementById('result');
    const tb = document.getElementById('token-box');
    el.style.display = 'block';
    try {
      const r = await fetch('/web/session/authenticate', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({login: document.getElementById('login').value,
                              password: document.getElementById('password').value})
      });
      const d = await r.json();
      el.textContent = JSON.stringify(d, null, 2);
      if (d.session_token) {
        _token = d.session_token;
        tb.style.display = 'block';
        tb.textContent = 'Session token saved — JSON-RPC calls will use it automatically.';
        loadCoreInfo();
      } else { tb.style.display = 'none'; }
    } catch(e) { el.textContent = 'Error: ' + e.message; }
  }

  async function doRpc() {
    const el = document.getElementById('rpc-result');
    el.style.display = 'block';
    try {
      const body = JSON.parse(document.getElementById('rpc-body').value);
      const headers = {'Content-Type':'application/json'};
      if (_token) headers['X-Session-Token'] = _token;
      const r = await fetch('/jsonrpc', {method:'POST', headers, body: JSON.stringify(body)});
      el.textContent = JSON.stringify(await r.json(), null, 2);
    } catch(e) { el.textContent = 'Error: ' + e.message; }
  }

  checkHealth();
  loadCoreInfo();
  setInterval(() => { checkHealth(); loadCoreInfo(); }, 10000);
</script>
</body>
</html>"""


def create_app(env: Environment) -> FastAPI:
    app = FastAPI(title="Dodoo ERP", version="0.1.0")
    app.state.env = env

    # CORS: localhost only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_origin_regex=r"http://127\.0\.0\.1(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(CorrelationMiddleware)

    # Root → redirect to web UI
    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse(url="/web/client")

    # JSON-RPC endpoint
    app.add_api_route("/jsonrpc", jsonrpc_handler, methods=["POST"])

    # Register module REST routes
    RouteRegistry.get().register_with_app(app)

    # Mount static file directories (e.g., from web addon)
    MountRegistry.get().register_with_app(app)

    @app.on_event("startup")
    async def _startup() -> None:
        _log.info("dodoo.http started")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await env.close()
        _log.info("dodoo.http stopped")

    return app
