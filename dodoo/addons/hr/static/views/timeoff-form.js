// Time Off request form — live duration preview + Approve/Refuse actions (feature 006).
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

function _row(label, el) {
  const r = document.createElement('div');
  r.className = 'o-form-row';
  const l = document.createElement('label');
  l.textContent = label;
  r.append(l, el);
  return r;
}

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const isNew = id === 'new';

  let rec = { state: 'to_approve' };
  if (!isNew) {
    rec = (await api.rpc('hr.leave', 'read', [[Number(id)]]))[0] || rec;
  }

  const form = document.createElement('form');
  form.className = 'o-form';

  const empSel = document.createElement('input');
  empSel.type = 'number';
  empSel.placeholder = t('Employee ID');
  empSel.value = Array.isArray(rec.employee_id) ? rec.employee_id[0] : (rec.employee_id ?? '');
  const typeSel = document.createElement('input');
  typeSel.type = 'number';
  typeSel.placeholder = t('Leave Type ID');
  typeSel.value = Array.isArray(rec.leave_type_id) ? rec.leave_type_id[0] : (rec.leave_type_id ?? '');
  const from = document.createElement('input');
  from.type = 'date';
  from.value = rec.date_from ? String(rec.date_from).slice(0, 10) : '';
  const to = document.createElement('input');
  to.type = 'date';
  to.value = rec.date_to ? String(rec.date_to).slice(0, 10) : '';

  const preview = document.createElement('output');
  preview.className = 'o-duration-preview';
  preview.textContent = rec.number_of_units ? `${rec.number_of_units} ${t('unit(s)')}` : '';

  async function refreshPreview() {
    if (!empSel.value || !from.value || !to.value) return;
    try {
      const res = await api.rpc('hr.leave', 'get_duration_preview', [], {
        employee_id: Number(empSel.value),
        date_from: from.value,
        date_to: to.value,
        unit: 'day',
      });
      preview.textContent = `${res.units} ${t('working day(s)')}`;
    } catch { preview.textContent = ''; }
  }
  [empSel, from, to].forEach(el => el.addEventListener('change', refreshPreview));

  form.append(
    _row(t('Employee'), empSel),
    _row(t('Leave Type'), typeSel),
    _row(t('From'), from),
    _row(t('To'), to),
    _row(t('Duration'), preview),
  );

  if (!isNew) {
    const badge = document.createElement('span');
    badge.className = 'o-state-badge';
    badge.textContent = t(rec.state);   // text, not colour-only
    form.appendChild(_row(t('Status'), badge));
  }

  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    if (isNew) {
      const submit = document.createElement('button');
      submit.className = 'btn btn-primary';
      submit.textContent = t('Submit');
      submit.onclick = async () => {
        try {
          const newId = await api.rpc('hr.leave', 'create', [{
            employee_id: Number(empSel.value),
            leave_type_id: Number(typeSel.value),
            date_from: from.value + 'T00:00:00',
            date_to: to.value + 'T23:59:59',
          }]);
          App.navigate(`#/hr/timeoff/${newId}`);
        } catch (err) {
          _error(container, err.message);
        }
      };
      bar.appendChild(submit);
    } else if (rec.state === 'to_approve' || rec.state === 'second_approval') {
      const approve = document.createElement('button');
      approve.className = 'btn btn-primary';
      approve.textContent = t('Approve');
      approve.onclick = () => _act(`/hr/leave/${id}/approve`, { expected_state: rec.state }, container);
      const refuse = document.createElement('button');
      refuse.className = 'btn btn-secondary';
      refuse.textContent = t('Refuse');
      refuse.onclick = () => _act(`/hr/leave/${id}/refuse`, { expected_state: rec.state, reason: '' }, container);
      bar.append(approve, refuse);
    }
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('Back');
    back.onclick = () => App.navigate('#/hr/timeoff');
    bar.appendChild(back);
  }

  container.appendChild(form);
}

function _error(container, msg) {
  const e = document.createElement('div');
  e.className = 'alert-error';
  e.textContent = t('Error') + ': ' + msg;
  container.prepend(e);
}

async function _act(url, body, container) {
  try {
    await api.post(url, body);
    App.navigate('#/hr/timeoff');
  } catch (err) {
    _error(container, err.message);
  }
}
