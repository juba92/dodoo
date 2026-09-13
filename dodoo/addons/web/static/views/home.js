import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const _MODULE_ICONS = {
  base:     '🧩',
  web:      '🌐',
  mail:     '✉️',
  sale:     '💰',
  purchase: '🛒',
  account:  '📊',
  hr:       '👥',
  fleet:    '🚗',
  project:  '📋',
  stock:    '📦',
  crm:      '🤝',
};

const _MODULE_DISPLAY_NAMES = {
  account:  'Accounting',
  base:     'Base',
  web:      'Web Client',
  sale:     'Sales',
  purchase: 'Purchase',
  hr:       'Employees',
  fleet:    'Fleet',
  project:  'Project',
  stock:    'Inventory',
  crm:      'CRM',
};

// App tiles that open their own dedicated screen instead of the generic model browser.
const _MODULE_HOME_ROUTE = {
  account: '#/accounting/invoices',
  hr:      '#/hr/employees',
  fleet:   '#/fleet/vehicles',
  stock:   '#/inventory/model/product.template',
};

// Odoo-style per-module colors (mirrors Odoo's app tile palette)
const _MODULE_COLORS = {
  base:     '#875A7B',
  web:      '#5B9BD5',
  mail:     '#E94F37',
  sale:     '#00A09D',
  purchase: '#F07B40',
  account:  '#7C5295',
  hr:       '#44B3A2',
  fleet:    '#017E84',
  project:  '#0083A9',
  stock:    '#B64DA0',
  crm:      '#D15E49',
};

const _COLOR_CYCLE = [
  '#875A7B','#E94F37','#00A09D','#F07B40','#5B9BD5',
  '#7C5295','#44B3A2','#0083A9','#B64DA0','#D15E49',
  '#6B9E26','#C19D00',
];

function _iconFor(name) {
  return _MODULE_ICONS[name] ?? '📦';
}

function _colorFor(name) {
  if (_MODULE_COLORS[name]) return _MODULE_COLORS[name];
  // Deterministic color from module name hash
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0x7fffffff;
  return _COLOR_CYCLE[h % _COLOR_CYCLE.length];
}

export async function render(container, params) {
  container.innerHTML = '';

  // Module detail mode: #/module/:name (sidebar is visible, no home-mode)
  if (params.mode === 'module' && params.name) {
    document.getElementById('app')?.classList.remove('home-mode');
    const cp = document.getElementById('control-panel');
    if (cp) cp.innerHTML = '';
    await _renderModuleDetail(container, params.name);
    return;
  }

  // Home screen — full width like Odoo's app switcher (no sidebar)
  document.getElementById('app')?.classList.add('home-mode');

  const loading = document.createElement('div');
  loading.className = 'loading';
  loading.textContent = t('Loading modules…');
  container.appendChild(loading);

  try {
    const info = await api.getInfo();
    App.state.modules = info.modules ?? [];
    App.state.models = info.models ?? [];

    // Refresh sidebar — ONLY if we are still on the home screen. getInfo() is
    // async; by the time it resolves the user may have navigated to an app
    // screen (#/hr, #/fleet, #/accounting, …) whose own sidebar renderer has
    // already run. Repainting the raw model list here would clobber it.
    const sidebar = document.getElementById('sidebar');
    const h = window.location.hash;
    if (sidebar && (h === '' || h === '#/' || h === '#/home')) {
      _refreshSidebar(sidebar, info.models ?? []);
    }
  } catch (err) {
    container.innerHTML = '';
    const alert = document.createElement('div');
    alert.className = 'alert-error';
    alert.textContent = t('Failed to load modules') + ': ' + err.message;
    container.appendChild(alert);
    return;
  }

  container.innerHTML = '';

  if (App.state.modules.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = t('No modules installed.');
    container.appendChild(empty);
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'module-grid';

  App.state.modules.forEach(mod => {
    const tile = document.createElement('button');
    tile.className = 'module-tile';
    const displayName = _MODULE_DISPLAY_NAMES[mod.name] ? t(_MODULE_DISPLAY_NAMES[mod.name]) : mod.name;
    tile.setAttribute('aria-label', `Open ${displayName} module`);
    tile.onclick = () => App.navigate(`#/module/${mod.name}`);

    // Colored icon square (Odoo-style)
    const iconWrap = document.createElement('div');
    iconWrap.className = 'tile-icon';
    iconWrap.style.setProperty('--tile-bg', _colorFor(mod.name));
    iconWrap.setAttribute('aria-hidden', 'true');
    iconWrap.textContent = _iconFor(mod.name);

    const name = document.createElement('span');
    name.className = 'tile-name';
    name.textContent = displayName;

    const version = document.createElement('span');
    version.className = 'tile-version';
    version.textContent = mod.version ?? '';

    tile.appendChild(iconWrap);
    tile.appendChild(name);
    tile.appendChild(version);
    grid.appendChild(tile);
  });

  container.appendChild(grid);
}

function _refreshSidebar(sidebar, models) {
  sidebar.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'sidebar-section-title';
  title.textContent = t('Models');
  sidebar.appendChild(title);
  const ul = document.createElement('ul');
  ul.className = 'sidebar-list';
  models.forEach(name => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = name;
    btn.onclick = () => App.navigate(`#/model/${name}`);
    li.appendChild(btn);
    ul.appendChild(li);
  });
  sidebar.appendChild(ul);
}

async function _renderModuleDetail(container, moduleName) {
  // Modules with a dedicated app screen redirect straight to it.
  if (_MODULE_HOME_ROUTE[moduleName]) {
    App.navigate(_MODULE_HOME_ROUTE[moduleName]);
    return;
  }

  const header = document.createElement('div');
  header.className = 'page-header';
  const h2 = document.createElement('h2');
  h2.textContent = moduleName;
  header.appendChild(h2);
  container.appendChild(header);

  // Show models that belong to this module: a model's own dotted first segment must equal
  // the module's technical name (e.g. `stock.warehouse` belongs to `stock`). This is a
  // fallback screen for a module with no `_MODULE_HOME_ROUTE` entry — reaching it at all
  // for an `application: true` module usually means that entry (and the matching
  // `_MODULE_ICONS`/`_MODULE_DISPLAY_NAMES`/`_MODULE_COLORS` ones) was forgotten; see
  // docs/adr/035-new-application-module-checklist.md.
  const prefix = moduleName + '.';
  const models = App.state.models.filter(m => m === moduleName || m.startsWith(prefix));

  const subtitle = document.createElement('p');
  subtitle.style.color = 'var(--text-muted)';
  subtitle.style.marginBottom = '1rem';
  subtitle.textContent = t('Browse models in the {module} module.', { module: moduleName });
  container.appendChild(subtitle);

  if (models.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = t(
      'No models are registered directly under "{module}" — this app may be missing its dedicated home screen wiring.',
      { module: moduleName }
    );
    container.appendChild(empty);
    return;
  }

  const grid = document.createElement('div');
  grid.style.display = 'grid';
  grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(200px, 1fr))';
  grid.style.gap = '.75rem';

  models.forEach(name => {
    const card = document.createElement('button');
    card.className = 'module-tile';
    card.style.padding = '1rem';
    card.setAttribute('aria-label', `Browse ${name} records`);
    card.onclick = () => App.navigate(`#/model/${name}`);
    const n = document.createElement('span');
    n.className = 'tile-name';
    n.style.fontFamily = 'var(--font-mono)';
    n.textContent = name;
    card.appendChild(n);
    grid.appendChild(card);
  });

  container.appendChild(grid);
}
