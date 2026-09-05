import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatDate, formatNumber } from '/web/static/i18n.js';

const _LIST_FIELD_TYPES = new Set(['char', 'text', 'integer', 'float', 'boolean', 'date', 'datetime']);

// Select at most N listable fields for columns
function _pickColumns(fields, max = 6) {
  // Prioritise name-like and short fields
  const priority = ['name', 'login', 'email', 'code', 'reference', 'state'];
  const picked = [];
  for (const p of priority) {
    if (fields[p] && _LIST_FIELD_TYPES.has(fields[p].type)) picked.push(p);
    if (picked.length >= max) break;
  }
  for (const [k, v] of Object.entries(fields)) {
    if (picked.length >= max) break;
    if (!picked.includes(k) && _LIST_FIELD_TYPES.has(v.type) && k !== 'id') {
      picked.push(k);
    }
  }
  return picked;
}

function _cellText(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return String(value[1] ?? value[0] ?? '');
  return String(value);
}

// Simple debounce
function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export async function render(container, params) {
  const model = params.model;
  if (!model) {
    container.textContent = t('No model specified.');
    return;
  }

  container.innerHTML = '';

  // Fetch field metadata (cached)
  let fields = App.state.fieldCache[model];
  if (!fields) {
    try {
      fields = await api.rpc(model, 'fields_get', [], {
        attributes: ['string', 'type', 'required', 'readonly', 'relation'],
      });
      App.state.fieldCache[model] = fields;
    } catch (err) {
      const alert = document.createElement('div');
      alert.className = 'alert-error';
      alert.textContent = 'Failed to load field metadata: ' + err.message;
      container.appendChild(alert);
      return;
    }
  }

  const columns = _pickColumns(fields);

  // ── State ──────────────────────────────────────────────────────────────────
  let offset = 0;
  let searchTerm = '';
  const LIMIT = 50;

  // ── Control panel: New button + search ─────────────────────────────────────
  const cp = document.getElementById('control-panel');
  const searchInput = document.createElement('input');
  searchInput.type = 'search';
  searchInput.className = 'search-input';
  searchInput.placeholder = t('Search…');
  searchInput.setAttribute('aria-label', `Search ${model} records`);

  if (cp) {
    cp.innerHTML = '';

    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.setAttribute('data-action', 'new');
    newBtn.textContent = t('Create');
    newBtn.onclick = () => App.navigate(`#/model/${model}/new`);
    cp.appendChild(newBtn);

    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);

    cp.appendChild(searchInput);
  }

  // Table wrapper
  const tableWrapper = document.createElement('div');
  tableWrapper.style.overflowX = 'auto';
  container.appendChild(tableWrapper);

  const table = document.createElement('table');
  table.className = 'data-table';

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = fields[col]?.string ?? col;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  tableWrapper.appendChild(table);

  // Pagination row
  const pagination = document.createElement('div');
  pagination.className = 'pagination';
  container.appendChild(pagination);

  // ── Data fetching ───────────────────────────────────────────────────────────
  async function fetchAndRender() {
    tbody.innerHTML = '';
    pagination.innerHTML = '';

    const loadingRow = document.createElement('tr');
    const loadingTd = document.createElement('td');
    loadingTd.colSpan = columns.length;
    loadingTd.textContent = t('Loading…');
    loadingTd.style.textAlign = 'center';
    loadingTd.style.color = 'var(--text-muted)';
    loadingRow.appendChild(loadingTd);
    tbody.appendChild(loadingRow);

    let records;
    try {
      const domain = searchTerm
        ? [['|', ...columns.flatMap(c =>
            fields[c]?.type === 'char' || fields[c]?.type === 'text'
              ? [[c, 'ilike', searchTerm]]
              : []
          )]]
        : [[]];
      // Flatten domain: search_read expects [[]] for no filter or domain tuples
      const finalDomain = searchTerm
        ? columns
            .filter(c => fields[c]?.type === 'char' || fields[c]?.type === 'text')
            .map(c => [c, 'ilike', searchTerm])
        : [];

      records = await api.rpc(model, 'search_read', [finalDomain], {
        fields: ['id', ...columns],
        limit: LIMIT,
        offset,
      });
    } catch (err) {
      tbody.innerHTML = '';
      const errRow = document.createElement('tr');
      const errTd = document.createElement('td');
      errTd.colSpan = columns.length;
      errTd.className = 'alert-error';
      errTd.textContent = 'Error: ' + err.message;
      errRow.appendChild(errTd);
      tbody.appendChild(errRow);
      return;
    }

    tbody.innerHTML = '';

    if (records.length === 0) {
      const emptyRow = document.createElement('tr');
      const emptyTd = document.createElement('td');
      emptyTd.colSpan = columns.length;
      emptyTd.className = 'empty-state';
      emptyTd.textContent = t('No records');
      emptyRow.appendChild(emptyTd);
      tbody.appendChild(emptyRow);
    } else {
      records.forEach(rec => {
        const tr = document.createElement('tr');
        tr.onclick = () => App.navigate(`#/model/${model}/${rec.id}`);
        columns.forEach(col => {
          const td = document.createElement('td');
          td.textContent = _cellText(rec[col]);  // always textContent
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    // Pagination
    const infoSpan = document.createElement('span');
    infoSpan.style.flex = '1';
    infoSpan.textContent = `${offset + 1}–${offset + records.length}`;
    pagination.appendChild(infoSpan);

    if (offset > 0) {
      const prevBtn = document.createElement('button');
      prevBtn.className = 'btn btn-secondary';
      prevBtn.textContent = '← ' + t('Prev');
      prevBtn.onclick = () => { offset = Math.max(0, offset - LIMIT); fetchAndRender(); };
      pagination.appendChild(prevBtn);
    }
    if (records.length === LIMIT) {
      const nextBtn = document.createElement('button');
      nextBtn.className = 'btn btn-secondary';
      nextBtn.textContent = t('Next') + ' →';
      nextBtn.onclick = () => { offset += LIMIT; fetchAndRender(); };
      pagination.appendChild(nextBtn);
    }
  }

  // Debounced search
  const debouncedSearch = _debounce(() => {
    searchTerm = searchInput.value.trim();
    offset = 0;
    fetchAndRender();
  }, 400);

  searchInput.addEventListener('input', debouncedSearch);

  await fetchAndRender();
}
