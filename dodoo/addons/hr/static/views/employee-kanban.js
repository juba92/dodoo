// Employees "card view" = the generic Kanban view type applied to hr.employee (feature 006).
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { render as renderKanban } from '/web/static/views/kanban.js';

export async function render(container, _params) {
  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.textContent = t('New');
    newBtn.onclick = () => App.navigate('#/hr/employee/new');
    cp.appendChild(newBtn);
    const toList = document.createElement('button');
    toList.className = 'btn btn-secondary';
    toList.textContent = t('List');
    toList.onclick = () => App.navigate('#/hr/model/hr.employee');
    cp.appendChild(toList);
  }
  await renderKanban(container, {
    model: 'hr.employee',
    groupBy: 'department_id',
    cardFields: ['name', 'job_title', 'work_email'],
    formRoute: id => `#/hr/employee/${id}`,
    hash: '#/hr/employees',
  });
}
