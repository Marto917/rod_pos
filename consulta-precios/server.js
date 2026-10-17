import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { promisify } from 'node:util';
import { gzip } from 'node:zlib';

import { verifyPassword, resolveAdmin } from './lib/auth.js';
import { loadCatalogFile } from './lib/catalog.js';
import { toCents } from './lib/consulta.js';
import {
  createEmpleado,
  createSession,
  deletePromo,
  deleteSession,
  ensureAdmin,
  findUser,
  getPromo,
  insertPromo,
  listEmpleados,
  listPromos,
  openDatabase,
  readSession,
  setEmpleadoActivo,
  updatePromo,
} from './lib/db.js';

const gzipAsync = promisify(gzip);
const root = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(root, 'public');
const catalogPath = path.join(root, 'catalogo', 'articulos.csv');
const SESSION_MS = 12 * 60 * 60 * 1000;
const MAX_FAILS = 5;
const LOCK_MS = 60 * 1000;

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

const SECURITY_HEADERS = {
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'x-frame-options': 'DENY',
  'x-robots-tag': 'noindex, nofollow',
  'permissions-policy': 'camera=(self), microphone=()',
  'content-security-policy': [
    "default-src 'self'",
    "img-src 'self'",
    "style-src 'self'",
    "script-src 'self'",
    "connect-src 'self'",
    "media-src 'self' blob:",
    "worker-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; '),
};

function clientIp(req) {
  const forwarded = req.headers['x-forwarded-for'];
  if (forwarded) return String(forwarded).split(',')[0].trim();
  return req.socket.remoteAddress || 'local';
}

function readCookie(req, name) {
  const header = req.headers.cookie || '';
  for (const part of header.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

function cookieValue(token, req, maxAge) {
  const parts = [
    `consulta_sesion=${encodeURIComponent(token)}`,
    'HttpOnly',
    'SameSite=Lax',
    'Path=/',
    `Max-Age=${maxAge}`,
  ];
  if (req.headers['x-forwarded-proto'] === 'https') parts.push('Secure');
  return parts.join('; ');
}

function readBody(req, limit = 8192) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(Object.assign(new Error('payload'), { status: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

async function readJson(req) {
  const raw = await readBody(req);
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    const error = new Error('json');
    error.status = 400;
    throw error;
  }
}

function publicFile(urlPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(urlPath);
  } catch {
    return null;
  }
  if (decoded.includes('\0') || decoded.includes('..')) return null;
  const relative = decoded.replace(/^\/+/, '');
  if (!relative) return null;
  const full = path.resolve(publicDir, relative);
  if (full !== publicDir && !full.startsWith(`${publicDir}${path.sep}`)) return null;
  return full;
}

function parseCantidad(value) {
  if (value === '' || value == null) return { ok: true, cantidad: null };
  const text = String(value).trim();
  if (!text) return { ok: true, cantidad: null };
  if (!/^\d+$/.test(text)) return { ok: false };
  const cantidad = Number(text);
  if (cantidad < 1 || cantidad > 9999) return { ok: false };
  return { ok: true, cantidad };
}

function parsePromo(body, catalogIds) {
  const productoId = String(body.productoId ?? '').trim();
  if (!productoId || !catalogIds.has(productoId)) {
    return { error: 'Ese producto no está en el catálogo activo.' };
  }
  if (body.medio !== 'efectivo' && body.medio !== 'transferencia') {
    return { error: 'El medio de pago tiene que ser efectivo o transferencia.' };
  }
  if (body.alcance !== 'unidad' && body.alcance !== 'lote') {
    return { error: 'El alcance tiene que ser unidad o lote.' };
  }
  const parsedCantidad = parseCantidad(body.cantidad);
  if (!parsedCantidad.ok) {
    return { error: 'La cantidad tiene que ser un entero mayor a 0, o vacía.' };
  }
  if (body.alcance === 'lote' && parsedCantidad.cantidad == null) {
    return { error: 'Si el precio es por lote, indicá la cantidad.' };
  }
  const precioCentavos = toCents(body.precio);
  if (precioCentavos == null || precioCentavos < 0) {
    return { error: 'El precio de la promoción no es válido.' };
  }
  const nota = String(body.nota ?? '').trim().slice(0, 200);
  return {
    promo: {
      productoId,
      cantidad: parsedCantidad.cantidad,
      medio: body.medio,
      precioCentavos,
      alcance: body.alcance,
      nota,
    },
  };
}

function parseUsuario(body) {
  const usuario = String(body.usuario ?? '').trim().toLowerCase();
  const password = String(body.password ?? '');
  if (!/^[a-z0-9._-]{3,32}$/.test(usuario)) {
    return { error: 'El usuario tiene que tener 3 a 32 caracteres: letras, números, punto o guión.' };
  }
  if (password.length < 4 || password.length > 72) {
    return { error: 'La contraseña tiene que tener al menos 4 caracteres.' };
  }
  return { usuario, password };
}

export function createServer({ admin, dataDir, products } = {}) {
  const resolved = admin || resolveAdmin();
  if (resolved.error || !resolved.user) {
    throw new Error(resolved.error || 'Falta el administrador.');
  }
  const catalog = products ?? loadCatalogFile(catalogPath);
  const catalogIds = new Set(catalog.map((product) => product.id));
  const db = openDatabase(dataDir || path.join(root, 'data'));
  ensureAdmin(db, resolved.user, resolved.password);
  const attempts = new Map();

  function actor(req) {
    return readSession(db, readCookie(req, 'consulta_sesion'));
  }

  function publicProduct(product) {
    return {
      id: product.id,
      codigo: product.codigo,
      codigos: product.codigos,
      nombre: product.nombre,
      precioCentavos: product.precioCentavos,
      categoria: product.categoria,
      nota: product.nota,
    };
  }

  async function send(req, res, status, body, contentType, extra = {}) {
    const payload = Buffer.isBuffer(body) ? body : Buffer.from(body);
    const headers = {
      ...SECURITY_HEADERS,
      'content-type': contentType,
      ...extra,
    };
    const accept = String(req.headers['accept-encoding'] || '');
    const compressible = /json|javascript|text|manifest/.test(contentType);
    if (req.method !== 'HEAD' && compressible && payload.length > 1024 && accept.includes('gzip')) {
      const compressed = await gzipAsync(payload);
      headers['content-encoding'] = 'gzip';
      headers.vary = 'Accept-Encoding';
      headers['content-length'] = String(compressed.length);
      res.writeHead(status, headers);
      res.end(compressed);
      return;
    }
    headers['content-length'] = String(payload.length);
    res.writeHead(status, headers);
    res.end(req.method === 'HEAD' ? undefined : payload);
  }

  function sendJson(req, res, status, data, extra = {}) {
    return send(req, res, status, JSON.stringify(data), 'application/json; charset=utf-8', {
      'cache-control': 'no-store',
      ...extra,
    });
  }

  async function handle(req, res) {
    const url = new URL(req.url || '/', 'http://localhost');
    const pathname = url.pathname;

    if (pathname === '/health' && (req.method === 'GET' || req.method === 'HEAD')) {
      await sendJson(req, res, 200, { ok: true });
      return;
    }

    if (pathname === '/api/session' && req.method === 'GET') {
      const user = actor(req);
      if (!user) {
        await sendJson(req, res, 401, { ok: false });
        return;
      }
      await sendJson(req, res, 200, { ok: true, usuario: user.usuario, rol: user.rol });
      return;
    }

    if (pathname === '/api/login' && req.method === 'POST') {
      const ip = clientIp(req);
      const state = attempts.get(ip) || { fails: 0, lockedUntil: 0 };
      if (state.lockedUntil > Date.now()) {
        await sendJson(req, res, 429, { error: 'Demasiados intentos. Esperá un minuto.' });
        return;
      }
      let body;
      try {
        body = await readJson(req);
      } catch (error) {
        await sendJson(req, res, error.status || 400, { error: 'No se pudo leer la solicitud.' });
        return;
      }
      const usuario = String(body.usuario ?? '').trim().toLowerCase();
      const password = String(body.password ?? '');
      const record = usuario ? findUser(db, usuario) : null;
      const passwordOk = record ? verifyPassword(password, record.password_hash) : false;
      if (!record || !passwordOk) {
        state.fails += 1;
        if (state.fails >= MAX_FAILS) {
          state.fails = 0;
          state.lockedUntil = Date.now() + LOCK_MS;
        }
        attempts.set(ip, state);
        await sendJson(req, res, 401, { error: 'Usuario o contraseña incorrectos.' });
        return;
      }
      if (!record.activo) {
        await sendJson(req, res, 403, { error: 'Usuario desactivado.' });
        return;
      }
      attempts.delete(ip);
      const token = createSession(db, record.id, SESSION_MS);
      await sendJson(req, res, 200, { ok: true, usuario: record.usuario, rol: record.rol }, {
        'set-cookie': cookieValue(token, req, Math.floor(SESSION_MS / 1000)),
      });
      return;
    }

    if (pathname === '/api/logout' && req.method === 'POST') {
      deleteSession(db, readCookie(req, 'consulta_sesion'));
      await sendJson(req, res, 200, { ok: true }, { 'set-cookie': cookieValue('', req, 0) });
      return;
    }

    const user = actor(req);

    if (pathname === '/api/catalog' && req.method === 'GET') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      await sendJson(req, res, 200, { productos: catalog.map(publicProduct) });
      return;
    }

    if (pathname === '/api/promociones' && req.method === 'GET') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      await sendJson(req, res, 200, { promociones: listPromos(db) });
      return;
    }

    if (pathname === '/api/promociones' && req.method === 'POST') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      if (user.rol !== 'admin') {
        await sendJson(req, res, 403, { error: 'No tenés permiso para hacer eso.' });
        return;
      }
      let body;
      try {
        body = await readJson(req);
      } catch {
        await sendJson(req, res, 400, { error: 'No se pudo leer la solicitud.' });
        return;
      }
      const parsed = parsePromo(body, catalogIds);
      if (parsed.error) {
        await sendJson(req, res, 400, { error: parsed.error });
        return;
      }
      const saved = insertPromo(db, parsed.promo);
      if (saved.error) {
        await sendJson(req, res, 409, { error: 'Ya hay una regla para esa cantidad y ese medio de pago.' });
        return;
      }
      await sendJson(req, res, 201, { promocion: saved.promo });
      return;
    }

    const promoMatch = pathname.match(/^\/api\/promociones\/(\d+)$/);
    if (promoMatch && (req.method === 'PUT' || req.method === 'DELETE')) {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      if (user.rol !== 'admin') {
        await sendJson(req, res, 403, { error: 'No tenés permiso para hacer eso.' });
        return;
      }
      const id = Number(promoMatch[1]);
      if (req.method === 'DELETE') {
        const removed = deletePromo(db, id);
        await sendJson(req, res, removed ? 200 : 404, removed ? { ok: true } : { error: 'No existe esa regla.' });
        return;
      }
      let body;
      try {
        body = await readJson(req);
      } catch {
        await sendJson(req, res, 400, { error: 'No se pudo leer la solicitud.' });
        return;
      }
      const current = getPromo(db, id);
      if (!current) {
        await sendJson(req, res, 404, { error: 'No existe esa regla.' });
        return;
      }
      const parsed = parsePromo({ ...body, productoId: current.productoId }, catalogIds);
      if (parsed.error) {
        await sendJson(req, res, 400, { error: parsed.error });
        return;
      }
      const saved = updatePromo(db, id, parsed.promo);
      if (saved.error === 'duplicada') {
        await sendJson(req, res, 409, { error: 'Ya hay una regla para esa cantidad y ese medio de pago.' });
        return;
      }
      await sendJson(req, res, 200, { promocion: saved.promo });
      return;
    }

    if (pathname === '/api/usuarios' && req.method === 'GET') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      if (user.rol !== 'admin') {
        await sendJson(req, res, 403, { error: 'No tenés permiso para hacer eso.' });
        return;
      }
      await sendJson(req, res, 200, { usuarios: listEmpleados(db) });
      return;
    }

    if (pathname === '/api/usuarios' && req.method === 'POST') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      if (user.rol !== 'admin') {
        await sendJson(req, res, 403, { error: 'No tenés permiso para hacer eso.' });
        return;
      }
      let body;
      try {
        body = await readJson(req);
      } catch {
        await sendJson(req, res, 400, { error: 'No se pudo leer la solicitud.' });
        return;
      }
      const parsed = parseUsuario(body);
      if (parsed.error) {
        await sendJson(req, res, 400, { error: parsed.error });
        return;
      }
      const created = createEmpleado(db, parsed.usuario, parsed.password);
      if (created.error) {
        await sendJson(req, res, 409, { error: 'Ese usuario ya existe.' });
        return;
      }
      await sendJson(req, res, 201, { id: created.id, usuario: parsed.usuario, rol: 'empleado', activo: true });
      return;
    }

    const userMatch = pathname.match(/^\/api\/usuarios\/(\d+)$/);
    if (userMatch && req.method === 'PATCH') {
      if (!user) {
        await sendJson(req, res, 401, { error: 'Tenés que iniciar sesión.' });
        return;
      }
      if (user.rol !== 'admin') {
        await sendJson(req, res, 403, { error: 'No tenés permiso para hacer eso.' });
        return;
      }
      let body;
      try {
        body = await readJson(req);
      } catch {
        await sendJson(req, res, 400, { error: 'No se pudo leer la solicitud.' });
        return;
      }
      if (typeof body.activo !== 'boolean') {
        await sendJson(req, res, 400, { error: 'Indicá si el empleado queda activo.' });
        return;
      }
      const result = setEmpleadoActivo(db, Number(userMatch[1]), body.activo);
      if (result !== 'ok') {
        await sendJson(req, res, 404, { error: 'No existe ese empleado.' });
        return;
      }
      await sendJson(req, res, 200, { ok: true });
      return;
    }

    if (pathname.startsWith('/api/')) {
      await sendJson(req, res, 404, { error: 'No encontrado.' });
      return;
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      await send(req, res, 405, 'Método no permitido', 'text/plain; charset=utf-8');
      return;
    }

    const shared = pathname === '/shared/consulta.js' ? path.join(root, 'lib', 'consulta.js') : null;
    const filePath = shared || (pathname === '/' ? path.join(publicDir, 'index.html') : publicFile(pathname));
    if (!filePath) {
      await send(req, res, 404, 'No encontrado', 'text/plain; charset=utf-8');
      return;
    }
    let stat;
    try {
      stat = fs.statSync(filePath);
    } catch {
      await send(req, res, 404, 'No encontrado', 'text/plain; charset=utf-8');
      return;
    }
    if (!stat.isFile()) {
      await send(req, res, 404, 'No encontrado', 'text/plain; charset=utf-8');
      return;
    }
    const type = TYPES[path.extname(filePath)] || 'application/octet-stream';
    const cache = pathname === '/' || pathname.endsWith('.html') ? 'no-cache' : 'public, max-age=300';
    await send(req, res, 200, fs.readFileSync(filePath), type, { 'cache-control': cache });
  }

  const server = http.createServer((req, res) => {
    handle(req, res).catch((error) => {
      if (res.headersSent) return;
      res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('Error');
      console.error(error);
    });
  });
  server.on('close', () => {
    try {
      db.close();
    } catch {
      // ya cerrada
    }
  });
  return server;
}

function isMain() {
  const entry = process.argv[1];
  if (!entry) return false;
  return import.meta.url === pathToFileURL(entry).href;
}

function resolveDataDir() {
  if (!process.env.DATA_DIR) return path.join(root, 'data');
  return path.resolve(root, process.env.DATA_DIR);
}

if (isMain()) {
  const admin = resolveAdmin();
  if (admin.error) {
    console.error(admin.error);
    process.exit(1);
  }
  const server = createServer({ admin, dataDir: resolveDataDir() });
  const port = Number(process.env.PORT) || 3000;
  server.listen(port, '0.0.0.0', () => {
    const mode = admin.dev ? 'administrador de desarrollo local' : 'administrador tomado de ADMIN_USER';
    console.log(`Consulta de precios en http://0.0.0.0:${port} (${mode})`);
  });
}
