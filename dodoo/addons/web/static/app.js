import * as api from '/web/static/api.js';

// ── Global state ─────────────────────────────────────────────────────────────
export const App = {
  state: {
    token: null,
    uid: null,
    modules: [],
    models: [],
    fieldCache: {},
  },
  breadcrumb: [],

  navigate(hash) {
    const existing = App.breadcrumb.findIndex(b => b.hash === hash);
    if (existing !== -1) {
      App.breadcrumb = App.breadcrumb.slice(0, existing + 1);
    } else {
      App.breadcrumb.push({ label: _labelFromHash(hash), hash });
    }
    window.location.hash = hash;
  },
};

const _ACC_LABELS = {
  'invoices': 'Customer Invoices', 'credit-notes': 'Customer Credit Notes',
  'customer-payments': 'Customer Payments', 'bills': 'Vendor Bills',
  'vendor-credit-notes': 'Vendor Credit Notes', 'vendor-payments': 'Vendor Payments',
  'journal-entries': 'Journal Entries', 'chart-of-accounts': 'Chart of Accounts',
  'journals': 'Journals',
};

function _labelFromHash(hash) {
  if (hash === '#/home' || hash === '#/') return 'Home';
  if (hash === '#/login') return 'Login';
  let m;
  if ((m = hash.match(/^#\/accounting\/move\/new$/))) return 'New Invoice';
  if ((m = hash.match(/^#\/accounting\/move\/(\d+)$/))) return `Invoice #${m[1]}`;
  if ((m = hash.match(/^#\/accounting\/reports\/([^/]+)$/))) return m[1].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  if ((m = hash.match(/^#\/accounting\/([^/]+)$/))) return _ACC_LABELS[m[1]] ?? m[1].replace(/-/g, ' ');
  if ((m = hash.match(/^#\/module\/(.+)$/))) return m[1];
  if ((m = hash.match(/^#\/model\/([^/]+)\/new$/))) return `New ${m[1]}`;
  if ((m = hash.match(/^#\/model\/([^/]+)\/(\d+)$/))) return `#${m[2]}`;
  if ((m = hash.match(/^#\/model\/([^/]+)$/))) return m[1];
  return hash.replace(/^#\//, '');
}

// ── Layout shell ─────────────────────────────────────────────────────────────
function _buildShell() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  app.classList.remove('home-mode');

  // Navbar — white bar matching Odoo's top navigation
  const header = document.createElement('header');
  header.className = 'app-header';
  header.setAttribute('role', 'banner');

  // Apps grid icon → navigate home
  const homeBtn = document.createElement('button');
  homeBtn.className = 'nav-home-btn';
  homeBtn.setAttribute('aria-label', 'Go to home');
  homeBtn.onclick = () => App.navigate('#/home');
  homeBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <rect x="1" y="1" width="7" height="7" rx="1.5"/>
    <rect x="12" y="1" width="7" height="7" rx="1.5"/>
    <rect x="1" y="12" width="7" height="7" rx="1.5"/>
    <rect x="12" y="12" width="7" height="7" rx="1.5"/>
  </svg>`;
  header.appendChild(homeBtn);

  // App name
  const appName = document.createElement('span');
  appName.className = 'nav-app-name';
  appName.textContent = 'Dodoo ERP';
  header.appendChild(appName);

  // Breadcrumb
  const bcNav = document.createElement('nav');
  bcNav.setAttribute('aria-label', 'breadcrumb');
  const bcOl = document.createElement('ol');
  bcOl.className = 'breadcrumb-strip';
  bcOl.id = 'breadcrumb';
  bcNav.appendChild(bcOl);
  header.appendChild(bcNav);

  // User avatar (click to sign out)
  const userArea = document.createElement('div');
  userArea.className = 'user-area';
  const avatarBtn = document.createElement('button');
  avatarBtn.className = 'o-user-avatar-btn';
  avatarBtn.id = 'btn-logout';
  avatarBtn.title = 'Sign out';
  avatarBtn.setAttribute('aria-label', 'Sign out');
  avatarBtn.textContent = 'A';  // generic initial; updated after login if name known
  avatarBtn.onclick = _handleLogout;
  userArea.appendChild(avatarBtn);
  header.appendChild(userArea);

  // Sidebar
  const sidebar = document.createElement('nav');
  sidebar.className = 'app-sidebar';
  sidebar.setAttribute('aria-label', 'model navigation');
  sidebar.id = 'sidebar';

  // Outer main wrapper (flex column: control-panel + content)
  const outerMain = document.createElement('main');
  outerMain.className = 'app-main';
  outerMain.setAttribute('tabindex', '-1');

  // Control panel: action buttons and search (populated by each view)
  const cp = document.createElement('div');
  cp.className = 'o-control-panel';
  cp.id = 'control-panel';
  outerMain.appendChild(cp);

  // Scrollable content area (views render here)
  const content = document.createElement('div');
  content.className = 'o-content';
  content.id = 'main';
  outerMain.appendChild(content);

  app.appendChild(header);
  app.appendChild(sidebar);
  app.appendChild(outerMain);
}

function _buildLoginShell() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  const page = document.createElement('div');
  page.className = 'login-page';
  page.id = 'main';
  app.appendChild(page);
}

function _renderBreadcrumb() {
  const ol = document.getElementById('breadcrumb');
  if (!ol) return;
  ol.innerHTML = '';
  App.breadcrumb.forEach((entry, i) => {
    if (i > 0) {
      const sep = document.createElement('li');
      sep.className = 'bc-sep';
      sep.setAttribute('aria-hidden', 'true');
      sep.textContent = '›';
      ol.appendChild(sep);
    }
    const li = document.createElement('li');
    if (i === App.breadcrumb.length - 1) {
      const span = document.createElement('span');
      span.setAttribute('aria-current', 'page');
      span.textContent = entry.label;
      li.appendChild(span);
    } else {
      const btn = document.createElement('button');
      btn.textContent = entry.label;
      btn.onclick = () => App.navigate(entry.hash);
      li.appendChild(btn);
    }
    ol.appendChild(li);
  });
}

function _renderSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const hash = window.location.hash || '';

  // Update app name in navbar
  const appNameEl = document.querySelector('.nav-app-name');
  if (appNameEl) {
    appNameEl.textContent = hash.startsWith('#/accounting') ? 'Accounting' : 'Dodoo ERP';
  }

  if (hash.startsWith('#/accounting')) {
    _renderAccountingMenu(sidebar, hash).catch(() => {});
    return;
  }

  sidebar.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'sidebar-section-title';
  title.textContent = 'Models';
  sidebar.appendChild(title);

  const ul = document.createElement('ul');
  ul.className = 'sidebar-list';
  App.state.models.forEach(name => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = name;
    btn.onclick = () => App.navigate(`#/model/${name}`);
    li.appendChild(btn);
    ul.appendChild(li);
  });
  sidebar.appendChild(ul);
}

async function _renderAccountingMenu(sidebar, currentHash) {
  const { ACCOUNTING_MENU } = await import('/account/static/account-menu.js');
  sidebar.innerHTML = '';
  ACCOUNTING_MENU.forEach(({ section, items }) => {
    const title = document.createElement('div');
    title.className = 'sidebar-section-title';
    title.textContent = section;
    sidebar.appendChild(title);
    const ul = document.createElement('ul');
    ul.className = 'sidebar-list';
    items.forEach(({ label, hash }) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = label;
      if (currentHash === hash || currentHash.startsWith(hash + '/')) btn.className = 'active';
      btn.onclick = () => App.navigate(hash);
      li.appendChild(btn);
      ul.appendChild(li);
    });
    sidebar.appendChild(ul);
  });
}

async function _handleLogout() {
  try { await api.logout(); } catch { /* ignore errors on logout */ }
  App.state.token = null;
  App.state.uid = null;
  sessionStorage.clear();
  App.breadcrumb = [];
  App.navigate('#/login');
}

// ── Router ────────────────────────────────────────────────────────────────────
const _ROUTES = [
  [/^#\/login(\?.*)?$/, () => import('/web/static/views/login.js')],
  [/^#\/home$/, () => import('/web/static/views/home.js')],
  [/^#\/module\/(.+)$/, () => import('/web/static/views/home.js')],
  // Accounting-specific routes (must come before generic model routes)
  [/^#\/accounting\/move\/(new|\d+)$/, () => import('/account/static/views/invoice-form.js')],
  [/^#\/accounting\/reports\/([^/]+)$/, () => import('/account/static/views/report-view.js')],
  [/^#\/accounting\/([^/]+)$/, () => import('/account/static/views/invoice-list.js')],
  // Generic model routes
  [/^#\/model\/([^/]+)\/new$/, () => import('/web/static/views/form.js')],
  [/^#\/model\/([^/]+)\/(\d+)$/, () => import('/web/static/views/form.js')],
  [/^#\/model\/([^/]+)$/, () => import('/web/static/views/list.js')],
];

function _parseHash(hash) {
  for (const [pattern, loader] of _ROUTES) {
    const m = hash.match(pattern);
    if (m) return { loader, groups: m.slice(1) };
  }
  return null;
}

function _paramsFromHash(hash) {
  let m;
  if ((m = hash.match(/^#\/accounting\/move\/new$/)))    return { id: 'new' };
  if ((m = hash.match(/^#\/accounting\/move\/(\d+)$/)))  return { id: parseInt(m[1], 10) };
  if ((m = hash.match(/^#\/accounting\/reports\/([^/]+)$/))) return { report: m[1] };
  if ((m = hash.match(/^#\/accounting\/([^/]+)$/)))      return { route: m[1] };
  if ((m = hash.match(/^#\/module\/(.+)$/)))  return { mode: 'module', name: m[1] };
  if ((m = hash.match(/^#\/model\/([^/]+)\/new$/)))      return { model: m[1], id: 'new' };
  if ((m = hash.match(/^#\/model\/([^/]+)\/(\d+)$/)))    return { model: m[1], id: parseInt(m[2], 10) };
  if ((m = hash.match(/^#\/model\/([^/]+)$/)))           return { model: m[1] };
  return {};
}

async function _route() {
  const hash = window.location.hash || '#/login';
  const isLogin = /^#\/login/.test(hash);

  // Guard: redirect to login if no session
  if (!App.state.token && !isLogin) {
    _buildLoginShell();
    const { render } = await import('/web/static/views/login.js');
    render(document.getElementById('main'), {});
    return;
  }

  const parsed = _parseHash(hash);
  if (!parsed) {
    window.location.hash = App.state.token ? '#/home' : '#/login';
    return;
  }

  if (isLogin) {
    _buildLoginShell();
    const { render } = await parsed.loader();
    render(document.getElementById('main'), _paramsFromHash(hash));
    return;
  }

  _buildShell();
  _renderBreadcrumb();
  _renderSidebar();

  const { render } = await parsed.loader();
  render(document.getElementById('main'), _paramsFromHash(hash));
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Restore session from storage
  const tok = sessionStorage.getItem('session_token');
  const uid = sessionStorage.getItem('session_uid');
  if (tok) {
    App.state.token = tok;
    App.state.uid = uid ? parseInt(uid, 10) : null;
  }

  // Pre-fetch model list for sidebar (non-blocking)
  if (App.state.token) {
    try {
      const info = await api.getInfo();
      App.state.modules = info.modules ?? [];
      App.state.models = info.models ?? [];
    } catch { /* continue without sidebar data */ }
  }

  // Seed breadcrumb from current hash
  const hash = window.location.hash || '#/login';
  if (hash !== '#/login' && App.state.token) {
    App.breadcrumb = [{ label: 'Home', hash: '#/home' }];
    if (hash !== '#/home') {
      App.breadcrumb.push({ label: _labelFromHash(hash), hash });
    }
  }

  window.addEventListener('hashchange', _route);
  await _route();
});
