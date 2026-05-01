import sqlite3
import os
import sys


def get_base_dir():
    """Carpeta donde está el ejecutable o el script (donde vive la BD y datos)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def get_db_path():
    """Ruta completa al archivo de base de datos (siempre junto al exe/script)."""
    base = get_base_dir()
    return os.path.join(base, "db", "pos.db")


def ensure_column(cursor, table_name, column_name, column_def):
    cursor.execute("PRAGMA table_info(%s)" % table_name)
    cols = [row[1] for row in cursor.fetchall()]
    if column_name not in cols:
        cursor.execute(
            "ALTER TABLE %s ADD COLUMN %s %s" % (table_name, column_name, column_def)
        )


def init_db():
    db_path = get_db_path()
    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(db_path)

    c = conn.cursor()
    
    # Tabla de usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               codigo TEXT UNIQUE NOT NULL,
               nombre TEXT NOT NULL,
               es_admin INTEGER DEFAULT 0,
               activo INTEGER DEFAULT 1)''')
    
    # Tabla de productos
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               codigo_barras TEXT UNIQUE,
               nombre TEXT NOT NULL,
               categoria TEXT NOT NULL,
               cantidad INTEGER NOT NULL DEFAULT 0,
               precio_lista REAL NOT NULL,
               precio_publico INTEGER NOT NULL)''')
    
    # Tabla de arqueos (¡ESTRUCTURA ACTUALIZADA!)
    c.execute('''CREATE TABLE IF NOT EXISTS arqueos_caja (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               usuario_id INTEGER NOT NULL,
               fecha TEXT NOT NULL,
               efectivo REAL NOT NULL DEFAULT 0,
               tarjeta REAL NOT NULL DEFAULT 0,
               otros REAL NOT NULL DEFAULT 0,
               total_sistema REAL NOT NULL,
               diferencia REAL NOT NULL,
               observaciones TEXT,
               FOREIGN KEY (usuario_id) REFERENCES usuarios (id))''')
    
    # Tabla de ventas
    c.execute('''CREATE TABLE IF NOT EXISTS ventas (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               usuario_id INTEGER NOT NULL,
               total REAL NOT NULL,
               fecha TEXT DEFAULT CURRENT_TIMESTAMP,
               es_ajuste INTEGER DEFAULT 0,
               metodo_pago TEXT)''')
    
    # Tabla de detalle_ventas
    c.execute('''CREATE TABLE IF NOT EXISTS detalle_ventas (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               venta_id INTEGER NOT NULL,
               producto_id INTEGER NOT NULL,
               cantidad INTEGER NOT NULL,
               precio_unitario REAL NOT NULL)''')

    # Campos fiscales de ventas (migración segura)
    ensure_column(c, "ventas", "fiscal_solicitado", "INTEGER DEFAULT 0")
    ensure_column(c, "ventas", "fiscal_estado", "TEXT DEFAULT 'NO_SOLICITADO'")
    ensure_column(c, "ventas", "fiscal_tipo", "TEXT")
    ensure_column(c, "ventas", "fiscal_cae", "TEXT")
    ensure_column(c, "ventas", "fiscal_numero", "TEXT")
    ensure_column(c, "ventas", "fiscal_error", "TEXT")

    # Configuración fiscal / ticket (clave-valor)
    c.execute('''CREATE TABLE IF NOT EXISTS fiscal_config (
               clave TEXT PRIMARY KEY,
               valor TEXT)''')

    # Cola de comprobantes fiscales pendientes
    c.execute('''CREATE TABLE IF NOT EXISTS fiscal_pendientes (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               venta_id INTEGER NOT NULL,
               payload_json TEXT NOT NULL,
               estado TEXT DEFAULT 'PENDIENTE',
               error_ultimo TEXT,
               fecha_creado TEXT DEFAULT CURRENT_TIMESTAMP,
               fecha_ultimo_intento TEXT)''')
    
    # Datos iniciales
    usuarios = [
        ('9999', 'Administrador', 1),
        ('1234', 'Vendedor 1', 0),
        ('5678', 'Vendedor 2', 0)
    ]
    
    for codigo, nombre, es_admin in usuarios:
        c.execute("INSERT OR IGNORE INTO usuarios (codigo, nombre, es_admin) VALUES (?, ?, ?)",
                 (codigo, nombre, es_admin))
    
    c.execute("INSERT OR IGNORE INTO productos (codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico) VALUES (?, ?, ?, ?, ?, ?)",
             ('105', 'DESCUENTO INAUGURACIÓN 10%', 'DESCUENTO', 9999, 0, 0))

    config_defaults = {
        "empresa_razon_social": "",
        "empresa_cuit": "",
        "empresa_iibb": "",
        "empresa_domicilio": "",
        "empresa_condicion_iva": "RESPONSABLE INSCRIPTO",
        "arca_punto_venta": "1",
        "arca_ambiente": "produccion",
        "arca_cert_path": "",
        "arca_key_path": "",
        "arca_cuit_representada": "",
        "ticket_logo_path": "",
        "ticket_pie_texto": "Gracias por su compra",
        "ticket_ancho_mm": "58",
        "ticket_incluir_logo": "1",
        "ticket_auto_imprimir": "0",
    }
    for clave, valor in config_defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO fiscal_config (clave, valor) VALUES (?, ?)",
            (clave, valor),
        )
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()