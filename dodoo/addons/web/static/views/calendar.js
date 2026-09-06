// Generic metadata-driven month Calendar view type (feature 006).
//
// render(container, {
//   model,               // required
//   dateStartField,      // required — date/datetime field
//   dateStopField,       // optional — end of a multi-day event
//   titleField,          // field shown on the event chip (default: first char field)
//   domain,              // optional base domain
//   formRoute,           // fn(id) → hash; default `#/model/<model>/<id>`
// })
import * as api from '/web/static/api.js';
import { App, modelRouteBase } from '/web/static/app.js';
import { t, formatDate } from '/web/static/i18n.js';

const _DAY = 86400000;

function _ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function _label(v) {
  if (Array.isArray(v)) return String(v[1] ?? v[0] ?? '');
  return v == null ? '' : String(v);
}

export async function render(container, params) {
  const { model, dateStartField } = params;
  if (!model || !dateStartField) {
    container.textContent = t('Calendar view needs a model and a dateStartField.');
    return;
  }
  const stopField = params.dateStopField || dateStartField;
  const formRoute = params.formRoute || (id => `${modelRouteBase()}/${model}/${id}`);
  container.innerHTML = '';

  let fields = App.state.fieldCache[model];
  if (!fields) {
    fields = await api.rpc(model, 'fields_get', [], { attributes: ['string', 'type', 'relation'] });
    App.state.fieldCache[model] = fields;
  }
  const titleField = params.titleField
    || Object.keys(fields).find(k => fields[k].type === 'char')
    || 'id';

  // Visible month state.
  const today = new Date();
  let view = new Date(today.getFullYear(), today.getMonth(), 1);

  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    const prev = document.createElement('button');
    prev.className = 'btn btn-secondary';
    prev.textContent = '←';
    prev.setAttribute('aria-label', t('Previous month'));
    prev.onclick = () => { view = new Date(view.getFullYear(), view.getMonth() - 1, 1); draw(); };
    const label = document.createElement('span');
    label.className = 'o-cal-label';
    const next = document.createElement('button');
    next.className = 'btn btn-secondary';
    next.textContent = '→';
    next.setAttribute('aria-label', t('Next month'));
    next.onclick = () => { view = new Date(view.getFullYear(), view.getMonth() + 1, 1); draw(); };
    cp.append(prev, label, next);
    cp._label = label;
  }

  const grid = document.createElement('div');
  grid.className = 'o-calendar';
  grid.setAttribute('role', 'grid');
  grid.setAttribute('aria-label', t('Calendar'));
  container.appendChild(grid);

  async function draw() {
    const first = new Date(view);
    const startGrid = new Date(first);
    startGrid.setDate(first.getDate() - ((first.getDay() + 6) % 7)); // Monday-first
    const endGrid = new Date(startGrid.getTime() + 41 * _DAY);
    if (cp && cp._label) {
      cp._label.textContent = view.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    }

    let records = [];
    try {
      records = await api.rpc(model, 'search_read', [[
        ...(params.domain || []),
        [dateStartField, '<=', _ymd(endGrid)],
        [stopField, '>=', _ymd(startGrid)],
      ]], { fields: ['id', dateStartField, stopField, titleField], limit: 500 });
    } catch (err) {
      grid.innerHTML = '';
      const e = document.createElement('div');
      e.className = 'alert-error';
      e.textContent = t('Error') + ': ' + err.message;
      grid.appendChild(e);
      return;
    }

    grid.innerHTML = '';
    for (let i = 0; i < 42; i++) {
      const day = new Date(startGrid.getTime() + i * _DAY);
      const cell = document.createElement('div');
      cell.className = 'o-cal-cell';
      cell.setAttribute('role', 'gridcell');
      cell.tabIndex = 0;
      cell.setAttribute('aria-label', formatDate(_ymd(day)));
      if (day.getMonth() !== view.getMonth()) cell.classList.add('o-cal-other');
      if (_ymd(day) === _ymd(today)) cell.classList.add('o-cal-today');

      const num = document.createElement('div');
      num.className = 'o-cal-num';
      num.textContent = String(day.getDate());
      cell.appendChild(num);

      const dstr = _ymd(day);
      records
        .filter(r => {
          const s = String(r[dateStartField]).slice(0, 10);
          const e = String(r[stopField] || r[dateStartField]).slice(0, 10);
          return s <= dstr && dstr <= e;
        })
        .forEach(r => {
          const chip = document.createElement('button');
          chip.className = 'o-cal-event';
          chip.textContent = _label(r[titleField]) || `#${r.id}`;
          chip.onclick = () => App.navigate(formRoute(r.id));
          cell.appendChild(chip);
        });

      cell.onkeydown = ev => {
        if (ev.key === 'Enter') { const first = cell.querySelector('.o-cal-event'); if (first) first.click(); }
      };
      grid.appendChild(cell);
    }
  }

  await draw();
}
