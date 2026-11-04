import { session } from '../auth/session';
import type { Catalog } from '../lib/formulas';
import type { AuthUser, DrawingTypeInfo, HistoryItem, OcrJob, ExportResult, Job, JobSummary, Row, SessionBody, UploadOptions } from './types';

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string = '') {
    super(message);
    this.name = 'ApiError';
  }
}

interface FastApiDetail {
  loc?: (string | number)[];
  msg: string;
}

/** FastAPI sends a string, a list of validation errors, or our own `{code, message}` object. */
function parseDetail(detail: unknown): { message: string; code: string } {
  if (!detail) return { message: '', code: '' };
  if (typeof detail === 'string') return { message: detail, code: '' };
  if (Array.isArray(detail)) {
    const message = (detail as FastApiDetail[]).map((e) => `${(e.loc ?? []).filter((x) => x !== 'body').join('.')}: ${e.msg}`).join('; ');
    return { message, code: 'validation' };
  }
  const d = detail as { code?: string; message?: string };
  return { message: d.message ?? JSON.stringify(detail), code: d.code ?? '' };
}

async function toError(res: Response): Promise<ApiError> {
  let parsed = { message: '', code: '' };
  try {
    parsed = parseDetail((await res.json()).detail);
  } catch {
    /* body was not JSON */
  }
  return new ApiError(parsed.message || `Request failed (${res.status})`, res.status, parsed.code);
}

async function rawFetch(path: string, init: RequestInit | undefined, withToken: boolean): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (withToken && session.token) headers.set('Authorization', `Bearer ${session.token}`);
  try {
    return await fetch(path, { ...init, headers, credentials: 'same-origin' });
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0, 'network');
  }
}

/* ------------------------------------------------------------------ refresh (single flight) */
let inflightRefresh: Promise<SessionBody | null> | null = null;

/**
 * Exchange the refresh cookie for a new access token. Concurrent callers share one request, because every refresh
 * rotates the cookie and a second, simultaneous attempt would otherwise look like a replayed token.
 */
export function refreshSession(): Promise<SessionBody | null> {
  inflightRefresh ??= (async () => {
    try {
      const res = await rawFetch('/auth/refresh', { method: 'POST' }, false);
      if (!res.ok) return null;
      const body = (await res.json()) as SessionBody;
      session.set(body.access_token);
      return body;
    } catch {
      return null;
    } finally {
      inflightRefresh = null;
    }
  })();
  return inflightRefresh;
}

/**
 * Authenticated request. On a 401 it refreshes once and retries once; if the refresh fails the session is over and
 * the app is told to show the sign-in page. Returns the successful Response, or throws ApiError.
 */
async function send(path: string, init?: RequestInit, opts: { auth?: boolean } = {}): Promise<Response> {
  const auth = opts.auth ?? true;
  let res = await rawFetch(path, init, auth);
  if (res.status === 401 && auth) {
    const renewed = await refreshSession();
    if (!renewed) {
      session.expire();
      throw await toError(res);
    }
    res = await rawFetch(path, init, auth);
  }
  if (!res.ok) throw await toError(res);
  return res;
}

async function request<T>(path: string, init?: RequestInit, opts?: { auth?: boolean }): Promise<T> {
  const res = await send(path, init, opts);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** The server names downloads after the drawing (`filename*=utf-8''...`); fall back to a given name. */
function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get('content-disposition') ?? '';
  const star = /filename\*=utf-8''([^;]+)/i.exec(cd);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* fall through */
    }
  }
  return /filename="?([^";]+)"?/i.exec(cd)?.[1] ?? fallback;
}

export const api = {
  health: () => request<{ ok: boolean }>('/health', undefined, { auth: false }),

  // ---- accounts
  async login(email: string, password: string): Promise<SessionBody> {
    const body = await request<SessionBody>('/auth/login', jsonInit('POST', { email, password }), { auth: false });
    session.set(body.access_token);
    return body;
  },
  async logout(): Promise<void> {
    try {
      // One call carries both credentials (header + refresh cookie), so the server can revoke this session either way.
      await rawFetch('/auth/logout', { method: 'POST' }, true);
    } catch {
      /* offline: the local sign-out below still happens */
    } finally {
      session.set(null);
    }
  },
  changePassword: (current_password: string, new_password: string) =>
    request<{ user: AuthUser }>('/auth/change-password', jsonInit('POST', { current_password, new_password })),

  // ---- drawings
  listJobs: () => request<JobSummary[]>('/extractions'),
  catalog: () => request<Catalog>('/reference/catalog'),
  getJob: (id: string) => request<Job>(`/extractions/${id}`),
  drawingTypes: () => request<DrawingTypeInfo[]>('/reference/drawing-types'),
  upload(file: File, { rotate, cols, rows, drawingType }: UploadOptions) {
    const body = new FormData();
    body.append('file', file);
    return request<{ id: string; status: string }>(`/extractions?rotate=${rotate}&cols=${cols}&rows=${rows}${drawingType ? `&drawing_type=${encodeURIComponent(drawingType)}` : ''}`, { method: 'POST', body });
  },
  saveRows: (id: string, rows: Row[]) => request<Job>(`/extractions/${id}/rows`, jsonInit('PUT', { rows })),
  exportRows: (rows: Row[], paintFactor: number, jobId: string) =>
    request<ExportResult>('/exports', jsonInit('POST', { rows, paint_factor: paintFactor, job_id: jobId })),

  // ---- files: a plain <a href> or pdf.js URL cannot send the Authorization header, so these fetch with it
  async fetchPdf(id: string): Promise<Uint8Array> {
    return new Uint8Array(await (await send(`/extractions/${id}/file`)).arrayBuffer());
  },
  /** Downloads the workbook; the file is named after the drawing with the extension swapped to .xlsm. */
  async downloadExport(exportId: string, sourceName: string): Promise<void> {
    const res = await send(`/exports/${exportId}?name=${encodeURIComponent(sourceName)}`);
    saveBlob(await res.blob(), filenameFrom(res, 'export.xlsm'));
  },
  // ---- OCR runs (server side: they keep running if the tab is closed)
  history: () => request<HistoryItem[]>('/history'),
  createOcrJob(file: File, pages: string, rotate: string | number) {
    const body = new FormData();
    body.append('file', file);
    body.append('pages', pages);
    body.append('rotate', String(rotate));
    return request<{ id: string; status: string }>('/ocr/jobs', { method: 'POST', body });
  },
  getOcrJob: (id: string) => request<OcrJob>(`/ocr/jobs/${id}`),
  retryOcrJob: (id: string) => request<{ id: string }>(`/ocr/jobs/${id}/retry`, { method: 'POST' }),
  async downloadOcrXlsx(id: string, fallbackName: string): Promise<void> {
    const res = await send(`/ocr/jobs/${id}/xlsx`);
    saveBlob(await res.blob(), filenameFrom(res, fallbackName));
  },
  async downloadRunLog(id: string): Promise<void> {
    const res = await send(`/extractions/${id}/run`);
    saveBlob(new Blob([await res.text()], { type: 'application/json' }), `run-${id}.json`);
  },
};
