/**
 * Chart of Accounts — a faithful take on Odoo's `account.account` list view:
 * code-ordered, grouped by account type, with the same category filters
 * (Receivable / Payable / Bank & Cash / Assets / Liabilities / Equity / Income /
 * Expenses / Off Balance), a text search, an archived toggle, and a New button.
 * Rows open the dedicated account form.
 */
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { ACCOUNT_TYPE_ORDER, typeGroup, typeLabel } from '/account/static/account-types.js';

const FILTERS = [
  { key: 'all',        label: 'All',           match: () => true },
  { key: 'receivable', label: 'Receivable',    match: a => a.account_type === 'asset_receivable' },
  { key: 'payable',    label: 'Payable',       match: a => a.account_type === 'liability_payable' },
  { key: 'bank_cash',  label: 'Bank & Cash',   match: a => a.account_type === 'asset_cash' },
  { key: 'asset',      label: 'Assets',        match: a => typeGroup(a.account_type) === 'asset' },
  { key: 'liability',  label: 'Liabilities',   match: a => typeGroup(a.account_type) === 'liability' },
  { key: 'equity',     label: 'Equity',        match: a => typeGroup(a.account_type) === 'equity' },
  { key: 'income',     label: 'Income',        match: a => typeGroup(a.account_type) === 'income' },
  { key: 'expense',    label: 'Expenses',      match: a => typeGroup(a.account_type) === 'expense' },
  { key: 'off',        label: 'Off Balance',   match: a => a.account_type === 'off_balance' },
];

function _debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

export async function render(container, _params) {
  container.innerHTML = '';

  // ── State ──────────────────────────────────────────────────────────────────
  let all = [];
  let filterKey = 'all';
  let search = '';
  let showArchived = false;
  let groupByType = true;

  // ── Control panel: New + search + archived toggle ─────────────────────────
  const cp = document.getElementById('control-panel');
  const searchInput = document.createElement('input');
  searchInput.type = 'search';
  searchInput.className = 'search-input';
  searchInput.placeholder = t('Search {name}…', { name: t('Chart of Accounts') });
  searchInput.setAttribute('aria-label', t('Search {name}…', { name: t('Chart of Accounts') }));
  searchInput.addEventListener('input', _debounce(() => { search = searchInput.value.trim().toLowerCase(); _paint(); }, 250));

  if (cp) {
    cp.innerHTML = '';
    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.textContent = t('New');
    newBtn.onclick = () => App.navigate('#/accounting/account/new');
    cp.appendChild(newBtn);

    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);

    const groupLabel = document.createElement('label');
    groupLabel.className = 'coa-toggle';
    const groupCb = document.createElement('input');
    groupCb.type = 'checkbox';
    groupCb.checked = groupByType;
    groupCb.onchange = () => { groupByType = groupCb.checked; _paint(); };
    groupLabel.append(groupCb, document.createTextNode(' ' + t('Group by Type')));
    cp.appendChild(groupLabel);

    const archLabel = document.createElement('label');
    archLabel.className = 'coa-toggle';
    const archCb = document.createElement('input');
    archCb.type = 'checkbox';
    archCb.checked = showArchived;
    archCb.onchange = () => { showArchived = archCb.checked; _load(); };
    archLabel.append(archCb, document.createTextNode(' ' + t('Show Archived')));
    cp.appendChild(archLabel);

    cp.appendChild(searchInput);
  }

  // ── Filter chip bar ───────────────────────────────────────────────────────
  const chipBar = document.createElement('div');
  chipBar.className = 'coa-filter-bar';
  chipBar.setAttribute('role', 'group');
  chipBar.setAttribute('aria-label', t('Filter by account type'));
  FILTERS.forEach(f => {
    const chip = document.createElement('button');
    chip.className = 'filter-chip' + (f.key === filterKey ? ' active' : '');
    chip.dataset.key = f.key;
    chip.textContent = t(f.label);
    chip.setAttribute('aria-pressed', String(f.key === filterKey));
    chip.onclick = () => {
      filterKey = f.key;
      chipBar.querySelectorAll('.filter-chip').forEach(c => {
        const on = c.dataset.key === filterKey;
        c.classList.toggle('active', on);
        c.setAttribute('aria-pressed', String(on));
      });
      _paint();
    };
    chipBar.appendChild(chip);
  });
  container.appendChild(chipBar);

  // ── Table shell ───────────────────────────────────────────────────────────
  const wrap = document.createElement('div');
  wrap.style.overflowX = 'auto';
  const table = document.createElement('table');
  table.className = 'data-table coa-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [
    { txt: 'Code', cls: 'coa-col-code' },
    { txt: 'Account Name', cls: '' },
    { txt: 'Type', cls: '' },
    { txt: 'Currency', cls: '' },
    { txt: 'Allow Reconciliation', cls: 'coa-col-recon' },
  ].forEach(({ txt, cls }) => {
    const th = document.createElement('th');
    th.textContent = t(txt);
    if (cls) th.className = cls;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  const footer = document.createElement('div');
  footer.className = 'coa-footer';
  container.appendChild(footer);

  // ── Data ──────────────────────────────────────────────────────────────────
  async function _load() {
    tbody.innerHTML = '';
    const loading = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 5;
    td.className = 'loading';
    td.textContent = t('Loading…');
    loading.appendChild(td);
    tbody.appendChild(loading);

    const domain = showArchived ? [] : [['active', '=', true]];
    try {
      all = await api.rpc('account.account', 'search_read', [domain], {
        fields: ['id', 'code', 'name', 'account_type', 'currency_id', 'reconcile', 'active'],
        order: 'code asc',
        limit: 2000,
      });
    } catch (err) {
      tbody.innerHTML = '';
      const er = document.createElement('tr');
      const etd = document.createElement('td');
      etd.colSpan = 5;
      etd.className = 'alert-error';
      etd.textContent = t('Error') + ': ' + err.message;
      er.appendChild(etd);
      tbody.appendChild(er);
      return;
    }
    _paint();
  }

  function _visible() {
    const f = FILTERS.find(x => x.key === filterKey) || FILTERS[0];
    return all.filter(a => {
      if (!f.match(a)) return false;
      if (search && !((a.code || '').toLowerCase().includes(search)
        || (a.name || '').toLowerCase().includes(search))) return false;
      return true;
    });
  }

  function _accountRow(a) {
    const tr = document.createElement('tr');
    if (!a.active) tr.classList.add('coa-archived');
    tr.onclick = () => App.navigate('#/accounting/account/' + a.id);

    const codeTd = document.createElement('td');
    codeTd.className = 'coa-col-code';
    codeTd.textContent = a.code || '';
    tr.appendChild(codeTd);

    const nameTd = document.createElement('td');
    nameTd.textContent = a.name || '';
    if (!a.active) {
      const badge = document.createElement('span');
      badge.className = 'badge badge-cancel coa-arch-badge';
      badge.textContent = t('Archived');
      nameTd.appendChild(document.createTextNode(' '));
      nameTd.appendChild(badge);
    }
    tr.appendChild(nameTd);

    const typeTd = document.createElement('td');
    typeTd.textContent = t(typeLabel(a.account_type));
    tr.appendChild(typeTd);

    const curTd = document.createElement('td');
    curTd.textContent = Array.isArray(a.currency_id) ? a.currency_id[1] : '';
    tr.appendChild(curTd);

    const reconTd = document.createElement('td');
    reconTd.className = 'coa-col-recon';
    reconTd.textContent = a.reconcile ? '✓' : '';
    reconTd.setAttribute('aria-label', a.reconcile ? t('Yes') : t('No'));
    tr.appendChild(reconTd);

    return tr;
  }

  function _groupHeaderRow(label, count) {
    const tr = document.createElement('tr');
    tr.className = 'coa-group-row';
    const td = document.createElement('td');
    td.colSpan = 5;
    td.textContent = `${label} (${count})`;
    tr.appendChild(td);
    return tr;
  }

  function _paint() {
    const rows = _visible();
    tbody.innerHTML = '';

    if (rows.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 5;
      td.className = 'empty-state';
      td.textContent = t('No records found.');
      tr.appendChild(td);
      tbody.appendChild(tr);
      footer.textContent = '';
      return;
    }

    if (groupByType) {
      const byType = new Map();
      for (const a of rows) {
        if (!byType.has(a.account_type)) byType.set(a.account_type, []);
        byType.get(a.account_type).push(a);
      }
      ACCOUNT_TYPE_ORDER.forEach(tc => {
        const group = byType.get(tc);
        if (!group || group.length === 0) return;
        tbody.appendChild(_groupHeaderRow(t(typeLabel(tc)), group.length));
        group.forEach(a => tbody.appendChild(_accountRow(a)));
      });
    } else {
      rows.forEach(a => tbody.appendChild(_accountRow(a)));
    }

    footer.textContent = t('{n} accounts', { n: rows.length });
  }

  await _load();
}
