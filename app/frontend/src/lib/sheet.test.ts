import { describe, expect, it } from 'vitest';
import type { Row } from '../api/types';
import { invalidFields, parseCell, sameRow, toApiRows, toSheetRows } from './sheet';

const row = (over: Partial<Row> = {}): Row => ({ section: 'ĐOẠN B', mark: 'B1', type: 'L', w: 50, t: 5, len: 704, qty: 4, ...over });

describe('parseCell', () => {
  it('parses numbers with a decimal comma', () => expect(parseCell('t', '5,5')).toBe(5.5));
  it('keeps garbage as a string so it can be flagged', () => expect(parseCell('len', '12ab')).toBe('12ab'));
  it('treats an empty thickness as null and keeps Bộ', () => {
    expect(parseCell('t', '  ')).toBeNull();
    expect(parseCell('t', 'Bộ')).toBe('Bộ');
  });
  it('does not turn text fields into numbers', () => expect(parseCell('mark', '12')).toBe('12'));
});

describe('invalidFields', () => {
  it('accepts a valid row', () => expect(invalidFields(row()).size).toBe(0));
  it('flags non-positive and non-numeric values', () => {
    const bad = invalidFields(row({ w: 0, len: 'abc', qty: 1.5, section: ' ' }));
    expect([...bad].sort()).toEqual(['len', 'qty', 'section', 'w']);
  });
  it('allows bolts to have Bộ as thickness', () => expect(invalidFields(row({ type: 'M', t: 'Bộ' })).size).toBe(0));
  it('rejects an unknown type', () => expect(invalidFields(row({ type: 'X' as never })).has('type')).toBe(true));
});

describe('row helpers', () => {
  it('round-trips rows and turns an empty mark into null', () => {
    const out = toApiRows(toSheetRows([row({ mark: '' })]));
    expect(out[0].mark).toBeNull();
    expect('id' in out[0]).toBe(false);
  });
  it('compares rows ignoring mark null vs empty', () => {
    expect(sameRow(row({ mark: null }), row({ mark: '' }))).toBe(true);
    expect(sameRow(row({ qty: 5 }), row())).toBe(false);
    expect(sameRow(row(), undefined)).toBe(false);
  });
});
