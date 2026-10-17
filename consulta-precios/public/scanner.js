const NATIVE_FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'code_93', 'codabar', 'itf', 'qr_code'];

export function preferredEngine(features) {
  if (features.barcodeDetector) return 'barcode-detector';
  if (features.zxing) return 'zxing';
  return null;
}

function permissionError(error) {
  return error && (error.name === 'NotAllowedError' || error.name === 'SecurityError');
}

async function openCamera() {
  const attempts = [
    { audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } } },
    { audio: false, video: { facingMode: 'environment' } },
    { audio: false, video: true },
  ];
  let lastError;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
      lastError = error;
      if (permissionError(error)) throw error;
    }
  }
  throw lastError || Object.assign(new Error('no-camera'), { code: 'no-camera' });
}

async function startNative({ video, emit, state }) {
  const stream = await openCamera();
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();

  let formats = NATIVE_FORMATS;
  if (typeof BarcodeDetector.getSupportedFormats === 'function') {
    const supported = await BarcodeDetector.getSupportedFormats();
    const usable = NATIVE_FORMATS.filter((format) => supported.includes(format));
    if (usable.length) formats = usable;
  }
  const detector = new BarcodeDetector({ formats });
  const timer = { id: 0 };
  const tick = async () => {
    if (state.stopped) return;
    try {
      const found = await detector.detect(video);
      if (found?.[0]?.rawValue) emit(found[0].rawValue);
    } catch {
      // un cuadro fallido no corta la lectura
    }
    if (!state.stopped) timer.id = setTimeout(tick, 140);
  };
  timer.id = setTimeout(tick, 200);

  return {
    engine: 'barcode-detector',
    async stop() {
      state.stopped = true;
      clearTimeout(timer.id);
      for (const track of stream.getTracks()) track.stop();
      video.srcObject = null;
    },
  };
}

async function startZxing({ video, emit, state }) {
  const { BrowserMultiFormatReader, BarcodeFormat, DecodeHintType } = window.ZXing;
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [
    BarcodeFormat.EAN_13,
    BarcodeFormat.EAN_8,
    BarcodeFormat.UPC_A,
    BarcodeFormat.UPC_E,
    BarcodeFormat.CODE_128,
    BarcodeFormat.CODE_39,
    BarcodeFormat.ITF,
    BarcodeFormat.CODABAR,
    BarcodeFormat.QR_CODE,
  ]);
  const reader = new BrowserMultiFormatReader(hints, 200);
  const onResult = (result) => {
    if (result) emit(result.getText());
  };
  let controls;
  try {
    controls = await reader.decodeFromConstraints(
      { audio: false, video: { facingMode: { ideal: 'environment' } } },
      video,
      onResult,
    );
  } catch (error) {
    if (permissionError(error)) throw error;
    controls = await reader.decodeFromConstraints({ audio: false, video: true }, video, onResult);
  }
  return {
    engine: 'zxing',
    async stop() {
      state.stopped = true;
      try { controls?.stop(); } catch { /* ya detenido */ }
      try { reader.reset(); } catch { /* ya detenido */ }
    },
  };
}

export async function startScanner({ video, onCode }) {
  if (!window.isSecureContext) {
    throw Object.assign(new Error('insecure'), { code: 'insecure' });
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw Object.assign(new Error('no-camera'), { code: 'no-camera' });
  }
  const engine = preferredEngine({
    barcodeDetector: 'BarcodeDetector' in window,
    zxing: Boolean(window.ZXing?.BrowserMultiFormatReader),
  });
  if (!engine) throw Object.assign(new Error('no-decoder'), { code: 'no-decoder' });

  const state = { stopped: false, last: '', lastAt: 0 };
  const emit = (value) => {
    if (state.stopped) return;
    const code = String(value || '').trim();
    if (!code) return;
    const now = Date.now();
    if (code === state.last && now - state.lastAt < 1500) return;
    state.last = code;
    state.lastAt = now;
    onCode(code);
  };

  if (engine === 'barcode-detector') {
    try {
      return await startNative({ video, emit, state });
    } catch (error) {
      if (permissionError(error) || !window.ZXing?.BrowserMultiFormatReader) throw error;
    }
  }
  return startZxing({ video, emit, state });
}
