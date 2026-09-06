import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const _EDITABLE_TYPES = new Set(['char', 'text', 'integer', 'float', 'boolean', 'date', 'datetime', 'many2one']);

function _inputType(fieldType) {
  switch (fieldType) {
    case 'integer':
    case 'float':   return 'number';
    case 'boolean': return 'checkbox';
    case 'date':    return 'date';
    case 'datetime': return 'datetime-local';
    default:        return 'text';
  }
}

function _displayValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? t('Yes') : t('No');
  if (Array.isArray(value)) return String(value[1] ?? value[0] ?? '');
  return String(value);
}

function _parseInputValue(input, fieldType) {
  if (fieldType === 'boolean') return input.checked;
  if (fieldType === 'integer') return parseInt(input.value, 10) || 0;
  if (fieldType === 'float') return parseFloat(input.value) || 0.0;
  if (fieldType === 'many2one') return parseInt(input.value, 10) || false;
  return input.value;
}

// Build a single field control
function _buildFieldControl(fieldName, fieldMeta, value, isNew) {
  const wrapper = document.createElement('div');
  wrapper.className = 'form-field';

  const label = document.createElement('label');
  label.htmlFor = `ff-${fieldName}`;
  label.textContent = fieldMeta.string ?? fieldName;
  if (fieldMeta.required) {
    const mark = document.createElement('span');
    mark.className = 'required-mark';
    mark.setAttribute('aria-hidden', 'true');
    mark.textContent = '*';
    label.appendChild(mark);
  }
  wrapper.appendChild(label);

  const errorEl = document.createElement('div');
  errorEl.className = 'field-error';
  errorEl.id = `ff-err-${fieldName}`;
  errorEl.setAttribute('aria-live', 'polite');

  if (fieldMeta.readonly && !isNew) {
    const span = document.createElement('span');
    span.className = 'field-readonly';
    span.id = `ff-${fieldName}`;
    span.setAttribute('data-field', fieldName);
    span.textContent = _displayValue(value);
    wrapper.appendChild(span);
  } else if (fieldMeta.type === 'text') {
    const ta = document.createElement('textarea');
    ta.id = `ff-${fieldName}`;
    ta.setAttribute('data-field', fieldName);
    ta.value = _displayValue(value);
    ta.setAttribute('aria-describedby', `ff-err-${fieldName}`);
    if (fieldMeta.required) ta.required = true;
    wrapper.appendChild(ta);
  } else if (fieldMeta.type === 'boolean') {
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.id = `ff-${fieldName}`;
    chk.setAttribute('data-field', fieldName);
    chk.checked = Boolean(value);
    wrapper.appendChild(chk);
  } else if (fieldMeta.type === 'many2one') {
    const inp = document.createElement('input');
    inp.type = 'number';
    inp.id = `ff-${fieldName}`;
    inp.setAttribute('data-field', fieldName);
    inp.value = Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '');
    inp.placeholder = t('Record ID');
    inp.setAttribute('aria-describedby', `ff-err-${fieldName}`);
    if (fieldMeta.required) inp.required = true;
    // Show related name as hint
    if (Array.isArray(value) && value[1]) {
      const hint = document.createElement('span');
      hint.style.fontSize = '.75rem';
      hint.style.color = 'var(--text-muted)';
      hint.textContent = _displayValue(value);
      wrapper.appendChild(inp);
      wrapper.appendChild(hint);
      wrapper.appendChild(errorEl);
      return wrapper;
    }
    wrapper.appendChild(inp);
  } else {
    const inp = document.createElement('input');
    inp.type = _inputType(fieldMeta.type);
    inp.id = `ff-${fieldName}`;
    inp.setAttribute('data-field', fieldName);
    inp.setAttribute('aria-describedby', `ff-err-${fieldName}`);
    if (fieldMeta.required) inp.required = true;
    if (fieldMeta.type !== 'boolean') {
      inp.value = _displayValue(value);
    }
    wrapper.appendChild(inp);
  }

  wrapper.appendChild(errorEl);
  return wrapper;
}

export async function render(container, params) {
  const { model, id } = params;
  const isNew = id === 'new';

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
      alert.textContent = t('Failed to load fields') + ': ' + err.message;
      container.appendChild(alert);
      return;
    }
  }

  // Fetch record data for existing records
  let record = {};
  let originalValues = {};
  if (!isNew) {
    try {
      const fieldNames = Object.keys(fields).filter(f => _EDITABLE_TYPES.has(fields[f].type) || fields[f].readonly);
      const results = await api.rpc(model, 'read', [[id]], { fields: fieldNames });
      record = results[0] ?? {};
      originalValues = { ...record };
    } catch (err) {
      const alert = document.createElement('div');
      alert.className = 'alert-error';
      alert.textContent = t('Failed to load record') + ': ' + err.message;
      container.appendChild(alert);
      return;
    }
  }

  // ── Status banner ───────────────────────────────────────────────────────────
  const statusBanner = document.createElement('div');
  statusBanner.id = 'form-status';
  statusBanner.style.display = 'none';
  container.appendChild(statusBanner);

  // ── Control panel: Save / Discard / Delete ────────────────────────────────────
  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn btn-primary';
  saveBtn.setAttribute('data-action', 'save');
  saveBtn.textContent = t('Save');

  const discardBtn = document.createElement('button');
  discardBtn.className = 'btn btn-secondary';
  discardBtn.setAttribute('data-action', 'discard');
  discardBtn.textContent = t('Discard');

  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    cp.appendChild(saveBtn);
    cp.appendChild(discardBtn);

    if (!isNew) {
      const spacer = document.createElement('div');
      spacer.className = 'o-cp-spacer';
      cp.appendChild(spacer);

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger';
      deleteBtn.setAttribute('data-action', 'delete');
      deleteBtn.textContent = t('Delete');
      cp.appendChild(deleteBtn);

      deleteBtn.onclick = async () => {
        if (!window.confirm(t('Delete record #{id}? This cannot be undone.', { id }))) return;
        try {
          await api.rpc(model, 'unlink', [[id]]);
          App.navigate(`#/model/${model}`);
        } catch (err) {
          _showBanner(statusBanner, 'error', t('Delete failed') + ': ' + err.message);
        }
      };
    }
  }

  // ── Form card ────────────────────────────────────────────────────────────────
  const formCard = document.createElement('div');
  formCard.className = 'form-card';

  const form = document.createElement('form');
  form.noValidate = true;
  form.setAttribute('aria-label', `${isNew ? 'New' : 'Edit'} ${model} record`);

  // Group fields (every 10 into a fieldset for wide models)
  const fieldEntries = Object.entries(fields).filter(
    ([name, meta]) => _EDITABLE_TYPES.has(meta.type) || meta.readonly
  );
  const GROUP_SIZE = 10;
  const groups = [];
  for (let i = 0; i < fieldEntries.length; i += GROUP_SIZE) {
    groups.push(fieldEntries.slice(i, i + GROUP_SIZE));
  }

  groups.forEach((group, gi) => {
    let fieldContainer;
    if (fieldEntries.length > GROUP_SIZE) {
      const fs = document.createElement('fieldset');
      fs.className = 'form-group';
      const legend = document.createElement('legend');
      const start = gi * GROUP_SIZE + 1;
      const end = Math.min((gi + 1) * GROUP_SIZE, fieldEntries.length);
      legend.textContent = t('Fields {start}–{end}', { start, end });
      fs.appendChild(legend);
      const grid = document.createElement('div');
      grid.className = 'field-grid';
      fs.appendChild(grid);
      form.appendChild(fs);
      fieldContainer = grid;
    } else {
      if (!form.querySelector('.field-grid')) {
        const grid = document.createElement('div');
        grid.className = 'field-grid';
        form.appendChild(grid);
      }
      fieldContainer = form.querySelector('.field-grid');
    }

    group.forEach(([fieldName, fieldMeta]) => {
      const ctrl = _buildFieldControl(fieldName, fieldMeta, record[fieldName], isNew);
      fieldContainer.appendChild(ctrl);
    });
  });

  formCard.appendChild(form);
  container.appendChild(formCard);

  // ── Collect dirty values ─────────────────────────────────────────────────────
  function _collectValues() {
    const vals = {};
    form.querySelectorAll('[data-field]').forEach(el => {
      const name = el.getAttribute('data-field');
      const meta = fields[name];
      if (!meta || meta.readonly) return;
      vals[name] = _parseInputValue(el, meta.type);
    });
    return vals;
  }

  function _clearErrors() {
    form.querySelectorAll('.field-error').forEach(el => (el.textContent = ''));
    form.querySelectorAll('[data-field]').forEach(el => el.removeAttribute('aria-invalid'));
  }

  function _validateRequired() {
    let valid = true;
    form.querySelectorAll('[data-field]').forEach(el => {
      const name = el.getAttribute('data-field');
      const meta = fields[name];
      if (!meta || meta.readonly) return;
      const errEl = document.getElementById(`ff-err-${name}`);
      if (meta.required && (el.value === '' || el.value === null)) {
        if (errEl) errEl.textContent = t('This field is required.');
        el.setAttribute('aria-invalid', 'true');
        valid = false;
      }
    });
    return valid;
  }

  // ── Save ─────────────────────────────────────────────────────────────────────
  saveBtn.onclick = async (e) => {
    e.preventDefault();
    _clearErrors();
    if (!_validateRequired()) {
      _showBanner(statusBanner, 'error', t('Please fill in all required fields.'));
      return;
    }
    const vals = _collectValues();
    try {
      if (isNew) {
        const newId = await api.rpc(model, 'create', [vals]);
        originalValues = { ...vals, id: newId };
        _showBanner(statusBanner, 'success', t('Record created successfully.'));
        App.navigate(`#/model/${model}/${newId}`);
      } else {
        await api.rpc(model, 'write', [[id], vals]);
        originalValues = { ...originalValues, ...vals };
        _showBanner(statusBanner, 'success', t('Settings saved.'));
      }
    } catch (err) {
      _showBanner(statusBanner, 'error', t('Save failed') + ': ' + err.message);
    }
  };

  // ── Discard ──────────────────────────────────────────────────────────────────
  discardBtn.onclick = () => {
    const h = window.location.hash;
    const listHash = h.startsWith('#/accounting/model/')
      ? `#/accounting/model/${model}`
      : `#/model/${model}`;
    App.navigate(listHash);
  };
}

function _showBanner(el, type, message) {
  el.className = type === 'success' ? 'success-banner' : type === 'error' ? 'alert-error' : '';
  el.textContent = message;
  el.style.display = message ? 'block' : 'none';
  if (message) {
    document.getElementById('status').textContent = message;
  }
}
