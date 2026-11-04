import type { Issue, MemberType, Row } from '../api/types';

export const MEMBER_TYPES: { value: MemberType; label: string }[] = [
  { value: 'L', label: 'L – angle' },
  { value: 'd', label: 'd – plate' },
  { value: 'Ф', label: 'Ф – round bar' },
  { value: 'M', label: 'M – bolt' },
];

export type Field = 'section' | 'mark' | 'type' | 'w' | 't' | 'len' | 'qty';

/** A grid row: the API row plus a stable id so React keys survive inserts and deletes. */
export interface SheetRow extends Row {
  id: string;
}

let counter = 0;
export const newId = () => `r${Date.now().toString(36)}${(counter++).toString(36)}`;

export const toSheetRows = (rows: Row[]): SheetRow[] => rows.map((r) => ({ ...r, id: newId() }));
export const toApiRows = (rows: SheetRow[]): Row[] =>
  rows.map(({ id: _id, ...r }) => ({ ...r, mark: r.mark === '' ? null : r.mark }));

const isPositive = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0;

/** Parses what the user typed into a cell. Unparseable numeric input stays a string so it can be flagged. */
export function parseCell(field: Field, raw: string): string | number | null {
  const v = raw.trim();
  if (field === 't') {
    if (v === '') return null;
    if (v === 'Bộ') return v;
  }
  if (field === 'w' || field === 't' || field === 'len' || field === 'qty') {
    const n = Number(v.replace(',', '.'));
    return v !== '' && Number.isFinite(n) ? n : v;
  }
  return raw;
}

/** Fields of a row that fail validation. Mirrors the server's rules so errors show before saving. */
export function invalidFields(r: Row): Set<Field> {
  const bad = new Set<Field>();
  if (!String(r.section ?? '').trim()) bad.add('section');
  if (!MEMBER_TYPES.some((t) => t.value === r.type)) bad.add('type');
  if (!isPositive(r.w)) bad.add('w');
  if (!isPositive(r.len)) bad.add('len');
  if (!(Number.isInteger(r.qty) && (r.qty as number) > 0)) bad.add('qty');
  if (!(r.t == null || r.t === 'Bộ' || isPositive(r.t))) bad.add('t');
  return bad;
}

export const sameRow = (a: Row, b: Row | undefined): boolean =>
  !!b &&
  a.section === b.section &&
  (a.mark ?? '') === (b.mark ?? '') &&
  a.type === b.type &&
  a.w === b.w &&
  (a.t ?? null) === (b.t ?? null) &&
  a.len === b.len &&
  a.qty === b.qty;

/** Marks that carry a server-side warning or error. Informational notes are not shown as problems. */
export function issuesByMark(issues: Issue[]): Map<string, Issue[]> {
  const map = new Map<string, Issue[]>();
  for (const i of issues) {
    if (i.mark && i.level !== 'info') map.set(i.mark, [...(map.get(i.mark) ?? []), i]);
  }
  return map;
}

export const isFlagged = (r: Row, byMark: Map<string, Issue[]>): boolean =>
  invalidFields(r).size > 0 || (!!r.mark && byMark.has(r.mark));
