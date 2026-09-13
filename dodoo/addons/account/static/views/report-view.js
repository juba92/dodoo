/**
 * Accounting reports — Trial Balance, General Ledger, Profit & Loss, Balance
 * Sheet, Aged Receivable, Aged Payable. Layout follows Odoo's financial reports:
 * a date filter in the control panel (a range for TB/GL/P&L, an "as of" date for
 * the Balance Sheet and Aged reports), sectioned rows with subtotals, a grand
 * total, and a balance check where one applies.
 */
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatNumber, formatDate } from '/web/static/i18n.js';

// FR-035: drill down from a reported figure to the underlying journal
// entries — the General Ledger, pre-filtered to this account (it already
// supports an `account_id` filter server-side) — or, for Aged reports, one
// specific move.
function _drillToAccount(accountId) {
  if (!accountId) return;
  App.breadcrumb = [];
  App.navigate(`#/accounting/reports/general-ledger?account_id=${accountId}`);
}

function _drillToMove(moveId) {
  if (!moveId) return;
  App.breadcrumb = [];
  App.navigate(`#/accounting/move/${moveId}`);
}

function _amount(v) {
  const n = parseFloat(v);
  if (!isFinite(n)) return '—';
  return formatNumber(n, 2);
}

function _isoToday() { return new Date().toISOString().slice(0, 10); }
function _isoYearStart() { return new Date().getFullYear() + '-01-01'; }

// ── generic table helpers ────────────────────────────────────────────────────
function _mount(parent, table) {
  const wrap = document.createElement('div');
  wrap.style.overflowX = 'auto';
  wrap.appendChild(table);
  parent.appendChild(wrap);
}

function _table(headers) {
  const table = document.createElement('table');
  table.className = 'data-table report-table';
  const thead = document.createElement('thead');
  const tr = document.createElement('tr');
  headers.forEach(h => {
    const th = document.createElement('th');
    th.textContent = typeof h === 'string' ? h : h.txt;
    if (h && h.right) th.className = 'text-right';
    tr.appendChild(th);
  });
  thead.appendChild(tr);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  return { table, tbody };
}

function _row(tbody, cells, opts = {}) {
  const tr = document.createElement('tr');
  if (opts.cls) tr.className = opts.cls;
  cells.forEach(c => {
    const td = document.createElement('td');
    const val = (c && typeof c === 'object') ? c.txt : c;
    if (c && typeof c === 'object' && c.onClick) {
      // FR-035 drill-down, kept keyboard-operable (ACC-002) — a real
      // <button>, not a div/span with a synthetic click handler.
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'link-button report-drill-link';
      btn.textContent = val == null ? '' : String(val);
      btn.onclick = c.onClick;
      td.appendChild(btn);
    } else {
      td.textContent = val == null ? '' : String(val);
    }
    if (c && typeof c === 'object') {
      if (c.right) td.className = (td.className ? td.className + ' ' : '') + 'text-right';
      if (c.strong) td.style.fontWeight = '700';
      if (c.neg) td.classList.add('report-neg');
      if (c.colspan) td.colSpan = c.colspan;
      if (c.indent) td.style.paddingLeft = (12 + c.indent * 16) + 'px';
    }
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
  return tr;
}

function _money(v, opts = {}) {
  const n = parseFloat(v) || 0;
  return { txt: _amount(v), right: true, neg: n < 0, ...opts };
}

// ── report definitions ───────────────────────────────────────────────────────
const REPORTS = {
  'trial-balance': {
    label: 'Trial Balance', filter: 'range', endpoint: '/account/report/trial-balance',
    render: renderTrialBalance,
  },
  'general-ledger': {
    label: 'General Ledger', filter: 'range', endpoint: '/account/report/general-ledger',
    withAccount: true, render: renderGeneralLedger,
  },
  'profit-loss': {
    label: 'Profit & Loss', filter: 'range', endpoint: '/account/report/profit-loss',
    render: renderProfitLoss,
  },
  'balance-sheet': {
    label: 'Balance Sheet', filter: 'asof', endpoint: '/account/report/balance-sheet',
    render: renderBalanceSheet,
  },
  'aged-receivable': {
    label: 'Aged Receivable', filter: 'asof', endpoint: '/account/report/aged-receivable',
    render: renderAged,
  },
  'aged-payable': {
    label: 'Aged Payable', filter: 'asof', endpoint: '/account/report/aged-payable',
    render: renderAged,
  },
  'tax-report': {
    label: 'Tax Report', filter: 'range', endpoint: '/account/report/tax-report',
    render: renderTaxReport,
  },
};

export async function render(container, params) {
  const cfg = REPORTS[params.report];
  container.innerHTML = '';
  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';
  if (!cfg) { container.textContent = `Unknown report: ${params.report}`; return; }

  const state = {
    date_from: _isoYearStart(),
    date_to: _isoToday(),
    date: _isoToday(),
    account_id: params.account_id ? String(params.account_id) : '',
  };

  // ── Control panel: date filter + optional account picker + Apply ──────────
  if (cp) {
    const mkDate = (labelKey, key) => {
      const wrap = document.createElement('label');
      wrap.className = 'report-filter';
      wrap.append(document.createTextNode(t(labelKey) + ' '));
      const inp = document.createElement('input');
      inp.type = 'date';
      inp.value = state[key];
      inp.onchange = () => { state[key] = inp.value; };
      wrap.appendChild(inp);
      cp.appendChild(wrap);
      return inp;
    };

    if (cfg.filter === 'range') {
      mkDate('From', 'date_from');
      mkDate('To', 'date_to');
    } else {
      mkDate('As of', 'date');
    }

    if (cfg.withAccount) {
      const wrap = document.createElement('label');
      wrap.className = 'report-filter';
      wrap.append(document.createTextNode(t('Account') + ' '));
      const sel = document.createElement('select');
      sel.add(new Option(t('All Accounts'), ''));
      try {
        const accts = await api.rpc('account.account', 'search_read', [[['active', '=', true]]],
          { fields: ['id', 'code', 'name'], order: 'code asc', limit: 2000 });
        accts.forEach(a => sel.add(new Option(`${a.code} ${a.name}`, String(a.id))));
      } catch { /* leave with just "All Accounts" */ }
      if (state.account_id) sel.value = state.account_id;
      sel.onchange = () => { state.account_id = sel.value; };
      wrap.appendChild(sel);
      cp.appendChild(wrap);
    }

    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);

    const applyBtn = document.createElement('button');
    applyBtn.className = 'btn btn-primary';
    applyBtn.textContent = t('Apply');
    applyBtn.onclick = () => _run();
    cp.appendChild(applyBtn);
  }

  const body = document.createElement('div');
  container.appendChild(body);

  async function _run() {
    body.innerHTML = '';
    const loading = document.createElement('div');
    loading.className = 'loading';
    loading.textContent = t('Loading {label}…', { label: t(cfg.label) });
    body.appendChild(loading);

    const qs = new URLSearchParams();
    if (cfg.filter === 'range') { qs.set('date_from', state.date_from); qs.set('date_to', state.date_to); }
    else { qs.set('date', state.date); }
    if (cfg.withAccount && state.account_id) qs.set('account_id', state.account_id);

    let data;
    try {
      const res = await fetch(cfg.endpoint + '?' + qs.toString(), {
        headers: { 'X-Session-Token': sessionStorage.getItem('session_token') ?? '' },
      });
      data = await res.json();
    } catch (err) {
      body.innerHTML = '';
      _err(body, t('Failed to load report') + ': ' + err.message);
      return;
    }
    body.innerHTML = '';
    if (data.error) { _err(body, data.error); return; }

    const title = document.createElement('h2');
    title.className = 'report-title';
    title.textContent = t(cfg.label);
    body.appendChild(title);

    const sub = document.createElement('div');
    sub.className = 'report-period';
    sub.textContent = cfg.filter === 'range'
      ? `${formatDate(state.date_from)} → ${formatDate(state.date_to)}`
      : `${t('As of')} ${formatDate(state.date)}`;
    body.appendChild(sub);

    cfg.render(body, data, params.report);
  }

  await _run();
}

function _err(parent, msg) {
  const el = document.createElement('div');
  el.className = 'alert-error';
  el.textContent = msg;
  parent.appendChild(el);
}

function _empty(parent) {
  const el = document.createElement('div');
  el.className = 'empty-state';
  el.textContent = t('No data for this period.');
  parent.appendChild(el);
}

// ── Trial Balance ────────────────────────────────────────────────────────────
function renderTrialBalance(parent, data) {
  const lines = data.lines || [];
  if (lines.length === 0) { _empty(parent); return; }

  const { table, tbody } = _table([
    t('Code'), t('Account'),
    { txt: t('Opening Balance'), right: true },
    { txt: t('Debit'), right: true }, { txt: t('Credit'), right: true }, { txt: t('Balance'), right: true },
  ]);
  lines.forEach(r => {
    _row(tbody, [
      r.code,
      { txt: r.name, onClick: () => _drillToAccount(r.account_id) },
      _money(r.opening_balance),
      _money(r.debit), _money(r.credit), _money(r.balance),
    ]);
  });
  const tt = data.totals || {};
  _row(tbody, [
    { txt: t('Total'), strong: true, colspan: 3 },
    _money(tt.debit, { strong: true }), _money(tt.credit, { strong: true }),
    _money(_d(tt.debit) - _d(tt.credit), { strong: true }),
  ], { cls: 'report-total-row' });
  _mount(parent, table);
  _balanceBadge(parent, tt.balanced);
}

// ── General Ledger ───────────────────────────────────────────────────────────
function renderGeneralLedger(parent, data) {
  const accounts = data.accounts || [];
  if (accounts.length === 0) { _empty(parent); return; }

  const { table, tbody } = _table([
    t('Date'), t('Journal Entry'), t('Partner'), t('Label'),
    { txt: t('Debit'), right: true }, { txt: t('Credit'), right: true }, { txt: t('Balance'), right: true },
  ]);
  accounts.forEach(acc => {
    _row(tbody, [{
      txt: `${acc.code} ${acc.name}`, strong: true, colspan: 7,
      onClick: () => _drillToAccount(acc.account_id),
    }], { cls: 'report-group-row' });
    if (acc.opening_balance !== undefined && _d(acc.opening_balance) !== 0) {
      _row(tbody, [
        { txt: t('Opening Balance'), colspan: 6 }, _money(acc.opening_balance),
      ]);
    }
    acc.lines.forEach(l => {
      _row(tbody, [
        formatDate(l.date),
        { txt: l.move_name || '', onClick: l.move_id ? () => _drillToMove(l.move_id) : null },
        l.partner_name || '', l.label || '',
        _money(l.debit), _money(l.credit), _money(l.running_balance),
      ]);
    });
    _row(tbody, [
      { txt: t('Subtotal'), strong: true, colspan: 4 },
      _money(acc.total_debit, { strong: true }), _money(acc.total_credit, { strong: true }),
      _money(acc.balance, { strong: true }),
    ], { cls: 'report-subtotal-row' });
  });
  const tt = data.totals || {};
  _row(tbody, [
    { txt: t('Grand Total'), strong: true, colspan: 4 },
    _money(tt.debit, { strong: true }), _money(tt.credit, { strong: true }),
    _money(_d(tt.debit) - _d(tt.credit), { strong: true }),
  ], { cls: 'report-total-row' });
  _mount(parent, table);
}

// ── Profit & Loss ────────────────────────────────────────────────────────────
function renderProfitLoss(parent, data) {
  const s = data.sections || {};
  const { table, tbody } = _table([t('Account'), { txt: t('Amount'), right: true }]);

  const section = (labelKey, sec) => {
    _row(tbody, [{ txt: t(labelKey), strong: true }, { txt: '', right: true }], { cls: 'report-group-row' });
    (sec.lines || []).forEach(l =>
      _row(tbody, [
        { txt: `${l.code} ${l.name}`, indent: 1, onClick: () => _drillToAccount(l.account_id) },
        _money(l.amount),
      ]));
    _row(tbody, [{ txt: t(labelKey) + ' — ' + t('Total'), strong: true }, _money(sec.total, { strong: true })],
      { cls: 'report-subtotal-row' });
  };

  section('Operating Income', s.income || {});
  section('Cost of Revenue', s.cost_of_revenue || {});
  _row(tbody, [{ txt: t('Gross Profit'), strong: true }, _money(s.gross_profit, { strong: true })],
    { cls: 'report-subtotal-row' });
  section('Expenses', s.expenses || {});
  _row(tbody, [{ txt: t('Net Profit'), strong: true }, _money(s.net_profit, { strong: true })],
    { cls: 'report-total-row' });
  _mount(parent, table);
}

// ── Balance Sheet ────────────────────────────────────────────────────────────
function renderBalanceSheet(parent, data) {
  const g = data.groups || {};
  const tt = data.totals || {};
  const { table, tbody } = _table([t('Account'), { txt: t('Amount'), right: true }]);

  const group = (labelKey, grp) => {
    _row(tbody, [{ txt: t(labelKey), strong: true }, { txt: '', right: true }], { cls: 'report-group-row' });
    (grp.lines || []).forEach(l =>
      _row(tbody, [
        { txt: `${l.code} ${l.name}`, indent: 1, onClick: () => _drillToAccount(l.account_id) },
        _money(l.amount),
      ]));
    _row(tbody, [{ txt: t(labelKey) + ' — ' + t('Total'), strong: true }, _money(grp.total, { strong: true })],
      { cls: 'report-subtotal-row' });
  };

  _row(tbody, [{ txt: t('ASSETS'), strong: true }, { txt: '' }], { cls: 'report-section-row' });
  group('Current Assets', g.current_assets || {});
  group('Fixed Assets', g.fixed_assets || {});
  _row(tbody, [{ txt: t('Total Assets'), strong: true }, _money(tt.assets, { strong: true })],
    { cls: 'report-total-row' });

  _row(tbody, [{ txt: t('LIABILITIES'), strong: true }, { txt: '' }], { cls: 'report-section-row' });
  group('Current Liabilities', g.current_liabilities || {});
  group('Non-current Liabilities', g.non_current_liabilities || {});
  _row(tbody, [{ txt: t('Total Liabilities'), strong: true }, _money(tt.liabilities, { strong: true })],
    { cls: 'report-total-row' });

  _row(tbody, [{ txt: t('EQUITY'), strong: true }, { txt: '' }], { cls: 'report-section-row' });
  (g.equity && g.equity.lines || []).forEach(l =>
    _row(tbody, [
      { txt: `${l.code} ${l.name}`, indent: 1, onClick: () => _drillToAccount(l.account_id) },
      _money(l.amount),
    ]));
  _row(tbody, [{ txt: t('Current Year Earnings'), indent: 1 }, _money(data.current_year_earnings)]);
  _row(tbody, [{ txt: t('Total Equity'), strong: true }, _money(tt.equity, { strong: true })],
    { cls: 'report-subtotal-row' });

  _row(tbody, [
    { txt: t('Total Liabilities') + ' + ' + t('Total Equity'), strong: true },
    _money(tt.liabilities_and_equity, { strong: true }),
  ], { cls: 'report-total-row' });
  _mount(parent, table);
  _balanceBadge(parent, tt.balanced);
}

// ── Aged Receivable / Payable ────────────────────────────────────────────────
const _AGED_BUCKETS = ['current', 'b_0_30', 'b_31_60', 'b_61_90', 'b_90_plus'];
const _AGED_LABELS = { current: 'Current', b_0_30: '1-30', b_31_60: '31-60', b_61_90: '61-90', b_90_plus: '90+' };

function renderAged(parent, data) {
  const partners = data.partners || [];
  if (partners.length === 0) { _empty(parent); return; }
  const { table, tbody } = _table([
    t('Partner'),
    ..._AGED_BUCKETS.map(b => ({ txt: t(_AGED_LABELS[b]), right: true })),
    { txt: t('Total'), right: true },
  ]);
  partners.forEach(p => {
    const moveIds = p.bucket_move_ids || {};
    _row(tbody, [
      { txt: p.partner_name, onClick: () => _drillToAccount(p.account_id) },
      ..._AGED_BUCKETS.map(b => {
        const cell = _money(p[b]);
        if (moveIds[b] && _d(p[b]) !== 0) cell.onClick = () => _drillToMove(moveIds[b]);
        return cell;
      }),
      _money(p.total, { strong: true }),
    ]);
  });
  const tt = data.totals || {};
  _row(tbody, [
    { txt: t('Grand Total'), strong: true },
    ..._AGED_BUCKETS.map(b => _money(tt[b], { strong: true })),
    _money(tt.total, { strong: true }),
  ], { cls: 'report-total-row' });
  _mount(parent, table);
}

// ── Tax Report ───────────────────────────────────────────────────────────────
function renderTaxReport(parent, data) {
  const lines = data.lines || [];
  if (lines.length === 0) { _empty(parent); return; }
  const { table, tbody } = _table([
    t('Tax Grid'),
    { txt: t('Base Amount'), right: true }, { txt: t('Tax Amount'), right: true },
  ]);
  lines.forEach(r => {
    _row(tbody, [r.tag_name, _money(r.base_amount), _money(r.tax_amount)]);
  });
  const tt = data.totals || {};
  _row(tbody, [
    { txt: t('Total'), strong: true },
    _money(tt.base_amount, { strong: true }), _money(tt.tax_amount, { strong: true }),
  ], { cls: 'report-total-row' });
  _mount(parent, table);
}

function _balanceBadge(parent, balanced) {
  const el = document.createElement('div');
  el.className = 'report-balance-badge';
  const badge = document.createElement('span');
  badge.className = 'badge ' + (balanced ? 'badge-paid' : 'badge-cancel');
  badge.textContent = balanced ? t('Balanced') + ' ✓' : t('Not Balanced') + ' ✗';
  el.appendChild(badge);
  parent.appendChild(el);
}

function _d(v) { return parseFloat(v) || 0; }
