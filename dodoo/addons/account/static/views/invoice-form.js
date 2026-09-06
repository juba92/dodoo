import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatNumber } from '/web/static/i18n.js';

const TYPE_LABEL = {
  out_invoice: 'Customer Invoice',  out_refund: 'Customer Credit Note',
  in_invoice:  'Vendor Bill',       in_refund:  'Vendor Credit Note',
  entry:        'Journal Entry',    out_receipt: 'Customer Receipt',
  in_receipt:  'Vendor Receipt',
};

/** Translated move-type label ('' → generic "Invoice"). */
function _typeLabel(moveType) {
  return TYPE_LABEL[moveType] ? t(TYPE_LABEL[moveType]) : t('Invoice');
}

const _TYPE_LIST_HASH = {
  out_invoice: '#/accounting/invoices',
  out_refund:  '#/accounting/credit-notes',
  in_invoice:  '#/accounting/bills',
  in_refund:   '#/accounting/vendor-credit-notes',
  entry:       '#/accounting/journal-entries',
};
function _listHashForType(moveType) { return _TYPE_LIST_HASH[moveType] ?? '#/accounting/invoices'; }

function _fmt(v) {
  if (v === null || v === undefined) return '—';
  return formatNumber(parseFloat(v), 2);
}
function _date(d) { return d ? d.substring(0, 10) : '—'; }
function _tok() { return sessionStorage.getItem('session_token') ?? ''; }

async function _post(url) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-Token': _tok() },
  });
  return res.json();
}

export async function render(container, params) {
  const { id } = params;
  const isNew = id === 'new';

  container.innerHTML = '';
  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';

  if (isNew) {
    await _renderNewInvoice(container, cp, params.moveType || 'out_invoice', params.editId || null);
    return;
  }

  // Fetch move
  let move;
  try {
    const rows = await api.rpc('account.move', 'read', [[id]], {
      fields: ['id', 'name', 'move_type', 'state', 'payment_state', 'partner_id',
        'journal_id', 'invoice_date', 'invoice_date_due', 'date',
        'invoice_payment_term_id', 'ref', 'narration',
        'amount_untaxed', 'amount_tax', 'amount_total', 'amount_residual',
        'currency_id', 'company_id', 'reversed_entry_id'],
    });
    move = rows[0];
    if (!move) { container.textContent = t('Record not found.'); return; }
  } catch (err) {
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = t('Failed to load') + ': ' + err.message;
    container.appendChild(el);
    return;
  }

  // Fetch product lines
  let lines = [];
  try {
    lines = await api.rpc('account.move.line', 'search_read',
      [[['move_id', '=', id], ['display_type', 'in', ['product', 'line_section', 'line_note']]]],
      { fields: ['id', 'name', 'account_id', 'debit', 'credit', 'quantity', 'price_unit',
        'tax_ids', 'display_type', 'sequence'], order: 'sequence asc' }
    );
  } catch { /* show empty lines */ }

  // Resolve tax names referenced by the lines
  const taxNames = {};
  const taxIds = [...new Set(lines.flatMap(l => Array.isArray(l.tax_ids) ? l.tax_ids : []))];
  if (taxIds.length) {
    try {
      const txs = await api.rpc('account.tax', 'read', [taxIds], { fields: ['id', 'name'] });
      txs.forEach(tx => { taxNames[tx.id] = tx.name; });
    } catch { /* names optional */ }
  }

  // Control panel
  if (cp) _buildCP(cp, move, id);

  // Status bar
  container.appendChild(_statusBar(move));

  // Header card
  container.appendChild(_headerCard(move));

  // Lines
  container.appendChild(_linesCard(lines, taxNames));

  // Totals
  container.appendChild(_totalsCard(move));
}

function _buildCP(cp, move, id) {
  const { state, payment_state, move_type } = move;

  if (state === 'draft') {
    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-primary';
    editBtn.textContent = t('Edit');
    editBtn.onclick = () => App.navigate(`#/accounting/move/new?type=${move_type}&edit=${id}`);
    cp.appendChild(editBtn);

    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'btn btn-secondary';
    confirmBtn.textContent = t('Confirm');
    confirmBtn.onclick = async () => {
      confirmBtn.disabled = true; confirmBtn.textContent = t('Confirming…');
      try {
        const data = await _post(`/account/move/${id}/post`);
        if (!data.result) { alert(data.error || t('Confirm failed')); confirmBtn.disabled = false; confirmBtn.textContent = t('Confirm'); return; }
        App.navigate(`#/accounting/move/${id}`);
      } catch (err) {
        alert(t('Error') + ': ' + err.message);
        confirmBtn.disabled = false; confirmBtn.textContent = t('Confirm');
      }
    };
    cp.appendChild(confirmBtn);
  }

  if (state === 'posted' && ['not_paid', 'partial'].includes(payment_state) && move_type !== 'entry') {
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary';
    btn.textContent = t('Register Payment');
    btn.onclick = () => _paymentDialog(move, id);
    cp.appendChild(btn);
  }

  if (state === 'posted') {
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = move_type === 'entry' ? t('Reverse Entry') : t('Add Credit Note');
    btn.onclick = async () => {
      if (!confirm(t('Create a reversal/credit note?'))) return;
      btn.disabled = true;
      try {
        const res = await fetch(`/account/move/${id}/reverse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': _tok() },
          body: JSON.stringify({ date: new Date().toISOString().substring(0, 10) }),
        });
        const data = await res.json();
        if (data.result?.length) App.navigate(`#/accounting/move/${data.result[0]}`);
        else alert(data.error ?? t('Failed to create credit note'));
      } catch (err) {
        alert(t('Error') + ': ' + err.message);
      } finally {
        btn.disabled = false;
      }
    };
    cp.appendChild(btn);
  }

  if (state === 'posted' && payment_state === 'not_paid') {
    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = t('Reset to Draft');
    btn.onclick = async () => {
      if (!confirm(t('Reset to draft? This unlocks the entry.'))) return;
      btn.disabled = true;
      try {
        const data = await _post(`/account/move/${id}/reset_to_draft`);
        if (!data.result) { alert(data.error || t('Reset to draft failed')); btn.disabled = false; return; }
        App.navigate(`#/accounting/move/${id}`);
      } catch (err) {
        alert(t('Error') + ': ' + err.message);
        btn.disabled = false;
      }
    };
    cp.appendChild(btn);
  }
}

function _statusBar(move) {
  const bar = document.createElement('div');
  bar.className = 'status-bar';
  const { state, payment_state } = move;
  const steps = [
    { label: t('Draft'),     active: state === 'draft' },
    { label: t('Confirmed'), active: state === 'posted' },
    { label: t('Paid'),      active: state === 'posted' && ['in_payment', 'paid'].includes(payment_state) },
  ];
  steps.forEach((step, i) => {
    if (i > 0) {
      const sep = document.createElement('span');
      sep.className = 'status-sep';
      sep.setAttribute('aria-hidden', 'true');
      sep.textContent = '›';
      bar.appendChild(sep);
    }
    const el = document.createElement('span');
    el.className = 'status-step' + (step.active ? ' active' : '');
    el.textContent = step.label;
    bar.appendChild(el);
  });
  return bar;
}

function _headerCard(move) {
  const card = document.createElement('div');
  card.className = 'form-card invoice-header-card';

  const top = document.createElement('div');
  top.className = 'invoice-header-top';

  const titleEl = document.createElement('h2');
  titleEl.className = 'invoice-number';
  titleEl.textContent = (move.name && move.name !== '/') ? move.name : _typeLabel(move.move_type);
  top.appendChild(titleEl);

  if (move.payment_state && move.state === 'posted') {
    const { label, cls } = _badge(move.state, move.payment_state);
    const span = document.createElement('span');
    span.className = `badge ${cls}`;
    span.textContent = label;
    top.appendChild(span);
  }

  card.appendChild(top);

  const grid = document.createElement('div');
  grid.className = 'header-grid';

  const fields = [
    [t('Customer / Vendor'),  Array.isArray(move.partner_id) ? move.partner_id[1] : '—'],
    [t('Journal'),            Array.isArray(move.journal_id) ? move.journal_id[1] : '—'],
    [t('Invoice Date'),       _date(move.invoice_date)],
    [t('Accounting Date'),    _date(move.date)],
    [t('Due Date'),           _date(move.invoice_date_due)],
    [t('Payment Terms'),      Array.isArray(move.invoice_payment_term_id) ? move.invoice_payment_term_id[1] : '—'],
    [t('Reference'),          move.ref || '—'],
    [t('Currency'),           Array.isArray(move.currency_id) ? move.currency_id[1] : '—'],
  ];

  fields.forEach(([label, value]) => {
    const row = document.createElement('div');
    row.className = 'header-row';
    const lbl = document.createElement('span');
    lbl.className = 'header-label';
    lbl.textContent = label;
    const val = document.createElement('span');
    val.className = 'header-value';
    val.textContent = value;
    row.appendChild(lbl);
    row.appendChild(val);
    grid.appendChild(row);
  });

  card.appendChild(grid);
  return card;
}

function _linesCard(lines, taxNames = {}) {
  const card = document.createElement('div');
  card.className = 'form-card';

  const h = document.createElement('h3');
  h.className = 'section-title';
  h.textContent = t('Invoice Lines');
  card.appendChild(h);

  const table = document.createElement('table');
  table.className = 'data-table invoice-lines-table';

  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [[t('Description'), ''], [t('Account'), ''], [t('Quantity'), 'text-right'],
   [t('Unit Price'), 'text-right'], [t('Taxes'), ''], [t('Debit'), 'text-right'],
   [t('Credit'), 'text-right'], [t('Balance'), 'text-right']].forEach(([txt, cls]) => {
    const th = document.createElement('th');
    th.textContent = txt;
    if (cls) th.className = cls;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  const productLines = lines.filter(l => l.display_type === 'product');

  if (productLines.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.className = 'empty-state';
    td.style.padding = '20px';
    td.textContent = t('No invoice lines.');
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    productLines.forEach(line => {
      const debit = parseFloat(line.debit || 0);
      const credit = parseFloat(line.credit || 0);
      const balance = debit - credit;
      const qty = line.quantity === null || line.quantity === undefined ? null : parseFloat(line.quantity);
      const unit = line.price_unit === null || line.price_unit === undefined ? null : parseFloat(line.price_unit);
      const taxLabel = (Array.isArray(line.tax_ids) ? line.tax_ids : [])
        .map(tid => taxNames[tid] || `#${tid}`).join(', ') || '—';
      const tr = document.createElement('tr');
      const cells = [
        { text: line.name || '—', cls: '' },
        { text: Array.isArray(line.account_id) ? line.account_id[1] : '—', cls: '' },
        { text: qty === null ? '—' : formatNumber(qty, 2), cls: 'text-right' },
        { text: unit === null ? '—' : _fmt(unit), cls: 'text-right' },
        { text: taxLabel, cls: '' },
        { text: _fmt(debit), cls: 'text-right' },
        { text: _fmt(credit), cls: 'text-right' },
        { text: _fmt(balance), cls: 'text-right' },
      ];
      cells.forEach(({ text, cls }) => {
        const td = document.createElement('td');
        td.textContent = text;
        if (cls) td.className = cls;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  table.appendChild(tbody);
  card.appendChild(table);
  return card;
}

function _totalsCard(move) {
  const card = document.createElement('div');
  card.className = 'form-card totals-card';

  const rows = [
    { label: t('Untaxed Amount'), value: _fmt(move.amount_untaxed) },
    { label: t('Taxes'),          value: _fmt(move.amount_tax) },
    { label: t('Total'),          value: _fmt(move.amount_total), bold: true },
    { label: t('Amount Due'),     value: _fmt(move.amount_residual), bold: true,
      highlight: parseFloat(move.amount_residual || 0) > 0 },
  ];

  rows.forEach(({ label, value, bold, highlight }) => {
    const row = document.createElement('div');
    row.className = 'totals-row' + (highlight ? ' totals-due' : '');
    const lbl = document.createElement('span');
    lbl.className = 'totals-label';
    lbl.textContent = label;
    const val = document.createElement('span');
    val.className = 'totals-value' + (bold ? ' bold' : '');
    val.textContent = value;
    row.appendChild(lbl);
    row.appendChild(val);
    card.appendChild(row);
  });

  return card;
}

function _badge(state, paymentState) {
  if (state === 'draft')  return { label: t('Draft'),      cls: 'badge-draft' };
  if (state === 'cancel') return { label: t('Cancelled'),  cls: 'badge-cancel' };
  if (paymentState === 'paid')     return { label: t('Paid'),     cls: 'badge-paid' };
  if (paymentState === 'reversed') return { label: t('Reversed'), cls: 'badge-cancel' };
  if (paymentState === 'partial')  return { label: t('Partial'),  cls: 'badge-partial' };
  return { label: t('Confirmed'), cls: 'badge-posted' };
}

async function _paymentDialog(move, moveId) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  document.body.appendChild(overlay);

  const dialog = document.createElement('div');
  dialog.className = 'modal-dialog';
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  overlay.appendChild(dialog);

  const title = document.createElement('h3');
  title.className = 'modal-title';
  title.textContent = t('Register Payment');
  dialog.appendChild(title);

  const amountF = _field(t('Amount'), 'number', String(parseFloat(move.amount_residual || 0).toFixed(2)));
  const dateF   = _field(t('Payment Date'), 'date', new Date().toISOString().substring(0, 10));
  dialog.appendChild(amountF.wrap);
  dialog.appendChild(dateF.wrap);

  const jWrap = document.createElement('div');
  jWrap.className = 'form-field';
  const jLabel = document.createElement('label');
  jLabel.textContent = t('Journal');
  const jSelect = document.createElement('select');
  jSelect.style.cssText = 'width:100%;padding:6px 10px;border:1px solid rgba(0,0,0,.15);border-radius:4px;font-size:.875rem';
  jWrap.appendChild(jLabel);
  jWrap.appendChild(jSelect);
  dialog.appendChild(jWrap);

  const errEl = document.createElement('div');
  errEl.className = 'alert-error';
  errEl.style.display = 'none';
  dialog.appendChild(errEl);

  const btnRow = document.createElement('div');
  btnRow.className = 'modal-btn-row';
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = t('Cancel');
  cancelBtn.onclick = () => overlay.remove();
  const payBtn = document.createElement('button');
  payBtn.className = 'btn btn-primary';
  payBtn.textContent = t('Pay');
  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(payBtn);
  dialog.appendChild(btnRow);

  // Load journals
  try {
    const journals = await api.rpc('account.journal', 'search_read',
      [[['type', 'in', ['bank', 'cash']]]], { fields: ['id', 'name', 'type'] });
    journals.forEach(j => {
      const opt = document.createElement('option');
      opt.value = j.id;
      opt.textContent = `${j.name} (${j.type})`;
      jSelect.appendChild(opt);
    });
  } catch { /* empty */ }

  payBtn.onclick = async () => {
    const amount    = parseFloat(amountF.input.value);
    const date      = dateF.input.value;
    const journalId = parseInt(jSelect.value, 10);

    if (!amount || !date || !journalId) {
      errEl.textContent = t('Please fill all fields.');
      errEl.style.display = 'block';
      return;
    }

    payBtn.disabled = true;
    payBtn.textContent = t('Processing…');
    errEl.style.display = 'none';

    try {
      const isOut    = ['in_invoice', 'in_refund'].includes(move.move_type);
      const partnerId  = Array.isArray(move.partner_id)  ? move.partner_id[0]  : move.partner_id;
      const currencyId = Array.isArray(move.currency_id) ? move.currency_id[0] : move.currency_id;
      const companyId  = Array.isArray(move.company_id)  ? move.company_id[0]  : move.company_id;

      const paymentId = await api.rpc('account.payment', 'create', [{
        payment_type: isOut ? 'outbound' : 'inbound',
        partner_type: isOut ? 'supplier'  : 'customer',
        partner_id:   partnerId,
        journal_id:   journalId,
        currency_id:  currencyId,
        company_id:   companyId,
        amount,
        date,
      }]);

      const tok = _tok();
      await fetch(`/account/payment/${paymentId}/post`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': tok },
      });
      await fetch(`/account/payment/${paymentId}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': tok },
        body: JSON.stringify({ invoice_ids: [parseInt(moveId, 10)] }),
      });

      overlay.remove();
      App.navigate(`#/accounting/move/${moveId}`);
    } catch (err) {
      errEl.textContent = t('Payment failed') + ': ' + err.message;
      errEl.style.display = 'block';
      payBtn.disabled = false;
      payBtn.textContent = t('Pay');
    }
  };
}

function _field(label, type, value) {
  const wrap = document.createElement('div');
  wrap.className = 'form-field';
  const lbl = document.createElement('label');
  lbl.textContent = label;
  const input = document.createElement('input');
  input.type = type;
  input.value = value;
  wrap.appendChild(lbl);
  wrap.appendChild(input);
  return { wrap, input };
}

// ── New invoice creation form ─────────────────────────────────────────────────

function _journalTypes(moveType) {
  if (['out_invoice', 'out_refund'].includes(moveType)) return ['sale'];
  if (['in_invoice', 'in_refund'].includes(moveType))   return ['purchase'];
  if (moveType === 'entry')                              return ['general'];
  return ['sale', 'purchase', 'general'];
}

/** Which account.tax.type_tax_use applies to a move type ('' → none, e.g. journal entry). */
function _taxUse(moveType) {
  if (['out_invoice', 'out_refund', 'out_receipt'].includes(moveType)) return 'sale';
  if (['in_invoice', 'in_refund', 'in_receipt'].includes(moveType)) return 'purchase';
  return '';
}

/** Untaxed subtotal of a draft invoice line = unit price × quantity. */
function _lineSubtotal(line) {
  const q = parseFloat(line.quantity || 0);
  const u = parseFloat(line.priceUnit || 0);
  return (q > 0 && u !== 0) ? q * u : 0;
}

/** Raw (unrounded) amount of one tax on a base — mirrors AccountTax._compute_amount. */
function _taxAmount(tax, base, quantity = 1) {
  const amount = parseFloat(tax.amount || 0);
  switch (tax.amount_type) {
    case 'percent':  return base * amount / 100;
    case 'fixed':    return amount * quantity;
    case 'division': return (100 - amount) === 0 ? 0 : base * amount / (100 - amount);
    default:         return 0;
  }
}

function _accountDomain(moveType) {
  if (['out_invoice', 'out_refund'].includes(moveType))
    return [['account_type', 'in', ['income', 'income_other']]];
  if (['in_invoice', 'in_refund'].includes(moveType))
    return [['account_type', 'in', ['expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost']]];
  return [];
}

function _headerRow(labelText, control) {
  const row = document.createElement('div');
  row.className = 'header-row';
  const lbl = document.createElement('span');
  lbl.className = 'header-label';
  lbl.textContent = labelText;
  row.appendChild(lbl);
  row.appendChild(control);
  return row;
}

function _inlineInput(type, placeholder, extraStyle = '') {
  const el = document.createElement('input');
  el.type = type;
  el.placeholder = placeholder;
  el.style.cssText = `width:100%;padding:4px 8px;border:1px solid rgba(0,0,0,.15);border-radius:4px;font-size:.875rem;${extraStyle}`;
  return el;
}

function _inlineSelect(options) {
  const sel = document.createElement('select');
  sel.style.cssText = 'width:100%;padding:4px 8px;border:1px solid rgba(0,0,0,.15);border-radius:4px;font-size:.875rem';
  options.forEach(([val, text]) => {
    const opt = document.createElement('option');
    opt.value = val;
    opt.textContent = text;
    sel.appendChild(opt);
  });
  return sel;
}

async function _renderNewInvoice(container, cp, moveType, editId = null) {
  const typeLabel = _typeLabel(moveType);
  const isEntry   = moveType === 'entry';

  // ── Title + loading (immediate) ──
  container.innerHTML = '';
  const titleEl = document.createElement('h2');
  titleEl.className = 'invoice-number';
  titleEl.style.padding = '12px 24px 0';
  titleEl.textContent = editId ? t('Edit {type}', { type: typeLabel }) : t('New {type}', { type: typeLabel });
  container.appendChild(titleEl);

  const loadingEl = document.createElement('div');
  loadingEl.className = 'loading';
  loadingEl.textContent = t('Loading form…');
  container.appendChild(loadingEl);

  // ── Control panel (immediate, before any await) ──
  let _saveForm = null;
  if (cp) {
    cp.innerHTML = '';
    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-primary';
    saveBtn.textContent = editId ? t('Save Changes') : t('Save as Draft');
    saveBtn.disabled = true;
    const _saveBtnLabel = saveBtn.textContent;
    saveBtn.onclick = async () => {
      if (!_saveForm) return;
      saveBtn.disabled = true;
      saveBtn.textContent = t('Saving…');
      try {
        await _saveForm();
      } catch (err) {
        alert(err.message);
        saveBtn.disabled = false;
        saveBtn.textContent = _saveBtnLabel;
      }
    };
    const discardBtn = document.createElement('button');
    discardBtn.className = 'btn btn-secondary';
    discardBtn.textContent = t('Discard');
    discardBtn.onclick = () => {
      if (editId) {
        App.navigate(`#/accounting/move/${editId}`);
      } else {
        App.navigate(_listHashForType(moveType));
      }
    };
    cp.appendChild(saveBtn);
    cp.appendChild(discardBtn);
  }

  // ── Load data ──
  let partners = [], journals = [], accounts = [], companies = [], taxes = [];
  const taxUse = _taxUse(moveType);
  try {
    [partners, journals, accounts, companies, taxes] = await Promise.all([
      api.rpc('res.partner', 'search_read', [[]], { fields: ['id', 'name'], limit: 200 }),
      api.rpc('account.journal', 'search_read', [[['type', 'in', _journalTypes(moveType)]]], { fields: ['id', 'name'] }),
      api.rpc('account.account', 'search_read',
        [[['active', '=', true], ..._accountDomain(moveType)]],
        { fields: ['id', 'code', 'name'], order: 'code asc', limit: 500 }),
      api.rpc('res.company', 'search_read', [[]], { fields: ['id', 'currency_id'], limit: 1 }),
      taxUse
        ? api.rpc('account.tax', 'search_read',
            [[['active', '=', true], ['type_tax_use', '=', taxUse]]],
            { fields: ['id', 'name', 'amount', 'amount_type'], order: 'amount desc' })
        : Promise.resolve([]),
    ]);
    // Fall back to all accounts if type-filtered list is empty
    if (accounts.length === 0) {
      accounts = await api.rpc('account.account', 'search_read',
        [[['active', '=', true]]], { fields: ['id', 'code', 'name'], order: 'code asc', limit: 500 });
    }
  } catch (err) {
    loadingEl.className = 'alert-error';
    loadingEl.textContent = t('Failed to load form data') + ': ' + err.message;
    return;
  }

  const company    = companies[0];
  const companyId  = company?.id ?? null;
  const currencyId = company
    ? (Array.isArray(company.currency_id) ? company.currency_id[0] : company.currency_id)
    : null;

  let existingMove = null, existingLines = [];
  if (editId) {
    try {
      [existingMove, existingLines] = await Promise.all([
        api.rpc('account.move', 'read', [[editId]], {
          fields: ['id', 'partner_id', 'journal_id', 'invoice_date', 'ref'],
        }).then(r => r[0]),
        api.rpc('account.move.line', 'search_read',
          [[['move_id', '=', editId], ['display_type', 'in', ['product', 'line_section', 'line_note']]]],
          { fields: ['id', 'name', 'account_id', 'debit', 'credit', 'quantity', 'price_unit',
            'tax_ids', 'display_type', 'sequence'], order: 'sequence asc' }
        ),
      ]);
    } catch { /* fall back to empty */ }
  }

  // ── Build form (replace loading indicator) ──
  loadingEl.remove();

  const lines = [];

  // Header card
  const headerCard = document.createElement('div');
  headerCard.className = 'form-card invoice-header-card';
  const grid = document.createElement('div');
  grid.className = 'header-grid';

  const partnerSel = _inlineSelect(
    [['', isEntry ? t('— Optional —') : t('— Select partner —')], ...partners.map(p => [p.id, p.name])]
  );
  grid.appendChild(_headerRow(isEntry ? t('Partner (optional)') : t('Customer / Vendor'), partnerSel));

  const journalSel = _inlineSelect(journals.length
    ? journals.map(j => [j.id, j.name])
    : [['', t('— No journals found —')]]);
  grid.appendChild(_headerRow(t('Journal'), journalSel));

  const dateInput = _inlineInput('date', '');
  dateInput.value = new Date().toISOString().substring(0, 10);
  grid.appendChild(_headerRow(t('Invoice Date'), dateInput));

  const refInput = _inlineInput('text', t('Optional'));
  grid.appendChild(_headerRow(t('Reference'), refInput));

  if (existingMove) {
    const exPartnerId = Array.isArray(existingMove.partner_id) ? existingMove.partner_id[0] : existingMove.partner_id;
    const exJournalId = Array.isArray(existingMove.journal_id) ? existingMove.journal_id[0] : existingMove.journal_id;
    if (exPartnerId) partnerSel.value = String(exPartnerId);
    if (exJournalId) journalSel.value = String(exJournalId);
    if (existingMove.invoice_date) dateInput.value = String(existingMove.invoice_date).substring(0, 10);
    if (existingMove.ref) refInput.value = existingMove.ref;
  }

  headerCard.appendChild(grid);
  container.appendChild(headerCard);

  // Lines card
  const linesCard = document.createElement('div');
  linesCard.className = 'form-card';
  const linesTitle = document.createElement('h3');
  linesTitle.className = 'section-title';
  linesTitle.textContent = isEntry ? t('Journal Entry Lines') : t('Invoice Lines');
  linesCard.appendChild(linesTitle);

  const table = document.createElement('table');
  table.className = 'data-table invoice-lines-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  const colDefs = isEntry
    ? [[t('Description'), ''], [t('Account'), ''], [t('Debit'), 'text-right'], [t('Credit'), 'text-right'], ['', '']]
    : [[t('Description'), ''], [t('Account'), ''], [t('Unit Price'), 'text-right'],
       [t('Quantity'), 'text-right'], [t('Taxes'), ''], [t('Subtotal'), 'text-right'], ['', '']];
  colDefs.forEach(([txt, cls]) => {
    const th = document.createElement('th');
    th.textContent = txt;
    if (cls) th.className = cls;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  linesCard.appendChild(table);

  const addBtn = document.createElement('button');
  addBtn.className = 'btn btn-secondary';
  addBtn.style.marginTop = '8px';
  addBtn.textContent = t('+ Add Line');
  linesCard.appendChild(addBtn);
  container.appendChild(linesCard);

  // Totals — a single line for journal entries; untaxed / tax / total for invoices.
  const totalsCard = document.createElement('div');
  totalsCard.className = 'form-card totals-card';

  function _totalsRow(labelText, bold) {
    const row = document.createElement('div');
    row.className = 'totals-row';
    const lbl = document.createElement('span');
    lbl.className = 'totals-label';
    lbl.textContent = labelText;
    const val = document.createElement('span');
    val.className = 'totals-value' + (bold ? ' bold' : '');
    val.textContent = _fmt(0);
    row.appendChild(lbl);
    row.appendChild(val);
    totalsCard.appendChild(row);
    return val;
  }

  const untaxedEl = isEntry ? null : _totalsRow(t('Untaxed Amount'), false);
  const taxEl     = isEntry ? null : _totalsRow(t('Taxes'), false);
  const totalEl   = _totalsRow(isEntry ? t('Total Debit') : t('Total'), true);
  container.appendChild(totalsCard);

  const taxById = new Map(taxes.map(tx => [tx.id, tx]));

  function updateTotals() {
    if (isEntry) {
      const total = lines.reduce((s, l) => s + parseFloat(l.debit || 0), 0);
      totalEl.textContent = _fmt(total);
      return;
    }
    let untaxed = 0;
    const rawByTax = new Map();
    for (const l of lines) {
      const base = _lineSubtotal(l);
      untaxed += base;
      for (const tid of l.taxIds || []) {
        const tax = taxById.get(tid);
        if (!tax) continue;
        rawByTax.set(tid, (rawByTax.get(tid) || 0) + _taxAmount(tax, base, parseFloat(l.quantity || 0)));
      }
    }
    // Round-globally: one rounding per tax, then sum (ADR-003).
    let taxTotal = 0;
    for (const amt of rawByTax.values()) taxTotal += Math.round(amt * 100) / 100;
    untaxed = Math.round(untaxed * 100) / 100;
    untaxedEl.textContent = _fmt(untaxed);
    taxEl.textContent = _fmt(taxTotal);
    totalEl.textContent = _fmt(untaxed + taxTotal);
  }

  function addLine() {
    const line = { name: '', accountId: '', priceUnit: '', quantity: '1', taxIds: [], debit: '', credit: '' };
    lines.push(line);
    tbody.appendChild(_buildNewLineRow(line, accounts, taxes, lines, isEntry, updateTotals));
    updateTotals();
  }

  addBtn.onclick = addLine;
  if (existingLines.length > 0) {
    existingLines.filter(l => l.display_type === 'product').forEach(el => {
      const accId  = Array.isArray(el.account_id) ? el.account_id[0] : el.account_id;
      const debit  = parseFloat(el.debit  || 0);
      const credit = parseFloat(el.credit || 0);
      const gross  = Math.max(debit, credit);
      const qty    = parseFloat(el.quantity || 0) || 1;
      const unit   = parseFloat(el.price_unit || 0) || (gross ? gross / qty : 0);
      const line   = {
        name: el.name || '',
        accountId: String(accId || ''),
        priceUnit: isEntry ? '' : (unit ? String(unit) : ''),
        quantity: isEntry ? '1' : String(qty),
        taxIds: Array.isArray(el.tax_ids) ? el.tax_ids.slice() : [],
        debit:  isEntry && debit  ? String(debit)  : '',
        credit: isEntry && credit ? String(credit) : '',
      };
      lines.push(line);
      tbody.appendChild(_buildNewLineRow(line, accounts, taxes, lines, isEntry, updateTotals));
      updateTotals();
    });
  } else {
    addLine();
  }

  // Wire save callback and enable the button
  _saveForm = () => _saveNewInvoice(moveType, companyId, currencyId,
    partnerSel, journalSel, dateInput, refInput, lines, isEntry, editId);
  if (cp) {
    const saveBtn = cp.querySelector('.btn-primary');
    if (saveBtn) saveBtn.disabled = false;
  }
}

function _buildNewLineRow(line, accounts, taxes, lines, isEntry, onUpdate) {
  const tr = document.createElement('tr');

  const tdStyle = 'padding:4px 6px;border:1px solid rgba(0,0,0,.12);border-radius:3px;font-size:.875rem';

  // Description
  const descTd = document.createElement('td');
  const descInput = document.createElement('input');
  descInput.type = 'text';
  descInput.placeholder = t('Description');
  descInput.style.cssText = `width:100%;${tdStyle}`;
  descInput.value = line.name || '';
  descInput.oninput = () => { line.name = descInput.value; };
  descTd.appendChild(descInput);
  tr.appendChild(descTd);

  // Account
  const accTd = document.createElement('td');
  const accSel = document.createElement('select');
  accSel.style.cssText = `width:100%;min-width:160px;${tdStyle}`;
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = t('— Account —');
  accSel.appendChild(blank);
  accounts.forEach(a => {
    const opt = document.createElement('option');
    opt.value = a.id;
    opt.textContent = `${a.code} ${a.name}`;
    accSel.appendChild(opt);
  });
  if (line.accountId) accSel.value = String(line.accountId);
  accSel.onchange = () => { line.accountId = accSel.value; };
  accTd.appendChild(accSel);
  tr.appendChild(accTd);

  if (isEntry) {
    // Debit input
    const debitTd = document.createElement('td');
    debitTd.className = 'text-right';
    const debitInput = document.createElement('input');
    debitInput.type = 'number';
    debitInput.placeholder = '0.00';
    debitInput.min = '0';
    debitInput.step = '0.01';
    debitInput.style.cssText = `width:90px;text-align:right;${tdStyle}`;
    if (line.debit) debitInput.value = line.debit;
    debitInput.oninput = () => {
      line.debit = debitInput.value;
      if (debitInput.value) { line.credit = ''; creditInput.value = ''; }
      onUpdate();
    };
    debitTd.appendChild(debitInput);
    tr.appendChild(debitTd);

    // Credit input
    const creditTd = document.createElement('td');
    creditTd.className = 'text-right';
    const creditInput = document.createElement('input');
    creditInput.type = 'number';
    creditInput.placeholder = '0.00';
    creditInput.min = '0';
    creditInput.step = '0.01';
    creditInput.style.cssText = `width:90px;text-align:right;${tdStyle}`;
    if (line.credit) creditInput.value = line.credit;
    creditInput.oninput = () => {
      line.credit = creditInput.value;
      if (creditInput.value) { line.debit = ''; debitInput.value = ''; }
      onUpdate();
    };
    creditTd.appendChild(creditInput);
    tr.appendChild(creditTd);
  } else {
    // Unit Price
    const priceTd = document.createElement('td');
    priceTd.className = 'text-right';
    const priceInput = document.createElement('input');
    priceInput.type = 'number';
    priceInput.placeholder = '0.00';
    priceInput.step = '0.01';
    priceInput.style.cssText = `width:100px;text-align:right;${tdStyle}`;
    if (line.priceUnit) priceInput.value = line.priceUnit;
    priceTd.appendChild(priceInput);
    tr.appendChild(priceTd);

    // Quantity
    const qtyTd = document.createElement('td');
    qtyTd.className = 'text-right';
    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.placeholder = '1';
    qtyInput.step = 'any';
    qtyInput.min = '0';
    qtyInput.style.cssText = `width:70px;text-align:right;${tdStyle}`;
    qtyInput.value = line.quantity ?? '1';
    qtyTd.appendChild(qtyInput);
    tr.appendChild(qtyTd);

    // Taxes (all taxes available for the company's country / tax type)
    const taxTd = document.createElement('td');
    const taxSel = document.createElement('select');
    taxSel.multiple = true;
    taxSel.size = Math.min(Math.max(taxes.length, 1), 4);
    taxSel.style.cssText = `width:100%;min-width:150px;${tdStyle}`;
    if (taxes.length === 0) {
      const opt = document.createElement('option');
      opt.disabled = true;
      opt.textContent = t('— No taxes —');
      taxSel.appendChild(opt);
    }
    taxes.forEach(tx => {
      const opt = document.createElement('option');
      opt.value = tx.id;
      opt.textContent = tx.name;
      opt.selected = (line.taxIds || []).includes(tx.id);
      taxSel.appendChild(opt);
    });
    taxTd.appendChild(taxSel);
    tr.appendChild(taxTd);

    // Subtotal (read-only, live)
    const subTd = document.createElement('td');
    subTd.className = 'text-right';
    subTd.textContent = _fmt(_lineSubtotal(line));
    tr.appendChild(subTd);

    const refresh = () => {
      line.priceUnit = priceInput.value;
      line.quantity  = qtyInput.value;
      line.taxIds    = Array.from(taxSel.selectedOptions).map(o => parseInt(o.value, 10));
      subTd.textContent = _fmt(_lineSubtotal(line));
      onUpdate();
    };
    priceInput.oninput = refresh;
    qtyInput.oninput   = refresh;
    taxSel.onchange    = refresh;
  }

  // Remove button
  const removeTd = document.createElement('td');
  removeTd.style.width = '30px';
  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn btn-secondary';
  removeBtn.style.cssText = 'padding:2px 6px;font-size:.75rem';
  removeBtn.textContent = '✕';
  removeBtn.onclick = () => {
    const idx = lines.indexOf(line);
    if (idx !== -1) lines.splice(idx, 1);
    tr.remove();
    onUpdate();
  };
  removeTd.appendChild(removeBtn);
  tr.appendChild(removeTd);

  return tr;
}

async function _saveNewInvoice(moveType, companyId, currencyId, partnerSel, journalSel, dateInput, refInput, lines, isEntry, editId = null) {
  const partnerId   = parseInt(partnerSel.value, 10) || null;
  const journalId   = parseInt(journalSel.value, 10) || null;
  const invoiceDate = dateInput.value;
  const ref         = refInput.value.trim() || null;

  if (!journalId)               throw new Error(t('Please select a journal.'));
  if (!invoiceDate)             throw new Error(t('Please enter an invoice date.'));
  if (!isEntry && !partnerId)   throw new Error(t('Please select a customer or vendor.'));
  if (!editId && (!companyId || !currencyId)) throw new Error(t('Company or currency not found. Check server setup.'));

  const validLines = lines.filter(l => l.accountId && (
    isEntry
      ? (parseFloat(l.debit || 0) > 0 || parseFloat(l.credit || 0) > 0)
      : _lineSubtotal(l) > 0
  ));
  if (validLines.length === 0) {
    throw new Error(t('Please add at least one line with an account and amount.'));
  }

  const isRevenue = ['out_invoice', 'out_refund'].includes(moveType);

  async function _writeLines(targetId) {
    for (const line of validLines) {
      let debit, credit;
      const vals = {
        move_id:      targetId,
        display_type: 'product',
        name:         line.name || t('Service'),
        account_id:   parseInt(line.accountId, 10),
        date:         invoiceDate,
      };
      if (isEntry) {
        debit  = parseFloat(line.debit  || 0);
        credit = parseFloat(line.credit || 0);
      } else {
        const subtotal = _lineSubtotal(line);
        debit  = isRevenue ? 0        : subtotal;
        credit = isRevenue ? subtotal : 0;
        vals.quantity       = parseFloat(line.quantity || 1) || 1;
        vals.price_unit     = parseFloat(line.priceUnit || 0);
        vals.price_subtotal = subtotal;
        vals.tax_ids        = (line.taxIds || []).map(Number);
      }
      vals.debit  = debit;
      vals.credit = credit;
      await api.rpc('account.move.line', 'create', [vals]);
    }
  }

  async function _refreshTotals(targetId) {
    try {
      await api.rpc('account.move', 'recompute_totals', [[targetId]]);
    } catch { /* totals are recomputed authoritatively on posting */ }
  }

  if (editId) {
    await api.rpc('account.move', 'write', [[editId], {
      journal_id:   journalId,
      partner_id:   partnerId,
      invoice_date: invoiceDate,
      date:         invoiceDate,
      ref,
    }]);
    const oldLineIds = await api.rpc('account.move.line', 'search',
      [[['move_id', '=', editId], ['display_type', 'in', ['product', 'line_section', 'line_note']]]]);
    if (oldLineIds.length) await api.rpc('account.move.line', 'unlink', [oldLineIds]);
    await _writeLines(editId);
    await _refreshTotals(editId);
    App.navigate(`#/accounting/move/${editId}`);
    return;
  }

  const moveId = await api.rpc('account.move', 'create', [{
    move_type:    moveType,
    journal_id:   journalId,
    company_id:   companyId,
    currency_id:  currencyId,
    partner_id:   partnerId,
    invoice_date: invoiceDate,
    date:         invoiceDate,
    ref,
  }]);
  await _writeLines(moveId);
  await _refreshTotals(moveId);
  App.navigate(`#/accounting/move/${moveId}`);
}
