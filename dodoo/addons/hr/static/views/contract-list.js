// Contracts list with an inline "Set state" control (feature 006, FR-012).
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const NEXT = {
  draft: ['running', 'cancelled'],
  running: ['expired', 'cancelled'],
  expired: ['draft'],
  cancelled: ['draft'],
};

export async function render(container, _params) {
  container.innerHTML = '';
  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const nb = document.createElement('button');
    nb.className = 'btn btn-primary';
    nb.textContent = t('New');
    nb.onclick = () => App.navigate('#/hr/model/hr.contract/new');
    cp.appendChild(nb);
  }

  const rows = await api.rpc('hr.contract', 'search_read', [[]], {
    fields: ['name', 'employee_id', 'contract_type_id', 'wage', 'date_start', 'date_end', 'state'],
    limit: 200,
    order: 'date_start desc',
  });

  const wrap = document.createElement('div');
  wrap.style.overflowX = 'auto';
  const table = document.createElement('table');
  table.className = 'data-table';
  table.innerHTML = '';
  const head = document.createElement('tr');
  [t('Reference'), t('Employee'), t('Type'), t('Wage'), t('Start'), t('End'), t('Status'), ''].forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    head.appendChild(th);
  });
  const thead = document.createElement('thead');
  thead.appendChild(head);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  table.appendChild(tbody);

  const cell = v => {
    const td = document.createElement('td');
    td.textContent = Array.isArray(v) ? (v[1] ?? '') : (v ?? '');
    return td;
  };

  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.appendChild(cell(r.name));
    tr.appendChild(cell(r.employee_id));
    tr.appendChild(cell(r.contract_type_id));
    tr.appendChild(cell(r.wage));
    tr.appendChild(cell(r.date_start));
    tr.appendChild(cell(r.date_end));
    const stateTd = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'o-state-badge';
    badge.textContent = t(r.state);        // text, not colour-only (ACC-003)
    stateTd.appendChild(badge);
    tr.appendChild(stateTd);

    const actTd = document.createElement('td');
    const sel = document.createElement('select');
    sel.setAttribute('aria-label', t('Change status of {name}', { name: r.name }));
    const noop = document.createElement('option');
    noop.value = '';
    noop.textContent = t('Set state…');
    sel.appendChild(noop);
    (NEXT[r.state] || []).forEach(s => {
      const o = document.createElement('option');
      o.value = s;
      o.textContent = t(s);
      sel.appendChild(o);
    });
    sel.onchange = async () => {
      if (!sel.value) return;
      try {
        await api.post(`/hr/contract/${r.id}/set-state`, {
          state: sel.value,
          expected_state: r.state,
        });
        App.navigate('#/hr/contracts');
      } catch (err) {
        sel.value = '';
        const e = document.createElement('div');
        e.className = 'alert-error';
        e.textContent = t('Error') + ': ' + err.message;
        container.prepend(e);
      }
    };
    actTd.appendChild(sel);
    tr.appendChild(actTd);
    tbody.appendChild(tr);
  });

  wrap.appendChild(table);
  container.appendChild(rows.length ? wrap : Object.assign(document.createElement('div'), {
    className: 'empty-state', textContent: t('No records'),
  }));
}
