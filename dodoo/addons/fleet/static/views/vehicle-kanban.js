// Fleet vehicles — generic Kanban grouped by lifecycle state (feature 006, US6).
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { render as renderKanban } from '/web/static/views/kanban.js';

const STATES = [
  'new_request', 'to_order', 'ordered', 'registered',
  'downgraded', 'reserved', 'waiting_list',
];

export async function render(container, _params) {
  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const nb = document.createElement('button');
    nb.className = 'btn btn-primary';
    nb.textContent = t('New');
    nb.onclick = () => App.navigate('#/fleet/model/fleet.vehicle/new');
    cp.appendChild(nb);
  }
  await renderKanban(container, {
    model: 'fleet.vehicle',
    groupBy: 'state',
    columns: STATES.map(s => ({ value: s, label: t(s) })),
    cardFields: ['name', 'license_plate', 'driver_id'],
    formRoute: id => `#/fleet/vehicle/${id}`,
    hash: '#/fleet/vehicles',
  });
}
