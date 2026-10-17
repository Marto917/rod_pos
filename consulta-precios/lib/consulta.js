// Funciones puras compartidas por el servidor (tests) y el navegador.

const MAX_RESULTS = 30;

export function fold(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/["“”″]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function toCents(raw) {
  let text = String(raw ?? '').trim().replace(/\s/g, '').replace(/\$/g, '');
  if (!text) return null;
  const negative = text.startsWith('-');
  if (negative) text = text.slice(1);
  const comma = text.lastIndexOf(',');
  const dot = text.lastIndexOf('.');
  if (comma !== -1 && dot !== -1) {
    text = comma > dot ? text.replace(/\./g, '').replace(',', '.') : text.replace(/,/g, '');
  } else if (comma !== -1) {
    text = text.replace(',', '.');
  } else if (dot !== -1) {
    const groups = text.split('.');
    const last = groups.at(-1);
    if (groups.length > 2 || (groups.length === 2 && last.length === 3)) text = groups.join('');
  }
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const [whole, fraction = ''] = text.split('.');
  const cents = Number(whole) * 100 + Number(`${fraction}00`.slice(0, 2));
  if (!Number.isSafeInteger(cents)) return null;
  return negative ? -cents : cents;
}

export function reglaAplicable(reglas, cantidad, medio) {
  const qty = Number(cantidad);
  const propias = (reglas || []).filter((regla) => regla.medio === medio);
  const exacta = propias.find((regla) => regla.cantidad != null && Number(regla.cantidad) === qty);
  if (exacta) return exacta;
  return propias.find((regla) => regla.cantidad == null) ?? null;
}

export function formatARS(cents) {
  const amount = Number(cents);
  if (!Number.isSafeInteger(amount)) return '';
  const negative = amount < 0;
  const absolute = Math.abs(amount);
  const whole = Math.floor(absolute / 100);
  const fraction = absolute % 100;
  const grouped = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const formatted = fraction === 0 ? grouped : `${grouped},${String(fraction).padStart(2, '0')}`;
  return `${negative ? '-' : ''}$ ${formatted}`;
}

function haystack(product) {
  if (product.nombreFold) return product.nombreFold;
  return fold(`${product.nombre || ''} ${product.nota || ''}`);
}

export function searchProducts(products, rawQuery) {
  const query = String(rawQuery ?? '').trim();
  if (query.length < 2) {
    return { items: [], truncated: false, short: query.length > 0 };
  }

  const compact = query.replace(/\s+/g, '');
  const folded = fold(query);
  const numeric = /^\d+$/.test(compact);
  const tokens = folded.split(' ').filter(Boolean);

  const primary = products.filter((product) => product.codigo && product.codigo === compact);
  if (primary.length > 0) return { items: primary, truncated: false, short: false };

  const hasLetters = /[a-z]/i.test(folded);
  if (!hasLetters) {
    const alternate = products.filter((product) => product.codigo !== compact && product.codigos?.includes(compact));
    if (alternate.length > 0) return { items: alternate, truncated: false, short: false };
  }

  const ranked = [];
  for (const product of products) {
    let score = 0;
    const name = haystack(product);

    if (numeric && compact.length >= 3 && product.codigos?.some((code) => code.startsWith(compact))) {
      score = 75;
    }

    if (!numeric && product.codigos?.some((code) => fold(code) === folded)) {
      score = 100;
    }

    const allowName = !numeric || compact.length < 8;
    if (allowName && folded.length >= 2) {
      if (name.includes(folded)) score = Math.max(score, 80);
      else if (tokens.length > 1 && tokens.every((token) => name.includes(token))) {
        score = Math.max(score, 65);
      }
    }

    if (score > 0) ranked.push({ product, score });
  }

  ranked.sort((left, right) => {
    if (right.score !== left.score) return right.score - left.score;
    return left.product.nombre.localeCompare(right.product.nombre, 'es');
  });

  return {
    items: ranked.slice(0, MAX_RESULTS).map((entry) => entry.product),
    truncated: ranked.length > MAX_RESULTS,
    short: false,
  };
}
