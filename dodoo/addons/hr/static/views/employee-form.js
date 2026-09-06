// Employee form — Personal / Work / Private / HR Settings tabs + skills + org chart
// (feature 006, FR-001 / FR-008). Uses fields_get for labels; renders inputs by type.
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';
import { mount as mountOrgChart } from '/hr/static/views/org-chart.js';

const TABS = {
  Work: ['work_email', 'work_phone', 'department_id', 'job_id', 'job_title', 'work_location', 'manager_id', 'coach_id', 'company_id'],
  Personal: ['gender', 'birthday', 'marital', 'private_email', 'private_phone', 'emergency_contact', 'emergency_phone'],
  Private: ['country_id', 'identification_id', 'bank_account', 'home_address', 'dependant_count'],
  'HR Settings': ['user_id', 'active', 'next_appraisal_date', 'appraisal_frequency_months'],
};

function _input(fmeta, name, value) {
  const type = fmeta[name]?.type;
  let el;
  if (type === 'boolean') {
    el = document.createElement('input');
    el.type = 'checkbox';
    el.checked = !!value;
  } else if (type === 'date') {
    el = document.createElement('input');
    el.type = 'date';
    el.value = value ? String(value).slice(0, 10) : '';
  } else if (type === 'integer') {
    el = document.createElement('input');
    el.type = 'number';
    el.value = value ?? '';
  } else if (type === 'text') {
    el = document.createElement('textarea');
    el.value = value ?? '';
  } else {
    el = document.createElement('input');
    el.type = 'text';
    el.value = Array.isArray(value) ? (value[1] ?? '') : (value ?? '');
  }
  el.name = name;
  el.id = 'f_' + name;
  return el;
}

export async function render(container, params) {
  container.innerHTML = '';
  const id = params.id;
  const isNew = id === 'new';

  const fmeta = await api.rpc('hr.employee', 'fields_get', [], {
    attributes: ['string', 'type', 'required', 'readonly', 'relation'],
  });
  let rec = { active: true };
  if (!isNew) {
    const rows = await api.rpc('hr.employee', 'read', [[Number(id)]]);
    rec = rows[0] || {};
  }

  const form = document.createElement('form');
  form.className = 'o-form';

  const nameField = _input(fmeta, 'name', rec.name);
  nameField.className = 'o-form-title-input';
  nameField.required = true;
  form.appendChild(nameField);

  const tabBar = document.createElement('div');
  tabBar.className = 'o-form-tabbar';
  tabBar.setAttribute('role', 'tablist');
  form.appendChild(tabBar);

  const panels = {};
  Object.entries(TABS).forEach(([label, names], i) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'o-form-tab';
    btn.textContent = t(label);
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
    tabBar.appendChild(btn);

    const panel = document.createElement('div');
    panel.className = 'o-form-panel';
    panel.setAttribute('role', 'tabpanel');
    panel.hidden = i !== 0;
    names.forEach(n => {
      if (!fmeta[n]) return;
      const row = document.createElement('div');
      row.className = 'o-form-row';
      const lab = document.createElement('label');
      lab.htmlFor = 'f_' + n;
      lab.textContent = fmeta[n].string || n;
      row.appendChild(lab);
      row.appendChild(_input(fmeta, n, rec[n]));
      panel.appendChild(row);
    });
    form.appendChild(panel);
    panels[label] = { btn, panel };

    btn.onclick = () => {
      Object.values(panels).forEach(p => {
        p.panel.hidden = true;
        p.btn.setAttribute('aria-selected', 'false');
      });
      panel.hidden = false;
      btn.setAttribute('aria-selected', 'true');
    };
  });

  // Skills section
  const skillsBox = document.createElement('section');
  skillsBox.className = 'o-form-panel';
  const skTitle = document.createElement('h3');
  skTitle.textContent = t('Skills');
  skillsBox.appendChild(skTitle);
  form.appendChild(skillsBox);
  if (!isNew) {
    try {
      const skills = await api.rpc('hr.employee.skill', 'search_read', [[['employee_id', '=', Number(id)]]], {
        fields: ['skill_id', 'skill_level_id', 'skill_type_id'],
      });
      const ul = document.createElement('ul');
      skills.forEach(s => {
        const li = document.createElement('li');
        li.textContent = `${Array.isArray(s.skill_id) ? s.skill_id[1] : s.skill_id} — ${Array.isArray(s.skill_level_id) ? s.skill_level_id[1] : s.skill_level_id}`;
        ul.appendChild(li);
      });
      skillsBox.appendChild(skills.length ? ul : Object.assign(document.createElement('p'), { textContent: t('No skills recorded') }));
    } catch { /* ignore */ }
  }

  // Org chart
  if (!isNew) {
    const orgBox = document.createElement('section');
    orgBox.className = 'o-form-panel';
    const oTitle = document.createElement('h3');
    oTitle.textContent = t('Organisation chart');
    orgBox.appendChild(oTitle);
    const orgMount = document.createElement('div');
    orgBox.appendChild(orgMount);
    form.appendChild(orgBox);
    mountOrgChart(orgMount, Number(id));
  }

  // Actions
  const bar = document.getElementById('control-panel');
  if (bar) {
    bar.innerHTML = '';
    const save = document.createElement('button');
    save.className = 'btn btn-primary';
    save.textContent = t('Save');
    save.onclick = async () => {
      const vals = {};
      form.querySelectorAll('input,textarea,select').forEach(el => {
        if (el.name === 'name' || el.closest('.o-form-row')) {
          vals[el.name] = el.type === 'checkbox' ? el.checked : (el.value === '' ? null : el.value);
        }
      });
      try {
        if (isNew) {
          const newId = await api.rpc('hr.employee', 'create', [vals]);
          App.navigate(`#/hr/employee/${newId}`);
        } else {
          await api.rpc('hr.employee', 'write', [[Number(id)], vals]);
          App.navigate('#/hr/employees');
        }
      } catch (err) {
        alert(t('Save failed') + ': ' + err.message);
      }
    };
    bar.appendChild(save);
    const back = document.createElement('button');
    back.className = 'btn btn-secondary';
    back.textContent = t('Discard');
    back.onclick = () => App.navigate('#/hr/employees');
    bar.appendChild(back);
  }

  container.appendChild(form);
}
