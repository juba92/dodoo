/**
 * Customer form (009-customer-database, US1/US3) — create/edit a customer's
 * master data (name, contact info, billing address, VAT, default payment
 * terms/currency) plus a read-only Accounts Receivable panel (balance +
 * invoice/credit-note/payment history with drill-down), modelled on
 * `account-form.js`'s field-input shape. Uses the dedicated `/account/partner`
 * routes (not the generic model CRUD) since `customer_rank`/
 * `property_currency_id`/`property_payment_term_id` aren't declared `Field`s
 * on `res.partner` (ADR-046) and the AR panel has no generic equivalent
 * (ADR-047/048).
 */
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatCurrency, formatDate } from '/web/static/i18n.js';

// Reuses invoice-list.js's existing badge palette rather than inventing a
// parallel status-color system.
const STATUS_BADGE = {
  paid: { label: 'Paid', cls: 'badge-paid' },
  partial: { label: 'Partial', cls: 'badge-partial' },
  open: { label: 'Open', cls: 'badge-posted' },
  cancelled: { label: 'Cancelled', cls: 'badge-cancel' },
};

const TYPE_LABEL = { invoice: 'Invoice', credit_note: 'Credit Note', payment: 'Payment' };

export async function render(container, params) {
  const id = params.id;
  const isNew = id === 'new';
  container.innerHTML = '';

  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';

  // ── Load record + reference data ───────────────────────────────────────
  let rec = {
    name: '', email: '', phone: '', street: '', city: '', state_id: null,
    zip: '', country_id: null, vat: '', active: true,
    property_payment_term_id: null, property_currency_id: null,
  };
  let countries = []; let states = []; let terms = []; let currencies = [];
  try {
    const jobs = [
      api.rpc('res.country', 'search_read', [[['active', '=', true]]], { fields: ['id', 'name'], order: 'name asc' }),
      api.rpc('res.country.state', 'search_read', [[]], { fields: ['id', 'name', 'country_id'], order: 'name asc' }),
      api.rpc('account.payment.term', 'search_read', [[['active', '=', true]]], { fields: ['id', 'name'], order: 'name asc' }),
      api.rpc('res.currency', 'search_read', [[['active', '=', true]]], { fields: ['id', 'name', 'code'], order: 'code asc' }),
    ];
    if (!isNew) jobs.push(api.get(`/account/partner/${id}`));
    const res = await Promise.all(jobs);
    [countries, states, terms, currencies] = res;
    if (!isNew) {
      rec = res[4];
      if (!rec) { container.textContent = t('Record not found.'); return; }
    }
  } catch (err) {
    const el = document.createElement('div');
    el.className = 'alert-error';
    el.textContent = t('Failed to load') + ': ' + err.message;
    container.appendChild(el);
    return;
  }

  // ── Title + banner ───────────────────────────────────────────────────────
  const title = document.createElement('h2');
  title.className = 'invoice-number';
  title.style.padding = '12px 24px 0';
  title.textContent = isNew ? t('New Customer') : (rec.name || '');
  container.appendChild(title);

  const banner = document.createElement('div');
  banner.id = 'customer-status';
  banner.style.display = 'none';
  banner.style.margin = '8px 24px 0';
  container.appendChild(banner);

  // ── Form card ────────────────────────────────────────────────────────────
  const card = document.createElement('div');
  card.className = 'form-card';
  const grid = document.createElement('div');
  grid.className = 'field-grid';
  card.appendChild(grid);
  container.appendChild(card);

  const nameInput = _text(grid, 'cust-name', t('Name'), rec.name || '', true);
  const emailInput = _text(grid, 'cust-email', t('Email'), rec.email || '', false);
  const phoneInput = _text(grid, 'cust-phone', t('Phone'), rec.phone || '', false);
  const streetInput = _text(grid, 'cust-street', t('Street'), rec.street || '', false);
  const cityInput = _text(grid, 'cust-city', t('City'), rec.city || '', false);
  const zipInput = _text(grid, 'cust-zip', t('ZIP'), rec.zip || '', false);

  const countrySel = document.createElement('select');
  countrySel.add(new Option('—', ''));
  countries.forEach(c => countrySel.add(new Option(c.name, String(c.id))));
  countrySel.value = rec.country_id ? String(rec.country_id) : '';
  _wrapField(grid, 'cust-country', t('Country'), countrySel, false);

  const stateSel = document.createElement('select');
  stateSel.add(new Option('—', ''));
  states.forEach(s => stateSel.add(new Option(s.name, String(s.id))));
  stateSel.value = rec.state_id ? String(rec.state_id) : '';
  _wrapField(grid, 'cust-state', t('State/Region'), stateSel, false);

  const vatInput = _text(grid, 'cust-vat', t('Tax/VAT Number'), rec.vat || '', false);

  const termSel = document.createElement('select');
  termSel.add(new Option(t('— Company default —'), ''));
  terms.forEach(pt => termSel.add(new Option(pt.name, String(pt.id))));
  termSel.value = rec.property_payment_term_id ? String(rec.property_payment_term_id) : '';
  _wrapField(grid, 'cust-term', t('Payment Terms'), termSel, false);

  const currSel = document.createElement('select');
  currSel.add(new Option(t('— Company default —'), ''));
  currencies.forEach(c => currSel.add(new Option(`${c.code} ${c.name || ''}`.trim(), String(c.id))));
  currSel.value = rec.property_currency_id ? String(rec.property_currency_id) : '';
  _wrapField(grid, 'cust-currency', t('Currency'), currSel, false);

  let archCb = null;
  if (!isNew) {
    const archWrap = document.createElement('div');
    archWrap.className = 'form-field';
    const archLabel = document.createElement('label');
    archLabel.htmlFor = 'cust-archived';
    archLabel.textContent = t('Archived');
    archCb = document.createElement('input');
    archCb.type = 'checkbox';
    archCb.id = 'cust-archived';
    archCb.checked = !rec.active;
    archWrap.append(archLabel, archCb);
    grid.appendChild(archWrap);
  }

  // ── Control panel: Save / Discard / Delete ────────────────────────────────
  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn btn-primary';
  saveBtn.textContent = t('Save');
  const discardBtn = document.createElement('button');
  discardBtn.className = 'btn btn-secondary';
  discardBtn.textContent = t('Discard');
  discardBtn.onclick = () => App.navigate('#/accounting/customers');
  const buttons = [saveBtn, discardBtn];

  let deleteBtn = null;
  if (!isNew) {
    deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-secondary';
    deleteBtn.textContent = t('Delete');
    deleteBtn.onclick = async () => {
      try {
        await api.rpc('res.partner', 'unlink', [[parseInt(id, 10)]]);
        App.navigate('#/accounting/customers');
      } catch (err) {
        _flash(banner, 'error', t('Delete failed') + ': ' + err.message);
      }
    };
    buttons.push(deleteBtn);
  }
  if (cp) cp.append(...buttons);

  saveBtn.onclick = async () => {
    const vals = {
      name: nameInput.value.trim(),
      email: emailInput.value.trim() || null,
      phone: phoneInput.value.trim() || null,
      street: streetInput.value.trim() || null,
      city: cityInput.value.trim() || null,
      country_id: countrySel.value ? parseInt(countrySel.value, 10) : null,
      state_id: stateSel.value ? parseInt(stateSel.value, 10) : null,
      zip: zipInput.value.trim() || null,
      vat: vatInput.value.trim() || null,
      property_payment_term_id: termSel.value ? parseInt(termSel.value, 10) : null,
      property_currency_id: currSel.value ? parseInt(currSel.value, 10) : null,
    };

    if (!vals.name) { _flash(banner, 'error', t('This field is required.') + ' — ' + t('Name')); return; }

    // Edge Cases: a duplicate VAT number is a non-blocking, advisory warning.
    if (vals.vat) {
      try {
        const dupes = await api.rpc('res.partner', 'search_read', [[['vat', '=', vals.vat]]], { fields: ['id'] });
        const others = dupes.filter(d => String(d.id) !== String(id));
        if (others.length) _flash(banner, 'warning', t('Another customer already uses this Tax/VAT number.'));
      } catch { /* advisory only — never blocks save */ }
    }

    saveBtn.disabled = true;
    saveBtn.textContent = t('Saving…');
    try {
      if (isNew) {
        const newId = await api.post('/account/partner', vals);
        App.navigate('#/accounting/customer/' + newId);
      } else {
        if (archCb) await api.rpc('res.partner', 'write', [[parseInt(id, 10)], { active: !archCb.checked }]);
        await api.patch(`/account/partner/${id}`, vals);
        render(container, params); // reload with fresh data
      }
    } catch (err) {
      _flash(banner, 'error', t('Save failed') + ': ' + err.message);
      saveBtn.disabled = false;
      saveBtn.textContent = t('Save');
    }
  };

  // ── Accounts Receivable panel (existing customers only) ───────────────────
  if (!isNew) {
    const heading = document.createElement('h3');
    heading.style.margin = '24px 24px 0';
    heading.textContent = t('Accounts Receivable');
    container.appendChild(heading);

    try {
      const ledger = await api.get(`/account/partner/${id}/ar-ledger`);
      const box = document.createElement('div');
      box.className = 'report-summary account-balance-box';
      box.style.margin = '8px 24px';
      const span = document.createElement('span');
      const strong = document.createElement('strong');
      strong.textContent = formatCurrency(parseFloat(ledger.balance || 0));
      span.append(document.createTextNode(t('Outstanding Balance') + ': '), strong);
      box.appendChild(span);
      container.appendChild(box);

      const table = document.createElement('table');
      table.className = 'data-table';
      table.style.margin = '0 24px';
      const thead = document.createElement('thead');
      thead.innerHTML = `<tr><th>${t('Date')}</th><th>${t('Type')}</th><th>${t('Reference')}</th><th>${t('Amount')}</th><th>${t('Status')}</th></tr>`;
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      if (!ledger.lines || !ledger.lines.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.textContent = t('No invoices, credit notes, or payments yet.');
        tr.appendChild(td);
        tbody.appendChild(tr);
      } else {
        ledger.lines.forEach(line => {
          const tr = document.createElement('tr');
          const refTd = document.createElement('td');
          const link = document.createElement('a');
          link.href = '#';
          link.textContent = line.reference || '—';
          link.onclick = (ev) => { ev.preventDefault(); App.navigate(`#/accounting/move/${line.move_id}`); };
          refTd.appendChild(link);
          tr.innerHTML = `<td>${formatDate(line.date)}</td><td>${t(TYPE_LABEL[line.type] || line.type)}</td>`;
          tr.appendChild(refTd);
          const amtTd = document.createElement('td');
          amtTd.textContent = formatCurrency(parseFloat(line.amount || 0));
          tr.appendChild(amtTd);
          const statusTd = document.createElement('td');
          const badge = STATUS_BADGE[line.status] || { label: line.status, cls: 'badge-posted' };
          const badgeSpan = document.createElement('span');
          badgeSpan.className = `badge ${badge.cls}`;
          badgeSpan.textContent = t(badge.label);
          statusTd.appendChild(badgeSpan);
          tr.appendChild(statusTd);
          tbody.appendChild(tr);
        });
      }
      table.appendChild(tbody);
      container.appendChild(table);
    } catch (err) {
      const el = document.createElement('div');
      el.className = 'alert-error';
      el.style.margin = '8px 24px';
      el.textContent = t('Failed to load Accounts Receivable data') + ': ' + err.message;
      container.appendChild(el);
    }
  }
}

// ── helpers ───────────────────────────────────────────────────────────────
// Explicit label/for + id association (not just sibling placement) — matches
// web/static/views/form.js's proven `ff-${fieldName}` pattern; account-form.js's
// older _wrapField predates that pattern and doesn't associate labels at all.
function _wrapField(grid, fieldId, labelText, control, required) {
  const wrap = document.createElement('div');
  wrap.className = 'form-field';
  const label = document.createElement('label');
  label.htmlFor = fieldId;
  label.textContent = labelText;
  if (required) {
    const m = document.createElement('span');
    m.className = 'required-mark';
    m.setAttribute('aria-hidden', 'true');
    m.textContent = '*';
    label.appendChild(m);
  }
  control.id = fieldId;
  wrap.append(label, control);
  grid.appendChild(wrap);
  return control;
}

function _text(grid, fieldId, labelText, value, required) {
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.value = value;
  if (required) inp.required = true;
  return _wrapField(grid, fieldId, labelText, inp, required);
}

function _flash(banner, kind, msg) {
  banner.className = kind === 'error' ? 'alert-error' : (kind === 'warning' ? 'alert-warning' : 'success-banner');
  banner.textContent = msg;
  banner.style.display = 'block';
}
