// Appraisal form — state actions + per-side feedback with visibility toggles (feature 006).
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const NEXT = {
  new: ['pending_confirmation', 'cancelled'],
  pending_confirmation: ['confirmed', 'cancelled'],
  confirmed: ['done', 'cancelled'],
};

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const isNew = id === 'new';

  if (isNew) {
    await _launcher(container);
    return;
  }

  const rec = (await api.rpc('hr.appraisal', 'read', [[Number(id)]]))[0];
  if (!rec) { container.textContent = t('Not found'); return; }

  const head = document.createElement('div');
  head.className = 'o-form-row';
  const badge = document.createElement('span');
  badge.className = 'o-state-badge';
  badge.textContent = t(rec.state);
  head.append(Object.assign(document.createElement('label'), { textContent: t('Status') }), badge);
  container.appendChild(head);

  // Feedback rows the caller is allowed to see (model layer filters hidden opposite-side rows).
  const feedback = await api.rpc('hr.appraisal.feedback', 'search_read',
    [[['appraisal_id', '=', Number(id)]]],
    { fields: ['side', 'section_title', 'content', 'is_visible'] });

  ['employee', 'manager'].forEach(side => {
    const box = document.createElement('section');
    box.className = 'o-form-panel';
    const h = document.createElement('h3');
    h.textContent = side === 'employee' ? t('Employee feedback') : t('Manager feedback');
    box.appendChild(h);
    feedback.filter(f => f.side === side).forEach(f => {
      const row = document.createElement('div');
      row.className = 'o-form-row';
      const lab = document.createElement('label');
      lab.textContent = f.section_title || '';
      const ta = document.createElement('textarea');
      ta.value = f.content || '';
      const vis = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!f.is_visible;
      vis.append(cb, document.createTextNode(' ' + t('Visible to the other side')));
      const saveBtn = document.createElement('button');
      saveBtn.type = 'button';
      saveBtn.className = 'btn btn-secondary';
      saveBtn.textContent = t('Save');
      saveBtn.onclick = async () => {
        try {
          await api.rpc('hr.appraisal.feedback', 'write',
            [[f.id], { content: ta.value, is_visible: cb.checked }]);
          App.navigate(`#/hr/appraisal/${id}`);
        } catch (err) { _error(container, err.message); }
      };
      row.append(lab, ta, vis, saveBtn);
      box.appendChild(row);
    });
    container.appendChild(box);
  });

  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    (NEXT[rec.state] || []).forEach(s => {
      const b = document.createElement('button');
      b.className = s === 'cancelled' ? 'btn btn-secondary' : 'btn btn-primary';
      b.textContent = t(s);
      b.onclick = async () => {
        try {
          await api.post(`/hr/appraisal/${id}/set-state`, { state: s, expected_state: rec.state });
          App.navigate(`#/hr/appraisal/${id}`);
        } catch (err) { _error(container, err.message); }
      };
      bar.appendChild(b);
    });
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('Back');
    back.onclick = () => App.navigate('#/hr/appraisals');
    bar.appendChild(back);
  }
}

async function _launcher(container) {
  const templates = await api.rpc('hr.appraisal.template', 'search_read', [[]], { fields: ['name'] });
  const emp = document.createElement('input');
  emp.type = 'number';
  emp.placeholder = t('Employee ID');
  const sel = document.createElement('select');
  templates.forEach(tpl => {
    const o = document.createElement('option');
    o.value = tpl.id;
    o.textContent = tpl.name;
    sel.appendChild(o);
  });
  const form = document.createElement('form');
  form.className = 'o-form';
  form.append(
    _row(t('Employee'), emp),
    _row(t('Template'), sel),
  );
  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const go = document.createElement('button');
    go.className = 'btn btn-primary';
    go.textContent = t('Launch');
    go.onclick = async () => {
      try {
        const res = await api.post('/hr/appraisal/launch',
          { employee_id: Number(emp.value), template_id: Number(sel.value) });
        App.navigate(`#/hr/appraisal/${res.appraisal_id}`);
      } catch (err) { _error(container, err.message); }
    };
    bar.appendChild(go);
  }
  container.appendChild(form);
}

function _row(label, el) {
  const r = document.createElement('div');
  r.className = 'o-form-row';
  r.append(Object.assign(document.createElement('label'), { textContent: label }), el);
  return r;
}
function _error(container, msg) {
  const e = document.createElement('div');
  e.className = 'alert-error';
  e.textContent = t('Error') + ': ' + msg;
  container.prepend(e);
}
