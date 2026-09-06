import * as api from '/web/static/api.js';
import { loadCatalog, applyDirection, t, currentLang } from '/web/static/i18n.js';

// Bump on any web/account/localization static change. Appended as ?v= to every
// lazily-imported view module so a new build is a new module URL — otherwise the
// browser keeps the first-imported version of a view for the whole tab session
// (hash navigation never reloads the document) and serves stale screens.
const CLIENT_BUILD = '2026-09-06.15';

/** Lazy-import a view module, cache-busted by the current build. */
const _view = path => import(path + '?v=' + CLIENT_BUILD);

// ── Global state ─────────────────────────────────────────────────────────────
export const App = {
  state: {
    token: null,
    uid: null,
    isAdmin: false,
    lang: 'en',
    modules: [],
    models: [],
    fieldCache: {},
  },
  breadcrumb: [],
  t,

  /** Re-resolve the effective language from the server and re-apply it. Call after
   *  login, logout, a system-language change, or a personal-language change. */
  async reloadLanguage() {
    try {
      const info = await api.getInfo();
      App.state.lang = info.lang || 'en';
      App.state.isAdmin = !!info.is_admin;
      App.state.hrGroups = info.hr_groups || [];
      App.state.fleetManager = !!info.fleet_manager;
      await loadCatalog(App.state.lang);
      applyDirection(info.direction);
    } catch { /* keep current catalog */ }
  },

  /** Re-render the header, sidebar and breadcrumb in place so a language/direction
   *  switch is reflected across the chrome without a manual navigation. The active
   *  view keeps its own DOM (callers that changed language re-render it themselves). */
  refreshChrome() {
    const hash = window.location.hash || '#/login';
    if (/^#\/login/.test(hash) || !App.state.token) return;
    const header = document.querySelector('.app-header');
    if (!header) return;
    const appNameEl = header.querySelector('.nav-app-name');
    if (appNameEl) {
      appNameEl.textContent = hash.startsWith('#/accounting') ? t('Accounting')
        : hash.startsWith('#/hr') ? t('Human Resources')
        : hash.startsWith('#/fleet') ? t('Fleet')
        : hash === '#/settings' ? t('Settings')
        : t('Dodoo ERP');
    }
    header.querySelector('.nav-home-btn')?.setAttribute('aria-label', t('Go to home'));
    const setBtn = header.querySelector('#btn-settings');
    if (setBtn) { setBtn.title = t('Settings'); setBtn.setAttribute('aria-label', t('Settings')); }
    const outBtn = header.querySelector('#btn-logout');
    if (outBtn) { outBtn.title = t('Sign out'); outBtn.setAttribute('aria-label', t('Sign out')); }
    // Recompute stored breadcrumb labels in the new language before re-rendering.
    App.breadcrumb = App.breadcrumb.map(b => ({ ...b, label: _labelFromHash(b.hash) }));
    _renderBreadcrumb();
    _renderSidebar(hash);
  },

  navigate(hash) {
    const existing = App.breadcrumb.findIndex(b => b.hash === hash);
    if (existing !== -1) {
      App.breadcrumb = App.breadcrumb.slice(0, existing + 1);
    } else {
      App.breadcrumb.push({ label: _labelFromHash(hash), hash });
    }
    if (window.location.hash === hash) {
      _route(); // same hash — hashchange won't fire, force re-render
    } else {
      window.location.hash = hash;
    }
  },
};

const _ACC_LABELS = {
  'invoices': 'Customer Invoices', 'credit-notes': 'Customer Credit Notes',
  'customer-payments': 'Customer Payments', 'bills': 'Vendor Bills',
  'vendor-credit-notes': 'Vendor Credit Notes', 'vendor-payments': 'Vendor Payments',
  'journal-entries': 'Journal Entries', 'chart-of-accounts': 'Chart of Accounts',
  'journals': 'Journals',
};

const _REPORT_LABELS = {
  'trial-balance': 'Trial Balance', 'general-ledger': 'General Ledger',
  'profit-loss': 'Profit & Loss', 'balance-sheet': 'Balance Sheet',
  'aged-receivable': 'Aged Receivable', 'aged-payable': 'Aged Payable',
};

function _labelFromHash(hash) {
  if (hash === '#/home' || hash === '#/') return t('Home');
  if (hash === '#/login') return t('Login');
  if (hash === '#/settings') return t('Settings');
  let m;
  if ((m = hash.match(/^#\/accounting\/move\/new(\?.*)?$/)))    return t('New Invoice');
  if ((m = hash.match(/^#\/accounting\/move\/(\d+)$/)))         return t('Invoice #{id}', { id: m[1] });
  if ((m = hash.match(/^#\/accounting\/account\/new$/)))        return t('New Account');
  if ((m = hash.match(/^#\/accounting\/account\/(\d+)$/)))      return t('Account') + ' #' + m[1];
  if ((m = hash.match(/^#\/accounting\/reports\/([^/]+)$/)))    return t(_REPORT_LABELS[m[1]] || m[1].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
  if ((m = hash.match(/^#\/accounting\/model\/([^/]+)\/new$/))) return t('New {name}', { name: m[1] });
  if ((m = hash.match(/^#\/accounting\/model\/([^/]+)\/(\d+)$/))) return `${m[1]} #${m[2]}`;
  if ((m = hash.match(/^#\/accounting\/model\/([^/]+)$/)))      return m[1];
  if ((m = hash.match(/^#\/accounting\/([^/]+)$/)))             return _ACC_LABELS[m[1]] ? t(_ACC_LABELS[m[1]]) : m[1].replace(/-/g, ' ');
  if ((m = hash.match(/^#\/module\/(.+)$/)))                    return m[1];
  if (hash === '#/hr/employees')                                return t('Employees');
  if (hash === '#/hr/contracts')                                return t('Contracts');
  if (hash === '#/hr/timeoff')                                  return t('Time Off');
  if (hash === '#/hr/allocations')                              return t('Allocations');
  if ((m = hash.match(/^#\/hr\/timeoff\/new$/)))               return t('New Request');
  if ((m = hash.match(/^#\/hr\/timeoff\/(\d+)$/)))            return t('Request') + ' #' + m[1];
  if (hash === '#/hr/recruitment')                              return t('Recruitment');
  if ((m = hash.match(/^#\/hr\/recruitment\/(\d+)$/)))        return t('Pipeline') + ' #' + m[1];
  if ((m = hash.match(/^#\/hr\/applicant\/new$/)))            return t('New Applicant');
  if ((m = hash.match(/^#\/hr\/applicant\/(\d+)$/)))         return t('Applicant') + ' #' + m[1];
  if (hash === '#/hr/appraisals')                              return t('Appraisals');
  if ((m = hash.match(/^#\/hr\/appraisal\/new$/)))           return t('New Appraisal');
  if ((m = hash.match(/^#\/hr\/appraisal\/(\d+)$/)))        return t('Appraisal') + ' #' + m[1];
  if (hash === '#/hr/referrals')                                return t('My Referrals');
  if (hash === '#/hr/referral/new')                             return t('Refer a Friend');
  if (hash === '#/fleet/vehicles')                              return t('Vehicles');
  if (hash === '#/fleet/alerts')                                return t('Fleet Alerts');
  if ((m = hash.match(/^#\/fleet\/vehicle\/(\d+)$/)))        return t('Vehicle') + ' #' + m[1];
  if ((m = hash.match(/^#\/fleet\/model\/([^/]+)$/)))         return m[1];
  if ((m = hash.match(/^#\/hr\/employee\/new$/)))               return t('New Employee');
  if ((m = hash.match(/^#\/hr\/employee\/(\d+)$/)))             return t('Employee') + ' #' + m[1];
  if ((m = hash.match(/^#\/hr\/model\/([^/]+)\/new$/)))         return t('New {name}', { name: m[1] });
  if ((m = hash.match(/^#\/hr\/model\/([^/]+)\/(\d+)$/)))       return `${m[1]} #${m[2]}`;
  if ((m = hash.match(/^#\/hr\/model\/([^/]+)$/)))              return m[1];
  if ((m = hash.match(/^#\/model\/([^/]+)\/new$/)))             return t('New {name}', { name: m[1] });
  if ((m = hash.match(/^#\/model\/([^/]+)\/(\d+)$/)))           return `#${m[2]}`;
  if ((m = hash.match(/^#\/model\/([^/]+)$/)))                  return m[1];
  return hash.replace(/^#\//, '');
}

let _activeMenuHash = null;

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
  homeBtn.setAttribute('aria-label', t('Go to home'));
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
  appName.textContent = t('Dodoo ERP');
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
  const settingsBtn = document.createElement('button');
  settingsBtn.className = 'o-user-avatar-btn';
  settingsBtn.id = 'btn-settings';
  settingsBtn.title = t('Settings');
  settingsBtn.setAttribute('aria-label', t('Settings'));
  settingsBtn.textContent = '⚙';
  settingsBtn.onclick = () => App.navigate('#/settings');
  userArea.appendChild(settingsBtn);

  const avatarBtn = document.createElement('button');
  avatarBtn.className = 'o-user-avatar-btn';
  avatarBtn.id = 'btn-logout';
  avatarBtn.title = t('Sign out');
  avatarBtn.setAttribute('aria-label', t('Sign out'));
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

function _renderSidebar(hash) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  // Update app name in navbar
  const appNameEl = document.querySelector('.nav-app-name');
  if (appNameEl) {
    appNameEl.textContent = hash.startsWith('#/accounting') ? t('Accounting')
      : hash.startsWith('#/hr') ? t('Human Resources')
      : hash.startsWith('#/fleet') ? t('Fleet')
      : hash === '#/settings' ? t('Settings')
      : t('Dodoo ERP');
  }

  // Settings is a standalone config page — no model navigation.
  if (hash === '#/settings') {
    document.getElementById('app')?.classList.add('home-mode');
    sidebar.innerHTML = '';
    return;
  }

  if (hash.startsWith('#/accounting')) {
    sidebar.innerHTML = '';
    _renderAccountingMenu(sidebar, hash).catch(err => console.error('[dodoo] Accounting menu render failed', err));
    return;
  }

  if (hash.startsWith('#/hr')) {
    // Clear immediately so a slow/failed menu load never leaves the generic
    // model list (or any stale content) showing on an HR screen.
    sidebar.innerHTML = '';
    _renderHrMenu(sidebar, hash).catch(err => console.error('[dodoo] HR menu render failed', err));
    return;
  }

  if (hash.startsWith('#/fleet')) {
    sidebar.innerHTML = '';
    _renderFleetMenu(sidebar, hash).catch(err => console.error('[dodoo] Fleet menu render failed', err));
    return;
  }

  // Generic model browser sidebar — only reachable from #/model/* and #/module/*
  // (accounting, HR and Fleet are handled above). Never shown on an app screen.
  sidebar.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'sidebar-section-title';
  title.textContent = t('Models');
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
  const { ACCOUNTING_MENU } = await _view('/account/static/account-menu.js');
  // Guard: if a new navigation replaced this sidebar, bail out
  if (!document.body.contains(sidebar)) return;
  sidebar.innerHTML = '';

  const allItems = ACCOUNTING_MENU.flatMap(s => s.items);
  const directMatch = allItems.find(({ hash }) => currentHash === hash || currentHash.startsWith(hash + '/'));
  if (directMatch) _activeMenuHash = directMatch.hash;
  // Account form lives under the Chart of Accounts menu entry.
  else if (/^#\/accounting\/account\/(new|\d+)$/.test(currentHash)) _activeMenuHash = '#/accounting/chart-of-accounts';

  ACCOUNTING_MENU.forEach(({ section, items }) => {
    const title = document.createElement('div');
    title.className = 'sidebar-section-title';
    title.textContent = t(section);
    sidebar.appendChild(title);
    const ul = document.createElement('ul');
    ul.className = 'sidebar-list';
    items.forEach(({ label, hash }) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = t(label);
      if (_activeMenuHash === hash) btn.className = 'active';
      btn.onclick = () => {
        // Reset breadcrumb when clicking a top-level menu item
        _activeMenuHash = hash;
        App.breadcrumb = [];
        App.navigate(hash);
      };
      li.appendChild(btn);
      ul.appendChild(li);
    });
    sidebar.appendChild(ul);
  });
}

function _hrHas(requires) {
  if (!requires) return true;
  const g = App.state.hrGroups || [];
  if (requires === 'officer') return g.includes('HR Officer') || g.includes('HR Administrator');
  if (requires === 'administrator') return g.includes('HR Administrator');
  if (requires === 'fleet_manager') return !!App.state.fleetManager;
  return true;
}

async function _renderHrMenu(sidebar, currentHash) {
  const { HR_MENU } = await _view('/hr/static/hr-menu.js');
  if (!document.body.contains(sidebar)) return;
  sidebar.innerHTML = '';
  HR_MENU.forEach(({ section, requires, items }) => {
    if (!_hrHas(requires)) return;
    const visible = items.filter(it => _hrHas(it.requires));
    if (!visible.length) return;
    const title = document.createElement('div');
    title.className = 'sidebar-section-title';
    title.textContent = t(section);
    sidebar.appendChild(title);
    const ul = document.createElement('ul');
    ul.className = 'sidebar-list';
    visible.forEach(({ label, hash }) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = t(label);
      if (currentHash === hash || currentHash.startsWith(hash + '/')) btn.className = 'active';
      btn.onclick = () => { App.breadcrumb = []; App.navigate(hash); };
      li.appendChild(btn);
      ul.appendChild(li);
    });
    sidebar.appendChild(ul);
  });
}

async function _renderFleetMenu(sidebar, currentHash) {
  const { FLEET_MENU } = await _view('/fleet/static/fleet-menu.js');
  if (!document.body.contains(sidebar)) return;
  sidebar.innerHTML = '';
  FLEET_MENU.forEach(({ section, requires, items }) => {
    if (requires === 'fleet_manager' && !App.state.fleetManager) return;
    const title = document.createElement('div');
    title.className = 'sidebar-section-title';
    title.textContent = t(section);
    sidebar.appendChild(title);
    const ul = document.createElement('ul');
    ul.className = 'sidebar-list';
    items.forEach(({ label, hash }) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = t(label);
      if (currentHash === hash || currentHash.startsWith(hash + '/')) btn.className = 'active';
      btn.onclick = () => { App.breadcrumb = []; App.navigate(hash); };
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
  App.state.isAdmin = false;
  sessionStorage.clear();
  App.breadcrumb = [];
  await App.reloadLanguage();  // back to the system default language
  App.navigate('#/login');
}

// ── Router ────────────────────────────────────────────────────────────────────
const _ROUTES = [
  [/^#\/login(\?.*)?$/, () => _view('/web/static/views/login.js')],
  [/^#\/home$/, () => _view('/web/static/views/home.js')],
  [/^#\/settings$/, () => _view('/localization/static/views/settings.js')],
  [/^#\/module\/(.+)$/, () => _view('/web/static/views/home.js')],
  // Accounting-specific routes (must come before generic model routes)
  [/^#\/accounting\/move\/(new|\d+)$/, () => _view('/account/static/views/invoice-form.js')],
  [/^#\/accounting\/chart-of-accounts$/, () => _view('/account/static/views/coa-list.js')],
  [/^#\/accounting\/account\/(new|\d+)$/, () => _view('/account/static/views/account-form.js')],
  [/^#\/accounting\/reports\/([^/]+)$/, () => _view('/account/static/views/report-view.js')],
  [/^#\/accounting\/model\/([^/]+)\/new$/, () => _view('/web/static/views/form.js')],
  [/^#\/accounting\/model\/([^/]+)\/(\d+)$/, () => _view('/web/static/views/form.js')],
  [/^#\/accounting\/model\/([^/]+)$/, () => _view('/web/static/views/list.js')],
  [/^#\/accounting\/([^/]+)$/, () => _view('/account/static/views/invoice-list.js')],
  // Human Resources routes (before the generic model routes)
  [/^#\/hr\/employees$/, () => _view('/hr/static/views/employee-kanban.js')],
  [/^#\/hr\/employee\/(new|\d+)$/, () => _view('/hr/static/views/employee-form.js')],
  [/^#\/hr\/contracts$/, () => _view('/hr/static/views/contract-list.js')],
  [/^#\/hr\/timeoff$/, () => _view('/hr/static/views/timeoff-calendar.js')],
  [/^#\/hr\/timeoff\/(new|\d+)$/, () => _view('/hr/static/views/timeoff-form.js')],
  [/^#\/hr\/recruitment$/, () => _view('/hr/static/views/recruitment-kanban.js')],
  [/^#\/hr\/recruitment\/(\d+)$/, () => _view('/hr/static/views/recruitment-kanban.js')],
  [/^#\/hr\/applicant\/(new|\d+)$/, () => _view('/hr/static/views/applicant-form.js')],
  [/^#\/hr\/appraisal\/(new|\d+)$/, () => _view('/hr/static/views/appraisal-form.js')],
  [/^#\/hr\/referrals$/, () => _view('/hr/static/views/referral-form.js')],
  [/^#\/hr\/referral\/new$/, () => _view('/hr/static/views/referral-form.js')],
  [/^#\/hr\/model\/([^/]+)\/new$/, () => _view('/web/static/views/form.js')],
  [/^#\/hr\/model\/([^/]+)\/(\d+)$/, () => _view('/web/static/views/form.js')],
  [/^#\/hr\/model\/([^/]+)$/, () => _view('/web/static/views/list.js')],
  // Fleet routes
  [/^#\/fleet\/vehicles$/, () => _view('/fleet/static/views/vehicle-kanban.js')],
  [/^#\/fleet\/vehicle\/(\d+)$/, () => _view('/fleet/static/views/vehicle-form.js')],
  [/^#\/fleet\/alerts$/, () => _view('/fleet/static/views/fleet-alerts.js')],
  [/^#\/fleet\/model\/([^/]+)\/new$/, () => _view('/web/static/views/form.js')],
  [/^#\/fleet\/model\/([^/]+)\/(\d+)$/, () => _view('/web/static/views/form.js')],
  [/^#\/fleet\/model\/([^/]+)$/, () => _view('/web/static/views/list.js')],
  // Generic model routes
  [/^#\/model\/([^/]+)\/new$/, () => _view('/web/static/views/form.js')],
  [/^#\/model\/([^/]+)\/(\d+)$/, () => _view('/web/static/views/form.js')],
  [/^#\/model\/([^/]+)$/, () => _view('/web/static/views/list.js')],
];

function _parseHash(hash) {
  const base = hash.split('?')[0]; // strip query string embedded in hash
  for (const [pattern, loader] of _ROUTES) {
    const m = base.match(pattern);
    if (m) return { loader, groups: m.slice(1) };
  }
  return null;
}

function _paramsFromHash(hash) {
  const base = hash.split('?')[0];
  // Extract query params from hash (e.g. #/accounting/move/new?type=out_invoice)
  const qs = hash.includes('?') ? new URLSearchParams(hash.split('?')[1]) : new URLSearchParams();
  let m;
  if ((m = base.match(/^#\/accounting\/move\/new$/)))                  return { id: 'new', moveType: qs.get('type') || 'out_invoice', editId: qs.get('edit') ? parseInt(qs.get('edit'), 10) : null };
  if ((m = base.match(/^#\/accounting\/move\/(\d+)$/)))                return { id: parseInt(m[1], 10) };
  if ((m = base.match(/^#\/accounting\/account\/new$/)))               return { id: 'new' };
  if ((m = base.match(/^#\/accounting\/account\/(\d+)$/)))             return { id: parseInt(m[1], 10) };
  if ((m = base.match(/^#\/accounting\/reports\/([^/]+)$/)))           return { report: m[1] };
  if ((m = base.match(/^#\/accounting\/model\/([^/]+)\/new$/)))        return { model: m[1], id: 'new' };
  if ((m = base.match(/^#\/accounting\/model\/([^/]+)\/(\d+)$/)))      return { model: m[1], id: parseInt(m[2], 10) };
  if ((m = base.match(/^#\/accounting\/model\/([^/]+)$/)))             return { model: m[1] };
  if ((m = base.match(/^#\/accounting\/([^/]+)$/)))                    return { route: m[1] };
  if ((m = base.match(/^#\/module\/(.+)$/)))                           return { mode: 'module', name: m[1] };
  if ((m = base.match(/^#\/hr\/employee\/(new|\d+)$/)))                return { id: m[1] === 'new' ? 'new' : parseInt(m[1], 10) };
  if ((m = base.match(/^#\/hr\/timeoff\/(new|\d+)$/)))                 return { id: m[1] === 'new' ? 'new' : parseInt(m[1], 10) };
  if ((m = base.match(/^#\/hr\/recruitment\/(\d+)$/)))               return { jobId: parseInt(m[1], 10) };
  if ((m = base.match(/^#\/hr\/applicant\/(new|\d+)$/)))              return { id: m[1] === 'new' ? 'new' : parseInt(m[1], 10), job: qs.get('job') };
  if ((m = base.match(/^#\/hr\/appraisal\/(new|\d+)$/)))              return { id: m[1] === 'new' ? 'new' : parseInt(m[1], 10) };
  if (base === '#/hr/referrals')                                       return { mode: 'list' };
  if (base === '#/hr/referral/new')                                    return { mode: 'new' };
  if ((m = base.match(/^#\/fleet\/vehicle\/(\d+)$/)))                return { id: parseInt(m[1], 10) };
  if ((m = base.match(/^#\/fleet\/model\/([^/]+)\/new$/)))          return { model: m[1], id: 'new' };
  if ((m = base.match(/^#\/fleet\/model\/([^/]+)\/(\d+)$/)))       return { model: m[1], id: parseInt(m[2], 10) };
  if ((m = base.match(/^#\/fleet\/model\/([^/]+)$/)))               return { model: m[1] };
  if ((m = base.match(/^#\/hr\/model\/([^/]+)\/new$/)))               return { model: m[1], id: 'new' };
  if ((m = base.match(/^#\/hr\/model\/([^/]+)\/(\d+)$/)))             return { model: m[1], id: parseInt(m[2], 10) };
  if ((m = base.match(/^#\/hr\/model\/([^/]+)$/)))                    return { model: m[1] };
  if ((m = base.match(/^#\/model\/([^/]+)\/new$/)))                    return { model: m[1], id: 'new' };
  if ((m = base.match(/^#\/model\/([^/]+)\/(\d+)$/)))                  return { model: m[1], id: parseInt(m[2], 10) };
  if ((m = base.match(/^#\/model\/([^/]+)$/)))                         return { model: m[1] };
  return {};
}

async function _route() {
  const hash = window.location.hash || '#/login';
  const isLogin = /^#\/login/.test(hash);

  // Guard: redirect to login if no session
  if (!App.state.token && !isLogin) {
    _buildLoginShell();
    const { render } = await _view('/web/static/views/login.js');
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
  _renderSidebar(hash);

  const { render } = await parsed.loader();
  render(document.getElementById('main'), _paramsFromHash(hash));
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  console.info('[dodoo] web client build', CLIENT_BUILD);
  // Restore session from storage
  const tok = sessionStorage.getItem('session_token');
  const uid = sessionStorage.getItem('session_uid');
  if (tok) {
    App.state.token = tok;
    App.state.uid = uid ? parseInt(uid, 10) : null;
  }

  // Resolve the effective language (works logged-out too) and load its catalog before
  // the first render so every screen — including login — starts in the right language.
  try {
    const info = await api.getInfo();
    App.state.lang = info.lang || 'en';
    App.state.isAdmin = !!info.is_admin;
    App.state.modules = info.modules ?? [];
    App.state.models = info.models ?? [];
    App.state.hrGroups = info.hr_groups ?? [];
    App.state.fleetManager = !!info.fleet_manager;
    await loadCatalog(App.state.lang);
    applyDirection(info.direction);
  } catch {
    await loadCatalog('en');
    applyDirection('ltr');
  }

  // Seed breadcrumb from current hash
  const hash = window.location.hash || '#/login';
  if (hash !== '#/login' && App.state.token) {
    App.breadcrumb = [{ label: t('Home'), hash: '#/home' }];
    if (hash !== '#/home') {
      App.breadcrumb.push({ label: _labelFromHash(hash), hash });
    }
  }

  window.addEventListener('hashchange', _route);
  await _route();
});
