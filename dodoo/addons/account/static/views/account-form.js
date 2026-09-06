/**
 * Account form — the record view behind the Chart of Accounts, modelled on Odoo's
 * `account.account` form: Code / Account Name / Type / Account Currency / Allow
 * Reconciliation / Archived, plus a debit-credit-balance box (spec US-5 AC-5).
 * Receivable & Payable accounts force reconciliation on, matching the server guards.
 */
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatNumber } from '/web/static/i18n.js';
import {
  ACCOUNT_TYPE_ORDER, RECONCILABLE_TYPES, typeGroup, typeLabel,
} from '/account/static/account-types.js';

const GROUP_LABEL = {
  asset: 'Assets', liability: 'Liabilities', equity: 'Equity',
  income: 'Income', expense: 'Expenses', off_balance: 'Off Balance',
};

function _tok() { return sessionStorage.getItem('session_token') ?? ''; }

export async function render(container, params) {
  const id = params.id;
  const isNew = id === 'new';
  container.innerHTML = '';

  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';

  // ── Load record + currencies (+ balance for existing) ─────────────────────
  let rec = { code: '', name: '', account_type: '', reconcile: false, currency_id: false, active: true };
  let currencies = [];
  let balance = null;
  try {
    const jobs = [
      api.rpc('res.currency', 'search_read', [[['active', '=', true]]], { fields: ['id', 'name', 'code'], order: 'code asc' }),
    ];
    if (!isNew) {
      jobs.push(api.rpc('account.account', 'read', [[id]], {
        fields: ['id', 'code', 'name', 'account_type', 'reconcile', 'currency_id', 'active'],
      }));
    }
    const res = await Promise.all(jobs);
    currencies = res[0] || [];
    if (!isNew) {
      rec = (res[1] || [])[0];
      if (!rec) { container.textContent = t('Record not found.'); return; }
    }
  } catch (err) {
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = t('Failed to load') + ': ' + err.message;
    container.appendChild(el);
    return;
  }

  if (!isNew) {
    try {
      const r = await fetch(`/account/account/${id}/balance`, { headers: { 'X-Session-Token': _tok() } });
      const data = await r.json();
      if (data.result) balance = data.result;
    } catch { /* balance box just stays hidden */ }
  }

  // ── Title ─────────────────────────────────────────────────────────────────
  const title = document.createElement('h2');
  title.className = 'invoice-number';
  title.style.padding = '12px 24px 0';
  title.textContent = isNew ? t('New Account')
    : `${rec.code || ''} ${rec.name || ''}`.trim();
  container.appendChild(title);

  const banner = document.createElement('div');
  banner.id = 'account-status';
  banner.style.display = 'none';
  banner.style.margin = '8px 24px 0';
  container.appendChild(banner);
  if (params && params.saved) _flash(banner, 'success', t('Settings saved.'));

  // ── Balance box (existing accounts) ──────────────────────────────────────
  if (balance) {
    const box = document.createElement('div');
    box.className = 'report-summary account-balance-box';
    const rows = [
      [t('Total Debit'), balance.debit],
      [t('Total Credit'), balance.credit],
      [t('Balance'), balance.net],
    ];
    rows.forEach(([label, val]) => {
      const span = document.createElement('span');
      const strong = document.createElement('strong');
      strong.textContent = formatNumber(parseFloat(val || 0), 2);
      span.append(document.createTextNode(label + ': '), strong);
      box.appendChild(span);
    });
    container.appendChild(box);
  }

  // ── Form card ────────────────────────────────────────────────────────────
  const card = document.createElement('div');
  card.className = 'form-card';
  const grid = document.createElement('div');
  grid.className = 'field-grid';
  card.appendChild(grid);
  container.appendChild(card);

  const codeInput = _text(grid, t('Code'), rec.code || '', true);
  const nameInput = _text(grid, t('Account Name'), rec.name || '', true);

  // Type select, grouped by internal group like Odoo
  const typeSel = document.createElement('select');
  typeSel.id = 'acc-type';
  const seenGroups = {};
  ACCOUNT_TYPE_ORDER.forEach(code => {
    const g = typeGroup(code);
    if (!seenGroups[g]) {
      seenGroups[g] = document.createElement('optgroup');
      seenGroups[g].label = t(GROUP_LABEL[g] || g);
      typeSel.appendChild(seenGroups[g]);
    }
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = t(typeLabel(code));
    seenGroups[g].appendChild(opt);
  });
  typeSel.value = rec.account_type || 'asset_current';
  _wrapField(grid, t('Type'), typeSel, true);

  // Currency select (optional)
  const curSel = document.createElement('select');
  curSel.id = 'acc-currency';
  curSel.add(new Option('—', ''));
  currencies.forEach(c => curSel.add(new Option(`${c.code} ${c.name || ''}`.trim(), String(c.id))));
  const curId = Array.isArray(rec.currency_id) ? rec.currency_id[0] : rec.currency_id;
  curSel.value = curId ? String(curId) : '';
  _wrapField(grid, t('Account Currency'), curSel, false);

  // Allow Reconciliation
  const reconWrap = document.createElement('div');
  reconWrap.className = 'form-field';
  const reconLabel = document.createElement('label');
  reconLabel.htmlFor = 'acc-reconcile';
  reconLabel.textContent = t('Allow Reconciliation');
  const reconCb = document.createElement('input');
  reconCb.type = 'checkbox';
  reconCb.id = 'acc-reconcile';
  reconCb.checked = !!rec.reconcile;
  reconWrap.append(reconLabel, reconCb);
  const reconHint = document.createElement('span');
  reconHint.className = 'field-hint';
  reconWrap.appendChild(reconHint);
  grid.appendChild(reconWrap);

  function _syncRecon() {
    if (RECONCILABLE_TYPES.has(typeSel.value)) {
      reconCb.checked = true;
      reconCb.disabled = true;
      reconHint.textContent = t('Receivable and Payable accounts are always reconcilable.');
    } else {
      reconCb.disabled = false;
      reconHint.textContent = '';
    }
  }
  typeSel.addEventListener('change', _syncRecon);
  _syncRecon();

  // Archived (existing only)
  let archCb = null;
  if (!isNew) {
    const archWrap = document.createElement('div');
    archWrap.className = 'form-field';
    const archLabel = document.createElement('label');
    archLabel.htmlFor = 'acc-archived';
    archLabel.textContent = t('Archived');
    archCb = document.createElement('input');
    archCb.type = 'checkbox';
    archCb.id = 'acc-archived';
    archCb.checked = !rec.active;
    archWrap.append(archLabel, archCb);
    grid.appendChild(archWrap);
  }

  // ── Control panel: Save / Discard ────────────────────────────────────────
  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn btn-primary';
  saveBtn.textContent = t('Save');
  const discardBtn = document.createElement('button');
  discardBtn.className = 'btn btn-secondary';
  discardBtn.textContent = t('Discard');
  discardBtn.onclick = () => App.navigate('#/accounting/chart-of-accounts');
  if (cp) { cp.append(saveBtn, discardBtn); }

  saveBtn.onclick = async () => {
    const vals = {
      code: codeInput.value.trim(),
      name: nameInput.value.trim(),
      account_type: typeSel.value,
      reconcile: reconCb.checked,
      currency_id: curSel.value ? parseInt(curSel.value, 10) : false,
    };
    if (archCb) vals.active = !archCb.checked;

    if (!vals.code) { _flash(banner, 'error', t('This field is required.') + ' — ' + t('Code')); return; }
    if (!vals.name) { _flash(banner, 'error', t('This field is required.') + ' — ' + t('Account Name')); return; }

    saveBtn.disabled = true;
    saveBtn.textContent = t('Saving…');
    try {
      if (isNew) {
        const companies = await api.rpc('res.company', 'search_read', [[]], { fields: ['id'], limit: 1 });
        vals.company_id = companies[0]?.id;
        const newId = await api.rpc('account.account', 'create', [vals]);
        App.navigate('#/accounting/account/' + newId);
      } else {
        await api.rpc('account.account', 'write', [[id], vals]);
        render(container, { ...params, saved: true }); // reload with fresh balance + title
      }
    } catch (err) {
      _flash(banner, 'error', t('Save failed') + ': ' + err.message);
      saveBtn.disabled = false;
      saveBtn.textContent = t('Save');
    }
  };
}

// ── helpers ───────────────────────────────────────────────────────────────
function _wrapField(grid, labelText, control, required) {
  const wrap = document.createElement('div');
  wrap.className = 'form-field';
  const label = document.createElement('label');
  label.textContent = labelText;
  if (required) {
    const m = document.createElement('span');
    m.className = 'required-mark';
    m.setAttribute('aria-hidden', 'true');
    m.textContent = '*';
    label.appendChild(m);
  }
  wrap.append(label, control);
  grid.appendChild(wrap);
  return control;
}

function _text(grid, labelText, value, required) {
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.value = value;
  if (required) inp.required = true;
  return _wrapField(grid, labelText, inp, required);
}

function _flash(banner, kind, msg) {
  banner.className = kind === 'error' ? 'alert-error' : 'success-banner';
  banner.textContent = msg;
  banner.style.display = 'block';
}
