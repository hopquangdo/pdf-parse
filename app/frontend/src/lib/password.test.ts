import { describe, expect, it } from 'vitest';
import { generatePassword, passwordProblem } from './password';

describe('passwordProblem', () => {
  it('accepts a long passphrase and a random mix', () => {
    expect(passwordProblem('correct horse battery')).toBeNull();
    expect(passwordProblem('x9#Lw!qZ2m')).toBeNull();
  });
  it('rejects short, padded, repetitive and email-derived passwords', () => {
    expect(passwordProblem('short')).toMatch(/ít nhất 10/);
    expect(passwordProblem(' padded password ')).toMatch(/dấu cách/);
    expect(passwordProblem('aaaaaaaaaaaa')).toMatch(/lặp/);
    expect(passwordProblem('alice.smith-2026!', 'alice.smith@example.com')).toMatch(/tên email/);
  });
  it('does not flag a short email name that merely appears by chance', () => {
    expect(passwordProblem('a-long-banana-pudding', 'al@example.com')).toBeNull();
  });
});

describe('generatePassword', () => {
  it('has the requested length and avoids look-alike characters', () => {
    const p = generatePassword(24);
    expect(p).toHaveLength(24);
    expect(p).not.toMatch(/[01OIl]/);
  });
  it('never repeats across a large sample and passes the policy', () => {
    const seen = new Set(Array.from({ length: 500 }, () => generatePassword()));
    expect(seen.size).toBe(500);
    expect([...seen].every((p) => passwordProblem(p) === null)).toBe(true);
  });
});
