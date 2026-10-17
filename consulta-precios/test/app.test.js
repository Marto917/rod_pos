import assert from 'node:assert/strict';
import { once } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { DEV_ADMIN_PASSWORD, DEV_ADMIN_USER, resolveAdmin } from '../lib/auth.js';
import { loadCatalog, loadCatalogFile } from '../lib/catalog.js';
import { formatARS, reglaAplicable, searchProducts, toCents } from '../lib/consulta.js';
import { preferredEngine } from '../public/scanner.js';
import { createServer } from '../server.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const catalog = loadCatalogFile(path.join(root, 'catalogo', 'articulos.csv'));
const raw = fs.readFileSync(path.join(root, 'catalogo', 'articulos.csv'), 'utf8');

function cookieFrom(response) {
  const rawCookie = response.headers.getSetCookie?.()[0] || response.headers.get('set-cookie') || '';
  return rawCookie.split(';')[0];
}

async function listen(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return `http://127.0.0.1:${server.address().port}`;
}

async function login(base, usuario, password) {
  const response = await fetch(`${base}/api/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ usuario, password }),
  });
  return { response, cookie: cookieFrom(response), body: await response.json() };
}

test('el catálogo activo no publica mayorista ni inactivos', () => {
  assert.equal(raw.split(/\r?\n/).filter((line) => line.trim()).length, 619);
  const sinCodigo = raw.split(/\r?\n/).slice(1).filter((line) => line.startsWith(';')).length;
  assert.equal(sinCodigo, 300);
  assert.equal(new Set(catalog.map((product) => product.id)).size, catalog.length);
  assert.ok(catalog.length < 495);
  const aceitera = catalog.find((product) => product.codigo === '1100000875161');
  assert.equal(aceitera.nombre, 'Aceitera Spray Acero Inoxidable');
  assert.equal(aceitera.precioCentavos, 300000);
  assert.equal(aceitera.categoria, 'bazar');
  assert.equal(formatARS(aceitera.precioCentavos), '$ 3.000');
  assert.equal(catalog.find((product) => product.codigo === '0714604235606'), undefined);
  assert.equal(searchProducts(catalog, 'almohada rouge').items.length, 0);
  const guantes = catalog.find((product) => product.nombre === 'Guantes de silicona');
  assert.equal(guantes.precioCentavos, 600000);
  assert.equal(JSON.stringify(guantes).includes('mayorista'), false);
  assert.equal(JSON.stringify(guantes).includes('proveedor'), false);
  const bolso = catalog.find((product) => product.nombre === 'Bolso Para Herramientas 12"');
  assert.ok(bolso);
  assert.equal(searchProducts(catalog, 'borosilicato').items[0].codigo, '');
  assert.equal(searchProducts(catalog, '1100000875161').items[0].id, aceitera.id);
  assert.equal(searchProducts(catalog, '0000000000000').items.length, 0);
  assert.equal(searchProducts(catalog, '1100000948735').items[0].nombre, 'Frasco de vidrio grande');
  assert.equal(formatARS(800002), '$ 8.000,02');
  assert.equal(toCents('2.500'), 250000);
  assert.equal(toCents('3000.00'), 300000);
  assert.equal(toCents('2500,50'), 250050);
});

test('la regla exacta gana, si no la de cantidad vacía, si no el precio de lista', () => {
  const reglas = [
    { id: 1, cantidad: 6, medio: 'efectivo', precioCentavos: 250000, alcance: 'lote' },
    { id: 2, cantidad: 1, medio: 'efectivo', precioCentavos: 320000, alcance: 'unidad' },
    { id: 3, cantidad: 12, medio: 'efectivo', precioCentavos: 200000, alcance: 'unidad' },
    { id: 4, cantidad: null, medio: 'transferencia', precioCentavos: 280000, alcance: 'unidad' },
  ];
  assert.equal(reglaAplicable(reglas, 6, 'efectivo').id, 1);
  assert.equal(reglaAplicable(reglas, 1, 'efectivo').id, 2);
  assert.equal(reglaAplicable(reglas, 12, 'efectivo').id, 3);
  assert.equal(reglaAplicable(reglas, 4, 'efectivo'), null);
  assert.equal(reglaAplicable(reglas, 6, 'transferencia').id, 4);
  assert.equal(reglaAplicable(reglas, 2, 'transferencia').id, 4);
  assert.equal(preferredEngine({ barcodeDetector: true, zxing: true }), 'barcode-detector');
  assert.equal(preferredEngine({ barcodeDetector: false, zxing: true }), 'zxing');
  assert.equal(preferredEngine({ barcodeDetector: false, zxing: false }), null);
});

test('resolveAdmin exige credenciales en producción y deja un admin local', () => {
  assert.deepEqual(resolveAdmin({}), {
    user: DEV_ADMIN_USER,
    password: DEV_ADMIN_PASSWORD,
    dev: true,
  });
  assert.equal(DEV_ADMIN_USER, 'admin');
  assert.equal(DEV_ADMIN_PASSWORD, 'admin1357');
  assert.ok(resolveAdmin({ NODE_ENV: 'production' }).error);
  assert.ok(resolveAdmin({ RAILWAY_ENVIRONMENT: 'production' }).error);
  assert.equal(resolveAdmin({ ADMIN_USER: 'Maria', ADMIN_PASSWORD: 'secreta' }).user, 'maria');
  assert.ok(resolveAdmin({ ADMIN_USER: 'admin' }).error);
});

test('login, permisos y promociones', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'consulta-'));
  const server = createServer({
    admin: { user: 'admin', password: 'admin1357', dev: true },
    dataDir,
    products: catalog,
  });
  const base = await listen(server);
  try {
    assert.equal((await fetch(`${base}/health`)).status, 200);
    assert.equal((await fetch(`${base}/api/catalog`)).status, 401);
    assert.equal((await fetch(`${base}/catalogo/articulos.csv`)).status, 404);
    assert.equal((await fetch(`${base}/api/promociones`)).status, 401);

    const wrong = await login(base, 'admin', 'no-es');
    assert.equal(wrong.response.status, 401);

    const admin = await login(base, 'admin', 'admin1357');
    assert.equal(admin.response.status, 200);
    assert.equal(admin.body.rol, 'admin');
    assert.match(admin.response.headers.get('set-cookie'), /HttpOnly/i);
    assert.match(admin.response.headers.get('set-cookie'), /consulta_sesion=/);

    const catalogResponse = await fetch(`${base}/api/catalog`, { headers: { cookie: admin.cookie } });
    const catalogBody = await catalogResponse.json();
    assert.equal(catalogBody.productos.some((product) => product.codigo === '1100000875161'), true);
    assert.equal(JSON.stringify(catalogBody).includes('precio_mayorista'), false);
    assert.equal(JSON.stringify(catalogBody).includes('mayorista'), false);

    const created = await fetch(`${base}/api/usuarios`, {
      method: 'POST',
      headers: { cookie: admin.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ usuario: 'sofia', password: 'salon123' }),
    });
    assert.equal(created.status, 201);
    const sofiaId = (await created.json()).id;

    const empleado = await login(base, 'sofia', 'salon123');
    assert.equal(empleado.response.status, 200);
    assert.equal(empleado.body.rol, 'empleado');
    const forbiddenPromo = await fetch(`${base}/api/promociones`, {
      method: 'POST',
      headers: { cookie: empleado.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ productoId: 'x', cantidad: 1, medio: 'efectivo', precio: 1, alcance: 'unidad' }),
    });
    assert.equal(forbiddenPromo.status, 403);
    const forbiddenUsers = await fetch(`${base}/api/usuarios`, { headers: { cookie: empleado.cookie } });
    assert.equal(forbiddenUsers.status, 403);

    const producto = catalog.find((product) => product.codigo === '1100000875161');
    const reglas = [
      { cantidad: 6, medio: 'efectivo', precio: 2500, alcance: 'lote', nota: '' },
      { cantidad: 1, medio: 'efectivo', precio: 3200, alcance: 'unidad', nota: '' },
      { cantidad: 12, medio: 'efectivo', precio: 2000, alcance: 'unidad', nota: 'docena' },
      { cantidad: '', medio: 'transferencia', precio: '2.800', alcance: 'unidad', nota: '' },
    ];
    for (const regla of reglas) {
      const response = await fetch(`${base}/api/promociones`, {
        method: 'POST',
        headers: { cookie: admin.cookie, 'content-type': 'application/json' },
        body: JSON.stringify({ productoId: producto.id, ...regla }),
      });
      assert.equal(response.status, 201, await response.clone().text());
    }
    const loteSinCantidad = await fetch(`${base}/api/promociones`, {
      method: 'POST',
      headers: { cookie: admin.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ productoId: producto.id, cantidad: '', medio: 'efectivo', precio: 10, alcance: 'lote' }),
    });
    assert.equal(loteSinCantidad.status, 400);

    const listed = await fetch(`${base}/api/promociones`, { headers: { cookie: empleado.cookie } });
    const promociones = (await listed.json()).promociones.filter((promo) => promo.productoId === producto.id);
    assert.equal(promociones.length, 4);
    assert.equal(reglaAplicable(promociones, 6, 'efectivo').precioCentavos, 250000);
    assert.equal(reglaAplicable(promociones, 1, 'efectivo').precioCentavos, 320000);
    assert.equal(reglaAplicable(promociones, 12, 'efectivo').nota, 'docena');
    assert.equal(reglaAplicable(promociones, 3, 'efectivo'), null);
    assert.equal(reglaAplicable(promociones, 8, 'transferencia').precioCentavos, 280000);

    const updated = promociones.find((promo) => promo.cantidad === 1);
    const edit = await fetch(`${base}/api/promociones/${updated.id}`, {
      method: 'PUT',
      headers: { cookie: admin.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ cantidad: 1, medio: 'efectivo', precio: 3100, alcance: 'unidad', nota: 'mostrador' }),
    });
    assert.equal(edit.status, 200);
    const employeeEdit = await fetch(`${base}/api/promociones/${updated.id}`, {
      method: 'PUT',
      headers: { cookie: empleado.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ cantidad: 1, medio: 'efectivo', precio: 1, alcance: 'unidad' }),
    });
    assert.equal(employeeEdit.status, 403);

    const off = await fetch(`${base}/api/usuarios/${sofiaId}`, {
      method: 'PATCH',
      headers: { cookie: admin.cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ activo: false }),
    });
    assert.equal(off.status, 200);
    const blocked = await login(base, 'sofia', 'salon123');
    assert.equal(blocked.response.status, 403);
    const stale = await fetch(`${base}/api/catalog`, { headers: { cookie: empleado.cookie } });
    assert.equal(stale.status, 401);

    const page = await fetch(`${base}/`);
    const html = await page.text();
    assert.match(html, /Consulta de precios/);
    assert.match(html, /manifest.webmanifest/);
    assert.doesNotMatch(html, /precio_mayorista/);
  } finally {
    server.close();
    await once(server, 'close');
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('loadCatalog agrupa filas idénticas sin código', () => {
  const csv = [
    'codigo;nombre;precio;precio_mayorista;categoria;proveedor;activo;sku_principal;nota_codigo',
    ';Vaso Igual;1000.00;1;bazar;Aqua;1;;',
    ';Vaso Igual;1000.00;1;bazar;Aqua;1;;',
    ';Vaso Igual;1200.00;1;bazar;Aqua;1;;',
    ';Otro;500.00;1;bazar;Aqua;0;;',
  ].join('\n');
  const products = loadCatalog(csv);
  assert.equal(products.length, 2);
  assert.equal(new Set(products.map((product) => product.id)).size, 2);
  assert.ok(products.every((product) => product.id.startsWith('n:')));
});
