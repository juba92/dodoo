// Generic metadata-driven Kanban view type (feature 006).
//
// render(container, {
//   model,                // required
//   groupBy,              // field name to group columns by (Many2one → uses [id,label])
//   columns,              // optional [{value, label}] to force column set + order
//   cardFields,           // optional [fieldName] shown on each card (else auto)
//   domain,               // optional base domain
//   moveEndpoint,         // optional "/hr/applicant/{id}/set-stage" — enables drag + keyboard move
//   moveField,            // field the move endpoint sets (default = groupBy)
//   formRoute,            // fn(id) → hash; default `#/model/<model>/<id>`
//   hash,                 // current route hash (for back-nav)
// })
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

const _CARD_TYPES = new Set(['char', 'text', 'integer', 'float', 'boolean', 'date', 'datetime', 'selection', 'many2one']);

function _label(value) {
  if (value === null || value === undefined || value === false) return '';
  if (Array.isArray(value)) return String(value[1] ?? value[0] ?? '');
  if (typeof value === 'boolean') return value ? t('Yes') : t('No');
  return String(value);
}

function _groupKey(value) {
  if (Array.isArray(value)) return String(value[0]);
  if (value === null || value === undefined || value === false) return '__none__';
  return String(value);
}

export async function render(container, params) {
  const { model, groupBy } = params;
  if (!model || !groupBy) {
    container.textContent = t('Kanban view needs a model and a groupBy field.');
    return;
  }
  const moveField = params.moveField || groupBy;
  const formRoute = params.formRoute || (id => `#/model/${model}/${id}`);
  container.innerHTML = '';

  let fields = App.state.fieldCache[model];
  if (!fields) {
    fields = await api.rpc(model, 'fields_get', [], {
      attributes: ['string', 'type', 'required', 'readonly', 'relation'],
    });
    App.state.fieldCache[model] = fields;
  }

  const cardFields = params.cardFields
    || Object.keys(fields).filter(k => k !== 'id' && k !== groupBy && _CARD_TYPES.has(fields[k].type)).slice(0, 4);

  const records = await api.rpc(model, 'search_read', [params.domain || []], {
    fields: ['id', groupBy, ...cardFields],
    limit: 500,
  });

  // Column set: explicit, else derived from the data (stable order of first appearance).
  let columns = params.columns;
  if (!columns) {
    const seen = new Map();
    records.forEach(r => {
      const k = _groupKey(r[groupBy]);
      if (!seen.has(k)) seen.set(k, { value: k, label: _label(r[groupBy]) || t('None') });
    });
    columns = [...seen.values()];
  }

  const byCol = new Map(columns.map(c => [String(c.value), []]));
  records.forEach(r => {
    const k = _groupKey(r[groupBy]);
    (byCol.get(k) || byCol.set(k, []).get(k)).push(r);
  });

  const board = document.createElement('div');
  board.className = 'o-kanban';
  board.setAttribute('role', 'list');
  container.appendChild(board);

  async function move(recId, toValue) {
    if (!params.moveEndpoint) return;
    const url = params.moveEndpoint.replace('{id}', String(recId));
    await api.post(url, { [moveField + '_id']: Number(toValue) });
    App.navigate(params.hash || window.location.hash); // re-render
  }

  columns.forEach(col => {
    const colEl = document.createElement('section');
    colEl.className = 'o-kanban-col';
    colEl.setAttribute('role', 'listitem');
    colEl.setAttribute('aria-label', col.label);

    const head = document.createElement('h3');
    head.className = 'o-kanban-col-title';
    head.textContent = `${col.label} (${(byCol.get(String(col.value)) || []).length})`;
    colEl.appendChild(head);

    if (params.moveEndpoint) {
      colEl.addEventListener('dragover', e => e.preventDefault());
      colEl.addEventListener('drop', e => {
        e.preventDefault();
        const recId = e.dataTransfer.getData('text/plain');
        if (recId) move(recId, col.value);
      });
    }

    (byCol.get(String(col.value)) || []).forEach(rec => {
      const card = document.createElement('article');
      card.className = 'o-kanban-card';
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      const title = cardFields.map(f => _label(rec[f])).find(Boolean) || `#${rec.id}`;
      card.setAttribute('aria-label', title);
      cardFields.forEach(f => {
        const line = document.createElement('div');
        line.className = 'o-kanban-card-line';
        line.textContent = _label(rec[f]);
        if (line.textContent) card.appendChild(line);
      });
      const open = () => App.navigate(formRoute(rec.id));
      card.onclick = open;

      if (params.moveEndpoint) {
        card.draggable = true;
        card.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', String(rec.id)));
        // Keyboard alternative to drag: a "Move to…" select (ACC-002).
        const mover = document.createElement('select');
        mover.className = 'o-kanban-move';
        mover.setAttribute('aria-label', t('Move {title} to another column', { title }));
        const noop = document.createElement('option');
        noop.value = '';
        noop.textContent = t('Move to…');
        mover.appendChild(noop);
        columns.forEach(c => {
          if (String(c.value) === String(col.value)) return;
          const o = document.createElement('option');
          o.value = String(c.value);
          o.textContent = c.label;
          mover.appendChild(o);
        });
        mover.onclick = e => e.stopPropagation();
        mover.onchange = () => { if (mover.value) move(rec.id, mover.value); };
        card.appendChild(mover);
      }

      card.onkeydown = e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      };
      colEl.appendChild(card);
    });

    board.appendChild(colEl);
  });

  if (records.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = t('No records');
    container.appendChild(empty);
  }
}
