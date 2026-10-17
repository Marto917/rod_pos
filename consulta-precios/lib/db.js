import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';

import { hashPassword, verifyPassword } from './auth.js';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN ('admin', 'empleado')),
  activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sesiones (
  token TEXT PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  vence_en INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS promociones (
  id INTEGER PRIMARY KEY,
  producto_id TEXT NOT NULL,
  cantidad INTEGER,
  medio TEXT NOT NULL CHECK (medio IN ('efectivo', 'transferencia')),
  precio_centavos INTEGER NOT NULL CHECK (precio_centavos >= 0),
  alcance TEXT NOT NULL CHECK (alcance IN ('unidad', 'lote')),
  nota TEXT NOT NULL DEFAULT '',
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (cantidad IS NULL OR cantidad >= 1),
  CHECK (alcance = 'unidad' OR cantidad IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS promociones_unicas
  ON promociones (producto_id, ifnull(cantidad, -1), medio);
`;

export function openDatabase(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  const db = new DatabaseSync(path.join(dataDir, 'consulta.sqlite'));
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  db.exec('PRAGMA busy_timeout = 3000');
  db.exec(SCHEMA);
  return db;
}

export function ensureAdmin(db, usuario, password) {
  const existing = db.prepare(
    'SELECT id, password_hash, rol, activo FROM usuarios WHERE usuario = ?',
  ).get(usuario);
  if (!existing) {
    db.prepare(
      `INSERT INTO usuarios (usuario, password_hash, rol, activo) VALUES (?, ?, 'admin', 1)`,
    ).run(usuario, hashPassword(password));
    return;
  }
  const samePassword = verifyPassword(password, existing.password_hash);
  if (samePassword && existing.rol === 'admin' && existing.activo) return;
  db.prepare(
    `UPDATE usuarios SET password_hash = ?, rol = 'admin', activo = 1 WHERE id = ?`,
  ).run(hashPassword(password), existing.id);
  db.prepare('DELETE FROM sesiones WHERE usuario_id = ?').run(existing.id);
}

export function findUser(db, usuario) {
  return db.prepare(
    'SELECT id, usuario, password_hash, rol, activo FROM usuarios WHERE usuario = ?',
  ).get(usuario) || null;
}

export function createSession(db, usuarioId, ttlMs) {
  const token = randomBytes(32).toString('hex');
  db.prepare('INSERT INTO sesiones (token, usuario_id, vence_en) VALUES (?, ?, ?)').run(
    token,
    usuarioId,
    Date.now() + ttlMs,
  );
  return token;
}

export function readSession(db, token) {
  if (!token) return null;
  const row = db.prepare(`
    SELECT u.id AS usuario_id, u.usuario, u.rol, u.activo, s.vence_en
    FROM sesiones s
    JOIN usuarios u ON u.id = s.usuario_id
    WHERE s.token = ?
  `).get(token);
  if (!row) return null;
  if (Number(row.vence_en) < Date.now() || !row.activo) {
    db.prepare('DELETE FROM sesiones WHERE token = ?').run(token);
    return null;
  }
  return { id: Number(row.usuario_id), usuario: row.usuario, rol: row.rol };
}

export function deleteSession(db, token) {
  if (token) db.prepare('DELETE FROM sesiones WHERE token = ?').run(token);
}

function mapPromo(row) {
  return {
    id: Number(row.id),
    productoId: row.producto_id,
    cantidad: row.cantidad == null ? null : Number(row.cantidad),
    medio: row.medio,
    precioCentavos: Number(row.precio_centavos),
    alcance: row.alcance,
    nota: row.nota || '',
  };
}

export function listPromos(db) {
  return db.prepare(`
    SELECT id, producto_id, cantidad, medio, precio_centavos, alcance, nota
    FROM promociones
    ORDER BY producto_id, medio, ifnull(cantidad, 9999), id
  `).all().map(mapPromo);
}

export function getPromo(db, id) {
  const row = db.prepare(`
    SELECT id, producto_id, cantidad, medio, precio_centavos, alcance, nota
    FROM promociones WHERE id = ?
  `).get(id);
  return row ? mapPromo(row) : null;
}

export function insertPromo(db, promo) {
  try {
    const info = db.prepare(`
      INSERT INTO promociones (producto_id, cantidad, medio, precio_centavos, alcance, nota)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      promo.productoId,
      promo.cantidad,
      promo.medio,
      promo.precioCentavos,
      promo.alcance,
      promo.nota,
    );
    return { promo: getPromo(db, Number(info.lastInsertRowid)) };
  } catch (error) {
    if (String(error.message).includes('UNIQUE')) return { error: 'duplicada' };
    throw error;
  }
}

export function updatePromo(db, id, promo) {
  const current = getPromo(db, id);
  if (!current) return { error: 'missing' };
  try {
    db.prepare(`
      UPDATE promociones
      SET producto_id = ?, cantidad = ?, medio = ?, precio_centavos = ?, alcance = ?, nota = ?,
          actualizado_en = datetime('now')
      WHERE id = ?
    `).run(
      promo.productoId,
      promo.cantidad,
      promo.medio,
      promo.precioCentavos,
      promo.alcance,
      promo.nota,
      id,
    );
    return { promo: getPromo(db, id) };
  } catch (error) {
    if (String(error.message).includes('UNIQUE')) return { error: 'duplicada' };
    throw error;
  }
}

export function deletePromo(db, id) {
  const info = db.prepare('DELETE FROM promociones WHERE id = ?').run(id);
  return info.changes > 0;
}

export function listEmpleados(db) {
  return db.prepare(`
    SELECT id, usuario, rol, activo FROM usuarios WHERE rol = 'empleado' ORDER BY usuario
  `).all().map((row) => ({
    id: Number(row.id),
    usuario: row.usuario,
    rol: row.rol,
    activo: Boolean(row.activo),
  }));
}

export function createEmpleado(db, usuario, password) {
  try {
    const info = db.prepare(`
      INSERT INTO usuarios (usuario, password_hash, rol, activo) VALUES (?, ?, 'empleado', 1)
    `).run(usuario, hashPassword(password));
    return { id: Number(info.lastInsertRowid) };
  } catch (error) {
    if (String(error.message).includes('UNIQUE')) return { error: 'existe' };
    throw error;
  }
}

export function setEmpleadoActivo(db, id, activo) {
  const row = db.prepare('SELECT id, rol FROM usuarios WHERE id = ?').get(id);
  if (!row || row.rol !== 'empleado') return 'missing';
  db.prepare('UPDATE usuarios SET activo = ? WHERE id = ?').run(activo ? 1 : 0, id);
  if (!activo) db.prepare('DELETE FROM sesiones WHERE usuario_id = ?').run(id);
  return 'ok';
}
