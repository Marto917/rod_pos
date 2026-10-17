import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

export const DEV_ADMIN_USER = 'admin';
export const DEV_ADMIN_PASSWORD = 'admin1357';

export function hashPassword(password) {
  const salt = randomBytes(16);
  const hash = scryptSync(String(password), salt, 32);
  return `${salt.toString('hex')}:${hash.toString('hex')}`;
}

export function verifyPassword(password, stored) {
  const [saltHex, hashHex] = String(stored || '').split(':');
  if (!saltHex || !hashHex) return false;
  const salt = Buffer.from(saltHex, 'hex');
  const expected = Buffer.from(hashHex, 'hex');
  if (salt.length === 0 || expected.length === 0) return false;
  const actual = scryptSync(String(password), salt, expected.length);
  if (actual.length !== expected.length) return false;
  return timingSafeEqual(actual, expected);
}

export function resolveAdmin(env = process.env) {
  const user = String(env.ADMIN_USER ?? '').trim().toLowerCase();
  const password = env.ADMIN_PASSWORD ?? '';
  const hosted = env.NODE_ENV === 'production'
    || Boolean(env.RAILWAY_ENVIRONMENT)
    || Boolean(env.RAILWAY_PROJECT_ID);
  if (user || password) {
    if (!user || !password) {
      return { error: 'Definí ADMIN_USER y ADMIN_PASSWORD juntos.' };
    }
    return { user, password, dev: false };
  }
  if (hosted) {
    return { error: 'En producción hacen falta ADMIN_USER y ADMIN_PASSWORD.' };
  }
  return { user: DEV_ADMIN_USER, password: DEV_ADMIN_PASSWORD, dev: true };
}
