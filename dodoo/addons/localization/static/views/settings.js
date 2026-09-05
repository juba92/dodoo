import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t } from '/web/static/i18n.js';

/** Settings screen: system language + company country (admin), personal language (any user). */
export async function render(container, _params) {
  container.innerHTML = '';
  const page = document.createElement('div');
  page.className = 'settings-page';
  container.appendChild(page);

  const h2 = document.createElement('h2');
  h2.textContent = t('Settings');
  page.appendChild(h2);

  const banner = document.createElement('div');
  banner.setAttribute('role', 'status');
  banner.setAttribute('aria-live', 'polite');
  banner.hidden = true;
  page.appendChild(banner);

  let values;
  try {
    values = await api.rpc('res.config.settings', 'get_values', []);
  } catch (err) {
    banner.hidden = false;
    banner.className = 'settings-banner error';
    banner.textContent = err.message;
    return;
  }

  const isAdmin = !!App.state.isAdmin;

  // ── Personal language (every user) ─────────────────────────────────────────
  const meField = _field(t('My language'));
  const meSelect = document.createElement('select');
  meSelect.id = 'set-user-lang';
  const optDefault = new Option(t('Use system default'), '');
  meSelect.add(optDefault);
  for (const l of values.available_langs) meSelect.add(new Option(l.name, l.code));
  meSelect.value = '';
  meField.appendChild(meSelect);
  page.appendChild(meField);

  const meBtn = _btn(t('Save'), async () => {
    try {
      const res = await api.rpc('res.config.settings', 'set_user_lang', [meSelect.value || null]);
      await App.reloadLanguage();
      _flash(banner, 'success', t('Settings saved.'));
      if (res && res.direction) document.documentElement.setAttribute('dir', res.direction);
      _rerender(container);
    } catch (err) { _flash(banner, 'error', err.message); }
  });
  page.appendChild(_actions(meBtn));

  if (!isAdmin) return;

  // ── System language + country (admin only) ────────────────────────────────
  const sep = document.createElement('hr');
  page.appendChild(sep);

  const langField = _field(t('System Language'));
  const langSelect = document.createElement('select');
  langSelect.id = 'set-sys-lang';
  for (const l of values.available_langs) langSelect.add(new Option(l.name, l.code));
  langSelect.value = values.lang;
  langField.appendChild(langSelect);
  page.appendChild(langField);

  const countryField = _field(t('Country'));
  const countrySelect = document.createElement('select');
  countrySelect.id = 'set-country';
  for (const c of values.available_countries) {
    countrySelect.add(new Option(t(c.name), c.code));
  }
  countrySelect.value = values.country_code || '';
  countryField.appendChild(countrySelect);
  page.appendChild(countryField);

  // Derived, read-only, pack-driven config
  const derived = document.createElement('div');
  derived.className = 'derived';
  const dl = document.createElement('dl');
  _drow(dl, t('Tax Label'), values.tax_label || '—');
  _drow(dl, t('Rounding Method'),
    values.tax_rounding_method === 'round_per_line' ? t('Round per Line') : t('Round Globally'));
  _drow(dl, t('Default Sales Tax'), values.default_sale_tax_id ?? '—');
  _drow(dl, t('Default Purchase Tax'), values.default_purchase_tax_id ?? '—');
  _drow(dl, t('Default Fiscal Position'), values.default_fiscal_position_id ?? '—');
  derived.appendChild(dl);
  page.appendChild(derived);

  const saveBtn = _btn(t('Save'), () => _save(false));
  page.appendChild(_actions(saveBtn));

  async function _save(confirmCurrency) {
    const payload = {
      lang: langSelect.value,
      country_code: countrySelect.value,
      company_write_date: values.company_write_date,
      confirm_currency_change: confirmCurrency,
    };
    let res;
    try {
      res = await api.rpc('res.config.settings', 'set_values', [payload]);
    } catch (err) {
      if (String(err.message).includes('settings_stale')) {
        _staleBanner(banner, container);
      } else {
        _flash(banner, 'error', err.message);
      }
      return;
    }
    if (res && res.ok === false && res.warning === 'currency_change_requires_confirmation') {
      const d = res.detail || {};
      const msg = t(
        'Changing the country will change the functional currency from {from} to {to}. ' +
        '{posted_lines} posted accounting line(s) exist. Continue?',
        { from: d.from, to: d.to, posted_lines: d.posted_lines },
      );
      if (window.confirm(msg)) {
        await _save(true);
      } else {
        countrySelect.value = values.country_code || '';
      }
      return;
    }
    await App.reloadLanguage();
    _flash(banner, 'success',
      res && res.applied ? t('Localization package applied.') : t('Settings saved.'));
    _rerender(container);
  }
}

// ── helpers ─────────────────────────────────────────────────────────────────
function _field(labelText) {
  const wrap = document.createElement('div');
  wrap.className = 'field';
  const label = document.createElement('label');
  label.textContent = labelText;
  wrap.appendChild(label);
  return wrap;
}
function _btn(text, onclick) {
  const b = document.createElement('button');
  b.className = 'btn btn-primary';
  b.textContent = text;
  b.onclick = onclick;
  return b;
}
function _actions(...btns) {
  const row = document.createElement('div');
  row.className = 'settings-actions';
  btns.forEach(b => row.appendChild(b));
  return row;
}
function _drow(dl, term, val) {
  const dt = document.createElement('dt'); dt.textContent = term;
  const dd = document.createElement('dd'); dd.textContent = String(val);
  dl.appendChild(dt); dl.appendChild(dd);
}
function _flash(banner, kind, msg) {
  banner.hidden = false;
  banner.className = 'settings-banner ' + kind;
  banner.textContent = msg;
}
function _staleBanner(banner, container) {
  _flash(banner, 'error',
    t('These settings were changed by someone else. Reload and try again.'));
  const reload = _btn(t('Reload'), () => _rerender(container));
  banner.appendChild(document.createTextNode(' '));
  banner.appendChild(reload);
}
function _rerender(container) {
  render(container, {});
}
