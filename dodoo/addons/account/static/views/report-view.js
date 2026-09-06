import { t, formatNumber } from '/web/static/i18n.js';

const REPORT_CONFIG = {
  'trial-balance': {
    label: 'Trial Balance',
    endpoint: '/account/report/trial-balance',
    columns: [['Code', ''], ['Account', ''], ['Type', ''], ['Debit', 'text-right'], ['Credit', 'text-right'], ['Balance', 'text-right']],
    rowMapper: r => [r.code, r.name, r.account_type, r.total_debit, r.total_credit, r.balance],
    hasSummary: true,
  },
  'general-ledger':   { label: 'General Ledger',  endpoint: null },
  'profit-loss':      { label: 'Profit & Loss',   endpoint: null },
  'balance-sheet':    { label: 'Balance Sheet',   endpoint: null },
  'aged-receivable':  { label: 'Aged Receivable', endpoint: null },
  'aged-payable':     { label: 'Aged Payable',    endpoint: null },
};

function _fmt(v) {
  if (v === null || v === undefined) return '—';
  return formatNumber(parseFloat(v), 2);
}

export async function render(container, params) {
  const config = REPORT_CONFIG[params.report];
  container.innerHTML = '';
  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';

  if (!config) { container.textContent = `Unknown report: ${params.report}`; return; }

  const label = t(config.label);

  if (!config.endpoint) {
    const msg = document.createElement('div');
    msg.className = 'empty-state';
    msg.style.padding = '60px';
    msg.textContent = t('{label} — coming soon.', { label });
    container.appendChild(msg);
    return;
  }

  const loading = document.createElement('div');
  loading.className = 'loading';
  loading.textContent = t('Loading {label}…', { label });
  container.appendChild(loading);

  try {
    const res = await fetch(config.endpoint, {
      headers: { 'X-Session-Token': sessionStorage.getItem('session_token') ?? '' },
    });
    const data = await res.json();
    container.innerHTML = '';

    if (data.error) {
      const el = document.createElement('div');
      el.className = 'alert-error';
      el.textContent = data.error;
      container.appendChild(el);
      return;
    }

    const result = data.result ?? {};

    // Summary row (trial balance)
    if (config.hasSummary && result.total_debit !== undefined) {
      const summary = document.createElement('div');
      summary.className = 'report-summary';
      const balanced = result.balanced;
      summary.innerHTML = `
        <span>${t('Total Debit')}: <strong>${_fmt(result.total_debit)}</strong></span>
        <span>${t('Total Credit')}: <strong>${_fmt(result.total_credit)}</strong></span>
        <span class="badge ${balanced ? 'badge-paid' : 'badge-cancel'}">
          ${balanced ? t('Balanced') + ' ✓' : t('Not Balanced') + ' ✗'}
        </span>
      `;
      container.appendChild(summary);
    }

    const rows = Array.isArray(result.lines) ? result.lines : (Array.isArray(result) ? result : []);

    const table = document.createElement('table');
    table.className = 'data-table';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    config.columns.forEach(([txt, cls]) => {
      const th = document.createElement('th');
      th.textContent = txt ? t(txt) : txt;
      if (cls) th.className = cls;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach(row => {
      const tr = document.createElement('tr');
      config.rowMapper(row).forEach((val, i) => {
        const td = document.createElement('td');
        const [, cls] = config.columns[i];
        if (cls === 'text-right') { td.className = cls; td.textContent = _fmt(val); }
        else td.textContent = val ?? '—';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);

    if (rows.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = t('No data for this period.');
      container.appendChild(empty);
    }
  } catch (err) {
    container.innerHTML = '';
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = t('Failed to load report') + ': ' + err.message;
    container.appendChild(el);
  }
}
