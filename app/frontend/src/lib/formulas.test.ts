import { describe, expect, it } from 'vitest';
import type { Row } from '../api/types';
import catalog from './fixtures/catalog.json';
import rows from './fixtures/rows.json';
import { compute, fmt, sumTotals, type Catalog } from './formulas';

const cat = catalog as Catalog;
const row = (over: Partial<Row>): Row => ({ section: 'S', mark: 'X', type: 'L', w: 50, t: 5, len: 1000, qty: 1, ...over });

describe('spec string (column H)', () => {
  it('angle: Dxexexf', () => expect(compute(row({ type: 'L', w: 100, t: 8, len: 3900 }), cat).spec).toBe('L100x100x8x3900'));
  it('plate: D thickness x width x length', () => expect(compute(row({ type: 'd', w: 100, t: 8, len: 172 }), cat).spec).toBe('d8x100x172'));
  it('round bar without thickness', () => expect(compute(row({ type: 'Ф', w: 20, t: null, len: 2200 }), cat).spec).toBe('Ф20x2200'));
  it('bolt keeps the nut-count suffix of the template', () => expect(compute(row({ type: 'M', w: 16, t: 'Bộ', len: 50 }), cat).spec).toBe('M16x50-2ecuxBộ'));
});

describe('quantities (columns J-N)', () => {
  it('angle L50x50x5, 704 mm, 4 pcs uses the Steel Lib unit weight', () => {
    const c = compute(row({ w: 50, t: 5, len: 704, qty: 4 }), cat);
    expect(c.unit).toBeCloseTo(0.704, 6);
    expect(c.unitWeight).toBe(3.77);
    expect(c.totalLen).toBeCloseTo(2.816, 6);
    expect(c.mass).toBeCloseTo(2.816 * 3.77, 6);
    expect(c.paint).toBeCloseTo((4 * 50 * 704 * 4) / 1e6, 9);
  });
  it('plate mass is area × 7850 × thickness', () => {
    const c = compute(row({ type: 'd', w: 100, t: 8, len: 172, qty: 8 }), cat);
    expect(c.unit).toBeCloseTo(0.0172, 9);
    expect(c.mass).toBeCloseTo(0.0172 * 8 * ((7850 * 8) / 1000), 6);
  });
  it('bolts are weighed per piece from the bolt table (no length/area)', () => {
    const c = compute(row({ type: 'M', w: 16, t: 'Bộ', len: 50, qty: 10 }), cat);
    expect(c.unit).toBeNull();
    expect(c.mass).toBeCloseTo(10 * cat.bolts.M16['50'], 9);
  });
  it('an angle that is not in the Steel Lib reports an error instead of a made-up weight', () => {
    const c = compute(row({ w: 77, t: 3 }), cat);
    expect(c.error).toMatch(/not in the Steel Lib/);
    expect(c.mass).toBeNull();
  });
  it('bad numbers give blanks, not NaN', () => {
    const c = compute(row({ len: 'abc' }), cat);
    expect(c.mass).toBeNull();
    expect(fmt(c.mass, 2)).toBe('');
  });
});

describe('whole schedule', () => {
  it('matches the 1,117.4 kg computed independently in Python for the DNHV04 drawing', () => {
    const totals = sumTotals((rows as Row[]).map((r) => compute(r, cat)));
    expect(totals.errors).toBe(0);
    expect(totals.mass).toBeGreaterThan(1116.4);
    expect(totals.mass).toBeLessThan(1118.4);
  });
  it('formats numbers with fixed decimals', () => expect(fmt(1234.5678, 2)).toBe('1,234.57'));
});
