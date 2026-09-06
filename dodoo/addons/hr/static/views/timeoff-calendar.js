// Time Off calendar — the generic Calendar view type applied to hr.leave (feature 006).
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { render as renderCalendar } from '/web/static/views/calendar.js';

export async function render(container, _params) {
  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const nb = document.createElement('button');
    nb.className = 'btn btn-primary';
    nb.textContent = t('New Request');
    nb.onclick = () => App.navigate('#/hr/timeoff/new');
    cp.appendChild(nb);
  }
  await renderCalendar(container, {
    model: 'hr.leave',
    dateStartField: 'date_from',
    dateStopField: 'date_to',
    titleField: 'employee_id',
    domain: [['state', '!=', 'refused']],
    formRoute: id => `#/hr/timeoff/${id}`,
  });
}
