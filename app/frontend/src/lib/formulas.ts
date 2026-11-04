import type { Row } from '../api/types';

/** Lookup data the template's formulas rely on (served by GET /reference/catalog, read from the template). */
export interface Catalog {
  angles: Record<string, number>;
  bolts: Record<string, Record<string, number>>;
  paint_factor: number;
}
export const EMPTY_CATALOG: Catalog = { angles: {}, bolts: {}, paint_factor: 1 };

export interface Computed {
  spec: string; // H: "Quy cách - kích thước"
  unit: number | null; // J: length (m) or area (m²) of one piece
  unitWeight: number | null; // K: kg/m, kg/m² or kg per bolt
  totalLen: number | null; // L: J × quantity
  mass: number | null; // M: kg
  paint: number | null; // N: paint area (m²)
  error: string | null; // set when a lookup fails (Excel would show #N/A)
}

export interface Totals { mass: number; paint: number; errors: number }

const blank = (v: unknown) => v === null || v === undefined || v === '';
const toNum = (v: unknown): number => (blank(v) ? NaN : typeof v === 'number' ? v : Number(String(v).replace(',', '.')));
const PI = Math.PI;

/** Mirrors the formulas in columns H, J, K, L, M, N of the template, cell for cell. */
export function compute(row: Row, cat: Catalog): Computed {
  const D = row.type;
  const E = toNum(row.w);
  const F = toNum(row.t);
  const G = toNum(row.len);
  const I = toNum(row.qty);
  const noF = blank(row.t);

  // H
  let spec: string;
  if (noF && D === 'Ф') spec = `${D}${row.w}x${row.len}`;
  else if (!noF && D === 'L') spec = `${D}${row.w}x${row.w}x${row.t}x${row.len}`;
  else if (!noF && D === 'M') spec = `${D}${row.w}x${row.len}-2ecux${row.t}`;
  else if (!noF && D === 'd') spec = `${D}${row.t}x${row.w}x${row.len}`;
  else spec = `${D}${row.w}x${row.t ?? ''}x${row.len}`;

  const out: Computed = { spec, unit: null, unitWeight: null, totalLen: null, mass: null, paint: null, error: null };
  if (![E, G, I].every(Number.isFinite)) return out;

  // J
  if (D === 'Ф' || D === 'L') out.unit = G / 1000;
  else if (D === 'd') out.unit = (G * E) / 1e6;

  // K
  if (D === 'Ф') {
    out.unitWeight = noF ? (7850 * PI * E ** 2) / 4e6 : (7850 * PI * (E ** 2 - (E - 2 * F) ** 2)) / 4e6;
  } else if (D === 'd') {
    if (Number.isFinite(F)) out.unitWeight = (7850 * F) / 1000;
    else out.error = 'A plate needs a thickness';
  } else if (D === 'L') {
    const key = `L${row.w}x${row.w}x${row.t}`;
    const kg = cat.angles[key];
    if (kg === undefined) out.error = `${key} is not in the Steel Lib table`;
    else out.unitWeight = kg;
  } else {
    const kg = cat.bolts[`${D}${row.w}`]?.[String(G)];
    if (kg === undefined) out.error = `No ${D}${row.w} bolt of length ${row.len} in the bolt table`;
    else out.unitWeight = kg;
  }
  if (out.error) return { ...out, unit: out.unit };

  // L, M
  if (out.unit !== null) out.totalLen = out.unit * I;
  out.mass = out.unit !== null ? (out.totalLen as number) * (out.unitWeight as number) : I * (out.unitWeight as number);

  // N
  const P = cat.paint_factor;
  if (D === 'Ф') out.paint = (PI * E * G * I * P) / 1e6;
  else if (D === 'd' && Number.isFinite(F)) out.paint = (2 * ((E + G) * F + E * G) * I * P) / 1e6;
  else if (D === 'L') out.paint = (4 * E * G * I * P) / 1e6;
  return out;
}

export function sumTotals(computed: Iterable<Computed>): Totals {
  const t: Totals = { mass: 0, paint: 0, errors: 0 };
  for (const c of computed) {
    if (c.error) t.errors += 1;
    t.mass += c.mass ?? 0;
    t.paint += c.paint ?? 0;
  }
  return t;
}

export const fmt = (n: number | null | undefined, digits: number): string =>
  n === null || n === undefined || !Number.isFinite(n)
    ? ''
    : n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
