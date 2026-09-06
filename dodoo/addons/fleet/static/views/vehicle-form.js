// Vehicle form — state control, driver assign, odometer / contracts / services (feature 006).
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const STATES = [
  'new_request', 'to_order', 'ordered', 'registered',
  'downgraded', 'reserved', 'waiting_list',
];

function _row(label, el) {
  const r = document.createElement('div');
  r.className = 'o-form-row';
  r.append(Object.assign(document.createElement('label'), { textContent: label }), el);
  return r;
}
function _err(container, msg) {
  const e = document.createElement('div');
  e.className = 'alert-error';
  e.textContent = t('Error') + ': ' + msg;
  container.prepend(e);
}

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const rec = (await api.rpc('fleet.vehicle', 'read', [[Number(id)]]))[0];
  if (!rec) { container.textContent = t('Not found'); return; }

  const form = document.createElement('form');
  form.className = 'o-form';
  form.appendChild(_row(t('Vehicle'), Object.assign(document.createElement('span'), { textContent: rec.name || `#${rec.id}` })));

  const stateBadge = document.createElement('span');
  stateBadge.className = 'o-state-badge';
  stateBadge.textContent = t(rec.state);
  form.appendChild(_row(t('Status'), stateBadge));

  form.appendChild(_row(t('Odometer'), Object.assign(document.createElement('span'), { textContent: String(rec.odometer ?? 0) })));

  // state control
  const sel = document.createElement('select');
  sel.setAttribute('aria-label', t('Change vehicle status'));
  const noop = document.createElement('option');
  noop.value = '';
  noop.textContent = t('Set state…');
  sel.appendChild(noop);
  STATES.filter(s => s !== rec.state).forEach(s => {
    const o = document.createElement('option');
    o.value = s;
    o.textContent = t(s);
    sel.appendChild(o);
  });
  sel.onchange = async () => {
    if (!sel.value) return;
    try {
      await api.post(`/fleet/vehicle/${id}/set-state`, { state: sel.value, expected_state: rec.state });
      App.navigate(`#/fleet/vehicle/${id}`);
    } catch (err) { sel.value = ''; _err(container, err.message); }
  };
  form.appendChild(_row(t('Change state'), sel));

  // driver assign
  const drv = document.createElement('input');
  drv.type = 'number';
  drv.value = Array.isArray(rec.driver_id) ? rec.driver_id[0] : (rec.driver_id ?? '');
  const drvBtn = document.createElement('button');
  drvBtn.type = 'button';
  drvBtn.className = 'btn btn-secondary';
  drvBtn.textContent = t('Assign');
  drvBtn.onclick = async () => {
    try {
      await api.post(`/fleet/vehicle/${id}/assign-driver`, { driver_id: drv.value ? Number(drv.value) : null });
      App.navigate(`#/fleet/vehicle/${id}`);
    } catch (err) { _err(container, err.message); }
  };
  const drvWrap = document.createElement('span');
  drvWrap.append(drv, drvBtn);
  form.appendChild(_row(t('Driver (employee id)'), drvWrap));

  container.appendChild(form);

  // sub-lists
  for (const [model, label, cols] of [
    ['fleet.vehicle.odometer', t('Odometer log'), ['value', 'date', 'inconsistent']],
    ['fleet.vehicle.log.contract', t('Contracts'), ['cost_type', 'amount', 'expiration_date', 'state']],
    ['fleet.vehicle.log.services', t('Services'), ['service_type', 'date', 'amount']],
  ]) {
    const box = document.createElement('section');
    box.className = 'o-form-panel';
    box.appendChild(Object.assign(document.createElement('h3'), { textContent: label }));
    try {
      const rows = await api.rpc(model, 'search_read', [[['vehicle_id', '=', Number(id)]]], { fields: cols, order: 'id desc' });
      if (rows.length) {
        const ul = document.createElement('ul');
        rows.forEach(r => {
          const li = document.createElement('li');
          li.textContent = cols.map(c => r[c]).join(' · ');
          ul.appendChild(li);
        });
        box.appendChild(ul);
      } else {
        box.appendChild(Object.assign(document.createElement('p'), { textContent: t('Nothing recorded') }));
      }
    } catch { /* ignore */ }
    container.appendChild(box);
  }

  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('Back');
    back.onclick = () => App.navigate('#/fleet/vehicles');
    bar.appendChild(back);
  }
}
