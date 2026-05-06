# Manual Tecnico - ROD POS

Documentacion tecnica para instalacion, compilacion y soporte.

---

## 1) Stack tecnico

- Python + Tkinter (UI)
- SQLite (base local)
- FPDF2 (ticket PDF)
- Pillow (imagenes)
- qrcode (QR fiscal en ticket)
- pyafipws (WSAA/WSFE - ARCA)
- PyInstaller (empaquetado EXE)

---

## 2) Estructura principal

- `main.py`: bootstrap y navegacion.
- `db_init.py`: creacion/migracion de esquema.
- `fiscal_service.py`: autenticacion WSAA + emision WSFE + cola de pendientes.
- `ui/sales.py`: flujo de venta e impresion.
- `ui/admin.py`: configuracion, usuarios, productos, reportes.

---

## 3) Instalacion entorno de desarrollo

```bash
py -m pip install pillow fpdf2 qrcode pyinstaller
py -m pip install "git+https://github.com/reingart/pyafipws.git"
```

Ejecucion local:

```bash
py main.py
```

---

## 4) Compilacion EXE

```bash
py -m PyInstaller RodPOS.spec
```

Salida esperada:

- `dist/RodPOS.exe`

---

## 5) Configuracion ARCA

### Datos requeridos en Admin -> ARCA/Ticket

- `empresa_razon_social`
- `empresa_cuit`
- `empresa_iibb`
- `arca_punto_venta` (ej. 4)
- `arca_ambiente` (`produccion` o `homologacion`)
- `arca_cuit_representada`
- `arca_cert_path` (ruta absoluta `.crt`)
- `arca_key_path` (ruta absoluta `.key`)

### URLs segun ambiente

- Produccion:
  - `https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL`
  - `https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL`
- Homologacion:
  - `https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL`
  - `https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL`

> Certificado de produccion solo funciona en ambiente `produccion`.

---

## 6) Flujo fiscal implementado

1. Venta confirmada.
2. Si fiscal:
   - WSAA `Autenticar` con `.crt/.key`.
   - saneo + validacion TA.
   - WSFE `Conectar`, `SetTicketAcceso`, `CompUltimoAutorizado`, `CAESolicitar`.
3. Si error:
   - venta queda guardada,
   - estado fiscal `PENDIENTE`,
   - alta/actualizacion en `fiscal_pendientes`.

---

## 7) Archivos de diagnostico

- `debug_afip.txt`: logs crudos WSAA/WSFE.
- `cache_arca/`: cache de TA.

Errores comunes:

- `junk after document element`:
  - limpiar `cache_arca`,
  - reintentar emision.
- respuesta vacia/no XML:
  - revisar cert/key/rutas/ambiente.

---

## 8) Base de datos

Archivo local:

- `db/pos.db` (junto al exe en despliegue final)

Tablas relevantes:

- `ventas`
- `detalle_ventas`
- `productos`
- `usuarios`
- `fiscal_config`
- `fiscal_pendientes`

---

## 9) Checklist previa a entrega

1. Login admin/vendedor OK.
2. Venta normal + impresion OK.
3. Venta con fiscal B + CAE OK.
4. Pendientes ARCA reintento OK.
5. Backup y restauracion verificados.
6. `debug_afip.txt` se genera en caso de error.

