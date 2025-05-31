# stock_view.py
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3

def open_stock_view(user_id, user_name):
    ventana = tk.Tk()
    ventana.title(f"Stock - {user_name}")
    ventana.geometry("1000x600")
    ventana.state('zoomed')
    ventana.configure(bg='#f0f0f0')

    # Conexión a BD
    conn = sqlite3.connect('db/pos.db')
    cursor = conn.cursor()

    # Estilos
    style = ttk.Style()
    style.configure('TFrame', background='#f0f0f0')
    style.configure('TLabel', background='#f0f0f0', font=('Arial', 11))
    style.configure('TButton', font=('Arial', 11))
    style.configure('Treeview', rowheight=25, font=('Arial', 10))
    style.configure('Treeview.Heading', font=('Arial', 11, 'bold'))

    # Frame principal
    main_frame = ttk.Frame(ventana, padding=20)
    main_frame.pack(fill='both', expand=True)

    # Frame de búsqueda (inicialmente oculto)
    search_frame = ttk.Frame(main_frame)
    search_visible = False

    # Widgets de búsqueda
    ttk.Label(search_frame, text="Buscar:").pack(side='left')
    entry_busqueda = ttk.Entry(search_frame, width=50)
    entry_busqueda.pack(side='left', padx=5)
    btn_buscar = ttk.Button(search_frame, text="Buscar")
    btn_buscar.pack(side='left', padx=5)

    def toggle_search():
        nonlocal search_visible
        if search_visible:
            search_frame.pack_forget()
            search_visible = False
        else:
            search_frame.pack(fill='x', pady=10)
            entry_busqueda.focus()
            search_visible = True

    def buscar_productos(event=None):
        texto_busqueda = entry_busqueda.get().strip()
        try:
            tree.delete(*tree.get_children())
            if texto_busqueda:
                cursor.execute("""
                    SELECT id, codigo_barras, nombre, categoria, cantidad, precio_publico 
                    FROM productos 
                    WHERE nombre LIKE ? OR codigo_barras LIKE ? OR categoria LIKE ?
                    ORDER BY nombre
                """, (f'%{texto_busqueda}%', f'%{texto_busqueda}%', f'%{texto_busqueda}%'))
            else:
                cursor.execute("""
                    SELECT id, codigo_barras, nombre, categoria, cantidad, precio_publico 
                    FROM productos 
                    ORDER BY nombre
                """)
            
            for row in cursor.fetchall():
                tree.insert('', 'end', values=row)
                
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Error al buscar productos:\n{str(e)}")

    # Asignar la función al botón después de su definición
    btn_buscar.config(command=buscar_productos)
    entry_busqueda.bind('<KeyRelease>', buscar_productos)

    # Treeview
    tree = ttk.Treeview(main_frame, columns=('ID', 'Código', 'Nombre', 'Categoría', 'Stock', 'Precio'), show='headings')
    tree.heading('ID', text='ID')
    tree.heading('Código', text='Código Barras')
    tree.heading('Nombre', text='Nombre')
    tree.heading('Categoría', text='Categoría')
    tree.heading('Stock', text='Stock')
    tree.heading('Precio', text='Precio Público')

    tree.column('ID', width=50, anchor='center')
    tree.column('Código', width=120, anchor='center')
    tree.column('Nombre', width=300)
    tree.column('Categoría', width=150)
    tree.column('Stock', width=80, anchor='center')
    tree.column('Precio', width=100, anchor='e')

    tree.pack(fill='both', expand=True)

    # Scrollbar
    scrollbar = ttk.Scrollbar(tree, orient="vertical", command=tree.yview)
    scrollbar.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scrollbar.set)

    # Atajo de teclado para mostrar/ocultar búsqueda
    ventana.bind('<Control-L>', lambda e: toggle_search())
    ventana.bind('<Control-l>', lambda e: toggle_search())

    # Carga inicial
    buscar_productos()

    ventana.mainloop()
    conn.close()