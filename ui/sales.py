import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import os
import sys
from fpdf import FPDF
from db_init import get_db_path, get_base_dir
from fiscal_service import get_fiscal_config, emitir_o_encolar

sales_window_open = False


def open_sales_panel(user_id, user_name):
    global sales_window_open
    if sales_window_open:
        messagebox.showinfo("Ventana abierta", "Ya hay una ventana de venta abierta.")
        return
    sales_window_open = True

    try:
        conn = sqlite3.connect(get_db_path())
    except sqlite3.Error as e:
        messagebox.showerror("Error BD", "No se pudo conectar con la base de datos.\n" + str(e))
        sales_window_open = False
        return
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

    def agregar_articulo_manual():
        top = tk.Toplevel(ventana)
        top.title("Articulo manual")
        top.transient(ventana)
        top.grab_set()
        ttk.Label(top, text="Nombre:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        nombre_var = tk.StringVar(value="ART")
        ttk.Entry(top, textvariable=nombre_var, width=24).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(top, text="Precio:").grid(row=1, column=0, padx=6, pady=6, sticky="e")
        precio_var = tk.StringVar(value="")
        precio_entry = ttk.Entry(top, textvariable=precio_var, width=24)
        precio_entry.grid(row=1, column=1, padx=6, pady=6)
        precio_entry.focus_set()

        def aceptar():
            nombre = (nombre_var.get() or "ART").strip()
            try:
                precio = float((precio_var.get() or "0").replace(",", "."))
                if precio <= 0:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Manual", "Precio invalido.", parent=top)
                return
            productos_vendidos.append({
                'id': None, 'codigo': 'ART', 'nombre': nombre, 'precio': round(precio, 2)
            })
            actualizar_ticket()
            top.destroy()
            codigo_entry.delete(0, tk.END)
            codigo_entry.focus_set()

        ttk.Button(top, text="Agregar", command=aceptar).grid(row=2, column=0, pady=8)
        ttk.Button(top, text="Cancelar", command=top.destroy).grid(row=2, column=1, pady=8)
        top.bind('<Return>', lambda e: aceptar())
        top.wait_window()

    def agregar_producto():
        codigo = codigo_entry.get().strip()
        if not codigo:
            return
        if codigo.upper() in ("ART", "MANUAL", "0"):
            agregar_articulo_manual()
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
            if messagebox.askyesno(
                "Producto no encontrado",
                "No existe en stock.\nDesea cargarlo como articulo manual?",
                parent=ventana,
            ):
                agregar_articulo_manual()
            else:
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

    def pedir_tipo_comprobante():
        top = tk.Toplevel(ventana)
        top.title("Tipo de comprobante")
        top.transient(ventana)
        top.grab_set()
        data = {"tipo": "B", "cliente_doc": "", "cliente_nombre": ""}

        ttk.Label(top, text="Seleccione tipo fiscal").grid(row=0, column=0, columnspan=2, pady=10)
        tipo_var = tk.StringVar(value="B")
        ttk.Radiobutton(top, text="Ticket / Factura B", variable=tipo_var, value="B").grid(row=1, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(top, text="Factura A", variable=tipo_var, value="A").grid(row=2, column=0, columnspan=2, sticky="w", padx=10)

        ttk.Label(top, text="CUIT cliente (solo A):").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        doc_entry = ttk.Entry(top, width=25)
        doc_entry.grid(row=3, column=1, padx=5, pady=4)
        ttk.Label(top, text="Razon social cliente (solo A):").grid(row=4, column=0, sticky="e", padx=5, pady=4)
        nombre_entry = ttk.Entry(top, width=25)
        nombre_entry.grid(row=4, column=1, padx=5, pady=4)

        def aceptar():
            data["tipo"] = tipo_var.get()
            data["cliente_doc"] = doc_entry.get().strip()
            data["cliente_nombre"] = nombre_entry.get().strip()
            if data["tipo"] == "A" and (not data["cliente_doc"] or not data["cliente_nombre"]):
                messagebox.showwarning("Fiscal", "Para Factura A completá CUIT y razón social.", parent=top)
                return
            top.destroy()

        ttk.Button(top, text="Aceptar", command=aceptar).grid(row=5, column=0, pady=10)
        ttk.Button(top, text="Cancelar", command=lambda: data.update(tipo="") or top.destroy()).grid(row=5, column=1, pady=10)
        top.wait_window()
        return data

    def _wrap_line(texto, max_chars):
        t = (texto or "").strip()
        if len(t) <= max_chars:
            return [t]
        partes = []
        actual = ""
        for palabra in t.split(" "):
            nuevo = (actual + " " + palabra).strip()
            if len(nuevo) <= max_chars:
                actual = nuevo
            else:
                if actual:
                    partes.append(actual)
                actual = palabra
        if actual:
            partes.append(actual)
        return partes or [t[:max_chars]]

    def _linea_item(nombre, cantidad, precio, ancho_chars):
        base = "%s x %s" % (cantidad, nombre)
        monto = "$%.2f" % precio
        espacio = max(1, ancho_chars - len(base) - len(monto))
        if len(base) + len(monto) + 1 <= ancho_chars:
            return base + (" " * espacio) + monto
        rec = _wrap_line(base, max(8, ancho_chars - len(monto) - 1))
        if len(rec) == 1:
            return rec[0] + " " + monto
        return rec[0] + "\n" + rec[1][:max(8, ancho_chars - len(monto) - 1)] + " " + monto

    def generar_comprobante(venta_id, total, fiscal_info=None):
        cfg = get_fiscal_config()
        comprobantes_dir = os.path.join(get_base_dir(), "comprobantes")
        if not os.path.exists(comprobantes_dir):
            os.makedirs(comprobantes_dir)
        fecha = datetime.now().strftime("%d%m%Y")
        nombre_archivo = os.path.join(comprobantes_dir, "%s_%06d.pdf" % (fecha, venta_id))
        ancho_mm = 58
        try:
            ancho_mm = int(cfg.get("ticket_ancho_mm") or "58")
        except Exception:
            pass
        ancho_chars = 32 if ancho_mm <= 58 else 42
        pdf = FPDF(unit="mm", format=(ancho_mm, 220))
        pdf.add_page()
        pdf.set_font("Arial", size=8)
        logo_path = (cfg.get("ticket_logo_path") or "").strip()
        incluir_logo = (cfg.get("ticket_incluir_logo") or "1") == "1"
        if incluir_logo and logo_path and os.path.exists(logo_path):
            try:
                pdf.image(logo_path, x=3, w=ancho_mm - 6)
                pdf.ln(14)
            except Exception:
                pass
        pdf.set_font("Arial", "B", 9)
        pdf.cell(ancho_mm - 4, 5, txt=(cfg.get("empresa_razon_social") or "Comercio"), ln=1, align='C')
        pdf.set_font("Arial", size=8)
        if cfg.get("empresa_cuit"):
            pdf.cell(ancho_mm - 4, 4, txt="CUIT: %s" % cfg.get("empresa_cuit"), ln=1, align='C')
        pdf.cell(ancho_mm - 4, 4, txt="Ticket #%06d" % venta_id, ln=1, align='C')
        pdf.cell(ancho_mm - 4, 4, txt=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), ln=1, align='C')
        pdf.ln(3)
        subtotal = 0
        for p in productos_vendidos:
            if p['codigo'] != '105':
                linea = _linea_item(p['nombre'], 1, p['precio'], ancho_chars)
                pdf.multi_cell(ancho_mm - 4, 4, txt=linea, align='L')
                subtotal += p['precio']
            else:
                pdf.multi_cell(ancho_mm - 4, 4, txt=p['nombre'], align='L')
        pdf.ln(2)
        pdf.set_font("Arial", 'B', size=10)
        pdf.cell(ancho_mm - 4, 5, txt="SUBTOTAL: $%.2f" % subtotal, ln=1, align='R')
        if descuento_activo.get():
            descuento = round(subtotal * 0.10, 2)
            pdf.cell(ancho_mm - 4, 5, txt="DESCUENTO: -$%.2f" % descuento, ln=1, align='R')
        pdf.cell(ancho_mm - 4, 6, txt="TOTAL: $%.2f" % float(total_var.get()), ln=1, align='R')
        pdf.ln(2)
        pdf.set_font("Arial", size=8)
        pdf.cell(ancho_mm - 4, 4, txt="Pago: %s" % metodo_pago_var.get(), ln=1, align='L')
        if fiscal_info:
            pdf.cell(ancho_mm - 4, 4, txt="Fiscal: %s" % fiscal_info.get("estado", ""), ln=1, align='L')
            if fiscal_info.get("cae"):
                pdf.cell(ancho_mm - 4, 4, txt="CAE: %s" % fiscal_info["cae"], ln=1, align='L')
        pie = (cfg.get("ticket_pie_texto") or "").strip()
        if pie:
            pdf.ln(2)
            pdf.multi_cell(ancho_mm - 4, 4, txt=pie, align='C')
        pdf.output(nombre_archivo)
        return nombre_archivo

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
            fiscal_info = None
            emitir_fiscal = messagebox.askyesno(
                "Comprobante fiscal",
                "Desea emitir comprobante fiscal ARCA para esta venta?",
                parent=ventana,
            )
            if emitir_fiscal:
                data_tipo = pedir_tipo_comprobante()
                if data_tipo.get("tipo"):
                    payload = {
                        "venta_id": venta_id,
                        "fecha": fecha,
                        "total": total,
                        "metodo_pago": metodo_pago,
                        "tipo_comprobante": data_tipo["tipo"],
                        "cliente_doc": data_tipo.get("cliente_doc", ""),
                        "cliente_nombre": data_tipo.get("cliente_nombre", ""),
                        "items": [
                            {
                                "codigo": p["codigo"],
                                "nombre": p["nombre"],
                                "precio": p["precio"],
                                "cantidad": 1,
                            }
                            for p in productos_vendidos
                            if p["codigo"] != "105"
                        ],
                    }
                    c.execute(
                        "UPDATE ventas SET fiscal_solicitado=1, fiscal_tipo=?, fiscal_estado='EN_PROCESO' WHERE id=?",
                        (data_tipo["tipo"], venta_id),
                    )
                    conn.commit()
                    ok_fiscal, res_fiscal = emitir_o_encolar(venta_id, payload)
                    if ok_fiscal:
                        fiscal_info = {"estado": "EMITIDO", "cae": res_fiscal.get("cae", "")}
                        mostrar_popup("Fiscal", "Comprobante fiscal emitido OK.")
                    else:
                        fiscal_info = {"estado": "PENDIENTE"}
                        mostrar_popup("Fiscal", "No se pudo emitir ahora. Quedo en pendientes ARCA.")
                else:
                    c.execute(
                        "UPDATE ventas SET fiscal_solicitado=0, fiscal_estado='NO_SOLICITADO' WHERE id=?",
                        (venta_id,),
                    )
                    conn.commit()
            else:
                c.execute(
                    "UPDATE ventas SET fiscal_solicitado=0, fiscal_estado='NO_SOLICITADO' WHERE id=?",
                    (venta_id,),
                )
                conn.commit()
            try:
                pdf_path = generar_comprobante(venta_id, total, fiscal_info=fiscal_info)
            except Exception as e:
                messagebox.showwarning(
                    "Comprobante",
                    "Venta registrada correctamente.\nNo se pudo guardar el PDF: %s" % str(e),
                    parent=ventana,
                )
            else:
                mostrar_popup("Éxito", "Venta registrada\nTotal: $%s\nMétodo: %s" % (("%.2f" % total), metodo_pago))
                auto_print = (cfg.get("ticket_auto_imprimir") or "0") == "1"
                desea_imprimir = auto_print or messagebox.askyesno(
                    "Impresion",
                    "Desea imprimir ticket ahora?",
                    parent=ventana,
                )
                if desea_imprimir:
                    try:
                        if sys.platform.startswith("win"):
                            os.startfile(pdf_path, "print")
                        else:
                            raise RuntimeError("Impresion directa solo soportada en Windows")
                    except Exception as e:
                        messagebox.showwarning("Impresion", "No se pudo enviar a impresora:\n%s" % str(e), parent=ventana)
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
    ttk.Button(input_frame, text="Manual", command=agregar_articulo_manual).grid(row=0, column=3, padx=4)

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
    ventana.bind('<F2>', lambda e: agregar_articulo_manual())
    ventana.bind('<Escape>', cancelar_venta)
    ventana.bind('<F5>', eliminar_item)

    ventana.mainloop()
