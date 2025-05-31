import tkinter as tk
from tkinter import ttk
import sqlite3
from datetime import datetime
import os
from fpdf import FPDF

# Control de ventana única
sales_window_open = False

def open_sales_panel(user_id, user_name):
    global sales_window_open
    if sales_window_open:
        mostrar_popup("Ventana abierta", "Ya hay una ventana de venta abierta.")
        return
    sales_window_open = True

    conn = sqlite3.connect('db/pos.db')
    c = conn.cursor()

    ventana = tk.Toplevel()
    ventana.title(f"POS - Venta - {user_name}")
    ventana.state('zoomed')
    ventana.configure(bg='#eaeaea')

    productos_vendidos = []
    subtotal_var = tk.StringVar(value="0.00")
    descuento_var = tk.StringVar(value="0.00")
    total_var = tk.StringVar(value="0.00")
    descuento_activo = tk.BooleanVar(value=False)
    metodo_pago_var = tk.StringVar(value="EFECTIVO")

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TLabel', background='#eaeaea', font=('Segoe UI', 11))
    style.configure('TButton', font=('Segoe UI', 11, 'bold'))
    style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
    style.configure('Discount.TLabel', foreground='red')

    def mostrar_popup(titulo, mensaje):
        popup = tk.Toplevel(ventana)
        popup.title(titulo)
        popup.transient(ventana)
        popup.grab_set()
        popup.configure(bg="white")
        ttk.Label(popup, text=mensaje, font=('Segoe UI', 10), padding=15).pack()
        ttk.Button(popup, text="Aceptar", command=popup.destroy).pack(pady=10)
        popup.bind('<Return>', lambda e: popup.destroy())
        popup.focus_force()
        popup.wait_window()

    def actualizar_ticket():
        ticket_tree.delete(*ticket_tree.get_children())
        subtotal = 0.0
        for p in productos_vendidos:
            if p['codigo'] != '105':
                ticket_tree.insert('', 'end', values=(
                    p['codigo'], p['nombre'], f"${p['precio']:.2f}", 1, f"${p['precio']:.2f}"
                ))
                subtotal += p['precio']
            else:
                ticket_tree.insert('', 'end', values=(
                    p['codigo'], p['nombre'], "-", "-", "-"
                ), tags=('discount',))
        descuento = round(subtotal * 0.10, 2) if descuento_activo.get() else 0.0
        total = subtotal - descuento
        subtotal_var.set(f"{subtotal:.2f}")
        descuento_var.set(f"{descuento:.2f}")
        total_var.set(f"{total:.2f}")
        ticket_tree.tag_configure('discount', foreground='red')

    def agregar_producto():
        codigo = codigo_entry.get().strip()
        if not codigo:
            return
        if codigo == '105':
            if any(p['codigo'] == '105' for p in productos_vendidos):
                mostrar_popup("Descuento", "Ya hay un descuento aplicado en este ticket")
                codigo_entry.delete(0, tk.END)
                return
            if not any(p['codigo'] != '105' for p in productos_vendidos):
                mostrar_popup("Error", "No hay productos para aplicar descuento")
                codigo_entry.delete(0, tk.END)
                return
            productos_vendidos.append({
                'id': None, 'codigo': '105',
                'nombre': 'DESCUENTO INAUGURACIÓN 10%', 'precio': 0
            })
            descuento_activo.set(True)
            actualizar_ticket()
            codigo_entry.delete(0, tk.END)
            return

        c.execute("SELECT id, nombre, precio_publico, cantidad FROM productos WHERE codigo_barras = ?", (codigo,))
        prod = c.fetchone()
        if not prod:
            mostrar_popup("Error", "Producto no encontrado")
            return
        if prod[3] < 1:
            mostrar_popup("Sin stock", "No hay stock disponible")
            return

        productos_vendidos.append({
            'id': prod[0], 'codigo': codigo, 'nombre': prod[1], 'precio': prod[2]
        })
        actualizar_ticket()
        codigo_entry.delete(0, tk.END)

    def eliminar_item(event=None):
        seleccion = ticket_tree.selection()
        if not seleccion:
            return
        index = ticket_tree.index(seleccion[0])
        producto_eliminado = productos_vendidos.pop(index)
        if producto_eliminado['codigo'] == '105':
            descuento_activo.set(False)
        actualizar_ticket()

    def resetear_ticket():
        productos_vendidos.clear()
        subtotal_var.set("0.00")
        descuento_var.set("0.00")
        total_var.set("0.00")
        descuento_activo.set(False)
        metodo_pago_var.set("EFECTIVO")
        actualizar_ticket()
        codigo_entry.focus_set()

    def generar_comprobante(venta_id, total):
        if not os.path.exists('comprobantes'):
            os.makedirs('comprobantes')
        fecha = datetime.now().strftime("%d%m%Y")
        nombre_archivo = f"comprobantes/{fecha}_{venta_id:06d}.pdf"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Kiosco L3M", ln=1, align='C') #TITULO DEL TICKET
        pdf.cell(200, 10, txt=f"Ticket #{venta_id:06d}", ln=1, align='C')
        pdf.cell(200, 10, txt=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), ln=1, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", size=10)
        subtotal = 0
        for p in productos_vendidos:
            if p['codigo'] != '105':
                pdf.cell(100, 8, txt=f"{p['nombre']}", align='L')
                pdf.cell(30, 8, txt=f"1 x ${p['precio']:.2f}", align='R')
                pdf.cell(30, 8, txt=f"${p['precio']:.2f}", ln=1, align='R')
                subtotal += p['precio']
            else:
                pdf.cell(100, 8, txt=f"{p['nombre']}", align='L')
                pdf.cell(60, 8, txt="DESCUENTO", ln=1, align='R')
        pdf.ln(5)
        pdf.set_font("Arial", 'B', size=10)
        pdf.cell(130, 8, txt="SUBTOTAL:", align='R')
        pdf.cell(30, 8, txt=f"${subtotal:.2f}", ln=1, align='R')
        if descuento_activo.get():
            descuento = round(subtotal * 0.10, 2)
            pdf.cell(130, 8, txt="DESCUENTO (10%):", align='R')
            pdf.cell(30, 8, txt=f"-${descuento:.2f}", ln=1, align='R')
        pdf.cell(130, 8, txt="TOTAL:", align='R')
        pdf.cell(30, 8, txt=f"${float(total_var.get()):.2f}", ln=1, align='R')
        pdf.ln(5)
        pdf.cell(200, 8, txt=f"Método de pago: {metodo_pago_var.get()}", ln=1, align='L')
        pdf.output(nombre_archivo)

    def finalizar_venta(event=None):
        if not productos_vendidos:
            mostrar_popup("Atención", "No hay productos cargados")
            return
        total = float(total_var.get())
        metodo_pago = metodo_pago_var.get()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            c.execute("INSERT INTO ventas (usuario_id, total, fecha, metodo_pago) VALUES (?, ?, ?, ?)",
                      (user_id, total, fecha, metodo_pago))
            venta_id = c.lastrowid
            for p in productos_vendidos:
                if p['id']:
                    c.execute("INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario) VALUES (?, ?, ?, ?)",
                              (venta_id, p['id'], 1, p['precio']))
                    c.execute("UPDATE productos SET cantidad = cantidad - 1 WHERE id = ?", (p['id'],))
            conn.commit()
            generar_comprobante(venta_id, total)
            mostrar_popup("Éxito", f"Venta registrada\nTotal: ${total:.2f}\nMétodo: {metodo_pago}")
            resetear_ticket()
        except sqlite3.Error as e:
            conn.rollback()
            mostrar_popup("Error BD", str(e))

    def cancelar_venta(event=None):
        if confirmar("¿Cancelar la venta actual?"):
            al_cerrar()

    def confirmar(mensaje):
        popup = tk.Toplevel(ventana)
        popup.title("Confirmar")
        popup.transient(ventana)
        popup.grab_set()
        popup.configure(bg="white")
        respuesta = {'valor': False}
        ttk.Label(popup, text=mensaje, font=('Segoe UI', 10), padding=15).pack()
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Sí", command=lambda: (popup.destroy(), respuesta.update(valor=True))).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="No", command=popup.destroy).pack(side='left', padx=5)
        popup.focus_force()
        popup.wait_window()
        return respuesta['valor']

    def al_cerrar():
        global sales_window_open
        try:
            conn.close()
        except:
            pass
        sales_window_open = False
        ventana.destroy()

    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)

    # Layout
    top_frame = ttk.Frame(ventana, padding=10)
    top_frame.pack(fill='x')
    ttk.Label(top_frame, text=f"POS Venta - {user_name}", style="Header.TLabel").pack(side='left')

    input_frame = ttk.Frame(ventana, padding=10)
    input_frame.pack(fill='x')
    ttk.Label(input_frame, text="Código:").grid(row=0, column=0, padx=5)
    codigo_entry = ttk.Entry(input_frame, width=30)
    codigo_entry.grid(row=0, column=1, padx=5)
    codigo_entry.focus_set()
    ttk.Button(input_frame, text="Agregar", command=agregar_producto).grid(row=0, column=2, padx=10)

    ticket_frame = ttk.LabelFrame(ventana, text="Ticket de Venta", padding=10)
    ticket_frame.pack(fill='both', expand=True, padx=10, pady=10)
    columnas = ("Código", "Producto", "Precio", "Cantidad", "Subtotal")
    ticket_tree = ttk.Treeview(ticket_frame, columns=columnas, show='headings', height=15)
    for col in columnas:
        ticket_tree.heading(col, text=col)
        ticket_tree.column(col, anchor='center')
    ticket_tree.column("Producto", anchor='w', width=250)
    ticket_tree.pack(fill='both', expand=True)
    ticket_tree.tag_configure('discount', foreground='red')

    resumen_frame = ttk.Frame(ventana, padding=10)
    resumen_frame.pack(fill='x')
    ttk.Label(resumen_frame, text="Subtotal: $").grid(row=0, column=0, sticky='e')
    ttk.Label(resumen_frame, textvariable=subtotal_var).grid(row=0, column=1, sticky='w', padx=10)
    ttk.Label(resumen_frame, text="Descuento: $").grid(row=1, column=0, sticky='e')
    ttk.Label(resumen_frame, textvariable=descuento_var).grid(row=1, column=1, sticky='w', padx=10)
    ttk.Label(resumen_frame, text="Total: $", font=('Segoe UI', 12, 'bold')).grid(row=2, column=0, sticky='e', pady=5)
    ttk.Label(resumen_frame, textvariable=total_var, font=('Segoe UI', 12, 'bold')).grid(row=2, column=1, sticky='w', padx=10)
    ttk.Label(resumen_frame, text="Método de pago:").grid(row=0, column=2, sticky='e', padx=10)
    metodo_pago = ttk.Combobox(resumen_frame, textvariable=metodo_pago_var,
                                values=["EFECTIVO", "TARJETA DÉBITO", "TARJETA CRÉDITO", "MERCADOPAGO"],
                                state="readonly", width=20)
    metodo_pago.grid(row=0, column=3, sticky='w')
    boton_frame = ttk.Frame(resumen_frame)
    boton_frame.grid(row=0, column=4, rowspan=3, padx=20)
    tk.Button(boton_frame, text="PAGAR", bg="green", fg="white", font=('Segoe UI', 14, 'bold'), width=15, height=2, command=finalizar_venta).pack(pady=5)
    tk.Button(boton_frame, text="CANCELAR", bg="red", fg="white", font=('Segoe UI', 12, 'bold'), width=15, command=cancelar_venta).pack(pady=5)

    ventana.bind('<Return>', lambda e: agregar_producto())
    ventana.bind('<F1>', finalizar_venta)
    ventana.bind('<Escape>', cancelar_venta)
    ventana.bind('<F5>', eliminar_item)

    ventana.mainloop()
