export const MIN_PASSWORD = 10;

/**
 * Early feedback only. The server enforces the real policy (length, common passwords, email name) and its message
 * is shown if it rejects something this check let through.
 */
export function passwordProblem(password: string, email = ''): string | null {
  if (password.length < MIN_PASSWORD) return `Dùng ít nhất ${MIN_PASSWORD} ký tự.`;
  if (password.length > 128) return 'Dùng tối đa 128 ký tự.';
  if (password.trim() !== password) return 'Không để dấu cách ở đầu hoặc cuối mật khẩu.';
  if (new Set(password).size < 4) return 'Mật khẩu đang lặp ký tự quá nhiều.';
  const local = email.split('@')[0]?.toLowerCase() ?? '';
  if (local.length >= 4 && password.toLowerCase().includes(local)) return 'Không đặt tên email vào mật khẩu.';
  return null;
}

// No look-alike characters (0/O, 1/l/I): a password read out loud or typed from a note is easy to get wrong.
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';

/** A random password from the browser's CSPRNG, for the temporary passwords an administrator hands out. */
export function generatePassword(length = 16): string {
  const limit = 256 - (256 % ALPHABET.length); // reject the biased tail so every character is equally likely
  let out = '';
  while (out.length < length) {
    for (const byte of crypto.getRandomValues(new Uint8Array(length * 2))) {
      if (byte < limit && out.length < length) out += ALPHABET[byte % ALPHABET.length];
    }
  }
  return out;
}
