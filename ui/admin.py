import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import shutil
import json
import sys
from db_init import get_db_path, get_base_dir
from fiscal_service import get_fiscal_config, save_fiscal_config
from licencia import obtener_hwid, activar_licencia
from licencia import obtener_dias_restantes, obtener_fecha_vencimiento

def open_admin_panel(user_id, user_name):
    ventana = tk.Tk()
    ventana.title(f"Panel Admin - {user_name}")
    ventana.state('zoomed')
    ventana.configure(bg='#f0f0f0')
    
    base_dir = get_base_dir()
    # Conexión a BD
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # ----------------------------
    # FUNCIÓN DE SALIDA
    # ----------------------------
    def salir():
        try:
            conn.commit()
            conn.close()
            plt.close('all')
            ventana.quit()
            ventana.destroy()
            os._exit(0)
        except Exception:
            import sys
            sys.exit(0)

    # Estilos
    style = ttk.Style()
    style.configure('TNotebook', background='#f0f0f0')
    style.configure('TFrame', background='#f0f0f0')
    style.configure('TLabel', background='#f0f0f0', font=('Arial', 11))
    style.configure('TButton', font=('Arial', 11))
    style.configure('Treeview', rowheight=25, font=('Arial', 10))
    style.configure('Treeview.Heading', font=('Arial', 11, 'bold'))

    # Notebook (pestañas)
    notebook = ttk.Notebook(ventana)
    notebook.pack(fill='both', expand=True, padx=10, pady=10)

    # ----------------------------
    # PESTAÑA USUARIOS
    # ----------------------------
    tab_usuarios = ttk.Frame(notebook)
    notebook.add(tab_usuarios, text='👥 Usuarios')

    # Treeview para usuarios
    tree_usuarios = ttk.Treeview(tab_usuarios, columns=('ID', 'Código', 'Nombre', 'Rol', 'Estado'), show='headings')
    tree_usuarios.heading('ID', text='ID')
    tree_usuarios.heading('Código', text='Código')
    tree_usuarios.heading('Nombre', text='Nombre')
    tree_usuarios.heading('Rol', text='Rol')
    tree_usuarios.heading('Estado', text='Estado')

    tree_usuarios.column('ID', width=50, anchor='center')
    tree_usuarios.column('Código', width=100, anchor='center')
    tree_usuarios.column('Nombre', width=250)
    tree_usuarios.column('Rol', width=100, anchor='center')
    tree_usuarios.column('Estado', width=80, anchor='center')

    tree_usuarios.pack(fill='both', expand=True, padx=10, pady=10)

    # Scrollbar
    scrollbar_usuarios = ttk.Scrollbar(tab_usuarios, orient="vertical", command=tree_usuarios.yview)
    scrollbar_usuarios.pack(side='right', fill='y')
    tree_usuarios.configure(yscrollcommand=scrollbar_usuarios.set)

    # Frame para botones de usuarios
    btn_frame_usuarios = ttk.Frame(tab_usuarios)
    btn_frame_usuarios.pack(pady=10)

    def cargar_usuarios():
        try:
            tree_usuarios.delete(*tree_usuarios.get_children())
            cursor.execute("SELECT id, codigo, nombre, es_admin, activo FROM usuarios ORDER BY nombre")
            for usuario in cursor.fetchall():
                rol = "Admin" if usuario[3] else "Vendedor"
                estado = "Activo" if usuario[4] else "Inactivo"
                tree_usuarios.insert('', 'end', values=(
                    usuario[0],  # ID
                    usuario[1],  # Código
                    usuario[2],  # Nombre
                    rol,        # Rol
                    estado      # Estado
                ))
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"No se pudieron cargar usuarios:\n{str(e)}")

    def agregar_usuario():
        ventana_agregar = tk.Toplevel(ventana)
        ventana_agregar.title("Agregar Usuario")
        ventana_agregar.resizable(False, False)

        # Campos del formulario
        ttk.Label(ventana_agregar, text="Código:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        codigo = ttk.Entry(ventana_agregar)
        codigo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(ventana_agregar, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        nombre = ttk.Entry(ventana_agregar)
        nombre.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(ventana_agregar, text="Rol:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        rol = ttk.Combobox(ventana_agregar, values=["Vendedor", "Administrador"])
        rol.grid(row=2, column=1, padx=5, pady=5)
        rol.current(0)

        def guardar_usuario():
            try:
                es_admin = 1 if rol.get() == "Administrador" else 0
                cursor.execute(
                    "INSERT INTO usuarios (codigo, nombre, es_admin) VALUES (?, ?, ?)",
                    (codigo.get(), nombre.get(), es_admin)
                )
                conn.commit()
                messagebox.showinfo("Éxito", "Usuario agregado correctamente")
                ventana_agregar.destroy()
                cargar_usuarios()
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "El código de usuario ya existe")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo agregar usuario:\n{str(e)}")

        ttk.Button(ventana_agregar, text="Guardar", command=guardar_usuario).grid(row=3, column=1, pady=10)

    def editar_usuario():
        seleccionado = tree_usuarios.selection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un usuario")
            return

        usuario_id = tree_usuarios.item(seleccionado[0], 'values')[0]
        cursor.execute("SELECT codigo, nombre, es_admin, activo FROM usuarios WHERE id = ?", (usuario_id,))
        datos = cursor.fetchone()

        ventana_editar = tk.Toplevel(ventana)
        ventana_editar.title("Editar Usuario")
        ventana_editar.resizable(False, False)

        # Campos del formulario
        ttk.Label(ventana_editar, text="Código:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        codigo = ttk.Entry(ventana_editar)
        codigo.grid(row=0, column=1, padx=5, pady=5)
        codigo.insert(0, datos[0])

        ttk.Label(ventana_editar, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        nombre = ttk.Entry(ventana_editar)
        nombre.grid(row=1, column=1, padx=5, pady=5)
        nombre.insert(0, datos[1])

        ttk.Label(ventana_editar, text="Rol:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        rol = ttk.Combobox(ventana_editar, values=["Vendedor", "Administrador"])
        rol.grid(row=2, column=1, padx=5, pady=5)
        rol.current(1 if datos[2] else 0)

        ttk.Label(ventana_editar, text="Estado:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        estado = ttk.Combobox(ventana_editar, values=["Activo", "Inactivo"])
        estado.grid(row=3, column=1, padx=5, pady=5)
        estado.current(1 if not datos[3] else 0)

        def actualizar_usuario():
            try:
                es_admin = 1 if rol.get() == "Administrador" else 0
                activo = 1 if estado.get() == "Activo" else 0
                cursor.execute(
                    "UPDATE usuarios SET codigo = ?, nombre = ?, es_admin = ?, activo = ? WHERE id = ?",
                    (codigo.get(), nombre.get(), es_admin, activo, usuario_id)
                )
                conn.commit()
                messagebox.showinfo("Éxito", "Usuario actualizado correctamente")
                ventana_editar.destroy()
                cargar_usuarios()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar usuario:\n{str(e)}")

        ttk.Button(ventana_editar, text="Guardar", command=actualizar_usuario).grid(row=4, column=1, pady=10)

    def cambiar_estado_usuario():
        seleccionado = tree_usuarios.selection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un usuario")
            return

        usuario_id = tree_usuarios.item(seleccionado[0], 'values')[0]
        estado_actual = tree_usuarios.item(seleccionado[0], 'values')[4]
        nuevo_estado = 0 if estado_actual == "Activo" else 1
        texto_estado = "inactivar" if estado_actual == "Activo" else "activar"

        if messagebox.askyesno("Confirmar", f"¿Desea {texto_estado} este usuario?"):
            try:
                cursor.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (nuevo_estado, usuario_id))
                conn.commit()
                messagebox.showinfo("Éxito", f"Usuario {texto_estado}do correctamente")
                cargar_usuarios()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cambiar el estado:\n{str(e)}")

    # Botones de usuarios
    ttk.Button(btn_frame_usuarios, text="Actualizar", command=cargar_usuarios).pack(side='left', padx=5)
    ttk.Button(btn_frame_usuarios, text="Agregar", command=agregar_usuario).pack(side='left', padx=5)
    ttk.Button(btn_frame_usuarios, text="Editar", command=editar_usuario).pack(side='left', padx=5)
    ttk.Button(btn_frame_usuarios, text="Activar/Desactivar", command=cambiar_estado_usuario).pack(side='left', padx=5)

    # ----------------------------
    # PESTAÑA PRODUCTOS
    # ----------------------------
    tab_productos = ttk.Frame(notebook)
    notebook.add(tab_productos, text='📦 Productos')

    # Treeview para productos
    tree_productos = ttk.Treeview(tab_productos, columns=('ID', 'Código', 'Nombre', 'Categoría', 'Stock', 'Precio'), show='headings')
    tree_productos.heading('ID', text='ID')
    tree_productos.heading('Código', text='Código Barras')
    tree_productos.heading('Nombre', text='Nombre')
    tree_productos.heading('Categoría', text='Categoría')
    tree_productos.heading('Stock', text='Stock')
    tree_productos.heading('Precio', text='Precio Público')

    tree_productos.column('ID', width=50, anchor='center')
    tree_productos.column('Código', width=120, anchor='center')
    tree_productos.column('Nombre', width=250)
    tree_productos.column('Categoría', width=150)
    tree_productos.column('Stock', width=80, anchor='center')
    tree_productos.column('Precio', width=100, anchor='e')

    tree_productos.pack(fill='both', expand=True, padx=10, pady=10)

    # Scrollbar
    scrollbar = ttk.Scrollbar(tab_productos, orient="vertical", command=tree_productos.yview)
    scrollbar.pack(side='right', fill='y')
    tree_productos.configure(yscrollcommand=scrollbar.set)

    # Frame para botones
    btn_frame_productos = ttk.Frame(tab_productos)
    btn_frame_productos.pack(pady=10)

    def cargar_productos():
        try:
            tree_productos.delete(*tree_productos.get_children())
            cursor.execute("""
                SELECT id, codigo_barras, nombre, categoria, cantidad, precio_publico 
                FROM productos 
                ORDER BY nombre
            """)
            for producto in cursor.fetchall():
                tree_productos.insert('', 'end', values=producto)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"No se pudieron cargar productos:\n{str(e)}")

    def editar_stock():
        seleccionado = tree_productos.selection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un producto")
            return
            
        producto_id = tree_productos.item(seleccionado[0], 'values')[0]
        nombre = tree_productos.item(seleccionado[0], 'values')[2]
        stock_actual = tree_productos.item(seleccionado[0], 'values')[4]

        # Ventana de edición
        edicion = tk.Toplevel(ventana)
        edicion.title(f"Editar stock de {nombre}")
        edicion.resizable(False, False)

        ttk.Label(edicion, text=f"Producto: {nombre}").pack(pady=5)
        ttk.Label(edicion, text="Nuevo stock:").pack()

        nuevo_stock = ttk.Entry(edicion)
        nuevo_stock.pack(pady=5)
        nuevo_stock.insert(0, stock_actual)

        def guardar_cambios():
            try:
                cantidad = int(nuevo_stock.get())
                cursor.execute("UPDATE productos SET cantidad = ? WHERE id = ?", (cantidad, producto_id))
                conn.commit()
                messagebox.showinfo("Éxito", "Stock actualizado correctamente")
                edicion.destroy()
                cargar_productos()
            except ValueError:
                messagebox.showerror("Error", "Ingrese un valor numérico válido")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar:\n{str(e)}")

        ttk.Button(edicion, text="Guardar", command=guardar_cambios).pack(pady=10)

    ttk.Button(btn_frame_productos, text="Actualizar", command=cargar_productos).pack(side='left', padx=5)
    ttk.Button(btn_frame_productos, text="Editar Stock", command=editar_stock).pack(side='left', padx=5)

    # ----------------------------
    # PESTAÑA DESCUENTOS
    # ----------------------------
    tab_descuentos = ttk.Frame(notebook)
    notebook.add(tab_descuentos, text='🏷️ Descuentos')

    # Treeview para descuentos
    tree_descuentos = ttk.Treeview(tab_descuentos, columns=('ID', 'Código', 'Nombre', 'Tipo', 'Valor'), show='headings')
    tree_descuentos.heading('ID', text='ID')
    tree_descuentos.heading('Código', text='Código')
    tree_descuentos.heading('Nombre', text='Nombre')
    tree_descuentos.heading('Tipo', text='Tipo')
    tree_descuentos.heading('Valor', text='Valor')

    tree_descuentos.column('ID', width=50, anchor='center')
    tree_descuentos.column('Código', width=100, anchor='center')
    tree_descuentos.column('Nombre', width=250)
    tree_descuentos.column('Tipo', width=100, anchor='center')
    tree_descuentos.column('Valor', width=80, anchor='center')

    tree_descuentos.pack(fill='both', expand=True, padx=10, pady=10)

    # Scrollbar
    scrollbar_desc = ttk.Scrollbar(tab_descuentos, orient="vertical", command=tree_descuentos.yview)
    scrollbar_desc.pack(side='right', fill='y')
    tree_descuentos.configure(yscrollcommand=scrollbar_desc.set)

    # Frame para botones
    btn_frame_desc = ttk.Frame(tab_descuentos)
    btn_frame_desc.pack(pady=10)

    def cargar_descuentos():
        try:
            tree_descuentos.delete(*tree_descuentos.get_children())
            cursor.execute("""
                SELECT id, codigo_barras, nombre, categoria, precio_publico 
                FROM productos 
                WHERE categoria = 'DESCUENTO'
                ORDER BY nombre
            """)
            for descuento in cursor.fetchall():
                tipo = "Porcentaje" if "%" in descuento[2] else "Fijo"
                tree_descuentos.insert('', 'end', values=(
                    descuento[0],  # ID
                    descuento[1],  # Código
                    descuento[2],  # Nombre
                    tipo,         # Tipo
                    descuento[4]  # Valor
                ))
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"No se pudieron cargar descuentos:\n{str(e)}")

    def agregar_descuento():
        descuento = tk.Toplevel(ventana)
        descuento.title("Agregar Descuento")
        descuento.resizable(False, False)

        ttk.Label(descuento, text="Código:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        codigo = ttk.Entry(descuento)
        codigo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(descuento, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        nombre = ttk.Entry(descuento)
        nombre.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(descuento, text="Tipo:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        tipo = ttk.Combobox(descuento, values=["Porcentaje", "Monto fijo"])
        tipo.grid(row=2, column=1, padx=5, pady=5)
        tipo.current(0)

        ttk.Label(descuento, text="Valor:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        valor = ttk.Entry(descuento)
        valor.grid(row=3, column=1, padx=5, pady=5)

        def guardar_descuento():
            try:
                nombre_desc = nombre.get()
                if tipo.get() == "Porcentaje":
                    nombre_desc += f" {valor.get()}%"
                    valor_num = float(valor.get())
                else:
                    valor_num = float(valor.get())

                cursor.execute("""
                    INSERT INTO productos 
                    (codigo_barras, nombre, categoria, cantidad, precio_lista, precio_publico) 
                    VALUES (?, ?, 'DESCUENTO', 9999, 0, ?)
                """, (codigo.get(), nombre_desc, valor_num))
                conn.commit()
                messagebox.showinfo("Éxito", "Descuento agregado correctamente")
                descuento.destroy()
                cargar_descuentos()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo agregar:\n{str(e)}")

        ttk.Button(descuento, text="Guardar", command=guardar_descuento).grid(row=4, column=1, pady=10)

    def eliminar_descuento():
        seleccionado = tree_descuentos.selection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un descuento")
            return
            
        descuento_id = tree_descuentos.item(seleccionado[0], 'values')[0]
        nombre = tree_descuentos.item(seleccionado[0], 'values')[2]

        if messagebox.askyesno("Confirmar", f"¿Eliminar el descuento {nombre}?"):
            try:
                cursor.execute("DELETE FROM productos WHERE id = ?", (descuento_id,))
                conn.commit()
                messagebox.showinfo("Éxito", "Descuento eliminado correctamente")
                cargar_descuentos()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar:\n{str(e)}")

    ttk.Button(btn_frame_desc, text="Actualizar", command=cargar_descuentos).pack(side='left', padx=5)
    ttk.Button(btn_frame_desc, text="Agregar", command=agregar_descuento).pack(side='left', padx=5)
    ttk.Button(btn_frame_desc, text="Eliminar", command=eliminar_descuento).pack(side='left', padx=5)

    # ----------------------------
    # PESTAÑA REPORTES
    # ----------------------------
    tab_reportes = ttk.Frame(notebook)
    notebook.add(tab_reportes, text='📊 Reportes')

    def actualizar_reporte():
        try:
            if hasattr(tab_reportes, 'canvas'):
                tab_reportes.canvas.get_tk_widget().destroy()
            fig, ax = plt.subplots(figsize=(8, 4))
            cursor.execute("""
                SELECT date(fecha) as dia, SUM(total) as total
                FROM ventas 
                WHERE date(fecha) BETWEEN ? AND ?
                GROUP BY date(fecha)
                ORDER BY date(fecha)
            """, (fecha_inicio.get(), fecha_fin.get()))
            datos = cursor.fetchall()
            if datos:
                fechas = [d[0] for d in datos]
                totales = [d[1] for d in datos]
                ax.bar(fechas, totales, color='#4CAF50')
                ax.set_title('Ventas por Día')
                ax.set_xlabel('Fecha')
                ax.set_ylabel('Total ($)')
                plt.xticks(rotation=45)
                fig.tight_layout()
                tab_reportes.canvas = FigureCanvasTkAgg(fig, master=tab_reportes)
                tab_reportes.canvas.draw()
                tab_reportes.canvas.get_tk_widget().pack(fill='both', expand=True)
            else:
                messagebox.showinfo("Información", "No hay datos de ventas en el rango seleccionado")
        except sqlite3.Error as e:
            messagebox.showerror("Error BD", "Error en consulta:\n%s" % str(e))
        except Exception as e:
            messagebox.showerror("Error", "Error al generar reporte:\n%s" % str(e))

    # Controles de fecha
    controles_frame = ttk.Frame(tab_reportes)
    controles_frame.pack(pady=10, fill='x')
    
    ttk.Label(controles_frame, text="Desde:").pack(side='left')
    fecha_inicio = ttk.Entry(controles_frame, width=10)
    fecha_inicio.pack(side='left', padx=5)
    fecha_inicio.insert(0, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    
    ttk.Label(controles_frame, text="Hasta:").pack(side='left')
    fecha_fin = ttk.Entry(controles_frame, width=10)
    fecha_fin.pack(side='left', padx=5)
    fecha_fin.insert(0, datetime.now().strftime('%Y-%m-%d'))
    
    ttk.Button(controles_frame, text="Generar Reporte", command=actualizar_reporte).pack(side='left', padx=10)

    # ----------------------------
    # PESTAÑA BACKUP
    # ----------------------------
    tab_backup = ttk.Frame(notebook)
    notebook.add(tab_backup, text='💾 Backup')

    # Contenedor principal
    backup_mainframe = ttk.Frame(tab_backup)
    backup_mainframe.pack(fill='both', expand=True, padx=10, pady=10)

    # Frame para botones superiores
    backup_btn_frame = ttk.Frame(backup_mainframe)
    backup_btn_frame.pack(fill='x', pady=5)

    ttk.Button(backup_btn_frame, text="Crear Backup", command=lambda: hacer_backup()).pack(side='left', padx=5)
    ttk.Button(backup_btn_frame, text="Exportar Backup", command=lambda: exportar_backup()).pack(side='left', padx=5)
    ttk.Button(backup_btn_frame, text="Verificar Compatibilidad", command=lambda: verificar_compatibilidad()).pack(side='left', padx=5)

    # Frame para lista de backups
    backup_list_frame = ttk.Frame(backup_mainframe)
    backup_list_frame.pack(fill='both', expand=True)

    # Scrollbar
    backup_scrollbar = ttk.Scrollbar(backup_list_frame)
    backup_scrollbar.pack(side='right', fill='y')

    # Listbox
    lista_backups = tk.Listbox(
        backup_list_frame,
        yscrollcommand=backup_scrollbar.set,
        selectmode='single',
        font=('Arial', 10),
        height=15
    )
    lista_backups.pack(side='left', fill='both', expand=True)
    backup_scrollbar.config(command=lista_backups.yview)

    def actualizar_lista_backups():
        lista_backups.delete(0, tk.END)
        backups_dir = os.path.join(base_dir, 'backups')
        if os.path.exists(backups_dir):
            try:
                archivos = sorted(
                    [f for f in os.listdir(backups_dir) if f.endswith('.db')],
                    key=lambda x: os.path.getmtime(os.path.join(backups_dir, x)),
                    reverse=True
                )
                for archivo in archivos:
                    lista_backups.insert(tk.END, archivo)
            except Exception as e:
                messagebox.showerror("Error", f"Error al leer backups:\n{str(e)}")

    def hacer_backup():
        try:
            backups_dir = os.path.join(base_dir, 'backups')
            if not os.path.exists(backups_dir):
                os.makedirs(backups_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archivo_backup = os.path.join(backups_dir, f'pos_backup_{timestamp}.db')
            db_path = get_db_path()
            
            if not os.path.exists(db_path):
                messagebox.showerror("Error", f"No se encontró la base de datos en:\n{db_path}")
                return
                
            shutil.copy2(db_path, archivo_backup)
            
            metadata = {
                "version_sistema": "1.0",
                "fecha_backup": timestamp,
                "estructura_bd": obtener_estructura_bd()
            }
            
            with open(os.path.join(backups_dir, f'pos_backup_{timestamp}.meta'), 'w') as f:
                json.dump(metadata, f)
            
            messagebox.showinfo("Éxito", f"Backup creado:\n{archivo_backup}")
            actualizar_lista_backups()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear backup:\n{str(e)}")
        
    def exportar_backup():
        seleccionado = lista_backups.curselection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un backup de la lista")
            return
            
        archivo = lista_backups.get(seleccionado)
        destino = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("Backup POS", "*.db"), ("Todos los archivos", "*.*")],
            initialfile=archivo
        )
        
        if destino:
            try:
                backups_dir = os.path.join(base_dir, 'backups')
                shutil.copy2(os.path.join(backups_dir, archivo), destino)
                meta_src = os.path.join(backups_dir, f'{archivo[:-3]}.meta')
                if os.path.exists(meta_src):
                    shutil.copy2(meta_src, f'{destino[:-3]}.meta')
                messagebox.showinfo("Éxito", f"Backup exportado a:\n{destino}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo exportar:\n{str(e)}")

    def obtener_estructura_bd():
        estructura = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for tabla in cursor.fetchall():
            cursor.execute(f"PRAGMA table_info({tabla[0]})")
            estructura[tabla[0]] = [col[1] for col in cursor.fetchall()]
        return estructura

    def verificar_compatibilidad():
        seleccionado = lista_backups.curselection()
        if not seleccionado:
            messagebox.showwarning("Advertencia", "Seleccione un backup de la lista")
            return
            
        archivo = lista_backups.get(seleccionado)
        meta_file = os.path.join(base_dir, 'backups', f'{archivo[:-3]}.meta')
        
        if not os.path.exists(meta_file):
            messagebox.showwarning("Advertencia", "Este backup no tiene metadata de compatibilidad")
            return
            
        try:
            with open(meta_file, 'r') as f:
                metadata = json.load(f)
            
            estructura_actual = obtener_estructura_bd()
            problemas = []
            
            for tabla, columnas in metadata["estructura_bd"].items():
                if tabla not in estructura_actual:
                    problemas.append(f"❌ Tabla faltante: {tabla}")
                    continue
                    
                for col in columnas:
                    if col not in estructura_actual[tabla]:
                        problemas.append(f"❌ Columna faltante: {tabla}.{col}")
            
            reporte = (
                f"Backup: {archivo}\n"
                f"Fecha: {metadata['fecha_backup']}\n"
                f"Versión original: {metadata['version_sistema']}\n\n"
                "Resultado verificación:\n" +
                ("✅ Compatible (sin problemas detectados)" if not problemas 
                else "⚠️ Potenciales problemas:\n" + "\n".join(problemas))
            )
            messagebox.showinfo("Verificación de Compatibilidad", reporte)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al verificar:\n{str(e)}")

    # ----------------------------
    # PESTAÑA CONFIG ARCA / TICKET
    # ----------------------------
    tab_fiscal = ttk.Frame(notebook)
    notebook.add(tab_fiscal, text='ARCA/Ticket')

    fiscal_cfg = get_fiscal_config()
    fiscal_vars = {}
    campos = [
        ("Razon social", "empresa_razon_social"),
        ("CUIT empresa", "empresa_cuit"),
        ("IIBB", "empresa_iibb"),
        ("Domicilio", "empresa_domicilio"),
        ("Condicion IVA", "empresa_condicion_iva"),
        ("Punto de venta", "arca_punto_venta"),
        ("Ambiente (produccion/homologacion)", "arca_ambiente"),
        ("CUIT representada ARCA", "arca_cuit_representada"),
        ("Ruta certificado CRT", "arca_cert_path"),
        ("Ruta clave KEY", "arca_key_path"),
        ("Ruta logo ticket", "ticket_logo_path"),
        ("Pie ticket", "ticket_pie_texto"),
        ("Ancho ticket mm", "ticket_ancho_mm"),
        ("Incluir logo (1/0)", "ticket_incluir_logo"),
        ("Auto imprimir ticket (1/0)", "ticket_auto_imprimir"),
    ]
    form = ttk.Frame(tab_fiscal, padding=12)
    form.pack(fill="both", expand=True)
    for idx, (label, key) in enumerate(campos):
        ttk.Label(form, text=label + ":").grid(row=idx, column=0, sticky="e", padx=5, pady=4)
        fiscal_vars[key] = tk.StringVar(value=fiscal_cfg.get(key, ""))
        ttk.Entry(form, textvariable=fiscal_vars[key], width=58).grid(row=idx, column=1, sticky="w", padx=5, pady=4)
    ttk.Label(
        form,
        text="Nota: para emitir ARCA en produccion necesitás cert/key validos y pyafipws instalado.",
        font=("Arial", 9, "italic"),
    ).grid(row=len(campos), column=0, columnspan=2, pady=(10, 6), sticky="w")

    def guardar_config_fiscal():
        data = {k: v.get().strip() for k, v in fiscal_vars.items()}
        errores = []
        cuit = data.get("empresa_cuit", "")
        if cuit and (not cuit.isdigit() or len(cuit) != 11):
            errores.append("CUIT empresa debe tener 11 digitos.")
        cuit_rep = data.get("arca_cuit_representada", "")
        if cuit_rep and (not cuit_rep.isdigit() or len(cuit_rep) != 11):
            errores.append("CUIT representada ARCA debe tener 11 digitos.")
        pto = data.get("arca_punto_venta", "")
        if not pto.isdigit() or int(pto) <= 0:
            errores.append("Punto de venta debe ser numerico mayor a 0.")
        ambiente = (data.get("arca_ambiente", "") or "").lower()
        if ambiente not in ("produccion", "homologacion"):
            errores.append("Ambiente debe ser 'produccion' o 'homologacion'.")
        ancho = data.get("ticket_ancho_mm", "")
        if (not ancho.isdigit()) or int(ancho) < 40 or int(ancho) > 120:
            errores.append("Ancho ticket mm debe estar entre 40 y 120.")
        cert_path = data.get("arca_cert_path", "")
        if cert_path and not os.path.exists(cert_path):
            errores.append("No existe la ruta del certificado CRT.")
        key_path = data.get("arca_key_path", "")
        if key_path and not os.path.exists(key_path):
            errores.append("No existe la ruta de la clave KEY.")
        logo_path = data.get("ticket_logo_path", "")
        if logo_path and not os.path.exists(logo_path):
            errores.append("No existe la ruta del logo de ticket.")
        auto_print = data.get("ticket_auto_imprimir", "")
        if auto_print not in ("0", "1"):
            errores.append("Auto imprimir ticket debe ser 1 o 0.")
        if errores:
            messagebox.showerror("ARCA/Ticket", "\n".join(errores), parent=ventana)
            return
        save_fiscal_config(data)
        messagebox.showinfo("ARCA/Ticket", "Configuracion guardada.")

    def ayuda_impresion():
        msg = (
            "Impresion de ticket:\n"
            "1) En Windows, configurá la Xprinter como impresora predeterminada.\n"
            "2) El sistema imprime enviando el PDF al comando print del sistema.\n"
            "3) Si querés imprimir sin preguntar en cada venta, poné 'Auto imprimir ticket' en 1.\n"
            "4) Recomendado: ancho ticket 58 mm."
        )
        messagebox.showinfo("Ayuda impresion", msg, parent=ventana)

    ttk.Button(form, text="Guardar configuracion", command=guardar_config_fiscal).grid(
        row=len(campos) + 1, column=1, sticky="w", pady=8
    )
    ttk.Button(form, text="Ayuda impresion", command=ayuda_impresion).grid(
        row=len(campos) + 2, column=1, sticky="w", pady=4
    )

    # ----------------------------
    # PESTAÑA LICENCIA
    # ----------------------------
    tab_licencia = ttk.Frame(notebook)
    notebook.add(tab_licencia, text='🔑 Licencia')

    # Instrucciones para el cliente
    ttk.Label(
        tab_licencia,
        text="Para activar o renovar: 1) Copiá el HWID y enviálo a tu proveedor. "
             "2) Pegá el código que te envíen abajo y pulsá Activar.",
        font=("Arial", 10),
        wraplength=500,
    ).pack(pady=(10, 15))

    # HWID + botón copiar
    f_hwid = ttk.Frame(tab_licencia)
    f_hwid.pack(pady=5)
    ttk.Label(f_hwid, text="HWID de este equipo:").pack(side="left", padx=(0, 8))
    hwid_var = tk.StringVar(value=obtener_hwid())
    ttk.Entry(f_hwid, textvariable=hwid_var, state='readonly', width=45).pack(side="left", padx=5)

    def copiar_hwid():
        ventana.clipboard_clear()
        ventana.clipboard_append(hwid_var.get())
        messagebox.showinfo("Copiado", "HWID copiado al portapapeles. Envialo a tu proveedor.", parent=ventana)

    ttk.Button(f_hwid, text="Copiar HWID", command=copiar_hwid).pack(side="left")

    ttk.Label(tab_licencia, text="Código de licencia (pegá el que te enviaron):").pack(pady=(15, 5))
    licencia_var = tk.StringVar()
    entry_licencia = ttk.Entry(tab_licencia, textvariable=licencia_var, width=65)
    entry_licencia.pack(pady=5)

    # Estado actual (se actualiza después de activar)
    estado_licencia_var = tk.StringVar()
    def actualizar_estado_licencia():
        dias = obtener_dias_restantes()
        fecha_venc = obtener_fecha_vencimiento()
        if fecha_venc == "PERPETUA":
            estado_licencia_var.set("Licencia activa de por vida (perpetua).")
            return
        if dias is not None and fecha_venc:
            try:
                from datetime import datetime as dt
                f = dt.strptime(fecha_venc, "%Y-%m-%d").strftime("%d/%m/%Y")
                estado_licencia_var.set(f"⏳ Quedan {dias} días. Vence: {f}")
            except Exception:
                estado_licencia_var.set(f"⏳ Quedan {dias} días de licencia.")
        elif fecha_venc:
            estado_licencia_var.set(f"⚠️ Licencia vencida (vencía: {fecha_venc})")
        else:
            estado_licencia_var.set("❌ Sin licencia activa. Activá un código para usar como vendedor.")

    ttk.Label(tab_licencia, textvariable=estado_licencia_var, font=("Arial", 10, "italic")).pack(pady=8)
    actualizar_estado_licencia()

    def activar():
        codigo = licencia_var.get().strip()
        if not codigo:
            messagebox.showwarning("Licencia", "Ingresá el código que te envió el proveedor.", parent=ventana)
            return
        if activar_licencia(codigo):
            messagebox.showinfo("Licencia", "✅ Licencia activada correctamente.", parent=ventana)
            actualizar_estado_licencia()
            entry_licencia.delete(0, tk.END)
        else:
            messagebox.showerror(
                "Licencia",
                "❌ El código es inválido, está vencido o ya fue usado en este equipo.",
                parent=ventana,
            )

    ttk.Button(tab_licencia, text="Activar licencia", command=activar).pack(pady=10)

    # ----------------------------
    # BOTÓN DE SALIDA
    # ----------------------------
    btn_salir = ttk.Button(ventana, text="Salir", command=salir, style='TButton')
    btn_salir.pack(side='bottom', pady=10)

    # Carga inicial
    cargar_usuarios()
    cargar_productos()
    cargar_descuentos()
    actualizar_reporte()
    actualizar_lista_backups()

    ventana.mainloop()

if __name__ == "__main__":
    open_admin_panel(1, "Administrador")