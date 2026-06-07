import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';

const TYPE_LABEL = {
  out_invoice: 'Customer Invoice',  out_refund: 'Customer Credit Note',
  in_invoice:  'Vendor Bill',       in_refund:  'Vendor Credit Note',
  entry:        'Journal Entry',    out_receipt: 'Customer Receipt',
  in_receipt:  'Vendor Receipt',
};

function _fmt(v) {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parseFloat(v));
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
    await _renderNewInvoice(container, cp, params.moveType || 'out_invoice');
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
        'currency_id', 'reversed_entry_id'],
    });
    move = rows[0];
    if (!move) { container.textContent = 'Record not found.'; return; }
  } catch (err) {
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = 'Failed to load: ' + err.message;
    container.appendChild(el);
    return;
  }

  // Fetch product lines
  let lines = [];
  try {
    lines = await api.rpc('account.move.line', 'search_read',
      [[['move_id', '=', id], ['display_type', 'in', ['product', 'line_section', 'line_note']]]],
      { fields: ['id', 'name', 'account_id', 'debit', 'credit', 'display_type', 'sequence'], order: 'sequence asc' }
    );
  } catch { /* show empty lines */ }

  // Control panel
  if (cp) _buildCP(cp, move, id);

  // Status bar
  container.appendChild(_statusBar(move));

  // Header card
  container.appendChild(_headerCard(move));

  // Lines
  container.appendChild(_linesCard(lines));

  // Totals
  container.appendChild(_totalsCard(move));
}

function _buildCP(cp, move, id) {
  const { state, payment_state, move_type } = move;

  if (state === 'draft') {
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary';
    btn.textContent = 'Confirm';
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = 'Confirming…';
      const data = await _post(`/account/move/${id}/post`);
      if (data.error) { alert(data.error); btn.disabled = false; btn.textContent = 'Confirm'; return; }
      App.navigate(`#/accounting/move/${id}`);
    };
    cp.appendChild(btn);
  }

  if (state === 'posted' && ['not_paid', 'partial'].includes(payment_state) && move_type !== 'entry') {
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary';
    btn.textContent = 'Register Payment';
    btn.onclick = () => _paymentDialog(move, id);
    cp.appendChild(btn);
  }

  if (state === 'posted') {
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = move_type === 'entry' ? 'Reverse Entry' : 'Add Credit Note';
    btn.onclick = async () => {
      if (!confirm('Create a reversal/credit note?')) return;
      btn.disabled = true;
      const res = await fetch(`/account/move/${id}/reverse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': _tok() },
        body: JSON.stringify({ date: new Date().toISOString().substring(0, 10) }),
      });
      const data = await res.json();
      btn.disabled = false;
      if (data.result?.length) App.navigate(`#/accounting/move/${data.result[0]}`);
      else alert(data.error ?? 'Failed');
    };
    cp.appendChild(btn);
  }

  if (state === 'draft' || (state === 'posted' && payment_state === 'not_paid')) {
    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = 'Reset to Draft';
    btn.onclick = async () => {
      if (state === 'posted' && !confirm('Reset to draft? This unlocks the entry.')) return;
      btn.disabled = true;
      const data = await _post(`/account/move/${id}/reset_to_draft`);
      if (data.error) { alert(data.error); btn.disabled = false; return; }
      App.navigate(`#/accounting/move/${id}`);
    };
    cp.appendChild(btn);
  }
}

function _statusBar(move) {
  const bar = document.createElement('div');
  bar.className = 'status-bar';
  const { state, payment_state } = move;
  const steps = [
    { label: 'Draft',     active: state === 'draft' },
    { label: 'Confirmed', active: state === 'posted' },
    { label: 'Paid',      active: state === 'posted' && ['in_payment', 'paid'].includes(payment_state) },
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
  titleEl.textContent = (move.name && move.name !== '/') ? move.name : (TYPE_LABEL[move.move_type] ?? move.move_type);
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
    ['Customer / Vendor',  Array.isArray(move.partner_id) ? move.partner_id[1] : '—'],
    ['Journal',            Array.isArray(move.journal_id) ? move.journal_id[1] : '—'],
    ['Invoice Date',       _date(move.invoice_date)],
    ['Accounting Date',    _date(move.date)],
    ['Due Date',           _date(move.invoice_date_due)],
    ['Payment Terms',      Array.isArray(move.invoice_payment_term_id) ? move.invoice_payment_term_id[1] : '—'],
    ['Reference',          move.ref || '—'],
    ['Currency',           Array.isArray(move.currency_id) ? move.currency_id[1] : '—'],
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

function _linesCard(lines) {
  const card = document.createElement('div');
  card.className = 'form-card';

  const h = document.createElement('h3');
  h.className = 'section-title';
  h.textContent = 'Invoice Lines';
  card.appendChild(h);

  const table = document.createElement('table');
  table.className = 'data-table invoice-lines-table';

  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [['Description', ''], ['Account', ''], ['Debit', 'text-right'], ['Credit', 'text-right'], ['Balance', 'text-right']].forEach(([txt, cls]) => {
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
    td.colSpan = 5;
    td.className = 'empty-state';
    td.style.padding = '20px';
    td.textContent = 'No invoice lines.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    productLines.forEach(line => {
      const debit = parseFloat(line.debit || 0);
      const credit = parseFloat(line.credit || 0);
      const balance = debit - credit;
      const tr = document.createElement('tr');
      const cells = [
        { text: line.name || '—', cls: '' },
        { text: Array.isArray(line.account_id) ? line.account_id[1] : '—', cls: '' },
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
    { label: 'Untaxed Amount', value: _fmt(move.amount_untaxed) },
    { label: 'Taxes',          value: _fmt(move.amount_tax) },
    { label: 'Total',          value: _fmt(move.amount_total), bold: true },
    { label: 'Amount Due',     value: _fmt(move.amount_residual), bold: true,
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
  if (state === 'draft')  return { label: 'Draft',      cls: 'badge-draft' };
  if (state === 'cancel') return { label: 'Cancelled',  cls: 'badge-cancel' };
  if (paymentState === 'paid')     return { label: 'Paid',     cls: 'badge-paid' };
  if (paymentState === 'reversed') return { label: 'Reversed', cls: 'badge-cancel' };
  if (paymentState === 'partial')  return { label: 'Partial',  cls: 'badge-partial' };
  return { label: 'Confirmed', cls: 'badge-posted' };
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
  title.textContent = 'Register Payment';
  dialog.appendChild(title);

  const amountF = _field('Amount', 'number', String(parseFloat(move.amount_residual || 0).toFixed(2)));
  const dateF   = _field('Payment Date', 'date', new Date().toISOString().substring(0, 10));
  dialog.appendChild(amountF.wrap);
  dialog.appendChild(dateF.wrap);

  const jWrap = document.createElement('div');
  jWrap.className = 'form-field';
  const jLabel = document.createElement('label');
  jLabel.textContent = 'Journal';
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
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = () => overlay.remove();
  const payBtn = document.createElement('button');
  payBtn.className = 'btn btn-primary';
  payBtn.textContent = 'Pay';
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
      errEl.textContent = 'Please fill all fields.';
      errEl.style.display = 'block';
      return;
    }

    payBtn.disabled = true;
    payBtn.textContent = 'Processing…';
    errEl.style.display = 'none';

    try {
      const isOut    = ['in_invoice', 'in_refund'].includes(move.move_type);
      const partnerId = Array.isArray(move.partner_id) ? move.partner_id[0] : move.partner_id;
      const currencyId = Array.isArray(move.currency_id) ? move.currency_id[0] : move.currency_id;

      const paymentId = await api.rpc('account.payment', 'create', [{
        payment_type: isOut ? 'outbound' : 'inbound',
        partner_type: isOut ? 'supplier'  : 'customer',
        partner_id:   partnerId,
        journal_id:   journalId,
        amount,
        date,
        currency_id: currencyId,
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
      errEl.textContent = 'Payment failed: ' + err.message;
      errEl.style.display = 'block';
      payBtn.disabled = false;
      payBtn.textContent = 'Pay';
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

async function _renderNewInvoice(container, cp, moveType) {
  const typeLabel = TYPE_LABEL[moveType] ?? 'Invoice';
  const isEntry   = moveType === 'entry';

  // Load data in parallel
  let partners = [], journals = [], accounts = [];
  try {
    [partners, journals, accounts] = await Promise.all([
      api.rpc('res.partner', 'search_read', [[['active', '=', true]]],
        { fields: ['id', 'name'], limit: 200, order: 'name asc' }),
      api.rpc('account.journal', 'search_read', [[['type', 'in', _journalTypes(moveType)]]],
        { fields: ['id', 'name', 'type'] }),
      api.rpc('account.account', 'search_read',
        [[['active', '=', true], ..._accountDomain(moveType)]],
        { fields: ['id', 'code', 'name'], order: 'code asc', limit: 500 }),
    ]);
    // Fall back to all accounts if filter yields nothing
    if (accounts.length === 0) {
      accounts = await api.rpc('account.account', 'search_read',
        [[['active', '=', true]]], { fields: ['id', 'code', 'name'], order: 'code asc', limit: 500 });
    }
  } catch (err) {
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = 'Failed to load form data: ' + err.message;
    container.appendChild(el);
    return;
  }

  const lines = [];

  // ── Title ──
  const titleEl = document.createElement('h2');
  titleEl.className = 'invoice-number';
  titleEl.style.padding = '12px 24px 0';
  titleEl.textContent = `New ${typeLabel}`;
  container.appendChild(titleEl);

  // ── Header card ──
  const headerCard = document.createElement('div');
  headerCard.className = 'form-card invoice-header-card';
  const grid = document.createElement('div');
  grid.className = 'header-grid';

  // Partner
  const partnerSel = _inlineSelect(
    [['', isEntry ? '— Optional —' : '— Select partner —'], ...partners.map(p => [p.id, p.name])]
  );
  grid.appendChild(_headerRow(isEntry ? 'Partner (optional)' : 'Customer / Vendor', partnerSel));

  // Journal
  const journalSel = _inlineSelect(journals.map(j => [j.id, j.name]));
  grid.appendChild(_headerRow('Journal', journalSel));

  // Date
  const dateInput = _inlineInput('date', '');
  dateInput.value = new Date().toISOString().substring(0, 10);
  grid.appendChild(_headerRow('Invoice Date', dateInput));

  // Reference
  const refInput = _inlineInput('text', 'Optional');
  grid.appendChild(_headerRow('Reference', refInput));

  headerCard.appendChild(grid);
  container.appendChild(headerCard);

  // ── Lines card ──
  const linesCard = document.createElement('div');
  linesCard.className = 'form-card';

  const linesTitle = document.createElement('h3');
  linesTitle.className = 'section-title';
  linesTitle.textContent = isEntry ? 'Journal Entry Lines' : 'Invoice Lines';
  linesCard.appendChild(linesTitle);

  const table = document.createElement('table');
  table.className = 'data-table invoice-lines-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  const colDefs = isEntry
    ? [['Description', ''], ['Account', ''], ['Debit', 'text-right'], ['Credit', 'text-right'], ['', '']]
    : [['Description', ''], ['Account', ''], ['Amount', 'text-right'], ['', '']];
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
  addBtn.textContent = '+ Add Line';
  linesCard.appendChild(addBtn);
  container.appendChild(linesCard);

  // ── Totals ──
  const totalsCard = document.createElement('div');
  totalsCard.className = 'form-card totals-card';
  const totalsRow = document.createElement('div');
  totalsRow.className = 'totals-row';
  const totalsLbl = document.createElement('span');
  totalsLbl.className = 'totals-label';
  totalsLbl.textContent = isEntry ? 'Total Debit' : 'Subtotal';
  const subtotalEl = document.createElement('span');
  subtotalEl.className = 'totals-value bold';
  subtotalEl.textContent = _fmt(0);
  totalsRow.appendChild(totalsLbl);
  totalsRow.appendChild(subtotalEl);
  totalsCard.appendChild(totalsRow);
  container.appendChild(totalsCard);

  function updateTotals() {
    const total = lines.reduce((s, l) => {
      return s + (isEntry ? parseFloat(l.debit || 0) : parseFloat(l.amount || 0));
    }, 0);
    subtotalEl.textContent = _fmt(total);
  }

  function addLine() {
    const line = { name: '', accountId: '', amount: '', debit: '', credit: '' };
    lines.push(line);
    tbody.appendChild(_buildNewLineRow(line, accounts, lines, tbody, isEntry, updateTotals));
    updateTotals();
  }

  addBtn.onclick = addLine;
  addLine(); // start with one empty row

  // ── Control panel ──
  if (cp) {
    cp.innerHTML = '';
    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-primary';
    saveBtn.textContent = 'Save as Draft';
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving…';
      try {
        await _saveNewInvoice(moveType, partnerSel, journalSel, dateInput, refInput, lines, isEntry);
      } catch (err) {
        alert(err.message);
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save as Draft';
      }
    };
    const discardBtn = document.createElement('button');
    discardBtn.className = 'btn btn-secondary';
    discardBtn.textContent = 'Discard';
    discardBtn.onclick = () => history.back();
    cp.appendChild(saveBtn);
    cp.appendChild(discardBtn);
  }
}

function _buildNewLineRow(line, accounts, lines, tbody, isEntry, onUpdate) {
  const tr = document.createElement('tr');

  const tdStyle = 'padding:4px 6px;border:1px solid rgba(0,0,0,.12);border-radius:3px;font-size:.875rem';

  // Description
  const descTd = document.createElement('td');
  const descInput = document.createElement('input');
  descInput.type = 'text';
  descInput.placeholder = 'Description';
  descInput.style.cssText = `width:100%;${tdStyle}`;
  descInput.oninput = () => { line.name = descInput.value; };
  descTd.appendChild(descInput);
  tr.appendChild(descTd);

  // Account
  const accTd = document.createElement('td');
  const accSel = document.createElement('select');
  accSel.style.cssText = `width:100%;min-width:160px;${tdStyle}`;
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = '— Account —';
  accSel.appendChild(blank);
  accounts.forEach(a => {
    const opt = document.createElement('option');
    opt.value = a.id;
    opt.textContent = `${a.code} ${a.name}`;
    accSel.appendChild(opt);
  });
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
    creditInput.oninput = () => {
      line.credit = creditInput.value;
      if (creditInput.value) { line.debit = ''; debitInput.value = ''; }
      onUpdate();
    };
    creditTd.appendChild(creditInput);
    tr.appendChild(creditTd);
  } else {
    // Amount input
    const amtTd = document.createElement('td');
    amtTd.className = 'text-right';
    const amtInput = document.createElement('input');
    amtInput.type = 'number';
    amtInput.placeholder = '0.00';
    amtInput.min = '0';
    amtInput.step = '0.01';
    amtInput.style.cssText = `width:110px;text-align:right;${tdStyle}`;
    amtInput.oninput = () => { line.amount = amtInput.value; onUpdate(); };
    amtTd.appendChild(amtInput);
    tr.appendChild(amtTd);
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

async function _saveNewInvoice(moveType, partnerSel, journalSel, dateInput, refInput, lines, isEntry) {
  const partnerId  = parseInt(partnerSel.value, 10) || false;
  const journalId  = parseInt(journalSel.value, 10);
  const invoiceDate = dateInput.value;
  const ref        = refInput.value.trim();

  if (!journalId)   throw new Error('Please select a journal.');
  if (!invoiceDate) throw new Error('Please enter an invoice date.');
  if (!isEntry && !partnerId) throw new Error('Please select a customer or vendor.');

  const validLines = lines.filter(l => l.accountId && (
    isEntry
      ? (parseFloat(l.debit || 0) > 0 || parseFloat(l.credit || 0) > 0)
      : parseFloat(l.amount || 0) > 0
  ));
  if (validLines.length === 0) {
    throw new Error('Please add at least one line with an account and amount.');
  }

  const moveId = await api.rpc('account.move', 'create', [{
    move_type:    moveType,
    journal_id:   journalId,
    partner_id:   partnerId || false,
    invoice_date: invoiceDate,
    date:         invoiceDate,
    ref:          ref || false,
  }]);

  const isRevenue = ['out_invoice', 'out_refund'].includes(moveType);
  for (const line of validLines) {
    let debit, credit;
    if (isEntry) {
      debit  = parseFloat(line.debit  || 0);
      credit = parseFloat(line.credit || 0);
    } else {
      debit  = isRevenue ? 0                         : parseFloat(line.amount);
      credit = isRevenue ? parseFloat(line.amount)   : 0;
    }
    await api.rpc('account.move.line', 'create', [{
      move_id:      moveId,
      display_type: 'product',
      name:         line.name || 'Service',
      account_id:   parseInt(line.accountId, 10),
      debit,
      credit,
    }]);
  }

  App.navigate(`#/accounting/move/${moveId}`);
}
