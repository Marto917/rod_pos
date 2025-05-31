import sqlite3

def create_users():
    conn = sqlite3.connect('db/pos.db')
    c = conn.cursor()
    
    nuevos_usuarios = [
        ('1111', 'Vendedor 3', 0),
        ('0000', 'Admin 2', 1)
    ]
    
    for codigo, nombre, es_admin in nuevos_usuarios:
        try:
            c.execute("INSERT INTO usuarios (codigo, nombre, es_admin) VALUES (?, ?, ?)",
                     (codigo, nombre, es_admin))
            print(f"Usuario creado: {nombre} ({codigo})")
        except sqlite3.Error as e:
            print(f"Error al crear usuario: {str(e)}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_users()