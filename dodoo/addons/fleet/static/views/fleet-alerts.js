// Fleet expiry alerts — leasing/insurance contracts due soon or overdue (feature 006, US6).
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

export async function render(container, _params) {
  container.innerHTML = '';
  const cp = document.getElementById('control-panel');
  if (cp) cp.innerHTML = '';

  let alerts;
  try {
    alerts = await api.get('/fleet/alerts');
  } catch (err) {
    container.textContent = t('Error') + ': ' + err.message;
    return;
  }
  if (!alerts.length) {
    container.appendChild(Object.assign(document.createElement('div'), { className: 'empty-state', textContent: t('No expiring contracts') }));
    return;
  }
  const table = document.createElement('table');
  table.className = 'data-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [t('Vehicle'), t('Type'), t('Expiry'), t('Days left')].forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);
  const tb = document.createElement('tbody');
  alerts.forEach(a => {
    const tr = document.createElement('tr');
    tr.onclick = () => App.navigate(`#/fleet/vehicle/${a.vehicle_id}`);
    const daysLabel = a.days_left < 0
      ? t('{n} days overdue', { n: -a.days_left })
      : t('{n} days left', { n: a.days_left });
    [a.vehicle_name, t(a.cost_type), a.expiration_date, daysLabel].forEach(v => {
      const td = document.createElement('td');
      td.textContent = v ?? '';
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  table.appendChild(tb);
  container.appendChild(table);
}
