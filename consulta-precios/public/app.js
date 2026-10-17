import { formatARS, reglaAplicable, searchProducts } from '/shared/consulta.js';
import { startScanner } from '/scanner.js';

const app = document.querySelector('#app');
const state = {
  session: null,
  products: [],
  promos: [],
  view: 'buscar',
  query: '',
  selectedId: null,
  cantidad: 1,
  medio: 'efectivo',
  empleados: [],
  form: emptyForm(),
  confirmDeleteId: null,
  error: '',
  cameraError: '',
  hint: localStorage.getItem('consulta-precios-hint') !== '0',
  empleadosLoading: false,
};

let scanner = null;
let deferredPrompt = null;

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  deferredPrompt = event;
});

function emptyForm() {
  return { id: null, cantidad: '', medio: 'efectivo', precio: '', alcance: 'unidad', nota: '' };
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) node.setAttribute(key, '');
    else if (value !== false && value != null) node.setAttribute(key, String(value));
  }
  for (const child of [].concat(children)) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function isAdmin() {
  return state.session?.rol === 'admin';
}

function promosDe(productId) {
  return state.promos.filter((promo) => promo.productoId === productId);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers: options.body ? { 'content-type': 'application/json' } : undefined,
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'No se pudo completar.');
    error.status = response.status;
    throw error;
  }
  return data;
}

boot();

async function boot() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  try {
    const session = await fetch('/api/session', { credentials: 'same-origin' });
    if (!session.ok) {
      renderLogin();
      return;
    }
    state.session = await session.json();
    await enterApp();
  } catch {
    app.replaceChildren(el('p', { class: 'boot', text: 'No se pudo conectar.' }));
  }
}

function renderLogin(message = '', usuario = '') {
  const user = el('input', { id: 'usuario', name: 'usuario', autocomplete: 'username', autocapitalize: 'none', value: usuario });
  const pass = el('input', { id: 'password', name: 'password', type: 'password', autocomplete: 'current-password' });
  const error = message ? el('p', { class: 'error', role: 'alert', text: message }) : null;
  const form = el('form', { class: 'login' }, [
    el('p', { class: 'kicker', text: 'Salón' }),
    el('h1', { text: 'Consulta de precios' }),
    el('p', { class: 'status', text: 'Ingresá con tu usuario. El catálogo no es público.' }),
    error,
    el('label', { class: 'field', text: 'Usuario' }, [user]),
    el('label', { class: 'field', text: 'Contraseña' }, [pass]),
    el('button', { class: 'btn', type: 'submit', text: 'Entrar' }),
  ]);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      state.session = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ usuario: user.value, password: pass.value }),
      });
      await enterApp();
    } catch (error) {
      renderLogin(error.message, user.value);
    }
  });
  app.className = 'shell';
  app.replaceChildren(form);
  user.focus();
}

async function enterApp() {
  const catalog = await api('/api/catalog');
  const promos = await api('/api/promociones');
  state.products = catalog.productos;
  state.promos = promos.promociones;
  state.view = 'buscar';
  state.query = '';
  state.selectedId = null;
  renderShell();
}

function renderShell() {
  stopScan();
  const salir = el('button', { class: 'ghost', type: 'button', text: 'Salir', onClick: logout });
  const header = el('header', { class: 'topbar' }, [
    el('div', { class: 'topbar-row' }, [
      el('div', {}, [
        el('h1', { text: 'Consulta de precios' }),
        el('p', { class: 'who', text: `${state.session.usuario} · ${isAdmin() ? 'administrador' : 'empleado'}` }),
      ]),
      salir,
    ]),
  ]);
  if (isAdmin()) {
    header.append(el('div', { class: 'nav' }, [
      el('button', {
        type: 'button',
        text: 'Precios',
        'aria-pressed': state.view === 'buscar' ? 'true' : 'false',
        onClick: () => switchView('buscar'),
      }),
      el('button', {
        type: 'button',
        text: 'Empleados',
        'aria-pressed': state.view === 'empleados' ? 'true' : 'false',
        onClick: () => switchView('empleados'),
      }),
    ]));
  }
  const camera = el('div', { id: 'camera', class: 'camera', hidden: true }, [
    el('video', { id: 'preview', playsinline: true, muted: true, autoplay: true }),
    el('p', { text: 'Apuntá al código de barras' }),
  ]);
  const stage = el('main', { id: 'stage', class: 'stage' });
  app.className = 'shell';
  app.replaceChildren(header, camera, stage);
  if (state.view === 'buscar') {
    app.append(renderDock());
    renderStage();
  } else {
    renderEmpleados();
  }
}

function switchView(view) {
  state.view = view;
  state.error = '';
  if (view === 'empleados') {
    loadEmpleados();
    return;
  }
  renderShell();
}

function renderDock() {
  const input = el('input', {
    id: 'q',
    type: 'text',
    enterkeyhint: 'search',
    placeholder: 'Nombre o código',
    autocomplete: 'off',
    autocapitalize: 'none',
    autocorrect: 'off',
    spellcheck: 'false',
    value: state.query,
  });
  input.addEventListener('input', () => {
    state.query = input.value;
    state.selectedId = null;
    renderStage();
  });
  const form = el('form', { class: 'search', role: 'search' }, [
    el('label', { class: 'sr-only', for: 'q', text: 'Buscar por nombre o código' }),
    input,
    el('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Borrar búsqueda', text: '×', onClick: () => {
      input.value = '';
      state.query = '';
      state.selectedId = null;
      renderStage();
      input.focus();
    } }),
  ]);
  form.addEventListener('submit', (event) => event.preventDefault());
  const scan = el('button', { id: 'scan', class: 'btn', type: 'button', text: 'Escanear código', onClick: toggleScan });
  const message = el('p', { id: 'camera-msg', class: 'error', hidden: !state.cameraError, role: 'alert', text: state.cameraError });
  return el('div', { class: 'dock' }, [form, scan, message]);
}

function renderStage() {
  const stage = document.querySelector('#stage');
  if (!stage) return;
  const result = searchProducts(state.products, state.query);
  if (result.items.length === 1) state.selectedId = result.items[0].id;
  else if (!result.items.some((product) => product.id === state.selectedId)) state.selectedId = null;
  const nodes = [];
  if (state.hint) nodes.push(renderHint());
  if (!state.query.trim()) {
    nodes.push(el('p', { class: 'empty', text: 'Escaneá un código o escribí un nombre.' }));
  } else if (result.short) {
    nodes.push(el('p', { class: 'empty', text: 'Seguí escribiendo para buscar.' }));
  } else if (result.items.length === 0) {
    nodes.push(el('div', { class: 'miss', role: 'status' }, [
      el('h2', { text: 'No encontrado' }),
      el('p', { text: 'No hay un artículo activo con esa búsqueda. Probá con otra parte del nombre o el código.' }),
    ]));
  } else {
    const selected = state.products.find((product) => product.id === state.selectedId);
    if (selected) nodes.push(renderDetail(selected));
    if (result.items.length > 1) {
      nodes.push(el('p', { class: 'status', text: result.truncated ? 'Hay más coincidencias. Afiná la búsqueda.' : `${result.items.length} resultados` }));
      for (const product of result.items) {
        const button = el('button', { class: 'result', type: 'button', onClick: () => selectProduct(product.id) }, [
          el('strong', { text: formatARS(product.precioCentavos) }),
          el('span', { text: product.nombre }),
        ]);
        if (product.id === state.selectedId) button.setAttribute('aria-current', 'true');
        nodes.push(button);
      }
    }
  }
  stage.replaceChildren(...nodes);
}

function renderHint() {
  return el('div', { class: 'hint' }, [
    el('p', { text: 'Para tenerla a mano: en el menú del navegador elegí Agregar a inicio. En Safari: Compartir → Agregar a inicio.' }),
    el('button', { type: 'button', text: 'Entendido', onClick: () => {
      state.hint = false;
      localStorage.setItem('consulta-precios-hint', '0');
      renderStage();
    } }),
    deferredPrompt ? el('button', { type: 'button', text: 'Agregar a inicio', onClick: async () => {
      deferredPrompt.prompt();
      deferredPrompt = null;
      state.hint = false;
      localStorage.setItem('consulta-precios-hint', '0');
      renderStage();
    } }) : null,
  ]);
}

function selectProduct(id) {
  if (state.selectedId !== id) {
    state.cantidad = 1;
    state.medio = 'efectivo';
    state.form = emptyForm();
    state.confirmDeleteId = null;
  }
  state.selectedId = id;
  renderStage();
}

function renderDetail(product) {
  const reglas = promosDe(product.id).slice().sort(compareReglas);
  const aplica = reglas.length ? reglaAplicable(reglas, state.cantidad, state.medio) : null;
  const parts = [
    el('article', { class: 'hero' }, [
      el('p', { class: 'kicker', text: 'Precio de lista' }),
      el('p', { class: 'price', text: formatARS(product.precioCentavos) }),
      el('h2', { text: product.nombre }),
      product.categoria ? el('p', { class: 'category', text: product.categoria }) : null,
      product.nota ? el('p', { class: 'note', text: product.nota }) : null,
      product.codigo ? el('p', { class: 'code', text: product.codigo }) : null,
    ]),
  ];
  if (reglas.length === 0) {
    parts.push(el('p', { class: 'none', text: 'Sin promoción' }));
  } else {
    parts.push(renderControles());
    if (!aplica) {
      parts.push(el('p', { class: 'status', text: 'Con esta cantidad y este medio aplica el precio de lista.' }));
    }
    for (const regla of reglas) parts.push(renderRegla(regla, aplica && aplica.id === regla.id));
  }
  if (isAdmin()) parts.push(renderPromoForm(product));
  return el('section', { 'aria-live': 'polite' }, parts);
}

function compareReglas(a, b) {
  const medio = (a.medio === 'transferencia') - (b.medio === 'transferencia');
  if (medio) return medio;
  return (a.cantidad ?? 9999) - (b.cantidad ?? 9999);
}

function renderControles() {
  const input = el('input', {
    id: 'cantidad',
    inputmode: 'numeric',
    value: String(state.cantidad),
    'aria-label': 'Cantidad',
  });
  input.addEventListener('input', () => {
    const next = Number(input.value.replace(/\D/g, ''));
    state.cantidad = Number.isInteger(next) && next > 0 ? Math.min(next, 9999) : 1;
    renderStage();
    const fresh = document.querySelector('#cantidad');
    if (fresh) {
      fresh.focus();
      const end = fresh.value.length;
      fresh.setSelectionRange(end, end);
    }
  });
  return el('div', { class: 'controls' }, [
    el('div', { class: 'stepper' }, [
      el('button', { type: 'button', 'aria-label': 'Menos cantidad', text: '−', onClick: () => {
        state.cantidad = Math.max(1, state.cantidad - 1);
        renderStage();
      } }),
      input,
      el('button', { type: 'button', 'aria-label': 'Más cantidad', text: '+', onClick: () => {
        state.cantidad = Math.min(9999, state.cantidad + 1);
        renderStage();
      } }),
    ]),
    el('div', { class: 'choices', role: 'group', 'aria-label': 'Medio de pago' }, [
      medioButton('efectivo', 'Efectivo'),
      medioButton('transferencia', 'Transferencia'),
    ]),
  ]);
}

function medioButton(medio, label) {
  return el('button', {
    type: 'button',
    class: 'choice',
    'aria-pressed': state.medio === medio ? 'true' : 'false',
    text: label,
    onClick: () => {
      state.medio = medio;
      renderStage();
    },
  });
}

function renderRegla(regla, aplica) {
  const actions = isAdmin() ? el('div', { class: 'rule-actions' }, [
    el('button', { class: 'text-btn', type: 'button', text: 'Editar', onClick: () => {
      state.form = {
        id: regla.id,
        cantidad: regla.cantidad ?? '',
        medio: regla.medio,
        precio: (regla.precioCentavos / 100).toFixed(regla.precioCentavos % 100 ? 2 : 0).replace('.', ','),
        alcance: regla.alcance,
        nota: regla.nota,
      };
      state.confirmDeleteId = null;
      renderStage();
    } }),
    el('button', {
      class: 'text-btn danger',
      type: 'button',
      text: state.confirmDeleteId === regla.id ? 'Confirmar' : 'Borrar',
      onClick: () => borrarRegla(regla.id),
    }),
  ]) : null;
  return el('article', {
    class: aplica ? 'rule is-match' : 'rule',
    'data-cantidad': regla.cantidad ?? '',
    'data-medio': regla.medio,
    'aria-current': aplica ? 'true' : 'false',
  }, [
    el('div', { class: 'rule-top' }, [
      el('strong', { text: regla.cantidad ? `${regla.cantidad} u. · ${etiquetaMedio(regla.medio)}` : `Cualquier cantidad · ${etiquetaMedio(regla.medio)}` }),
      aplica ? el('span', { class: 'badge', text: 'Aplica' }) : null,
    ]),
    el('p', { class: 'rule-price', text: formatARS(regla.precioCentavos) }),
    el('p', { class: 'note', text: etiquetaAlcance(regla) }),
    regla.nota ? el('p', { text: regla.nota }) : null,
    actions,
  ]);
}

function etiquetaMedio(medio) {
  return medio === 'transferencia' ? 'Transferencia' : 'Efectivo';
}

function etiquetaAlcance(regla) {
  if (regla.alcance === 'lote') return regla.cantidad ? `Por el lote de ${regla.cantidad}` : 'Por el lote';
  return 'Por unidad';
}

function renderPromoForm(product) {
  const form = state.form;
  const cantidad = el('input', {
    id: 'f-cantidad',
    inputmode: 'numeric',
    placeholder: 'Vacío = cualquier cantidad',
    value: form.cantidad,
  });
  const precio = el('input', { id: 'f-precio', inputmode: 'decimal', placeholder: '2500', value: form.precio });
  const nota = el('input', { id: 'f-nota', maxlength: '200', value: form.nota });
  cantidad.addEventListener('input', () => { state.form.cantidad = cantidad.value; });
  precio.addEventListener('input', () => { state.form.precio = precio.value; });
  nota.addEventListener('input', () => { state.form.nota = nota.value; });
  return el('form', { class: 'panel', id: 'promo-form' }, [
    el('h2', { text: form.id ? 'Editar regla' : 'Nueva regla' }),
    state.error ? el('p', { class: 'error', role: 'alert', text: state.error }) : null,
    el('label', { class: 'field', text: 'Cantidad' }, [cantidad]),
    el('div', { class: 'segment', role: 'group', 'aria-label': 'Medio de la regla' }, [
      formChoice('medio', 'efectivo', 'Efectivo'),
      formChoice('medio', 'transferencia', 'Transferencia'),
    ]),
    el('label', { class: 'field', text: 'Precio' }, [precio]),
    el('div', { class: 'segment', role: 'group', 'aria-label': 'Alcance' }, [
      formChoice('alcance', 'unidad', 'Por unidad'),
      formChoice('alcance', 'lote', 'Por el lote'),
    ]),
    el('label', { class: 'field', text: 'Nota para el salón' }, [nota]),
    el('button', { class: 'btn', type: 'submit', text: form.id ? 'Guardar cambios' : 'Guardar regla' }),
    form.id ? el('button', { class: 'text-btn', type: 'button', text: 'Cancelar', onClick: () => {
      state.form = emptyForm();
      state.error = '';
      renderStage();
    } }) : null,
  ]);
  function formChoice(key, value, label) {
    return el('button', {
      type: 'button',
      text: label,
      'aria-pressed': form[key] === value ? 'true' : 'false',
      onClick: () => {
        state.form[key] = value;
        renderStage();
      },
    });
  }
}

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== 'promo-form') return;
  event.preventDefault();
  const product = state.products.find((item) => item.id === state.selectedId);
  if (!product) return;
  state.error = '';
  const payload = {
    productoId: product.id,
    cantidad: state.form.cantidad,
    medio: state.form.medio,
    precio: state.form.precio,
    alcance: state.form.alcance,
    nota: state.form.nota,
  };
  try {
    if (state.form.id) {
      await api(`/api/promociones/${state.form.id}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await api('/api/promociones', { method: 'POST', body: JSON.stringify(payload) });
    }
    state.form = emptyForm();
    state.promos = (await api('/api/promociones')).promociones;
    renderStage();
  } catch (error) {
    state.error = error.message;
    renderStage();
  }
});

async function borrarRegla(id) {
  if (state.confirmDeleteId !== id) {
    state.confirmDeleteId = id;
    renderStage();
    return;
  }
  try {
    await api(`/api/promociones/${id}`, { method: 'DELETE' });
    state.confirmDeleteId = null;
    state.form = emptyForm();
    state.promos = (await api('/api/promociones')).promociones;
    renderStage();
  } catch (error) {
    state.error = error.message;
    renderStage();
  }
}

function renderEmpleados() {
  const stage = document.querySelector('#stage');
  if (!stage || !isAdmin()) return;
  if (state.empleadosLoading) {
    stage.replaceChildren(el('p', { class: 'empty', text: 'Cargando…' }));
    return;
  }
  const usuario = el('input', { id: 'nuevo-usuario', autocomplete: 'off', autocapitalize: 'none' });
  const password = el('input', { id: 'nuevo-password', type: 'password', autocomplete: 'new-password' });
  const form = el('form', { class: 'panel' }, [
    el('h2', { text: 'Nuevo empleado' }),
    state.error ? el('p', { class: 'error', role: 'alert', text: state.error }) : null,
    el('label', { class: 'field', text: 'Usuario' }, [usuario]),
    el('label', { class: 'field', text: 'Contraseña' }, [password]),
    el('button', { class: 'btn dark', type: 'submit', text: 'Crear empleado' }),
  ]);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    state.error = '';
    try {
      await api('/api/usuarios', {
        method: 'POST',
        body: JSON.stringify({ usuario: usuario.value, password: password.value }),
      });
      usuario.value = '';
      password.value = '';
      await loadEmpleados();
    } catch (error) {
      state.error = error.message;
      renderEmpleados();
    }
  });
  const list = el('div', { class: 'panel' }, [el('h2', { text: 'Empleados' })]);
  if (state.empleados.length === 0) list.append(el('p', { class: 'status', text: 'Todavía no hay empleados.' }));
  for (const empleado of state.empleados) {
    list.append(el('div', { class: empleado.activo ? 'employee' : 'employee off' }, [
      el('div', {}, [
        el('strong', { text: empleado.usuario }),
        el('p', { class: 'note', text: empleado.activo ? 'Activo' : 'Desactivado' }),
      ]),
      el('button', {
        class: 'text-btn',
        type: 'button',
        text: empleado.activo ? 'Desactivar' : 'Activar',
        onClick: () => cambiarEmpleado(empleado),
      }),
    ]));
  }
  stage.replaceChildren(form, list);
}

async function loadEmpleados() {
  state.empleadosLoading = true;
  if (state.view === 'empleados') renderShell();
  try {
    state.empleados = (await api('/api/usuarios')).usuarios;
    state.error = '';
  } catch (error) {
    state.error = error.message;
  } finally {
    state.empleadosLoading = false;
    if (state.view === 'empleados') renderShell();
  }
}

async function cambiarEmpleado(empleado) {
  try {
    await api(`/api/usuarios/${empleado.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ activo: !empleado.activo }),
    });
    await loadEmpleados();
  } catch (error) {
    state.error = error.message;
    renderEmpleados();
  }
}

async function toggleScan() {
  if (scanner) {
    await stopScan();
    return;
  }
  state.cameraError = '';
  const camera = document.querySelector('#camera');
  const video = document.querySelector('#preview');
  camera.hidden = false;
  video.muted = true;
  video.playsInline = true;
  const warm = video.play();
  if (warm) warm.catch(() => {});
  paintScan(true);
  try {
    scanner = await startScanner({
      video,
      onCode: (code) => {
        stopScan();
        const input = document.querySelector('#q');
        if (input) input.value = code;
        state.query = code;
        state.selectedId = null;
        renderStage();
        if (navigator.vibrate) navigator.vibrate(30);
      },
    });
  } catch (error) {
    state.cameraError = cameraMessage(error);
    camera.hidden = true;
    scanner = null;
    paintScan(false);
  }
}

async function stopScan() {
  const current = scanner;
  scanner = null;
  if (current) await current.stop();
  const camera = document.querySelector('#camera');
  if (camera) camera.hidden = true;
  paintScan(false);
}

function paintScan(active) {
  const button = document.querySelector('#scan');
  const message = document.querySelector('#camera-msg');
  if (button) {
    button.textContent = active ? 'Cerrar cámara' : 'Escanear código';
    button.className = active ? 'btn dark' : 'btn';
  }
  if (message) {
    message.hidden = !state.cameraError;
    message.textContent = state.cameraError;
  }
}

function cameraMessage(error) {
  if (!window.isSecureContext || error?.code === 'insecure') {
    return 'Para escanear hace falta HTTPS. La búsqueda por nombre o código sigue disponible.';
  }
  if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
    return 'El navegador no tiene permiso para usar la cámara.';
  }
  if (error?.code === 'no-decoder') return 'Este navegador no puede leer códigos con la cámara. Escribí el código.';
  return 'No se pudo abrir la cámara. Podés escribir el código igual.';
}

async function logout() {
  await stopScan();
  await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  state.session = null;
  state.products = [];
  state.promos = [];
  renderLogin();
}
