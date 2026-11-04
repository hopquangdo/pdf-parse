export type JobStatus = 'pending' | 'running' | 'done' | 'failed';
export type MemberType = 'L' | 'd' | 'Ф' | 'M';

/** A schedule row as the API stores it. Numeric fields may hold a raw string while the user is typing. */
export interface Row {
  section: string;
  mark: string | null;
  type: MemberType;
  w: number | string;
  t: number | string | null;
  len: number | string;
  qty: number | string;
}

export interface Issue {
  level: 'error' | 'warning' | 'info';
  message: string;
  mark: string | null;
}

export interface JobUsage {
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cost_vnd: number;
  unpriced_calls: number;
  call_seconds: number;
  wall_seconds?: number;
}

export interface Job {
  id: string;
  status: JobStatus;
  filename: string;
  rows: Row[];
  issues: Issue[];
  error: string | null;
  page_count: number;
  created_at: number;
  usage?: JobUsage;
}

export interface JobSummary {
  id: string;
  filename: string;
  status: JobStatus;
  page_count: number;
  created_at: number;
  rows: number;
  issues: number;
  cost_usd: number | null;
  cost_vnd: number | null;
  wall_seconds: number | null;
}

/** One line of the shared history: a drawing extraction (steel) or an OCR run (ocr). */
export interface HistoryItem extends JobSummary { kind: 'steel' | 'ocr' }

/** flags: "row,col" -> why a person should check that cell (a rule repaired it, or the recognizer was unsure) */
export interface OcrTable { name: string; rows: string[][]; warnings: string[]; flags?: Record<string, string> }

export interface OcrPage {
  page: number;
  status: 'wait' | 'run' | 'done' | 'error';
  tables: OcrTable[];
  error: string;
  cost_vnd: number;
  seconds: number;
}

export interface OcrJob {
  id: string;
  filename: string;
  status: JobStatus;
  page_count: number;
  rotate: number;
  created_at: number;
  pages: OcrPage[];
}

export interface ExportResult {
  id: string;
  rows: number;
  expected_mass_kg: number;
  rows_without_mass: number;
  download_url: string;
}

export interface UploadOptions {
  rotate: 0 | 90 | 180 | 270;
  cols: number;
  rows: number;
  drawingType?: string;
}

export interface DrawingTypeInfo { key: string; label: string; default: boolean }

export type Role = 'admin' | 'user';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  must_change_password: boolean;
}

/** Body of /auth/login and /auth/refresh. The access token is kept in memory by auth/session.ts. */
export interface SessionBody {
  user: AuthUser;
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface AdminUser extends AuthUser {
  is_active: boolean;
  locked: boolean;
  created_at: string;
  last_login_at: string | null;
}
