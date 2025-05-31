# db_init.py
import sqlite3
import os

def init_db():
    if not os.path.exists('db'):
        os.makedirs('db')
    
    conn = sqlite3.connect('db/pos.db')
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
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()