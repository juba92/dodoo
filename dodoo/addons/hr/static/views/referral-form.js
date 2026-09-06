// Referral — refer a candidate to a published job + "My Referrals" list (feature 006, US5).
// #/hr/referral/new  → submit form
// #/hr/referrals     → my referrals list with live status
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

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

export async function render(container, params) {
  container.innerHTML = '';
  if (params.mode === 'list') {
    await _list(container);
    return;
  }

  const jobs = await api.rpc('hr.job', 'search_read', [[['is_published', '=', true]]], { fields: ['name'] });
  const job = document.createElement('select');
  jobs.forEach(j => {
    const o = document.createElement('option');
    o.value = j.id;
    o.textContent = j.name;
    job.appendChild(o);
  });
  const name = document.createElement('input');
  name.type = 'text';
  const email = document.createElement('input');
  email.type = 'email';
  const phone = document.createElement('input');
  phone.type = 'text';

  const form = document.createElement('form');
  form.className = 'o-form';
  form.append(
    _row(t('Published Job'), job),
    _row(t('Candidate name'), name),
    _row(t('Candidate email'), email),
    _row(t('Candidate phone'), phone),
  );
  if (!jobs.length) {
    form.prepend(Object.assign(document.createElement('p'), { className: 'empty-state', textContent: t('No published jobs to refer to.') }));
  }

  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const go = document.createElement('button');
    go.className = 'btn btn-primary';
    go.textContent = t('Submit Referral');
    go.disabled = !jobs.length;
    go.onclick = async () => {
      try {
        await api.post('/hr/referral/submit', {
          job_id: Number(job.value),
          candidate_name: name.value,
          candidate_email: email.value || null,
          candidate_phone: phone.value || null,
        });
        App.navigate('#/hr/referrals');
      } catch (err) { _error(container, err.message); }
    };
    bar.appendChild(go);
  }
  container.appendChild(form);
}

async function _list(container) {
  const refs = await api.rpc('hr.referral', 'get_my_referrals', [], {});
  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const nb = document.createElement('button');
    nb.className = 'btn btn-primary';
    nb.textContent = t('Refer a Friend');
    nb.onclick = () => App.navigate('#/hr/referral/new');
    bar.appendChild(nb);
  }
  if (!refs.length) {
    container.appendChild(Object.assign(document.createElement('div'), { className: 'empty-state', textContent: t('No referrals yet') }));
    return;
  }
  const table = document.createElement('table');
  table.className = 'data-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [t('Candidate'), t('Job'), t('Status')].forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);
  const tb = document.createElement('tbody');
  refs.forEach(r => {
    const tr = document.createElement('tr');
    [r.candidate_name, Array.isArray(r.job_id) ? r.job_id[1] : r.job_id, t(r.status)].forEach(v => {
      const td = document.createElement('td');
      td.textContent = v ?? '';
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  table.appendChild(tb);
  container.appendChild(table);
}
