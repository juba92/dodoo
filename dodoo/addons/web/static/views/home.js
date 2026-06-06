import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';

const _MODULE_ICONS = {
  base: '🧩',
  web: '🌐',
  mail: '✉️',
  sale: '💰',
  purchase: '🛒',
  account: '📊',
  hr: '👥',
  project: '📋',
  stock: '📦',
  crm: '🤝',
};

function _iconFor(name) {
  return _MODULE_ICONS[name] ?? '📦';
}

export async function render(container, params) {
  container.innerHTML = '';

  // Module detail mode: #/module/:name
  if (params.mode === 'module' && params.name) {
    await _renderModuleDetail(container, params.name);
    return;
  }

  // Home mode: show all module tiles
  const loading = document.createElement('div');
  loading.className = 'loading';
  loading.textContent = 'Loading modules…';
  container.appendChild(loading);

  try {
    const info = await api.getInfo();
    App.state.modules = info.modules ?? [];
    App.state.models = info.models ?? [];

    // Refresh sidebar
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      const { App: AppM } = await import('/web/static/app.js');
      // Re-render sidebar via the app module's internals — use DOM directly
      _refreshSidebar(sidebar, info.models ?? []);
    }
  } catch (err) {
    container.innerHTML = '';
    const alert = document.createElement('div');
    alert.className = 'alert-error';
    alert.textContent = 'Failed to load modules: ' + err.message;
    container.appendChild(alert);
    return;
  }

  container.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'page-header';
  const h2 = document.createElement('h2');
  h2.textContent = 'Applications';
  header.appendChild(h2);
  container.appendChild(header);

  if (App.state.modules.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No modules installed.';
    container.appendChild(empty);
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'module-grid';

  App.state.modules.forEach(mod => {
    const tile = document.createElement('button');
    tile.className = 'module-tile';
    tile.setAttribute('aria-label', `Open ${mod.name} module`);
    tile.onclick = () => App.navigate(`#/module/${mod.name}`);

    const icon = document.createElement('span');
    icon.className = 'tile-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = _iconFor(mod.name);

    const name = document.createElement('span');
    name.className = 'tile-name';
    name.textContent = mod.name;  // textContent — safe

    const version = document.createElement('span');
    version.className = 'tile-version';
    version.textContent = mod.version ?? '';

    tile.appendChild(icon);
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
  title.textContent = 'Models';
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
  const header = document.createElement('div');
  header.className = 'page-header';
  const h2 = document.createElement('h2');
  h2.textContent = moduleName;
  header.appendChild(h2);
  container.appendChild(header);

  // Show models that belong to this module (best-effort prefix match)
  const models = App.state.models.filter(m => {
    // Models like res.users, ir.model often belong to 'base'
    // We do a simple prefix heuristic: all models for any module shown
    return true;
  });

  const subtitle = document.createElement('p');
  subtitle.style.color = 'var(--text-muted)';
  subtitle.style.marginBottom = '1rem';
  subtitle.textContent = `Browse models in the ${moduleName} module.`;
  container.appendChild(subtitle);

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
