// Bespoke org-chart widget for the employee form (feature 006, per Odoo hr_org_chart).
// mount(container, employeeId): manager chain upward + direct reports downward,
// as an accessible nested <ul>. Not a generic view type.
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

function _node(rec, current = false) {
  const a = document.createElement('a');
  a.className = 'o-org-node' + (current ? ' o-org-current' : '');
  a.href = `#/hr/employee/${rec.id}`;
  a.textContent = rec.job_title ? `${rec.name} — ${rec.job_title}` : rec.name;
  a.onclick = e => { e.preventDefault(); App.navigate(`#/hr/employee/${rec.id}`); };
  return a;
}

export async function mount(container, employeeId) {
  container.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'o-orgchart';
  wrap.setAttribute('role', 'tree');
  wrap.setAttribute('aria-label', t('Organisation chart'));
  container.appendChild(wrap);

  let data;
  try {
    data = await api.get(`/hr/employee/${employeeId}/org-chart`);
  } catch (err) {
    wrap.textContent = t('Org chart unavailable') + ': ' + err.message;
    return;
  }

  // Manager chain: nested <ul>, root first, deepest wraps the current node + reports.
  let host = wrap;
  data.manager_chain.forEach(m => {
    const ul = document.createElement('ul');
    const li = document.createElement('li');
    li.setAttribute('role', 'treeitem');
    li.appendChild(_node(m));
    ul.appendChild(li);
    host.appendChild(ul);
    host = li;
  });

  const ul = document.createElement('ul');
  const selfLi = document.createElement('li');
  selfLi.setAttribute('role', 'treeitem');
  selfLi.setAttribute('aria-current', 'true');
  selfLi.appendChild(_node({ id: employeeId, name: t('This employee') }, true));
  if (data.reports.length) {
    const rUl = document.createElement('ul');
    data.reports.forEach(r => {
      const rLi = document.createElement('li');
      rLi.setAttribute('role', 'treeitem');
      rLi.appendChild(_node(r));
      rUl.appendChild(rLi);
    });
    selfLi.appendChild(rUl);
  }
  ul.appendChild(selfLi);
  host.appendChild(ul);
}
