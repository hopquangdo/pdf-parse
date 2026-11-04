import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '../auth/session';
import { api, ApiError, refreshSession } from './client';

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const user = { id: 'u1', email: 'a@x.com', name: 'A', role: 'user', must_change_password: false };
const sessionBody = (token: string) => ({ user, access_token: token, token_type: 'bearer', expires_in: 900 });

type Call = { url: string; auth: string | null; method: string };
let calls: Call[];
let handler: (url: string, call: Call) => Response | Promise<Response>;

beforeEach(() => {
  calls = [];
  session.set(null);
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const call = { url, auth: new Headers(init?.headers).get('Authorization'), method: init?.method ?? 'GET' };
    calls.push(call);
    return handler(url, call);
  }));
});
afterEach(() => vi.unstubAllGlobals());

describe('access token header', () => {
  it('sends Authorization: Bearer on data requests, and nothing before sign-in', async () => {
    handler = () => json(200, []);
    await api.listJobs();
    expect(calls[0].auth).toBeNull();
    session.set('tok-1');
    await api.listJobs();
    expect(calls[1].auth).toBe('Bearer tok-1');
  });

  it('login stores the token in memory and does not send an old one', async () => {
    session.set('stale');
    handler = () => json(200, sessionBody('fresh'));
    await api.login('a@x.com', 'pw');
    expect(calls[0].auth).toBeNull();
    expect(session.token).toBe('fresh');
  });

  it('keeps the token out of persistent storage', async () => {
    const setItem = vi.fn();
    vi.stubGlobal('localStorage', { setItem, getItem: () => null });
    vi.stubGlobal('sessionStorage', { setItem, getItem: () => null });
    handler = () => json(200, sessionBody('secret-token'));
    await api.login('a@x.com', 'pw');
    expect(setItem).not.toHaveBeenCalled();
  });
});

describe('refresh on 401', () => {
  it('refreshes once, retries with the new token, and returns the data', async () => {
    session.set('old');
    handler = (url, call) => {
      if (url === '/auth/refresh') return json(200, sessionBody('new'));
      return call.auth === 'Bearer new' ? json(200, [{ id: 'j1' }]) : json(401, { detail: { code: 'token_expired', message: 'expired' } });
    };
    const jobs = await api.listJobs();
    expect(jobs).toEqual([{ id: 'j1' }]);
    expect(calls.map((c) => c.url)).toEqual(['/extractions', '/auth/refresh', '/extractions']);
    expect(calls[1].auth).toBeNull(); // the refresh call itself carries only the cookie
    expect(session.token).toBe('new');
  });

  it('ends the session when the refresh is refused, and throws the original 401', async () => {
    session.set('old');
    const expired = vi.fn();
    const off = session.onExpired(expired);
    handler = (url) => (url === '/auth/refresh' ? json(401, { detail: { code: 'invalid_refresh', message: 'gone' } }) : json(401, { detail: { code: 'not_authenticated', message: 'Sign in to continue.' } }));
    await expect(api.listJobs()).rejects.toMatchObject({ status: 401, code: 'not_authenticated' });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(session.token).toBeNull();
    off();
  });

  it('does not loop: a second 401 after a successful refresh is an error, not another refresh', async () => {
    session.set('old');
    handler = (url) => (url === '/auth/refresh' ? json(200, sessionBody('new')) : json(401, { detail: 'nope' }));
    await expect(api.listJobs()).rejects.toBeInstanceOf(ApiError);
    expect(calls.filter((c) => c.url === '/auth/refresh')).toHaveLength(1);
    expect(calls.filter((c) => c.url === '/extractions')).toHaveLength(2);
  });

  it('shares one refresh between simultaneous 401s (each refresh rotates the cookie)', async () => {
    session.set('old');
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    handler = async (url, call) => {
      if (url === '/auth/refresh') { await gate; return json(200, sessionBody('new')); }
      return call.auth === 'Bearer new' ? json(200, []) : json(401, { detail: 'expired' });
    };
    const all = Promise.all([api.listJobs(), api.catalog(), api.getJob('abc')]);
    await vi.waitFor(() => expect(calls.filter((c) => c.url === '/auth/refresh').length).toBe(1));
    release();
    await all;
    expect(calls.filter((c) => c.url === '/auth/refresh')).toHaveLength(1);
  });

  it('a wrong password is shown as such and never triggers a refresh', async () => {
    handler = () => json(401, { detail: { code: 'invalid_credentials', message: 'Invalid email or password.' } });
    await expect(api.login('a@x.com', 'bad')).rejects.toMatchObject({ status: 401, code: 'invalid_credentials', message: 'Invalid email or password.' });
    expect(calls.map((c) => c.url)).toEqual(['/auth/login']);
  });

  it('refreshSession restores a session after a reload and reports failure as null', async () => {
    handler = () => json(200, sessionBody('restored'));
    expect((await refreshSession())?.user.email).toBe('a@x.com');
    expect(session.token).toBe('restored');
    handler = () => json(401, { detail: 'x' });
    expect(await refreshSession()).toBeNull();
  });
});

describe('errors', () => {
  it('reads our {code, message} detail, plain strings and validation lists', async () => {
    handler = () => json(409, { detail: { code: 'email_taken', message: 'Already exists.' } });
    session.set('t');
    await expect(api.changePassword('a', 'b')).rejects.toMatchObject({ status: 409, code: 'email_taken', message: 'Already exists.' });
    handler = () => json(404, { detail: 'Không tìm thấy job' });
    await expect(api.getJob('x')).rejects.toMatchObject({ message: 'Không tìm thấy job' });
    handler = () => json(422, { detail: [{ loc: ['body', 'rows', 0, 'w'], msg: 'must be greater than 0' }] });
    await expect(api.saveRows('x', [])).rejects.toMatchObject({ code: 'validation', message: 'rows.0.w: must be greater than 0' });
  });

  it('reports an unreachable server in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await expect(api.health()).rejects.toMatchObject({ status: 0, code: 'network' });
  });
});

describe('logout', () => {
  it('clears the token even when the server cannot be reached', async () => {
    session.set('tok');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
    await api.logout();
    expect(session.token).toBeNull();
  });

  it('sends the access token so the server can revoke exactly this session', async () => {
    session.set('tok');
    handler = () => new Response(null, { status: 204 });
    await api.logout();
    expect(calls[0]).toMatchObject({ url: '/auth/logout', method: 'POST', auth: 'Bearer tok' });
  });
});
