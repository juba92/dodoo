// Applicant form — details + Refuse (reason) + Create Employee (feature 006, US3).
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
function _field(value = '') {
  const i = document.createElement('input');
  i.type = 'text';
  i.value = value ?? '';
  return i;
}

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const isNew = id === 'new';
  const qsJob = params.job;

  let rec = { stage_id: null };
  if (!isNew) {
    rec = (await api.rpc('hr.applicant', 'read', [[Number(id)]]))[0] || rec;
  }

  const name = _field(rec.partner_name);
  const email = _field(rec.email_from);
  const phone = _field(rec.partner_phone);
  const job = _field(qsJob || (Array.isArray(rec.job_id) ? rec.job_id[0] : rec.job_id));
  job.type = 'number';
  const source = _field(Array.isArray(rec.source_id) ? rec.source_id[0] : rec.source_id);
  source.type = 'number';

  const form = document.createElement('form');
  form.className = 'o-form';
  form.append(
    _row(t('Candidate'), name),
    _row(t('Email'), email),
    _row(t('Phone'), phone),
    _row(t('Job Position'), job),
    _row(t('Source'), source),
  );

  if (!isNew) {
    const badge = document.createElement('span');
    badge.className = 'o-state-badge';
    badge.textContent = rec.refused ? t('Refused')
      : (Array.isArray(rec.stage_id) ? rec.stage_id[1] : t('In pipeline'));
    form.appendChild(_row(t('Status'), badge));
  }

  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    if (isNew) {
      const save = document.createElement('button');
      save.className = 'btn btn-primary';
      save.textContent = t('Create');
      save.onclick = async () => {
        try {
          const newId = await api.rpc('hr.applicant', 'create', [{
            partner_name: name.value,
            email_from: email.value || null,
            partner_phone: phone.value || null,
            job_id: Number(job.value),
            source_id: source.value ? Number(source.value) : null,
          }]);
          App.navigate(`#/hr/applicant/${newId}`);
        } catch (err) { _error(container, err.message); }
      };
      bar.appendChild(save);
    } else {
      if (!rec.refused && !rec.employee_id) {
        const refuse = document.createElement('button');
        refuse.className = 'btn btn-secondary';
        refuse.textContent = t('Refuse');
        refuse.onclick = async () => {
          const reasons = await api.rpc('hr.applicant.refuse.reason', 'search_read', [[]], { fields: ['name'] });
          const rid = reasons[0]?.id;
          if (!rid) return _error(container, t('No refusal reasons configured'));
          try {
            await api.post(`/hr/applicant/${id}/refuse`, { refuse_reason_id: rid });
            App.navigate(`#/hr/applicant/${id}`);
          } catch (err) { _error(container, err.message); }
        };
        bar.appendChild(refuse);

        const hire = document.createElement('button');
        hire.className = 'btn btn-primary';
        hire.textContent = t('Create Employee');
        hire.onclick = async () => {
          try {
            const res = await api.post(`/hr/applicant/${id}/create-employee`, {});
            App.navigate(`#/hr/employee/${res.employee_id}`);
          } catch (err) { _error(container, err.message); }
        };
        bar.appendChild(hire);
      }
    }
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('Back');
    back.onclick = () => App.navigate('#/hr/recruitment');
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
