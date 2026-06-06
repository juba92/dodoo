import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';

export function render(container, _params) {
  // Already authenticated → skip to home
  if (App.state.token) {
    App.navigate('#/home');
    return;
  }

  container.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'login-card';

  const h1 = document.createElement('h1');
  h1.textContent = 'Dodoo ERP';
  card.appendChild(h1);

  // Session-expired banner
  const qs = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
  if (qs.get('reason') === 'expired') {
    const banner = document.createElement('div');
    banner.className = 'error-banner';
    banner.setAttribute('role', 'alert');
    banner.textContent = 'Your session has expired. Please sign in again.';
    card.appendChild(banner);
  }

  // Error container (hidden initially)
  const errEl = document.createElement('div');
  errEl.className = 'error-banner';
  errEl.setAttribute('role', 'alert');
  errEl.setAttribute('aria-live', 'assertive');
  errEl.style.display = 'none';
  card.appendChild(errEl);

  // Login field
  const loginField = document.createElement('div');
  loginField.className = 'field';
  const loginLabel = document.createElement('label');
  loginLabel.htmlFor = 'f-login';
  loginLabel.textContent = 'Login';
  const loginInput = document.createElement('input');
  loginInput.type = 'text';
  loginInput.id = 'f-login';
  loginInput.name = 'login';
  loginInput.autocomplete = 'username';
  loginInput.required = true;
  loginField.appendChild(loginLabel);
  loginField.appendChild(loginInput);
  card.appendChild(loginField);

  // Password field
  const pwField = document.createElement('div');
  pwField.className = 'field';
  const pwLabel = document.createElement('label');
  pwLabel.htmlFor = 'f-password';
  pwLabel.textContent = 'Password';
  const pwInput = document.createElement('input');
  pwInput.type = 'password';
  pwInput.id = 'f-password';
  pwInput.name = 'password';
  pwInput.autocomplete = 'current-password';
  pwInput.required = true;
  pwField.appendChild(pwLabel);
  pwField.appendChild(pwInput);
  card.appendChild(pwField);

  // Submit button
  const submitBtn = document.createElement('button');
  submitBtn.type = 'submit';
  submitBtn.className = 'btn btn-primary btn-full';
  submitBtn.textContent = 'Sign In';
  card.appendChild(submitBtn);

  container.appendChild(card);

  // Focus first field
  loginInput.focus();

  // Submit handler
  async function onSubmit(e) {
    e.preventDefault();
    errEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in…';
    try {
      const data = await api.authenticate(loginInput.value.trim(), pwInput.value);
      App.state.token = data.session_token;
      App.state.uid = data.uid;
      sessionStorage.setItem('session_token', data.session_token);
      sessionStorage.setItem('session_uid', String(data.uid));

      // Announce for screen readers
      document.getElementById('status').textContent = 'Signed in successfully.';

      // Load info for sidebar
      try {
        const info = await api.getInfo();
        App.state.modules = info.modules ?? [];
        App.state.models = info.models ?? [];
      } catch { /* non-fatal */ }

      App.breadcrumb = [{ label: 'Home', hash: '#/home' }];
      App.navigate('#/home');
    } catch (err) {
      errEl.textContent = err.message ?? 'Authentication failed';
      errEl.style.display = 'block';
      document.getElementById('status').textContent = 'Sign in failed: ' + errEl.textContent;
      submitBtn.disabled = false;
      submitBtn.textContent = 'Sign In';
      pwInput.focus();
    }
  }

  card.addEventListener('submit', onSubmit);
  card.addEventListener('keydown', e => {
    if (e.key === 'Enter') onSubmit(e);
  });
}
