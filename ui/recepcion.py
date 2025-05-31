import tkinter as tk
from tkinter import ttk
import sqlite3
from tkinter.constants import END

def open_recepcion_panel(user_id, user_name):
    conn = sqlite3.connect('db/pos.db')
    c = conn.cursor()

    ventana = tk.Tk()
    ventana.title(f"Recepción - {user_name}")
    ventana.state('zoomed')
    ventana.configure(bg='#f9f9f9')

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TLabel', background='#f9f9f9', font=('Segoe UI', 11))
    style.configure('TButton', font=('Segoe UI', 11))
    style.configure('Treeview', font=('Segoe UI', 10), rowheight=28)
    style.configure('Treeview.Heading', font=('Segoe UI', 11, 'bold'))

    productos_recepcionados = []

    def mensaje_popup(tipo, titulo, mensaje):
        popup = tk.Toplevel(ventana)
        popup.transient(ventana)
        popup.grab_set()
        popup.title(titulo)
        popup.resizable(False, False)
        popup.configure(bg='white')
        ttk.Label(popup, text=mensaje, wraplength=300, justify='center').pack(padx=20, pady=15)

        if tipo == "info":
            btn_ok = ttk.Button(popup, text="OK", command=popup.destroy)
            btn_ok.pack(pady=10)
            popup.bind('<Return>', lambda e: btn_ok.invoke())
            btn_ok.focus_set()

        elif tipo == "confirm":
            resultado = {"resp": False}
            def si(): resultado["resp"] = True; popup.destroy()
            def no(): popup.destroy()
            frame = ttk.Frame(popup)
            frame.pack(pady=10)
            btn_si = ttk.Button(frame, text="Sí", command=si)
            btn_no = ttk.Button(frame, text="No", command=no)
            btn_si.pack(side='left', padx=10)
            btn_no.pack(side='left', padx=10)
            popup.bind('<Return>', lambda e: btn_si.invoke())
            btn_si.focus_set()
            popup.wait_window()
            return resultado["resp"]

        popup.wait_window()

    def buscar_producto():
        codigo = entry_codigo.get().strip()
        if not codigo:
            mensaje_popup("info", "Advertencia", "Ingrese un código para buscar")
            return

        c.execute("SELECT nombre, cantidad, precio_lista, precio_publico FROM productos WHERE codigo_barras = ?", (codigo,))
        producto = c.fetchone()

        if producto:
            entry_nombre.delete(0, END)
            entry_nombre.insert(0, producto[0])
            entry_cantidad.delete(0, END)
            entry_cantidad.insert(0, "1")
            entry_precio_lista.delete(0, END)
            entry_precio_lista.insert(0, str(producto[2]))
            entry_precio_publico.delete(0, END)
            entry_precio_publico.insert(0, str(producto[3]))
            mensaje_popup("info", "Encontrado", "Producto encontrado. Verifique los datos y modifique si es necesario.")
            entry_nombre.focus_set()
        else:
            mensaje_popup("info", "No encontrado", "No existe producto con ese código")
            entry_nombre.focus_set()

    def agregar_temporal():
        codigo = entry_codigo.get().strip()
        nombre = entry_nombre.get().strip()
        cantidad = entry_cantidad.get().strip()
        precio_lista = entry_precio_lista.get().strip()
        precio_publico = entry_precio_publico.get().strip()

        if not codigo or not nombre:
            mensaje_popup("info", "Error", "Código y nombre no pueden estar vacíos")
            return

        try:
            cantidad = int(cantidad)
            precio_lista = round(float(precio_lista), 2)
            precio_publico = int(round(float(precio_publico)))
            if cantidad <= 0 or precio_lista <= 0 or precio_publico <= 0:
                raise ValueError
        except ValueError:
            mensaje_popup("info", "Error", "Verifique que los valores numéricos sean válidos y positivos")
            return

        producto = (codigo, nombre.upper(), cantidad, precio_lista, precio_publico)
        productos_recepcionados.append(producto)
        actualizar_lista()
        limpiar_campos()
        mensaje_popup("info", "Agregado", "Producto agregado a la lista de recepción")

    def eliminar_item(event=None):
        seleccionado = tree_recepcion.selection()
        if not seleccionado:
            mensaje_popup("info", "Atención", "Seleccione un producto para eliminar")
            return
        valores = tree_recepcion.item(seleccionado[0], "values")
        codigo, nombre = valores[0], valores[1]
        confirmar = mensaje_popup("confirm", "Confirmar", f"¿Eliminar el producto:\nCódigo: {codigo}\nNombre: {nombre}?")
        if confirmar:
            productos_recepcionados[:] = [p for p in productos_recepcionados if not (p[0] == codigo and p[1] == nombre)]
            actualizar_lista()
            mensaje_popup("info", "Eliminado", "Producto eliminado de la lista")

    def confirmar_recepcion():
        if not productos_recepcionados:
            mensaje_popup("info", "Error", "No hay productos para recepcionar")
            return
        confirmar = mensaje_popup("confirm", "Confirmar Recepción", f"¿Recepcionar {len(productos_recepcionados)} productos?")
        if not confirmar:
            return
        try:
            for prod in productos_recepcionados:
                c.execute("SELECT id FROM productos WHERE codigo_barras = ?", (prod[0],))
                existe = c.fetchone()
                if existe:
                    c.execute("""
                        UPDATE productos SET 
                            nombre = ?,
                            cantidad = cantidad + ?,
                            precio_lista = ?,
                            precio_publico = ?
                        WHERE codigo_barras = ?
                    """, (prod[1], prod[2], prod[3], prod[4], prod[0]))
                else:
                    c.execute("""
                        INSERT INTO productos 
                        (codigo_barras, nombre, cantidad, precio_lista, precio_publico, categoria) 
                        VALUES (?, ?, ?, ?, ?, 'GENERAL')
                    """, (*prod,))
            conn.commit()
            productos_recepcionados.clear()
            actualizar_lista()
            mensaje_popup("info", "Éxito", "Recepción completada correctamente")
        except sqlite3.Error as e:
            conn.rollback()
            mensaje_popup("info", "Error BD", str(e))

    def actualizar_lista():
        tree_recepcion.delete(*tree_recepcion.get_children())
        for prod in productos_recepcionados:
            tree_recepcion.insert("", "end", values=prod)

    def limpiar_campos():
        entry_codigo.delete(0, END)
        entry_nombre.delete(0, END)
        entry_cantidad.delete(0, END)
        entry_precio_lista.delete(0, END)
        entry_precio_publico.delete(0, END)
        entry_cantidad.insert(0, "1")
        entry_codigo.focus_set()

    # UI Layout
    frame = ttk.Frame(ventana, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    form = ttk.LabelFrame(frame, text="Agregar Producto", padding=15)
    form.pack(fill=tk.X, pady=10)

    ttk.Label(form, text="Código de Barras:").grid(row=0, column=0, sticky='e')
    entry_codigo = ttk.Entry(form, width=30)
    entry_codigo.grid(row=0, column=1, padx=5)
    ttk.Button(form, text="Buscar", command=buscar_producto).grid(row=0, column=2, padx=5)

    ttk.Label(form, text="Nombre:").grid(row=1, column=0, sticky='e')
    entry_nombre = ttk.Entry(form, width=30)
    entry_nombre.grid(row=1, column=1, columnspan=2, padx=5, sticky='ew')

    ttk.Label(form, text="Cantidad:").grid(row=2, column=0, sticky='e')
    entry_cantidad = ttk.Entry(form, width=10)
    entry_cantidad.grid(row=2, column=1, sticky='w')
    entry_cantidad.insert(0, "1")

    ttk.Label(form, text="Precio Lista:").grid(row=3, column=0, sticky='e')
    entry_precio_lista = ttk.Entry(form, width=10)
    entry_precio_lista.grid(row=3, column=1, sticky='w')

    ttk.Label(form, text="Precio Público:").grid(row=4, column=0, sticky='e')
    entry_precio_publico = ttk.Entry(form, width=10)
    entry_precio_publico.grid(row=4, column=1, sticky='w')

    ttk.Button(form, text="Agregar Producto", command=agregar_temporal).grid(row=5, column=0, columnspan=3, pady=10)

    list_frame = ttk.LabelFrame(frame, text="Productos a Recepcionar")
    list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

    columnas = ("Código", "Nombre", "Cantidad", "P. Lista", "P. Público")
    tree_recepcion = ttk.Treeview(list_frame, columns=columnas, show="headings", selectmode='browse')
    for col in columnas:
        tree_recepcion.heading(col, text=col)
        tree_recepcion.column(col, anchor='center')
    tree_recepcion.pack(fill=tk.BOTH, expand=True)

    ttk.Button(frame, text="Recepcionar Productos", command=confirmar_recepcion).pack(pady=5)
    ttk.Button(frame, text="Volver al Menú", command=ventana.destroy).pack()

    ventana.bind('<Return>', lambda e: agregar_temporal())
    ventana.bind('<F5>', eliminar_item)
    entry_codigo.focus_set()

    ventana.mainloop()
    conn.close()
