// Employee form — Personal / Work / Private / HR Settings tabs + skills + org chart
// (feature 006, FR-001 / FR-008). Field labels come translated from fields_get.
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { mount as mountOrgChart } from '/hr/static/views/org-chart.js';

const TABS = {
  Work: ['work_email', 'work_phone', 'department_id', 'job_id', 'job_title',
         'work_location', 'manager_id', 'coach_id', 'company_id'],
  Personal: ['gender', 'birthday', 'marital', 'private_email', 'private_phone',
             'emergency_contact', 'emergency_phone'],
  Private: ['country_id', 'identification_id', 'bank_account', 'home_address',
            'dependant_count'],
  'HR Settings': ['user_id', 'active', 'next_appraisal_date', 'appraisal_frequency_months'],
};

function _display(v) {
  if (v === null || v === undefined || v === false) return '';
  if (Array.isArray(v)) return String(v[1] ?? v[0] ?? '');
  return String(v);
}

// One .form-field control (label + '*' + input), mirroring the generic form view.
function _field(name, meta, value, isNew) {
  const wrap = document.createElement('div');
  wrap.className = 'form-field';

  const label = document.createElement('label');
  label.htmlFor = 'f_' + name;
  label.textContent = meta.string || name;
  if (meta.required) {
    const star = document.createElement('span');
    star.className = 'required-mark';
    star.setAttribute('aria-hidden', 'true');
    star.textContent = '*';
    label.appendChild(star);
  }
  wrap.appendChild(label);

  let el;
  const type = meta.type;
  if (type === 'boolean') {
    el = document.createElement('input');
    el.type = 'checkbox';
    el.checked = value === undefined ? (meta.default ?? false) : !!value;
  } else if (type === 'text') {
    el = document.createElement('textarea');
    el.value = _display(value);
  } else if (type === 'many2one') {
    el = document.createElement('input');
    el.type = 'number';
    el.placeholder = t('Record ID');
    el.value = Array.isArray(value) ? String(value[0] ?? '') : (value ?? '');
    if (Array.isArray(value) && value[1]) {
      const hint = document.createElement('span');
      hint.className = 'field-hint';
      hint.textContent = value[1];
      wrap.dataset.hint = '1';
      el.dataset.name = name;
      wrap.appendChild(el);
      wrap.appendChild(hint);
      el.id = 'f_' + name;
      el.dataset.field = name;
      el.dataset.ftype = type;
      if (meta.required) el.required = true;
      el.setAttribute('aria-required', String(!!meta.required));
      return wrap;
    }
  } else if (type === 'date') {
    el = document.createElement('input');
    el.type = 'date';
    el.value = value ? String(value).slice(0, 10) : '';
  } else if (type === 'integer' || type === 'float') {
    el = document.createElement('input');
    el.type = 'number';
    el.value = value ?? '';
  } else {
    el = document.createElement('input');
    el.type = 'text';
    el.value = _display(value);
  }
  el.id = 'f_' + name;
  el.dataset.field = name;
  el.dataset.ftype = type;
  if (meta.required) el.required = true;
  el.setAttribute('aria-required', String(!!meta.required));
  wrap.appendChild(el);
  return wrap;
}

function _collect(form) {
  const vals = {};
  form.querySelectorAll('[data-field]').forEach(el => {
    const name = el.dataset.field;
    const ft = el.dataset.ftype;
    if (ft === 'boolean') { vals[name] = el.checked; return; }
    const raw = el.value.trim();
    if (raw === '') { vals[name] = null; return; }
    if (ft === 'many2one' || ft === 'integer') vals[name] = parseInt(raw, 10);
    else if (ft === 'float') vals[name] = parseFloat(raw);
    else vals[name] = raw;
  });
  return vals;
}

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const isNew = id === 'new';

  const fmeta = await api.rpc('hr.employee', 'fields_get', [], {
    attributes: ['string', 'type', 'required', 'readonly', 'relation'],
  });

  let rec = {};
  if (isNew) {
    // default company_id → the (single) company, so a required FK is never left null
    try {
      const co = await api.rpc('res.company', 'search_read', [[]], { fields: ['id'], limit: 1 });
      if (co[0]) rec.company_id = co[0].id;
    } catch { /* leave blank — user picks it */ }
    rec.active = true;
  } else {
    rec = (await api.rpc('hr.employee', 'read', [[Number(id)]]))[0] || {};
  }

  const form = document.createElement('form');
  form.className = 'o-form';

  // Title (the record name)
  const titleWrap = document.createElement('div');
  titleWrap.className = 'form-field o-form-title';
  const tLabel = document.createElement('label');
  tLabel.htmlFor = 'f_name';
  tLabel.textContent = fmeta.name.string || t('Name');
  const star = document.createElement('span');
  star.className = 'required-mark';
  star.textContent = '*';
  tLabel.appendChild(star);
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.id = 'f_name';
  nameInput.dataset.field = 'name';
  nameInput.dataset.ftype = 'char';
  nameInput.required = true;
  nameInput.value = rec.name || '';
  nameInput.placeholder = t('Name');
  titleWrap.append(tLabel, nameInput);
  form.appendChild(titleWrap);

  // Tabs
  const tabBar = document.createElement('div');
  tabBar.className = 'o-form-tabbar';
  tabBar.setAttribute('role', 'tablist');
  form.appendChild(tabBar);

  const panels = {};
  Object.entries(TABS).forEach(([key, names], i) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'o-form-tab';
    btn.textContent = t(key);
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
    btn.id = 'tab_' + i;
    tabBar.appendChild(btn);

    const panel = document.createElement('div');
    panel.className = 'o-form-panel field-grid';
    panel.setAttribute('role', 'tabpanel');
    panel.hidden = i !== 0;
    names.forEach(n => {
      if (fmeta[n]) panel.appendChild(_field(n, fmeta[n], rec[n], isNew));
    });
    form.appendChild(panel);
    panels[key] = { btn, panel };

    btn.onclick = () => {
      Object.values(panels).forEach(p => {
        p.panel.hidden = true;
        p.btn.setAttribute('aria-selected', 'false');
      });
      panel.hidden = false;
      btn.setAttribute('aria-selected', 'true');
    };
  });

  // Skills
  if (!isNew) {
    const box = document.createElement('section');
    box.className = 'o-form-section';
    box.appendChild(Object.assign(document.createElement('h3'), { textContent: t('Skills') }));
    try {
      const skills = await api.rpc('hr.employee.skill', 'search_read',
        [[['employee_id', '=', Number(id)]]],
        { fields: ['skill_id', 'skill_level_id'] });
      if (skills.length) {
        const ul = document.createElement('ul');
        skills.forEach(s => {
          const li = document.createElement('li');
          li.textContent = `${_display(s.skill_id)} — ${_display(s.skill_level_id)}`;
          ul.appendChild(li);
        });
        box.appendChild(ul);
      } else {
        box.appendChild(Object.assign(document.createElement('p'),
          { className: 'muted', textContent: t('No skills recorded') }));
      }
    } catch { /* ignore */ }
    form.appendChild(box);
  }

  // Appraisal history
  if (!isNew) {
    try {
      const hist = await api.rpc('hr.appraisal', 'get_history', [], { employee_id: Number(id) });
      if (hist.length) {
        const box = document.createElement('section');
        box.className = 'o-form-section';
        box.appendChild(Object.assign(document.createElement('h3'),
          { textContent: t('Appraisal history') }));
        const ul = document.createElement('ul');
        hist.forEach(a => {
          const li = document.createElement('li');
          li.textContent = `${a.date_close || t('open')} — ${t(a.state)}`;
          ul.appendChild(li);
        });
        box.appendChild(ul);
        form.appendChild(box);
      }
    } catch { /* ignore */ }
  }

  // Org chart
  if (!isNew) {
    const box = document.createElement('section');
    box.className = 'o-form-section';
    box.appendChild(Object.assign(document.createElement('h3'),
      { textContent: t('Organisation chart') }));
    const mountEl = document.createElement('div');
    box.appendChild(mountEl);
    form.appendChild(box);
    mountOrgChart(mountEl, Number(id));
  }

  // Actions
  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const save = document.createElement('button');
    save.className = 'btn btn-primary';
    save.type = 'button';
    save.textContent = t('Save');
    save.onclick = async () => {
      _clearError(container);
      if (!nameInput.value.trim()) {
        nameInput.focus();
        return _error(container, t('Name') + ' ' + t('is required'));
      }
      const vals = _collect(form);
      try {
        if (isNew) {
          const newId = await api.rpc('hr.employee', 'create', [vals]);
          App.navigate(`#/hr/employee/${newId}`);
        } else {
          await api.rpc('hr.employee', 'write', [[Number(id)], vals]);
          App.navigate('#/hr/employees');
        }
      } catch (err) {
        _error(container, t('Save failed') + ': ' + err.message);
      }
    };
    const discard = document.createElement('button');
    discard.className = 'btn btn-secondary';
    discard.type = 'button';
    discard.textContent = t('Discard');
    discard.onclick = () => App.navigate('#/hr/employees');
    bar.append(save, discard);
  }

  container.appendChild(form);
}

function _error(container, msg) {
  _clearError(container);
  const e = document.createElement('div');
  e.className = 'alert-error';
  e.id = 'o-form-error';
  e.textContent = msg;
  container.prepend(e);
}
function _clearError(container) {
  container.querySelector('#o-form-error')?.remove();
}
