(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const fields = ['username', 'password', 'operator', 'autostart', 'show-browser'];
  let api, lastLog = 0, lastNotice = 0, hydrated = false, savedUsername = '', hasPassword = false;
  let polling = false, pending = false, busy = false, dirty = false, logs = [], toastTimer, toastExitTimer, revealTimer;
  const titles = {connection: ['网络连接', '管理校园网账号与自动连接。'], preferences: ['偏好设置', '按你的使用习惯，调整连接与界面。'], activity: ['运行记录', '查看本次打开后的操作与网络状态。']};

  function showView(name) {
    if (!titles[name]) return;
    document.querySelectorAll('.view').forEach(view => { view.hidden = view.id !== `view-${name}`; });
    document.querySelectorAll('.nav-item').forEach(item => {
      const active = item.dataset.view === name;
      item.classList.toggle('active', active);
      if (active) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    });
    $('page-title').textContent = titles[name][0]; $('page-description').textContent = titles[name][1];
  }
  function toast(message, kind = 'info') {
    clearTimeout(toastTimer); clearTimeout(toastExitTimer); $('toast-message').textContent = message;
    $('toast').dataset.kind = kind; $('toast').classList.remove('is-leaving'); $('toast').classList.add('is-visible');
    toastTimer = setTimeout(dismissToast, 6500);
  }
  function dismissToast() {
    clearTimeout(toastTimer); $('toast').classList.add('is-leaving');
    toastExitTimer = setTimeout(() => $('toast').classList.remove('is-visible', 'is-leaving'), 140);
  }
  function hidePassword() {
    clearTimeout(revealTimer); $('password').type = 'password';
    $('reveal-password').setAttribute('aria-pressed', 'false');
    $('reveal-password').setAttribute('aria-label', '显示新输入的密码');
  }
  function setMotion(enabled) { document.body.dataset.motion = enabled ? 'on' : 'off'; $('motion').checked = enabled; }
  function setBusy(value) {
    busy = value; document.body.dataset.busy = String(value);
    [...fields, 'connect-button', 'save-button', 'clear-button', 'check-button', 'reveal-password'].forEach(id => { $(id).disabled = value || pending || !hydrated; });
    $('motion').disabled = !hydrated;
    $('connect-button').querySelector('span').textContent = value ? '正在处理…' : '保存并连接';
    if (value) hidePassword();
  }
  function hydrate(state) {
    savedUsername = state.account.username; hasPassword = state.account.has_password;
    $('username').value = savedUsername; $('password').value = '';
    $('operator').value = state.account.operator;
    if ($('operator').selectedIndex < 0) $('operator').value = '';
    $('autostart').checked = state.preferences.autostart; $('show-browser').checked = state.preferences.show_browser;
    setMotion(state.preferences.motion); updatePasswordHint(); dirty = false;
    $('save-hint').textContent = hasPassword ? '账号已在本机加密保存。' : '填写信息后，点击保存并连接。';
  }
  function updatePasswordHint() {
    const stored = hasPassword && $('username').value.trim() === savedUsername;
    $('password-saved').hidden = !stored;
    $('password').placeholder = stored ? '已保存密码，留空保留' : '输入校园网密码';
    $('password-note').textContent = stored ? '无需再次填写；输入新密码可替换原密码。' : '密码通过 Windows 加密后保存在本机。';
  }
  function logNode(entry, recent) {
    const row = document.createElement('div'); row.className = recent ? 'recent-line' : 'log-entry is-new';
    if (!recent) setTimeout(() => row.classList.remove('is-new'), 220);
    const time = document.createElement('span'); time.className = 'log-time'; time.textContent = entry.time;
    const dot = document.createElement('span'); dot.className = `log-level-dot ${entry.level}`;
    const message = document.createElement('span'); message.className = 'log-message'; message.textContent = entry.message;
    row.append(time, dot, message); return row;
  }
  function appendLogs(entries) {
    const fresh = entries.filter(entry => entry.id > lastLog);
    if (!fresh.length) return;
    const pane = $('log-scroll'), nearBottom = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 30;
    if (!logs.length) $('log-list').replaceChildren();
    for (const entry of fresh) { logs.push(entry); $('log-list').append(logNode(entry, false)); lastLog = Math.max(lastLog, entry.id); }
    while (logs.length > 500) { logs.shift(); $('log-list').firstElementChild.remove(); }
    $('recent-logs').replaceChildren(...logs.slice(-3).reverse().map(entry => logNode(entry, true)));
    $('log-badge').textContent = String(logs.length); $('log-total').textContent = `${logs.length} 条记录`;
    if (nearBottom) { pane.scrollTop = pane.scrollHeight; $('new-logs').hidden = true; } else $('new-logs').hidden = false;
  }
  function render(state, resetForm = false) {
    if (!hydrated || resetForm) { hydrate(state); hydrated = true; }
    window.campusApp.ready = true;
    $('version').textContent = state.version; document.querySelectorAll('.version-label').forEach(el => { el.textContent = state.version; });
    setBusy(state.busy);
    const status = state.status;
    $('status-title').textContent = status.title; $('status-detail').textContent = status.detail;
    $('chip-text').textContent = status.title; $('network-card').dataset.kind = status.kind; $('top-status').dataset.kind = status.kind;
    $('status-caption').textContent = status.checked_at ? `最近检查 ${status.checked_at}` : state.busy ? '请稍候，正在读取真实网络状态' : '连接前请接入校园 Wi-Fi 或网线';
    appendLogs(state.logs);
    if (state.notice && state.notice.id > lastNotice) { lastNotice = state.notice.id; toast(state.notice.message, state.notice.kind); }
  }
  function payload() {
    return {username: $('username').value, password: $('password').value, operator: $('operator').value,
      autostart: $('autostart').checked, show_browser: $('show-browser').checked, motion: $('motion').checked};
  }
  function validate() {
    $('form-error').hidden = true;
    for (const id of ['username', 'password']) $(id).removeAttribute('aria-invalid');
    let field, message;
    if (!$('username').value.trim()) { field = 'username'; message = '请先填写校园网账号。'; }
    else if (!$('password').value && !(hasPassword && $('username').value.trim() === savedUsername)) { field = 'password'; message = '请填写账号对应的密码。'; }
    if (!field) return true;
    $('form-error').textContent = message; $('form-error').hidden = false;
    $(field).setAttribute('aria-invalid', 'true'); $(field).focus(); return false;
  }
  async function act(method, args, resetForm = false) {
    if (!api || pending || busy) return;
    pending = true; setBusy(busy);
    try {
      const response = await api[method](...args);
      if (!response.ok && response.message) toast(response.message, 'error');
      render(response.state, response.ok && resetForm);
      if (response.ok) { hidePassword(); if (resetForm) $('form-error').hidden = true; }
    } catch (_) { toast('操作暂时未完成，请稍后重试。', 'error'); }
    finally { pending = false; setBusy(busy); }
  }
  async function poll() {
    if (!api || polling) return;
    polling = true;
    try { render(await api.get_state(lastLog)); }
    catch (_) { /* Keep the current form intact during a transient bridge interruption. */ }
    finally { polling = false; }
  }
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
  document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => showView(button.dataset.go)));
  $('account-form').addEventListener('submit', event => { event.preventDefault(); if (validate()) act('connect', [payload()], true); });
  $('save-button').addEventListener('click', () => { if (validate()) act('save_settings', [payload()], true); });
  $('check-button').addEventListener('click', () => act('check_status', []));
  $('clear-button').addEventListener('click', () => act('clear_settings', [], true));
  $('dismiss-toast').addEventListener('click', dismissToast);
  $('new-logs').addEventListener('click', () => { $('log-scroll').scrollTop = $('log-scroll').scrollHeight; $('new-logs').hidden = true; });
  $('log-scroll').addEventListener('scroll', () => { const pane = $('log-scroll'); if (pane.scrollHeight - pane.scrollTop - pane.clientHeight < 30) $('new-logs').hidden = true; });
  fields.forEach(id => $(id).addEventListener('input', () => {
    dirty = true; $('save-hint').textContent = '有未保存的更改，点击保存后生效。';
    $(id).removeAttribute('aria-invalid'); $('form-error').hidden = true; updatePasswordHint();
  }));
  $('reveal-password').addEventListener('click', () => {
    if ($('password').type === 'text') { hidePassword(); return; }
    $('password').type = 'text'; $('reveal-password').setAttribute('aria-pressed', 'true');
    $('reveal-password').setAttribute('aria-label', '隐藏新输入的密码');
    revealTimer = setTimeout(hidePassword, 15000);
  });
  window.addEventListener('blur', hidePassword);
  document.addEventListener('visibilitychange', () => { if (document.hidden) hidePassword(); });
  $('motion').addEventListener('change', async () => {
    const enabled = $('motion').checked; setMotion(enabled);
    try { const response = await api.set_motion(enabled); if (!response.ok) { setMotion(!enabled); toast(response.message, 'error'); } }
    catch (_) { setMotion(!enabled); toast('动效设置未能保存。', 'error'); }
  });
  document.addEventListener('dragover', event => event.preventDefault());
  document.addEventListener('drop', event => event.preventDefault());
  document.addEventListener('click', event => { if (event.target.closest('a')) event.preventDefault(); });

  async function start() {
    if (api || typeof window.pywebview?.api?.get_state !== 'function') return;
    api = window.pywebview.api;
    await poll();
    window.campusApp.ready = hydrated;
    setInterval(poll, 700);
  }
  window.campusApp = {ready: false, inspect: () => ({ui_loaded: hydrated, icon_loaded: document.querySelector('.brand img').complete,
    web_frontend: true, bridge_ready: Boolean(api), motion_loaded: document.querySelector('style').textContent.includes('busy-line'),
    horizontal_overflow: document.documentElement.scrollWidth > innerWidth, password_is_masked: $('password').type === 'password'})};
  window.addEventListener('pywebviewready', start);
  setBusy(false);
  start();
})();
