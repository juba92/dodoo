/**
 * Client-side i18n: catalog loading, string lookup, direction, and locale formatting.
 *
 * The catalog + locale metadata come from `GET /web/i18n/<lang>.json`. `t(key)` returns
 * the translation or the key itself (the key is the English source string, so untranslated
 * UI still reads correctly). Numbers/dates are formatted from the res.lang format fields so
 * the client matches the server exactly; digits follow the language's numeral system
 * (Eastern Arabic for `ar`, Western otherwise).
 */

let _catalog = { lang: 'en', direction: 'ltr', numeral_system: 'latn', terms: {},
                 date_format: '%m/%d/%Y', decimal_point: '.', thousands_sep: ',', grouping: [3, 0] };

export function currentLang() { return _catalog.lang; }
export function currentDirection() { return _catalog.direction; }

export async function loadCatalog(lang) {
  const code = lang || 'en';
  // Always fetch fresh: the endpoint is local, the payload is small, and a stale
  // sessionStorage copy would silently pin the UI to an old catalog after any
  // translation change. sessionStorage is now only an offline fallback.
  try {
    const res = await fetch('/web/i18n/' + encodeURIComponent(code) + '.json', { cache: 'no-store' });
    if (res.ok) {
      _catalog = await res.json();
      _catalog.terms = _catalog.terms || {};
      try { sessionStorage.setItem('i18n:' + code, JSON.stringify(_catalog)); } catch { /* ignore */ }
      return _catalog;
    }
  } catch { /* network failed — fall back to the last cached copy below */ }

  try {
    const cached = sessionStorage.getItem('i18n:' + code);
    if (cached) { _catalog = JSON.parse(cached); _catalog.terms = _catalog.terms || {}; }
  } catch { /* private mode / disabled storage */ }
  return _catalog;
}

export function clearCatalogCache(lang) {
  try {
    if (lang) sessionStorage.removeItem('i18n:' + lang);
    else Object.keys(sessionStorage).filter(k => k.startsWith('i18n:')).forEach(k => sessionStorage.removeItem(k));
  } catch { /* ignore */ }
}

/** Translate a static UI string. Placeholders like {name} are substituted from `params`. */
export function t(key, params) {
  let out = (_catalog.terms && _catalog.terms[key]) || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      out = out.split('{' + k + '}').join(String(v));
    }
  }
  return out;
}

/** Set <html dir/lang> from a direction string (or the current catalog). */
export function applyDirection(direction) {
  const dir = direction || _catalog.direction || 'ltr';
  document.documentElement.setAttribute('dir', dir);
  document.documentElement.setAttribute('lang', _catalog.lang || 'en');
}

const _EASTERN_ARABIC = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];

/** Map ASCII digits to the active language's numeral system (currently Eastern Arabic
 *  for `ar`). Applied to every user-visible number/date; input fields keep ASCII. */
function _localizeDigits(str) {
  if (_catalog.numeral_system !== 'arab') return str;
  return String(str).replace(/[0-9]/g, d => _EASTERN_ARABIC[+d]);
}

export function formatNumber(value, decimals) {
  const n = Number(value);
  if (!isFinite(n)) return String(value ?? '');
  const dp = _catalog.decimal_point || '.';
  const ts = _catalog.thousands_sep || ',';
  const grouping = (_catalog.grouping && _catalog.grouping[0]) || 3;
  const fixed = decimals == null ? n.toString() : n.toFixed(decimals);
  let [intPart, fracPart] = fixed.split('.');
  const neg = intPart.startsWith('-');
  if (neg) intPart = intPart.slice(1);
  let grouped = '';
  while (intPart.length > grouping) {
    grouped = ts + intPart.slice(-grouping) + grouped;
    intPart = intPart.slice(0, -grouping);
  }
  grouped = intPart + grouped;
  return _localizeDigits((neg ? '-' : '') + grouped + (fracPart ? dp + fracPart : ''));
}

export function formatCurrency(value, opts = {}) {
  const decimals = opts.decimals == null ? 2 : opts.decimals;
  const body = formatNumber(value, decimals);
  const sym = opts.symbol || '';
  if (!sym) return body;
  return opts.position === 'after' ? body + ' ' + sym : sym + ' ' + body;
}

/** Format an ISO date (YYYY-MM-DD or full ISO) using the active language's date_format. */
export function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso.length <= 10 ? iso + 'T00:00:00' : iso);
  if (isNaN(d.getTime())) return String(iso);
  const p2 = n => String(n).padStart(2, '0');
  const map = {
    '%d': p2(d.getDate()), '%m': p2(d.getMonth() + 1), '%Y': String(d.getFullYear()),
    '%y': p2(d.getFullYear() % 100), '%H': p2(d.getHours()), '%M': p2(d.getMinutes()),
  };
  return _localizeDigits((_catalog.date_format || '%m/%d/%Y').replace(/%[dmYyHM]/g, m => map[m] ?? m));
}
