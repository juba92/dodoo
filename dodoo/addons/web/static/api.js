/**
 * Thin fetch wrapper. All API communication goes through this module.
 * Token is read from sessionStorage and injected as X-Session-Token header.
 * JSON-RPC error code -32000 → redirect to #/login?reason=expired.
 */

function _token() {
  return sessionStorage.getItem('session_token') ?? '';
}

function _headers(extra = {}) {
  const h = { 'Content-Type': 'application/json', ...extra };
  const tok = _token();
  if (tok) h['X-Session-Token'] = tok;
  return h;
}

async function _json(res) {
  if (res.status === 401) {
    _expireSession();
    throw new Error('Session expired');
  }
  return res.json();
}

function _expireSession() {
  sessionStorage.clear();
  window.location.hash = '#/login?reason=expired';
}

export async function authenticate(login, password) {
  const res = await fetch('/web/session/authenticate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login, password }),
  });
  if (res.status === 401) {
    const data = await res.json();
    throw new Error(data.error ?? 'Authentication failed');
  }
  return res.json();
}

export async function logout() {
  const res = await fetch('/web/session/logout', {
    method: 'POST',
    headers: _headers(),
    body: JSON.stringify({}),
  });
  return _json(res);
}

export async function getInfo() {
  const res = await fetch('/web/core/info', { headers: _headers() });
  return _json(res);
}

let _rpcId = 1;

export async function rpc(model, method, args = [], kwargs = {}) {
  const id = _rpcId++;
  const res = await fetch('/jsonrpc', {
    method: 'POST',
    headers: _headers(),
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'call',
      id,
      params: {
        service: 'object',
        method: 'execute_kw',
        args: [model, method, args],
        kwargs,
      },
    }),
  });
  const data = await _json(res);
  if (data.error) {
    if (data.error.code === -32000) {
      _expireSession();
      throw new Error('Session expired');
    }
    throw new Error(data.error.message ?? JSON.stringify(data.error));
  }
  return data.result;
}
