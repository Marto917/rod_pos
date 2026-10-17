import { createHash } from 'node:crypto';
import fs from 'node:fs';

import { fold, toCents } from './consulta.js';
import { parseSemicolonCsv } from './csv.js';

function baseKey(product) {
  if (product.codigo) return `c:${product.codigo}`;
  const basis = `${fold(product.nombre)}|${fold(product.categoria)}`;
  const digest = createHash('sha256').update(basis).digest('hex').slice(0, 20);
  return `n:${digest}`;
}

export function loadCatalog(csvText) {
  const rows = parseSemicolonCsv(csvText);
  const products = [];

  for (const row of rows) {
    if (String(row.activo ?? '').trim() !== '1') continue;
    const codigo = String(row.codigo ?? '').trim();
    const sku = String(row.sku_principal ?? '').trim();
    const codigos = [...new Set([codigo, sku].filter(Boolean))];
    const precioCentavos = toCents(row.precio);
    if (precioCentavos === null) continue;
    products.push({
      codigo,
      codigos,
      nombre: String(row.nombre ?? '').trim(),
      precioCentavos,
      categoria: String(row.categoria ?? '').trim(),
      nota: String(row.nota_codigo ?? '').trim(),
    });
  }

  const groups = new Map();
  for (const product of products) {
    const key = baseKey(product);
    const group = groups.get(key) || [];
    group.push(product);
    groups.set(key, group);
  }

  const loaded = [];
  const seen = new Set();
  for (const product of products) {
    const key = baseKey(product);
    const group = groups.get(key);
    const prices = new Set(group.map((item) => item.precioCentavos));
    const id = group.length > 1 && prices.size > 1 ? `${key}:${product.precioCentavos}` : key;
    const fingerprint = `${id}|${product.nombre}|${product.nota}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    loaded.push({ id, ...product });
  }

  return loaded;
}

export function loadCatalogFile(filePath) {
  return loadCatalog(fs.readFileSync(filePath, 'utf8'));
}
