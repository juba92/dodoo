// Recruitment pipeline — applicants grouped by stage, drag + keyboard "Move to…" (feature 006).
// #/hr/recruitment            → job picker (published-first)
// #/hr/recruitment/:jobId     → the Kanban for one job
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { render as renderKanban } from '/web/static/views/kanban.js';

export async function render(container, params) {
  container.innerHTML = '';
  const jobId = params.jobId;

  if (!jobId) {
    await _jobPicker(container);
    return;
  }

  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const nb = document.createElement('button');
    nb.className = 'btn btn-primary';
    nb.textContent = t('New Applicant');
    nb.onclick = () => App.navigate(`#/hr/applicant/new?job=${jobId}`);
    cp.appendChild(nb);
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('All Jobs');
    back.onclick = () => App.navigate('#/hr/recruitment');
    cp.appendChild(back);
  }

  // Stage columns from get_pipeline (ordered by sequence).
  let pipeline;
  try {
    pipeline = await api.rpc('hr.applicant', 'get_pipeline', [], { job_id: Number(jobId) });
  } catch (err) {
    container.textContent = t('Error') + ': ' + err.message;
    return;
  }
  const columns = pipeline.stages.map(s => ({ value: s.id, label: s.name }));

  await renderKanban(container, {
    model: 'hr.applicant',
    groupBy: 'stage_id',
    columns,
    cardFields: ['partner_name', 'email_from', 'partner_phone'],
    domain: [['job_id', '=', Number(jobId)], ['refused', '=', false]],
    moveEndpoint: '/hr/applicant/{id}/set-stage',
    moveField: 'stage',
    formRoute: id => `#/hr/applicant/${id}`,
    hash: `#/hr/recruitment/${jobId}`,
  });
}

async function _jobPicker(container) {
  const jobs = await api.rpc('hr.job', 'search_read', [[]], {
    fields: ['name', 'is_published', 'department_id'],
    order: 'is_published desc, name',
  });
  const ul = document.createElement('ul');
  ul.className = 'sidebar-list';
  jobs.forEach(j => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = (j.is_published ? '● ' : '○ ') + j.name;
    btn.setAttribute('aria-label', `${j.name}${j.is_published ? ' (' + t('published') + ')' : ''}`);
    btn.onclick = () => App.navigate(`#/hr/recruitment/${j.id}`);
    li.appendChild(btn);
    ul.appendChild(li);
  });
  container.appendChild(jobs.length ? ul : Object.assign(document.createElement('div'), {
    className: 'empty-state', textContent: t('No records'),
  }));
}
