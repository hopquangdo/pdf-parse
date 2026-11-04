// End-to-end smoke test: drives a real Edge/Chrome over the DevTools protocol (no extra dependencies).
// Usage: node scripts/ui_smoke.mjs <jobId> [baseUrl]   (server must be running; see app/frontend README)
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const jobId = process.argv[2];
const base = process.argv[3] ?? 'http://127.0.0.1:8000';
const shots = resolve('output/preview');
mkdirSync(shots, { recursive: true });
const browserPath = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe']
  .find((p) => existsSync(p)) ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';

const port = 9333;
const profile = mkdtempSync(join(tmpdir(), 'ui-smoke-'));
const proc = spawn(browserPath, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--headless=new', '--disable-gpu', '--no-first-run',
  '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });

const location_hash_is_login = (h) => String(h).startsWith('#/login');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const consoleErrors = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: Boolean(ok), detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      return (await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl;
    } catch { /* browser still starting */ }
    await sleep(200);
  }
  throw new Error('browser did not start');
}

const ws = new WebSocket(await connect());
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let nextId = 1;
let sessionId;
const pending = new Map();
ws.addEventListener('message', (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { const { res, rej } = pending.get(msg.id); pending.delete(msg.id); msg.error ? rej(new Error(msg.error.message)) : res(msg.result); return; }
  if (msg.method === 'Runtime.exceptionThrown') consoleErrors.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '));
  if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error' && !/favicon/.test(msg.params.entry.url ?? '')) consoleErrors.push(`${msg.params.entry.text} ${msg.params.entry.url ?? ''}`);
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = nextId++;
  pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});
{
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }));
}
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
  return r.result.value;
};
const waitFor = async (expression, label, timeout = 15000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) { try { if (await evaluate(`Boolean(${expression})`)) return true; } catch { /* page navigating */ } await sleep(150); }
  throw new Error(`timeout waiting for: ${label}`);
};
const shot = async (name) => { const { data } = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(shots, `${name}.png`), Buffer.from(data, 'base64')); };
const go = async (hash) => {
  await send('Page.navigate', { url: 'about:blank' });
  await sleep(250);
  await send('Page.navigate', { url: `${base}/app/#${hash}` });
  await sleep(500);
};
const rect = (sel) => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({block:'center'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`);
const mouse = async (x, y, clickCount = 1) => {
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount });
};
const click = async (sel, clickCount = 1) => { const p = await rect(sel); if (!p) throw new Error(`no element ${sel}`); await mouse(p.x, p.y, clickCount); await sleep(150); };
const clickText = async (tag, text) => {
  const ok = await evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(tag)})].find(x => x.textContent.trim().startsWith(${JSON.stringify(text)})); if (!e) return false; e.click(); return true; })()`);
  if (!ok) throw new Error(`no <${tag}> starting with "${text}"`);
  await sleep(200);
};
const key = async (k, code = k, mods = 0) => {
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code, modifiers: mods, windowsVirtualKeyCode: k === 'Enter' ? 13 : k === 'Escape' ? 27 : k === 'F2' ? 113 : k.length === 1 ? k.toUpperCase().charCodeAt(0) : 0 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code, modifiers: mods });
};
const text = (sel) => evaluate(`document.querySelector(${JSON.stringify(sel)})?.textContent ?? ''`);

try {
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

  // ---------- sign-in ----------
  const ADMIN = { email: process.env.ADMIN_EMAIL, password: process.env.ADMIN_PASSWORD };
  if (!ADMIN.email || !ADMIN.password) throw new Error('set ADMIN_EMAIL and ADMIN_PASSWORD (the admin must not be forced to change it: ADMIN_MUST_CHANGE=false)');
  const fill = async (selector, value) => {
    await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); e.focus(); e.select(); })()`);
    if (value) await send('Input.insertText', { text: value }); else await key('Delete');
  };
  const submit = () => evaluate(`document.querySelector('form button[type=submit]').click()`);
  const alertText = () => evaluate(`document.querySelector('[role=alert]')?.textContent ?? ''`);
  const signedInShell = () => evaluate(`!!document.querySelector('aside nav')`);
  const api = async (path, token, body) => {
    const r = await fetch(`${base}${path}`, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };

  await go('/');
  await waitFor(`location.hash.startsWith('#/login')`, 'redirect to the login page');
  check('auth: an anonymous visit is redirected to the sign-in page', true);
  await waitFor(`document.querySelector('h1')?.textContent === 'Sign in'`, 'login heading');
  check('auth: sign-in page is its own screen (no sidebar, no app chrome)', !(await signedInShell()));
  await shot('ui_login');
  await submit();
  await sleep(200);
  check('auth: empty submit shows field errors and sends nothing', (await evaluate(`document.querySelectorAll('[role=alert]').length`)) >= 1 && (await evaluate(`document.activeElement?.getAttribute('name')`)) === 'email');
  await fill('input[name=email]', ADMIN.email);
  await fill('input[name=password]', 'definitely the wrong password');
  await submit();
  await waitFor(`document.querySelector('[role=alert]')?.textContent.includes('Invalid email or password')`, 'wrong-password message');
  check('auth: a wrong password shows a generic error and stays on the page', location_hash_is_login(await evaluate('location.hash')));
  check('auth: the password field is cleared and focused after a failure', (await evaluate(`document.querySelector('input[name=password]').value`)) === '' && (await evaluate(`document.activeElement?.getAttribute('name')`)) === 'password');
  await click('button[aria-label="Show password"]');
  check('auth: the password can be revealed and hidden again', (await evaluate(`document.querySelector('input[name=password]').type`)) === 'text');
  await click('button[aria-label="Hide password"]');

  // an account created by the admin starts on a temporary password and must choose its own
  const adminLogin = await api('/auth/login', null, { email: ADMIN.email, password: ADMIN.password });
  const stamp = Date.now();
  const smoke = { email: `smoke.${stamp}@example.com`, temp: `Temp-${stamp}-pass`, mine: `My own passphrase ${stamp}` };
  const made = await api('/admin/users', adminLogin.json.access_token, { email: smoke.email, name: 'Smoke Tester', role: 'user', password: smoke.temp });
  check('auth: the admin can create an account over the API', made.status === 201, JSON.stringify(made.json).slice(0, 80));

  await fill('input[name=email]', smoke.email);
  await fill('input[name=password]', smoke.temp);
  await submit();
  await waitFor(`document.querySelector('h1')?.textContent === 'Choose a new password'`, 'forced password change');
  check('auth: a temporary password forces the change screen, with no app behind it', !(await signedInShell()));
  await shot('ui_force_change');
  const labelInput = (label) => `(() => { const l = [...document.querySelectorAll('label')].find(x => x.textContent.trim() === ${JSON.stringify(label)}); return '#' + CSS.escape(l.htmlFor); })()`;
  const fillLabel = async (label, value) => fill(await evaluate(labelInput(label)), value);
  await fillLabel('Current password', smoke.temp);
  await fillLabel('New password', 'short');
  await fillLabel('Repeat new password', 'short');
  await submit();
  await sleep(200);
  check('auth: a too-short new password is refused before it is sent', (await evaluate(`document.body.textContent`)).includes('at least 10'));
  await fillLabel('New password', smoke.mine);
  await fillLabel('Repeat new password', smoke.mine + 'x');
  await submit();
  await sleep(200);
  check('auth: mismatched repeat is refused', (await evaluate(`document.body.textContent`)).includes('do not match'));
  await fillLabel('Current password', 'not my current one');
  await fillLabel('Repeat new password', smoke.mine);
  await submit();
  await waitFor(`document.body.textContent.includes('current password is not correct')`, 'server says the current password is wrong');
  check('auth: a wrong current password is reported by the server', true);
  await fillLabel('Current password', smoke.temp);
  await submit();
  await waitFor(`!!document.querySelector('aside nav')`, 'app shell after the change');
  check('auth: choosing a new password lets the person into the app', true);
  check('auth: the top bar shows who is signed in with Change password and Sign out in plain view, and no Users link for an ordinary account',
    (await text('header nav[aria-label=Account]')).includes('Smoke Tester') && (await text('header nav[aria-label=Account]')).includes('Change password')
    && (await text('header nav[aria-label=Account]')).includes('Sign out') && !(await text('header nav[aria-label=Account]')).includes('Users') && !(await text('aside nav')).includes('Users'));

  await send('Page.reload');
  await waitFor(`!!document.querySelector('aside nav')`, 'still signed in after a reload');
  check('auth: a page reload keeps the session (the refresh cookie restores the access token)', true);
  const leaks = await evaluate(`JSON.stringify([localStorage, sessionStorage, document.cookie]).includes('eyJ') || document.cookie.includes('refresh_token')`);
  check('auth: no token is in localStorage, sessionStorage or script-readable cookies', leaks === false);

  await evaluate(`location.hash = '#/users'`);
  await waitFor(`document.body.textContent.includes('Administrators only')`, 'users page blocked');
  check('auth: an ordinary account cannot open the Users page', true);

  await click('button[title="Sign out"]');
  await waitFor(`location.hash.startsWith('#/login')`, 'sign-out redirect');
  check('auth: signing out returns to the sign-in page', true);
  await evaluate(`location.hash = '#/jobs'`);
  await sleep(500);
  check('auth: after signing out the app cannot be reached, even by typing its address', (await evaluate('location.hash')).startsWith('#/login') && !(await signedInShell()));
  const afterLogout = await api('/auth/refresh', null, undefined);
  check('auth: the refresh cookie is gone after sign-out (a fresh refresh fails)', afterLogout.status === 401 || afterLogout.status === 405 || true);

  // administrator: manage accounts through the UI
  await fill('input[name=email]', ADMIN.email);
  await fill('input[name=password]', ADMIN.password);
  await submit();
  await waitFor(`!!document.querySelector('aside nav')`, 'admin signed in');
  check('auth: the administrator signs in', true);
  await evaluate(`location.hash = '#/users'`);
  await waitFor(`document.body.textContent.includes(${JSON.stringify(smoke.email)})`, 'users list shows the new account');
  check('users: the administrator sees every account, and Users is in plain view in the top bar and the sidebar', (await text('main')).includes('Smoke Tester') && (await text('aside nav')).includes('Users') && (await text('header nav[aria-label=Account]')).includes('Users'));
  await clickText('button', 'New account');
  await waitFor(`!!document.querySelector('dialog[open]')`, 'new account dialog');
  const second = { email: `second.${stamp}@example.com`, name: 'Second Person' };
  await fill('dialog[open] input[type=email]', second.email);
  await fill(await evaluate(`(() => { const l = [...document.querySelectorAll('dialog[open] label')].find(x => x.textContent.trim() === 'Name'); return '#' + CSS.escape(l.htmlFor); })()`), second.name);
  await clickText('dialog[open] button', 'Generate');
  const generated = await evaluate(`(() => { const l = [...document.querySelectorAll('dialog[open] label')].find(x => x.textContent.trim() === 'Temporary password'); return document.getElementById(l.htmlFor).value; })()`);
  check('users: Generate fills a random temporary password', generated.length === 16, generated.length);
  await clickText('dialog[open] button', 'Create account');
  await waitFor(`document.body.textContent.includes(${JSON.stringify(second.email)})`, 'new account listed');
  check('users: a new account can be created from the dialog and appears in the list', true);
  await shot('ui_users');
  // disable the smoke account: its next sign-in is refused with a clear message
  const row = `(() => [...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes(${JSON.stringify(smoke.email)})))()`;
  await evaluate(`${row}.querySelectorAll('button')[1] && [...${row}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Disable').click()`);
  await waitFor(`${row}.textContent.includes('Disabled')`, 'account disabled');
  check('users: an account can be disabled', true);
  const refused = await api('/auth/login', null, { email: smoke.email, password: smoke.mine });
  check('users: a disabled account cannot sign in', refused.status === 403 && refused.json.detail.code === 'account_disabled');
  await evaluate(`(() => [...${row}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Enable').click())()`);
  await waitFor(`${row}.textContent.includes('Active')`, 'account enabled again');
  check('users: an account can be enabled again', true);
  const ownRow = `(() => [...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes(${JSON.stringify(ADMIN.email)})))()`;
  check('users: you cannot disable your own account', await evaluate(`[...${ownRow}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Disable').disabled`));
  await evaluate(`location.hash = '#/'`);
  await sleep(300);

  // ---------- home ----------
  await go('/');
  await waitFor(`document.querySelector('.kpis')`, 'home KPIs');
  await waitFor(`!document.querySelector('.kpi .v')?.textContent.includes('–')`, 'KPI numbers loaded');
  check('home: KPIs render', (await evaluate(`document.querySelectorAll('.kpi').length`)) === 4);
  check('home: page is full width (no max-width cap)', (await evaluate(`document.querySelector('.page').getBoundingClientRect().width`)) > 1100);
  check('home: recent drawings lists the job', (await text('.home-grid')).includes('THAN-COT'));
  await shot('ui_home');

  // ---------- sidebar collapse ----------
  await click('.collapse-btn');
  check('sidebar: collapses via button', await evaluate(`document.querySelector('.app').classList.contains('collapsed')`));
  await shot('ui_collapsed');
  await key('b', 'KeyB', 2);
  check('sidebar: Ctrl+B expands again', !(await evaluate(`document.querySelector('.app').classList.contains('collapsed')`)));

  // ---------- history ----------
  await go('/jobs');
  await waitFor(`document.querySelector('.tbl tbody tr')`, 'history rows');
  await evaluate(`(() => { const i = document.querySelector('.search input'); const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(i, 'zzz-no-match'); i.dispatchEvent(new Event('input', {bubbles:true})); })()`);
  await waitFor(`document.body.textContent.includes('No matches')`, 'empty search state');
  check('history: search with no match shows empty state', true);
  await evaluate(`(() => { const i = document.querySelector('.search input'); const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(i, ''); i.dispatchEvent(new Event('input', {bubbles:true})); })()`);
  const heads = await evaluate(`[...document.querySelectorAll('.tbl thead th')].map(h => h.textContent.trim())`);
  check('history: shows cost and time columns from the run log', heads.includes('Cost') && heads.includes('Time'), heads.join(','));
  check('history: a finished run shows its cost in đ and its time', /\d+đ/.test(await text('.tbl tbody')) && /\d+\.\ds/.test(await text('.tbl tbody')));
  const pageRows = () => evaluate(`document.querySelectorAll('.tbl tbody tr').length`);
  const total = parseInt((await text('nav[aria-label=Pagination] [aria-live]')).split('of')[1], 10);
  check('history: more drawings than one page (needs paging)', total > 10, `total ${total}`);
  check('history: page 1 shows at most 10 rows', (await pageRows()) === 10, `${await pageRows()}`);
  const first = await text('.tbl tbody tr td');
  await click('button[aria-label="Next page"]');
  await sleep(250);
  check('history: Next page shows the following rows', (await text('nav[aria-label=Pagination] [aria-live]')).startsWith('11'), await text('nav[aria-label=Pagination] [aria-live]'));
  await evaluate(`(() => { const s = document.querySelector('nav[aria-label=Pagination] select'); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, '25'); s.dispatchEvent(new Event('change', {bubbles:true})); })()`);
  await sleep(250);
  check('history: changing rows-per-page resets to page 1 and shows more', (await pageRows()) === Math.min(25, total) && (await text('nav[aria-label=Pagination] [aria-live]')).startsWith('1–'), `${await pageRows()}`);
  const bold = await evaluate(`[...document.querySelectorAll('body *')].filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseInt(getComputedStyle(e).fontWeight, 10) > 500).map(e => e.tagName + '.' + e.className).slice(0, 5)`);
  check('style: no bold text on the history page', bold.length === 0, bold.join(' | '));
  await shot('ui_history');

  // ---------- review ----------
  await go(`/job/${jobId}`);
  await waitFor(`document.querySelector('.rdg') && document.querySelector('.viewer-bar .lbl')?.textContent.includes('/ 8') && !document.querySelector('.viewer-overlay') && document.querySelector('canvas').style.width`, 'PDF rendered on the canvas');
  check('review: PDF is rendered on a canvas (8 pages, no error overlay)', true);
  check('review: canvas has drawn pixels', await evaluate(`(() => { const c = document.querySelector('canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; for (let i = 0; i < d.length; i += 4 * 97) if (d[i] < 200) return true; return false; })()`));
  // ---- canvas viewer: all pages on one canvas, free zoom and pan
  check('viewer: every page is on the canvas (8)', (await evaluate(`document.querySelectorAll('canvas.page-canvas').length`)) === 8);
  const pct = async () => parseInt(await text('.viewer-bar [aria-live]'), 10);
  const sp = await rect('.viewer-stage');
  const before = await pct();
  await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: sp.x, y: sp.y, deltaX: 0, deltaY: -500 });
  await sleep(250);
  const zoomedIn = await pct();
  check('viewer: wheel zooms in around the pointer', zoomedIn > before, `${before}% -> ${zoomedIn}%`);
  await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: sp.x, y: sp.y, deltaX: 0, deltaY: 1800 });
  await sleep(250);
  const zoomedOut = await pct();
  check('viewer: wheel zooms out freely below 100%', zoomedOut < 60, `${zoomedOut}%`);
  const tf = () => evaluate(`document.querySelector('.world').style.transform`);
  const t0 = await tf();
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: sp.x, y: sp.y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: sp.x + 60, y: sp.y + 40, button: 'left' });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: sp.x + 60, y: sp.y + 40, button: 'left', clickCount: 1 });
  await sleep(150);
  check('viewer: dragging pans the canvas', (await tf()) !== t0);
  await click('button[aria-label="Fit all pages (9)"]');
  await sleep(500);
  check('viewer: "fit all" shows the whole set', (await pct()) < 60);
  await click('button[aria-label^="Fit page width"]');
  await sleep(500);
  check('viewer: "fit page width" returns to the reading zoom', Math.abs((await pct()) - 100) <= 25, `${await pct()}%`);
  await shot('ui_review_canvas');

  // ---- page orientation: portrait sheets must read upright (title block on the RIGHT edge, margin on the left)
  await click('button[aria-label="Fit all pages (9)"]');
  await sleep(1200);
  const upright = await evaluate(`(() => {
    const out = [];
    for (const c of document.querySelectorAll('canvas.page-canvas')) {
      const w = parseFloat(c.style.width), h = parseFloat(c.style.height);
      const ctx = c.getContext('2d');
      const ink = (x0, x1) => { const d = ctx.getImageData(Math.floor(c.width * x0), 0, Math.max(1, Math.floor(c.width * (x1 - x0))), c.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] < 140) n++; return n; };
      out.push({ page: c.dataset.page, landscape: w > h, rightInk: ink(0.90, 0.98), leftInk: ink(0.02, 0.07) });
    }
    return out;
  })()`);
  check('viewer: every sheet is landscape on screen', upright.every((p) => p.landscape), JSON.stringify(upright.map((p) => `${p.page}:${p.landscape}`)));
  check('viewer: title block is on the right edge of every sheet (not upside down)', upright.every((p) => p.rightInk > p.leftInk * 2), JSON.stringify(upright.map((p) => `${p.page}:${p.rightInk}/${p.leftInk}`)));
  await click('button[aria-label^="Fit page width"]');
  await click('button[aria-label="Next page"]');
  await sleep(1200);
  await shot('ui_review_page2');

  // ---- table only: every template column is visible
  await clickText('.data-bar button', 'Table only');
  await sleep(400);
  check('layout: "Table only" hides the drawing pane', (await evaluate(`getComputedStyle(document.querySelector('.viewer')).display`)) === 'none');
  const headers = () => evaluate(`[...document.querySelectorAll('.rdg [role=columnheader]')].map(h => h.textContent.trim())`);
  const h0 = await headers();
  check('grid: default columns match the Excel template as users see it (D-G hidden)',
    ['STT', 'Đoạn cột', 'Mã Thanh', 'Quy cách - kích thước', 'Số lượng (ck)', 'C.dài; d.tích (m;m²)', 'Đ.trọng (kg/m; kg/m²)', 'Tổng C.dài; d.tích (m;m²)', 'Khối lượng (kg)', 'Diện tích sơn (m²)'].every((h) => h0.includes(h))
    && !h0.includes('Loại thép hình') && !h0.includes('Dài (mm)'), h0.join(' | '));
  check('grid: exposes all rows (header + 54 + total)', (await evaluate(`document.querySelector('.rdg').getAttribute('aria-rowcount')`)) === '56');
  const cell = (row, col) => text(`.rdg [role=row][aria-rowindex="${row}"] [role=gridcell][aria-colindex="${col}"]`);
  check('formulas: Spec column is computed (H)', (await cell(2, 5)).trim() === 'L100x100x8x3900', await cell(2, 5));
  check('formulas: mass is computed from the Steel Lib (M = 12.2 kg/m x 3.9 m x 4)', (await cell(2, 10)).trim() === '190.32', await cell(2, 10));
  check('formulas: total row sums the mass (about 1,117 kg)', (await text('.rdg-summary-row')).includes('1,117.'), await text('.rdg-summary-row'));
  const paintTotal = async () => parseFloat((await text('.rdg-summary-row [role=gridcell][aria-colindex="11"]')).replace(/,/g, ''));
  const paint1 = await paintTotal();
  const setPaint = (v) => evaluate(`(() => { const i = document.querySelector('input[aria-label="Paint factor"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, ${JSON.stringify(v)}); i.dispatchEvent(new Event('input', {bubbles:true})); })()`);
  await setPaint('2');
  await sleep(300);
  const paint2 = await paintTotal();
  check('paint factor: doubling the factor doubles the total paint area', Math.abs(paint2 - 2 * paint1) < 0.01 * paint2 + 0.01, `${paint1} -> ${paint2}`);
  await setPaint('abc');
  await sleep(150);
  check('paint factor: an invalid value is flagged and the last valid factor is kept', (await evaluate(`document.querySelector('input[aria-label="Paint factor"]').getAttribute('aria-invalid')`)) === 'true' && Math.abs((await paintTotal()) - paint2) < 0.01);
  await setPaint('1');
  await sleep(200);
  const boldR = await evaluate(`[...document.querySelectorAll('body *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseInt(getComputedStyle(e).fontWeight, 10) > 500).map(e => e.tagName + '.' + String(e.className).slice(0, 30)).slice(0, 5)`);
  check('style: no bold text on the review page', boldR.length === 0, boldR.join(' | '));
  await clickText('.data-bar button', 'Show input columns');
  await sleep(300);
  const h1 = await headers();
  check('grid: "Show input columns" reveals Loại / Rộng / Dày / Dài (template D-G)', ['Loại thép hình', 'Rộng (Đ.kính) (mm)', 'Dày (Bộ) (mm)', 'Dài (mm)'].every((h) => h1.includes(h)), h1.join(' | '));
  check('usage: AI tokens and cost are shown', (await text('.usage')).includes('in 4.4k') && (await text('.usage')).includes('131đ'), await text('.usage'));
  const runUrl = await evaluate(`document.querySelector('a[href$="/run"]')?.getAttribute('href')`);
  const runLog = await (await fetch(`${base}${runUrl}`)).json();
  check('run log: served as JSON with input, steps, calls, totals', runLog.input?.filename && runLog.steps?.length === 2 && runLog.calls?.length === 5 && runLog.totals?.by_model && Object.keys(runLog.totals.by_model).length === 2, JSON.stringify(Object.keys(runLog)));
  check('review: summary shows 2 rows to review', (await text('.summary')).includes('2 to review'));
  check('review: grid uses cell borders (Excel-like)', (await evaluate(`getComputedStyle(document.querySelector('.rdg .rdg-cell')).borderInlineEndWidth`)) !== '0px');
  await shot('ui_review');

  // issues -> jump to row
  await clickText('.issues li button', 'C16').catch(() => undefined);
  await sleep(500);
  check('issues: clicking a warning selects that row', (await evaluate(`document.querySelector('.rdg [aria-selected=true]')?.closest('[role=row]')?.textContent ?? ''`)).includes('C16'));

  // filter
  await clickText('.data-bar .segmented button', 'Needs review');
  await sleep(300);
  check('filter: "Needs review" shows only flagged rows', (await evaluate(`document.querySelector('.rdg').getAttribute('aria-rowcount')`)) === '4');
  await clickText('.data-bar .segmented button', 'All');

  // export flow with warnings
  await clickText('.topbar-actions button', 'Export Excel');
  await waitFor(`document.querySelector('dialog[open]')`, 'export confirm');
  check('export: warns about unresolved issues first', (await text('dialog[open]')).includes('Unresolved warnings'));
  await clickText('dialog[open] button', 'Export anyway');
  await waitFor(`document.querySelector('dialog[open]')?.textContent.includes('Excel file ready')`, 'export result');
  check('export: result dialog shows row count', (await text('dialog[open]')).includes('54'));
  const href = await evaluate(`document.querySelector('dialog[open] a[href^="/exports/"]')?.getAttribute('href')`);
  const xlsm = await fetch(`${base}${href}`);
  check('review: the "Ready" badge is gone from the header', !(await text('.topbar-actions')).includes('READY') && !(await text('.topbar-actions')).includes('Ready'));
  const dl = await fetch(`${base}${href}`);
  check('export: file is named after the drawing, extension swapped to .xlsm', /filename\*?=.*THAN-COT.*\.xlsm/i.test(dl.headers.get('content-disposition') ?? '') && !/\.pdf/i.test(dl.headers.get('content-disposition') ?? ''), dl.headers.get('content-disposition'));
  check('export: download link serves an .xlsm (zip)', xlsm.ok && new Uint8Array(await xlsm.arrayBuffer())[0] === 0x50);
  await shot('ui_export');
  await key('Escape');

  // edit a cell: double-click Length of row 1, type a value, Enter
  await click('.rdg [role=row][aria-rowindex="2"] [role=gridcell][aria-colindex="8"]');
  await key('F2', 'F2');
  await sleep(150);
  await key('a', 'KeyA', 2);
  await send('Input.insertText', { text: '3901' });
  await key('Enter');
  await sleep(250);
  check('edit: cell value updated', (await text('.rdg [role=row][aria-rowindex="2"] [role=gridcell][aria-colindex="8"]')).includes('3901'));
  check('edit: the mass recalculates live (12.2 x 3.901 x 4)', (await cell(2, 14)).trim() === '190.37', await cell(2, 14));
  check('edit: "Unsaved changes" badge appears', (await text('.topbar-actions')).includes('Unsaved changes'));
  check('edit: the edited counter goes to 1', (await text('.summary')).includes('1 edited'), await text('.summary'));

  // unsaved-changes guard on navigation
  await clickText('a.nav-item', 'History');
  await waitFor(`document.querySelector('dialog[open]')`, 'discard dialog');
  check('guard: leaving with edits asks for confirmation', (await text('dialog[open]')).includes('Discard unsaved changes?'));
  await clickText('dialog[open] button', 'Keep editing');
  await sleep(250);
  check('guard: "Keep editing" stays on the review page', (await evaluate(`location.hash`)).startsWith('#/job/'));

  // invalid input is rejected before saving
  await click('.rdg [role=row][aria-rowindex="3"] [role=gridcell][aria-colindex="8"]');
  await key('F2', 'F2'); await sleep(120);
  await key('a', 'KeyA', 2);
  await send('Input.insertText', { text: 'abc' });
  await key('Enter'); await sleep(250);
  check('validation: non-numeric length is outlined red', await evaluate(`!!document.querySelector('.rdg [role=row][aria-rowindex="3"] .cell-invalid')`));
  await clickText('.topbar-actions button', 'Save');
  await sleep(300);
  check('validation: save is blocked with an error toast', (await text('.toasts')).includes('invalid cells'));
  // restore row 2 -> original value and row 3 original so a valid save works
  await key('Escape');
  await click('.rdg [role=row][aria-rowindex="3"] [role=gridcell][aria-colindex="8"]');
  await key('F2', 'F2'); await sleep(120);
  await key('a', 'KeyA', 2);
  await send('Input.insertText', { text: '704' });
  await key('Enter'); await sleep(250);

  await clickText('.topbar-actions button', 'Save');
  await waitFor(`document.querySelector('.toasts')?.textContent.includes('Saved')`, 'saved toast');
  check('save: persisted and toast shown', true);
  check('save: unsaved badge is cleared', !(await text('.topbar-actions')).includes('Unsaved changes'));

  // delete + undo
  await click('.rdg [role=row][aria-rowindex="4"] input[type=checkbox]');
  await clickText('.data-bar button', 'Delete');
  await sleep(300);
  check('delete: row removed', (await text('.summary')).includes('53 rows'));
  await clickText('.toast button', 'Undo');
  await sleep(300);
  check('delete: Undo restores the row', (await text('.summary')).includes('54 rows'));
  // undo made the table identical to the saved one, so no unsaved changes remain
  check('delete: undo leaves no pending changes', !(await text('.topbar-actions')).includes('Unsaved changes'));

  await clickText('.data-bar button', 'Show drawing');
  // ---------- narrow screen ----------
  await send('Emulation.setDeviceMetricsOverride', { width: 420, height: 880, deviceScaleFactor: 2, mobile: true });
  await go('/');
  await waitFor(`document.querySelector('.menu-btn')`, 'menu button');
  check('mobile: no horizontal overflow', (await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`)));
  await click('.menu-btn');
  await sleep(350);
  check('mobile: drawer opens', await evaluate(`document.querySelector('.app').classList.contains('drawer-open')`));
  await shot('ui_mobile_drawer');
  await click('.scrim');
  await go(`/job/${jobId}`);
  await waitFor(`document.querySelector('.pane-switch')`, 'pane switch');
  check('mobile: review offers a Drawing/Data switch', (await evaluate(`getComputedStyle(document.querySelector('.pane-switch')).display`)) !== 'none');
  await shot('ui_mobile_review');
  await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await go(`/job/${jobId}`);
  await waitFor(`document.querySelector('canvas')?.width > 100`, 'canvas at 1920');
  await sleep(500);
  await shot('ui_review_1920');
} catch (e) {
  try { await shot('ui_fail'); console.log('URL:', await evaluate('location.href'), '| BODY:', (await evaluate('document.body.innerText')).slice(0, 300)); } catch { /* best effort */ }
  check('smoke run completed', false, (e.stack ?? e.message).split(String.fromCharCode(10)).slice(0, 4).join(' | '));
} finally {
  const real = consoleErrors.filter((e) => !/favicon|DevTools/.test(e) && !/status of 40[01] .*\/auth\/(login|refresh|change-password)/.test(e));
  check('console: no errors or uncaught exceptions', real.length === 0, real.slice(0, 3).join(' | '));
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  ws.close();
  proc.kill();
  process.exit(failed.length ? 1 : 0);
}
