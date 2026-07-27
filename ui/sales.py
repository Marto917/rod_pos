import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import os
import sys
import json
import base64
from fpdf import FPDF
from db_init import get_db_path, get_base_dir
from fiscal_service import get_fiscal_config, emitir_o_encolar
from pos_config import is_client_mode, load_config
from services.stock_ops import StockError, create_sale, get_product_by_barcode


sales_window_open = False


def open_sales_panel(user_id, user_name):
    global sales_window_open
    if sales_window_open:
        messagebox.showinfo("Ventana abierta", "Ya hay una ventana de venta abierta.")
        return
    sales_window_open = True

    try:
        from db import get_connection
        conn = get_connection()
    except Exception as e:
        messagebox.showerror("Error BD", "No se pudo conectar con la base de datos.\n" + str(e))
        sales_window_open = False
        return
    c = conn.cursor()
    cfg_pos = load_config()

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
    cliente_doc_var = tk.StringVar(value="")
    cliente_nombre_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Elegí tipo de ticket · F1 manual · F5 efectivo")
    cobrando = {"activo": False}
    metodo_btns = {}
    tipo_sesion = {"modo": None, "cliente_doc": "", "cliente_nombre": ""}

    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TLabel', background='#eaeaea', font=('Segoe UI', 11))
    style.configure('TButton', font=('Segoe UI', 11, 'bold'))
    style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
    style.configure('Discount.TLabel', foreground='red')

    def flash_status(msg, ok=True):
        status_var.set(msg)
        try:
            status_lbl.configure(fg="#166534" if ok else "#b91c1c")
        except Exception:
            pass
        ventana.after(3500, lambda: status_var.set("F1 manual · F5 efectivo · F6 tarjeta · F7 Mercado Pago"))

    def limpiar_cliente():
        cliente_doc_var.set("")
        cliente_nombre_var.set("")
        try:
            cliente_resumen_var.set("Cliente: Consumidor Final")
        except Exception:
            pass

    def mostrar_popup(titulo, mensaje):
        """Solo para errores importantes; el cobro normal no bloquea con popups."""
        popup = tk.Toplevel(ventana)
        popup.title(titulo)
        popup.transient(ventana)
        popup.grab_set()
        popup.configure(bg="white")
        ttk.Label(popup, text=mensaje, font=('Segoe UI', 11), padding=15, wraplength=420).pack()
        btn = ttk.Button(popup, text="OK", command=popup.destroy)
        btn.pack(pady=10)
        popup.bind('<Return>', lambda e: popup.destroy())
        popup.bind('<Escape>', lambda e: popup.destroy())
        btn.focus_set()
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
        try:
            cobrar_btn.configure(text="COBRAR  $%s" % total_var.get())
        except Exception:
            pass

    def precio_para_metodo(prod_data, metodo):
        if metodo == "TARJETA":
            return float(prod_data.get("precio_lista", prod_data.get("precio", 0)))
        return float(prod_data.get("precio_publico", prod_data.get("precio", 0)))

    def recalcular_precios_por_metodo():
        metodo = metodo_pago_var.get()
        for p in productos_vendidos:
            if p.get("id") and p.get("codigo") not in ("105", "ART"):
                p["precio"] = precio_para_metodo(p, metodo)
        actualizar_ticket()

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

    def abrir_ajuste_caja():
        from services.ajuste_caja import METODOS_AJUSTE, registrar_ajuste

        top = tk.Toplevel(ventana)
        top.title("Ajuste de caja")
        top.transient(ventana)
        top.grab_set()
        top.resizable(False, False)

        ttk.Label(top, text="Corregir forma de pago", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(12, 8), sticky="w"
        )
        ttk.Label(top, text="Monto ($):").grid(row=1, column=0, padx=14, pady=6, sticky="w")
        monto_entry = ttk.Entry(top, width=18)
        monto_entry.grid(row=1, column=1, padx=14, pady=6, sticky="w")
        monto_entry.focus_set()

        metodos = list(METODOS_AJUSTE)
        ttk.Label(top, text="Sacar de:").grid(row=2, column=0, padx=14, pady=6, sticky="w")
        desde_var = tk.StringVar(value="EFECTIVO")
        ttk.Combobox(top, textvariable=desde_var, values=metodos, state="readonly", width=16).grid(
            row=2, column=1, padx=14, pady=6, sticky="w"
        )

        ttk.Label(top, text="Poner en:").grid(row=3, column=0, padx=14, pady=6, sticky="w")
        hacia_var = tk.StringVar(value="TARJETA")
        ttk.Combobox(top, textvariable=hacia_var, values=metodos, state="readonly", width=16).grid(
            row=3, column=1, padx=14, pady=6, sticky="w"
        )

        ttk.Label(top, text="Observaciones:").grid(row=4, column=0, padx=14, pady=6, sticky="w")
        obs_entry = ttk.Entry(top, width=28)
        obs_entry.grid(row=4, column=1, padx=14, pady=6, sticky="w")

        def confirmar():
            raw = (monto_entry.get() or "").strip().replace(",", ".")
            try:
                monto = float(raw)
            except ValueError:
                messagebox.showwarning("Ajuste", "Monto inválido.", parent=top)
                return
            try:
                result = registrar_ajuste(
                    usuario_id=user_id,
                    user_name=user_name,
                    monto=monto,
                    metodo_desde=desde_var.get(),
                    metodo_hacia=hacia_var.get(),
                    observaciones=obs_entry.get().strip(),
                )
            except Exception as e:
                messagebox.showerror("Ajuste", str(e), parent=top)
                return
            pdf_path = result.get("pdf_path")
            if pdf_path:
                try:
                    os.startfile(pdf_path, "print")
                except Exception:
                    try:
                        os.startfile(pdf_path)
                    except Exception:
                        pass
            messagebox.showinfo(
                "Ajuste OK",
                "Ajuste #%s registrado.\n$%.2f de %s → %s\n\nPDF guardado."
                % (
                    result.get("ajuste_id"),
                    result.get("monto") or monto,
                    result.get("metodo_desde"),
                    result.get("metodo_hacia"),
                ),
                parent=ventana,
            )
            top.destroy()
            codigo_entry.delete(0, tk.END)
            codigo_entry.focus_set()

        ttk.Button(top, text="Registrar e imprimir", command=confirmar).grid(
            row=5, column=0, pady=12, padx=14
        )
        ttk.Button(top, text="Cancelar", command=top.destroy).grid(row=5, column=1, pady=12, padx=14)
        top.bind("<Return>", lambda e: confirmar())
        top.wait_window()

    def agregar_producto():
        codigo = codigo_entry.get().strip()
        if not codigo:
            return
        from services.ajuste_caja import es_codigo_ajuste

        if es_codigo_ajuste(codigo):
            codigo_entry.delete(0, tk.END)
            abrir_ajuste_caja()
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

        prod = get_product_by_barcode(codigo)
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
        if int(prod.get("cantidad") or 0) < 1:
            mostrar_popup("Sin stock", "No hay stock disponible")
            return

        productos_vendidos.append({
            'id': prod["id"],
            'codigo': codigo,
            'nombre': prod["nombre"],
            'precio_lista': float(prod["precio_lista"]),
            'precio_publico': float(prod["precio_publico"]),
            'precio': float(prod["precio_publico"]),
        })
        productos_vendidos[-1]["precio"] = precio_para_metodo(productos_vendidos[-1], metodo_pago_var.get())
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
        limpiar_cliente()
        actualizar_ticket()
        resaltar_metodo()
        codigo_entry.focus_set()

    def elegir_tipo_comprobante(obligatorio=True):
        """Cartel fullscreen: Factura C o Ticket interno. Al entrar y tras cada venta."""
        top = tk.Toplevel(ventana)
        top.title("Tipo de ticket")
        top.transient(ventana)
        top.grab_set()
        try:
            top.state("zoomed")
        except Exception:
            try:
                top.attributes("-fullscreen", True)
            except Exception:
                top.geometry("1200x800")
        top.configure(bg="#0f172a")
        resultado = {"ok": False}

        wrap = tk.Frame(top, bg="#0f172a")
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            wrap,
            text="Que tipo de ticket vas a emitir?",
            font=("Segoe UI", 28, "bold"),
            bg="#0f172a",
            fg="#f8fafc",
        ).pack(pady=(0, 8))
        tk.Label(
            wrap,
            text="Elegi primero. Despues escaneas y cobras.",
            font=("Segoe UI", 14),
            bg="#0f172a",
            fg="#94a3b8",
        ).pack(pady=(0, 24))

        modo_var = tk.StringVar(value="")
        form_cliente = tk.Frame(wrap, bg="#1e293b", padx=20, pady=16)

        tk.Label(
            form_cliente,
            text="Datos del cliente (Factura C)",
            font=("Segoe UI", 13, "bold"),
            bg="#1e293b",
            fg="#f8fafc",
        ).pack(anchor="w")
        tk.Label(
            form_cliente,
            text="Si no pone DNI/CUIT = Consumidor Final",
            font=("Segoe UI", 10),
            bg="#1e293b",
            fg="#94a3b8",
        ).pack(anchor="w", pady=(0, 8))

        fila = tk.Frame(form_cliente, bg="#1e293b")
        fila.pack(fill="x", pady=4)
        tk.Label(fila, text="DNI o CUIT:", bg="#1e293b", fg="#e2e8f0", width=14, anchor="e").pack(side="left")
        doc_e = tk.Entry(fila, width=28, font=("Segoe UI", 14))
        doc_e.pack(side="left", padx=6)

        fila2 = tk.Frame(form_cliente, bg="#1e293b")
        fila2.pack(fill="x", pady=4)
        tk.Label(fila2, text="Nombre:", bg="#1e293b", fg="#e2e8f0", width=14, anchor="e").pack(side="left")
        nom_e = tk.Entry(fila2, width=28, font=("Segoe UI", 14))
        nom_e.pack(side="left", padx=6)

        def mostrar_form(mostrar):
            if mostrar:
                form_cliente.pack(fill="x", pady=16)
                doc_e.focus_set()
            else:
                form_cliente.pack_forget()

        def elegir_c(event=None):
            modo_var.set("factura_c")
            btn_c.configure(relief="sunken", bd=6)
            btn_t.configure(relief="raised", bd=2)
            mostrar_form(True)

        def elegir_t(event=None):
            modo_var.set("interno")
            btn_t.configure(relief="sunken", bd=6)
            btn_c.configure(relief="raised", bd=2)
            mostrar_form(False)

        btns = tk.Frame(wrap, bg="#0f172a")
        btns.pack(pady=12)
        btn_c = tk.Button(
            btns,
            text="FACTURA C\nAtajo: tecla C",
            bg="#2563eb",
            fg="white",
            font=("Segoe UI", 18, "bold"),
            width=22,
            height=4,
            command=elegir_c,
        )
        btn_c.pack(side="left", padx=16)
        btn_t = tk.Button(
            btns,
            text="TICKET INTERNO\nAtajo: tecla T",
            bg="#64748b",
            fg="white",
            font=("Segoe UI", 18, "bold"),
            width=22,
            height=4,
            command=elegir_t,
        )
        btn_t.pack(side="left", padx=16)

        def confirmar(event=None):
            modo = modo_var.get()
            if not modo:
                messagebox.showwarning(
                    "Elegi una opcion",
                    "Toca FACTURA C (tecla C) o TICKET INTERNO (tecla T).",
                    parent=top,
                )
                return
            if modo == "factura_c":
                doc = "".join(ch for ch in doc_e.get() if ch.isdigit())
                nom = nom_e.get().strip()
                if doc and not (7 <= len(doc) <= 8 or len(doc) == 11):
                    messagebox.showwarning("Cliente", "DNI (7-8) o CUIT (11 digitos).", parent=top)
                    return
                if doc and not nom:
                    messagebox.showwarning("Cliente", "Si hay DNI/CUIT, pone el nombre.", parent=top)
                    return
                if nom and not doc:
                    messagebox.showwarning("Cliente", "Si hay nombre, pone DNI o CUIT.", parent=top)
                    return
                tipo_sesion["cliente_doc"] = doc
                tipo_sesion["cliente_nombre"] = nom
                cliente_doc_var.set(doc)
                cliente_nombre_var.set(nom)
                if doc:
                    cliente_resumen_var.set("Cliente: %s · %s" % (nom, doc))
                else:
                    cliente_resumen_var.set("Cliente: Consumidor Final · Factura C")
            else:
                tipo_sesion["cliente_doc"] = ""
                tipo_sesion["cliente_nombre"] = ""
                limpiar_cliente()
                cliente_resumen_var.set("Ticket interno (sin factura)")
            tipo_sesion["modo"] = modo
            resultado["ok"] = True
            top.destroy()
            flash_status(
                "Listo: %s · ahora escanea y cobra" % ("Factura C" if modo == "factura_c" else "Ticket interno"),
                ok=True,
            )
            codigo_entry.focus_set()

        def cancelar(event=None):
            if obligatorio and tipo_sesion.get("modo") is None:
                if not messagebox.askyesno(
                    "Salir",
                    "Sin tipo de ticket no se puede vender.\nCerrar la ventana de venta?",
                    parent=top,
                ):
                    return
                top.destroy()
                al_cerrar()
                return
            top.destroy()

        acciones = tk.Frame(wrap, bg="#0f172a")
        acciones.pack(pady=28)
        tk.Button(
            acciones,
            text="CONFIRMAR  (Enter)",
            bg="#16a34a",
            fg="white",
            font=("Segoe UI", 16, "bold"),
            width=24,
            height=2,
            command=confirmar,
        ).pack(side="left", padx=10)
        tk.Button(
            acciones,
            text="Cancelar (Esc)",
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=16,
            height=2,
            command=cancelar,
        ).pack(side="left", padx=10)

        tk.Label(
            wrap,
            text="Atajos: C = Factura C   |   T = Ticket interno   |   Enter = Confirmar",
            font=("Segoe UI", 12),
            bg="#0f172a",
            fg="#64748b",
        ).pack(pady=(8, 0))

        top.bind("c", elegir_c)
        top.bind("C", elegir_c)
        top.bind("t", elegir_t)
        top.bind("T", elegir_t)
        top.bind("<Return>", confirmar)
        top.bind("<Escape>", cancelar)
        top.protocol("WM_DELETE_WINDOW", cancelar)
        elegir_c()
        top.wait_window()
        return resultado["ok"]

    def generar_comprobante(venta_id, total, fiscal_info=None):
        try:
            cfg = get_fiscal_config() or {}
        except Exception as e_cfg:
            print("[PDF DEBUG] Error leyendo config fiscal: %r" % e_cfg, flush=True)
            cfg = {}
        debug_marker = "DBG-TKT-20260506-1615"
        debug_ticket_path = os.path.join(get_base_dir(), "debug_ticket.txt")

        def _log_ticket_debug(msg):
            try:
                with open(debug_ticket_path, "a", encoding="utf-8", errors="replace") as fdbg:
                    fdbg.write("%s | %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
            except Exception:
                pass
        comprobantes_dir = os.path.join(get_base_dir(), "comprobantes")
        if not os.path.exists(comprobantes_dir):
            os.makedirs(comprobantes_dir)

        fecha_arch = datetime.now().strftime("%d%m%Y")
        nombre_archivo = os.path.join(comprobantes_dir, "%s_%06d.pdf" % (fecha_arch, venta_id))
        _log_ticket_debug("%s generar_comprobante inicio venta_id=%s archivo=%s" % (debug_marker, venta_id, nombre_archivo))

        # Layout térmico 58mm, texto secuencial desde arriba (sin espacio en blanco inicial).
        ancho_mm = 58
        W = 32
        usable = 54.0
        line_h = 3.2

        def wrap32(texto):
            t = (texto or "").strip()
            if not t:
                return [""]
            out = []
            while t:
                out.append(t[:W])
                t = t[W:]
            return out

        def center32(texto):
            return (texto or "")[:W].center(W)

        def pad32(texto):
            return (texto or "")[:W].ljust(W)

        def _safe_txt(v, default="-"):
            try:
                t = str(v if v is not None else "")
            except Exception:
                t = ""
            t = t.replace("\r", " ").replace("\n", " ").strip()
            return t if t else default

        razon = _safe_txt(cfg.get("empresa_razon_social"), "HECTOR RICARDO RODRIGUEZ").upper()
        cuit = _safe_txt(cfg.get("empresa_cuit"), "NO CONFIG")
        iibb = _safe_txt(cfg.get("empresa_iibb"), "NO CONFIG")
        inicio_act = _safe_txt(cfg.get("empresa_inicio_actividades"), "-")
        pto_raw = str((fiscal_info or {}).get("pto_vta") or (cfg.get("arca_punto_venta") or "4"))
        pto_digits = "".join(ch for ch in pto_raw if ch.isdigit()) or "4"
        pto = pto_digits.zfill(4)
        nro_factura = str((fiscal_info or {}).get("numero") or ("%06d" % venta_id)).zfill(8)
        cae = (fiscal_info or {}).get("cae", "")
        vto_cae = (fiscal_info or {}).get("vto_cae", "")
        print(
            "[PDF DEBUG] CAE=%r | nro_factura=%r | CUIT=%r | IIBB=%r"
            % (cae, nro_factura, cuit, iibb),
            flush=True,
        )
        _log_ticket_debug(
            "%s datos CAE=%r nro=%r CUIT=%r IIBB=%r"
            % (debug_marker, cae, nro_factura, cuit, iibb)
        )

        fecha_now = datetime.now()
        fecha_h = fecha_now.strftime("%d/%m/%Y")
        hora_h = fecha_now.strftime("%H:%M")

        items_ok = []
        subtotal = 0.0
        for p in productos_vendidos:
            if p.get("codigo") == "105":
                continue
            cant = 1
            precio = float(p.get("precio", 0.0))
            sub = round(cant * precio, 2)
            subtotal += sub
            items_ok.append((cant, precio, sub, (p.get("nombre") or "").strip()))
        try:
            total_num = float(str(total_var.get()).replace(",", "."))
        except Exception:
            total_num = float(total or 0.0)

        es_negro = bool((fiscal_info or {}).get("ticket_negro"))
        titulo_cmp = "TICKET INTERNO" if es_negro else "FACTURA C (Cod. 011)"

        lineas = [
            center32(razon),
            center32("CUIT: %s" % cuit),
            center32("IIBB: %s" % iibb),
            center32("Inicio actividades: %s" % inicio_act),
            center32("IVA RESPONSABLE MONOTRIBUTO"),
            "=" * W,
            center32(titulo_cmp),
            pad32("P.Vta: %s | Nro: %s" % (pto, nro_factura)),
            pad32("Fecha: %s | Hora: %s" % (fecha_h, hora_h)),
            "-" * W,
        ]

        cli_nom = _safe_txt((fiscal_info or {}).get("cliente_nombre"), "")
        cli_doc = "".join(
            ch for ch in str((fiscal_info or {}).get("cliente_doc") or "") if ch.isdigit()
        )
        if not es_negro:
            if cli_nom and cli_nom != "-":
                lineas.append(pad32("CLIENTE:"))
                for ln_cli in wrap32(cli_nom):
                    lineas.append(pad32(ln_cli))
                if cli_doc:
                    label_doc = "CUIT" if len(cli_doc) == 11 else "DNI"
                    lineas.append(pad32("%s: %s" % (label_doc, cli_doc)))
                lineas.append("-" * W)
            else:
                lineas.append(pad32("Cliente: Consumidor Final"))
                lineas.append("-" * W)

        if not items_ok:
            lineas.append(pad32("1 x PRODUCTO PRUEBA ....... $10.00"))
            lineas.append("-" * W)
        else:
            for cant, precio, sub, nombre in items_ok:
                lineas.append(pad32("%d x %.2f | %.2f" % (cant, precio, sub)))
                for ln_nom in wrap32(nombre or "ARTICULO"):
                    lineas.append(pad32(ln_nom))
                lineas.append("-" * W)

        lineas.append(pad32("TOTAL: $%.2f" % total_num))
        lineas.append("=" * W)
        if es_negro:
            lineas.append(center32("Comprobante interno"))
            lineas.append(center32("Sin CAE / no fiscal"))
        else:
            lineas.append(pad32("CAE: %s" % (cae if str(cae).strip() else "VACIO")))
            lineas.append(pad32("Vto. CAE: %s" % (vto_cae if str(vto_cae).strip() else "-")))

        logo_path = (cfg.get("ticket_logo_path") or "").strip()
        has_logo = ((cfg.get("ticket_incluir_logo") or "0") == "1") and bool(logo_path) and os.path.isfile(logo_path)
        include_qr = (not es_negro) and bool(
            str(cae).strip() and str((fiscal_info or {}).get("numero") or "").strip()
        )

        # Alto dinámico exacto para cortar al final del ticket (solo ~1cm de margen inferior).
        logo_h = 11.0 if has_logo else 0.0
        qr_h = 15.0 if include_qr else 0.0
        altura_final = (len(lineas) * line_h) + logo_h + qr_h + 10.0
        page_h = max(140.0, min(500.0, altura_final))

        try:
            pdf = FPDF(unit="mm", format=(ancho_mm, page_h))
            pdf.set_margins(2, 2, 2)
            pdf.set_auto_page_break(False)
            pdf.add_page()
            pdf.set_xy(2, 2)

            if has_logo:
                try:
                    size_logo = 10.0
                    x_logo = (ancho_mm - size_logo) / 2.0
                    y_logo = pdf.get_y()
                    pdf.image(logo_path, x=x_logo, y=y_logo, w=size_logo, h=size_logo)
                    pdf.set_y(y_logo + size_logo + 1.0)
                except Exception:
                    pdf.set_font("Courier", "", 7)
                    pdf.multi_cell(usable, line_h, "LOGO NO DISPONIBLE", align="C")

            # Render robusto: dibujado línea por línea con coordenada Y manual.
            y_inicio_texto = pdf.get_y()
            y_text = y_inicio_texto + 2.4
            lineas_impresas = 0
            for ln in lineas:
                es_total = ln.strip().startswith("TOTAL:")
                es_titulo = "FACTURA C" in ln or "TICKET INTERNO" in ln or ln.strip() == razon[:W]
                pdf.set_font("Courier", "B" if (es_total or es_titulo) else "", 7)
                pdf.set_text_color(0, 0, 0)
                pdf.text(2.0, y_text, ln[:W])
                y_text += line_h
                lineas_impresas += 1

            y_fin_texto = y_text
            pdf.set_y(y_fin_texto)
            print(
                "[PDF DEBUG] y_inicio_texto=%.2f | y_fin_texto=%.2f | lineas_impresas=%d"
                % (y_inicio_texto, y_fin_texto, lineas_impresas),
                flush=True,
            )
            _log_ticket_debug(
                "%s y0=%.2f y1=%.2f lineas=%d"
                % (debug_marker, y_inicio_texto, y_fin_texto, lineas_impresas)
            )

            # Debug visible en ticket: confirma que el bloque de texto se intentó renderizar.
            pdf.set_font("Courier", "", 6)
            pdf.set_text_color(0, 0, 0)
            pdf.text(
                2.0,
                y_fin_texto + 2.4,
                ("DEBUG TXT y0=%.1f y1=%.1f n=%d" % (y_inicio_texto, y_fin_texto, lineas_impresas))[:W],
            )
            pdf.set_y(y_fin_texto + 2.8)

            # Si por algun motivo no avanzó el cursor, forzar texto de rescate.
            if y_fin_texto <= (y_inicio_texto + 0.2):
                pdf.set_font("Courier", "B", 7)
                pdf.text(2.0, pdf.get_y() + 2.4, "DEBUG: BLOQUE TEXTO NO AVANZO"[:W])
                pdf.text(2.0, pdf.get_y() + 2.4 + line_h, ("CUIT: %s" % cuit)[:W])
                pdf.text(2.0, pdf.get_y() + 2.4 + (line_h * 2), ("IIBB: %s" % iibb)[:W])
                pdf.set_y(pdf.get_y() + (line_h * 3))

            # QR chico y centrado; si falla, no rompe el comprobante.
            if include_qr:
                try:
                    import qrcode

                    qr_data = {
                        "ver": 1,
                        "fecha": fecha_now.strftime("%Y-%m-%d"),
                        "cuit": int("".join(ch for ch in cuit if ch.isdigit()) or "0"),
                        "ptoVta": int((fiscal_info or {}).get("pto_vta") or pto),
                        "tipoCmp": 11,
                        "nroCmp": int((fiscal_info or {}).get("numero") or nro_factura),
                        "importe": round(total_num, 2),
                        "moneda": "PES",
                        "ctz": 1,
                        "tipoDocRec": int((fiscal_info or {}).get("tipo_doc_rec") or (80 if len(cli_doc) == 11 else (96 if cli_doc else 99))),
                        "nroDocRec": int(cli_doc or 0),
                        "tipoCodAut": "E",
                        "codAut": int(str(cae).strip()),
                    }
                    qr_json = json.dumps(qr_data, separators=(",", ":"))
                    qr_b64 = base64.b64encode(qr_json.encode("utf-8")).decode("ascii")
                    qr_url = "https://www.afip.gob.ar/fe/qr/?p=%s" % qr_b64

                    qr = qrcode.QRCode(version=1, box_size=2, border=1)
                    qr.add_data(qr_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    qr_path = os.path.join(comprobantes_dir, "qr_%s_%06d.png" % (fecha_arch, venta_id))
                    img.save(qr_path)

                    size_qr = 14.0
                    x_qr = (ancho_mm - size_qr) / 2.0
                    y_qr = pdf.get_y() + 1.0
                    pdf.image(qr_path, x=x_qr, y=y_qr, w=size_qr, h=size_qr)
                    pdf.set_y(y_qr + size_qr + 1.0)
                except Exception:
                    pdf.set_font("Courier", "", 7)
                    pdf.multi_cell(usable, line_h, "QR NO DISPONIBLE", align="C")

            pdf.output(nombre_archivo)
            _log_ticket_debug("%s pdf generado OK: %s" % (debug_marker, nombre_archivo))
        except Exception as e_pdf:
            # Fallback de emergencia: ticket mínimo para no bloquear ventas.
            _log_ticket_debug("%s ERROR render principal: %r" % (debug_marker, e_pdf))
            pdf = FPDF(unit="mm", format=(58, 120))
            pdf.set_margins(2, 2, 2)
            pdf.set_auto_page_break(False)
            pdf.add_page()
            pdf.set_xy(2, 2)
            pdf.set_font("Courier", "B", 8)
            pdf.multi_cell(54, 3.2, "TICKET RECUPERADO", align="C")
            pdf.set_font("Courier", "", 7)
            pdf.multi_cell(54, 3.2, "Error render PDF: %s" % str(e_pdf)[:32], align="L")
            pdf.multi_cell(54, 3.2, "CUIT: %s" % cuit, align="L")
            pdf.multi_cell(54, 3.2, "IIBB: %s" % iibb, align="L")
            pdf.multi_cell(54, 3.2, "TOTAL: $%.2f" % total_num, align="L")
            pdf.output(nombre_archivo)
            _log_ticket_debug("%s pdf fallback generado: %s" % (debug_marker, nombre_archivo))
        return nombre_archivo

    def finalizar_venta(event=None):
        cobrar_con_metodo(metodo_pago_var.get())

    def cobrar_con_metodo(metodo, event=None):
        if cobrando["activo"]:
            flash_status("Ya se está cobrando… esperá", ok=False)
            return
        if not productos_vendidos:
            flash_status("No hay productos. Escaneá antes de cobrar.", ok=False)
            return

        if not tipo_sesion.get("modo"):
            flash_status("Primero elegi Factura C o Ticket interno.", ok=False)
            elegir_tipo_comprobante(obligatorio=False)
            if not tipo_sesion.get("modo"):
                return

        metodo_pago_var.set(metodo)
        recalcular_precios_por_metodo()
        resaltar_metodo()

        emitir_fiscal = tipo_sesion["modo"] == "factura_c"
        cli_doc = (tipo_sesion.get("cliente_doc") or "").strip()
        cli_nom = (tipo_sesion.get("cliente_nombre") or "").strip()

        total = float(total_var.get())
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cobrando["activo"] = True
        try:
            cobrar_btn.configure(state="disabled", text="COBRANDO…")
        except Exception:
            pass
        tipo_txt = "Factura C" if emitir_fiscal else "ticket interno"
        flash_status("Cobrando $%s (%s) · %s…" % (("%.2f" % total), metodo, tipo_txt), ok=True)
        ventana.update_idletasks()

        try:
            items = []
            for p in productos_vendidos:
                if p.get("id"):
                    items.append(
                        {
                            "producto_id": p["id"],
                            "id": p["id"],
                            "cantidad": 1,
                            "precio": p["precio"],
                        }
                    )
            sale = create_sale(
                usuario_id=user_id,
                total=total,
                metodo_pago=metodo,
                items=items,
                fecha=fecha,
            )
            venta_id = sale["venta_id"]

            cfg = get_fiscal_config()
            tipo_default = (cfg.get("fiscal_tipo_default") or "C").strip().upper() or "C"

            fiscal_info = {
                "ticket_negro": not emitir_fiscal,
                "cliente_doc": cli_doc,
                "cliente_nombre": cli_nom,
                "tipo_doc_rec": 80 if len(cli_doc) == 11 else (96 if cli_doc else 99),
                "nro_doc_rec": int(cli_doc) if cli_doc.isdigit() else 0,
            }
            forzar_no_imprimir = False

            if emitir_fiscal:
                payload = {
                    "venta_id": venta_id,
                    "fecha": fecha,
                    "total": total,
                    "metodo_pago": metodo,
                    "tipo_comprobante": tipo_default,
                    "cliente_doc": cli_doc,
                    "cliente_nombre": cli_nom,
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
                try:
                    if is_client_mode():
                        from services.stock_ops import enqueue_fiscal

                        fiscal_res = enqueue_fiscal(venta_id, payload)
                        ok_fiscal = bool(fiscal_res.get("ok"))
                        res_fiscal = fiscal_res.get("result") or {}
                    else:
                        c.execute(
                            "UPDATE ventas SET fiscal_solicitado=1, fiscal_tipo=?, fiscal_estado='EN_PROCESO' WHERE id=?",
                            (tipo_default, venta_id),
                        )
                        conn.commit()
                        ok_fiscal, res_fiscal = emitir_o_encolar(venta_id, payload)
                except Exception as e_fiscal:
                    ok_fiscal = False
                    res_fiscal = {"error": str(e_fiscal)}

                if ok_fiscal:
                    fiscal_info.update(
                        {
                            "estado": "EMITIDO",
                            "cae": res_fiscal.get("cae", ""),
                            "vto_cae": res_fiscal.get("vto_cae", ""),
                            "tipo": res_fiscal.get("tipo", tipo_default),
                            "numero": res_fiscal.get("numero", ""),
                            "pto_vta": res_fiscal.get("pto_vta", ""),
                            "cliente_doc": res_fiscal.get("cliente_doc") or cli_doc,
                            "cliente_nombre": res_fiscal.get("cliente_nombre") or cli_nom,
                            "tipo_doc_rec": res_fiscal.get("tipo_doc_rec") or fiscal_info["tipo_doc_rec"],
                            "nro_doc_rec": res_fiscal.get("nro_doc_rec") or fiscal_info["nro_doc_rec"],
                        }
                    )
                    if not (fiscal_info.get("cae") or "").strip():
                        forzar_no_imprimir = True
                        flash_status("Venta OK. Fiscal sin CAE → no se imprime (papel).", ok=False)
                else:
                    fiscal_info["estado"] = "PENDIENTE"
                    fiscal_info["tipo"] = tipo_default
                    err = (res_fiscal or {}).get("error", "")
                    if "WSAA" in err:
                        forzar_no_imprimir = True
                        flash_status("Venta OK. Error ARCA (WSAA). Ticket no impreso.", ok=False)
                    else:
                        flash_status("Venta OK. Fiscal pendiente ARCA.", ok=False)
            else:
                if not is_client_mode():
                    try:
                        c.execute(
                            "UPDATE ventas SET fiscal_solicitado=0, fiscal_estado='NO_SOLICITADO' WHERE id=?",
                            (venta_id,),
                        )
                        conn.commit()
                    except Exception:
                        pass

            # Siempre guardar PDF (factura o interno) en la misma carpeta comprobantes/
            pdf_path = None
            try:
                pdf_path = generar_comprobante(venta_id, total, fiscal_info=fiscal_info)
            except Exception as e:
                flash_status("Venta OK. Falló PDF: %s" % str(e)[:60], ok=False)

            # Solo se imprime en papel la factura fiscal; el ticket interno solo deja PDF.
            auto_print = (
                emitir_fiscal
                and (cfg.get("ticket_auto_imprimir") or "1") == "1"
                and not forzar_no_imprimir
            )
            if pdf_path and auto_print:
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(pdf_path, "print")
                    else:
                        raise RuntimeError("Impresión solo en Windows")
                except Exception as e:
                    flash_status("Venta OK. No se pudo imprimir: %s" % str(e)[:40], ok=False)

            if emitir_fiscal and not forzar_no_imprimir:
                flash_status(
                    "LISTO · $%s · %s · %s · #%s"
                    % (("%.2f" % total), metodo, tipo_txt, venta_id),
                    ok=True,
                )
            elif not emitir_fiscal:
                flash_status(
                    "LISTO · $%s · %s · ticket interno · PDF en comprobantes · #%s"
                    % (("%.2f" % total), metodo, venta_id),
                    ok=True,
                )
            resetear_ticket()
            tipo_sesion["modo"] = None
            tipo_sesion["cliente_doc"] = ""
            tipo_sesion["cliente_nombre"] = ""
            ventana.after(200, lambda: elegir_tipo_comprobante(obligatorio=True))
        except StockError as e:
            mostrar_popup("Sin stock / error", str(e))
            flash_status(str(e), ok=False)
        except sqlite3.Error as e:
            try:
                conn.rollback()
            except Exception:
                pass
            mostrar_popup("Error BD", str(e))
        except Exception as e:
            mostrar_popup("Error", str(e))
        finally:
            cobrando["activo"] = False
            try:
                cobrar_btn.configure(state="normal", text="COBRAR  $%s" % total_var.get())
            except Exception:
                pass
            codigo_entry.focus_set()

    def elegir_metodo(metodo):
        metodo_pago_var.set(metodo)
        recalcular_precios_por_metodo()
        resaltar_metodo()
        codigo_entry.focus_set()

    def resaltar_metodo():
        actual = metodo_pago_var.get()
        for nombre, btn in metodo_btns.items():
            if nombre == actual:
                btn.configure(relief="sunken", bd=4, highlightthickness=3)
            else:
                btn.configure(relief="raised", bd=2, highlightthickness=0)

    def cancelar_venta(event=None):
        if not productos_vendidos:
            al_cerrar()
            return
        if messagebox.askyesno("Cancelar", "¿Cancelar esta venta y borrar el ticket?", parent=ventana):
            resetear_ticket()
            flash_status("Venta cancelada.", ok=False)

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

    cliente_resumen_var = tk.StringVar(value="Cliente: Consumidor Final")

    # Layout
    top_frame = ttk.Frame(ventana, padding=10)
    top_frame.pack(fill='x')
    ttk.Label(top_frame, text="POS Venta - %s" % user_name, style="Header.TLabel").pack(side='left')
    ttk.Label(
        top_frame,
        text="  Primero tipo de ticket · F1 manual · F5/F6/F7 cobrar",
        foreground="#475569",
    ).pack(side='left', padx=12)

    input_frame = ttk.Frame(ventana, padding=10)
    input_frame.pack(fill='x')
    ttk.Label(input_frame, text="Código:").grid(row=0, column=0, padx=5)
    codigo_entry = ttk.Entry(input_frame, width=30, font=('Segoe UI', 14))
    codigo_entry.grid(row=0, column=1, padx=5)
    codigo_entry.focus_set()
    ttk.Button(input_frame, text="Agregar", command=agregar_producto).grid(row=0, column=2, padx=10)
    ttk.Button(input_frame, text="Manual (F1)", command=agregar_articulo_manual).grid(row=0, column=3, padx=4)
    ttk.Label(input_frame, textvariable=cliente_resumen_var, foreground="#1e40af").grid(
        row=0, column=4, padx=10, sticky='w'
    )

    ticket_frame = ttk.LabelFrame(ventana, text="Ticket de Venta", padding=10)
    ticket_frame.pack(fill='both', expand=True, padx=10, pady=10)
    columnas = ("Código", "Producto", "Precio", "Cantidad", "Subtotal")
    ticket_tree = ttk.Treeview(ticket_frame, columns=columnas, show='headings', height=12)
    for col in columnas:
        ticket_tree.heading(col, text=col)
        ticket_tree.column(col, anchor='center')
    ticket_tree.column("Producto", anchor='w', width=250)
    ticket_tree.pack(fill='both', expand=True)
    ticket_tree.tag_configure('discount', foreground='red')

    cobro_frame = tk.Frame(ventana, bg="#0f172a", padx=12, pady=12)
    cobro_frame.pack(fill='x', padx=8, pady=8)

    totales = tk.Frame(cobro_frame, bg="#0f172a")
    totales.pack(side='left', padx=8)
    tk.Label(totales, text="TOTAL", fg="#94a3b8", bg="#0f172a", font=('Segoe UI', 11, 'bold')).pack(anchor='w')
    tk.Label(
        totales,
        textvariable=total_var,
        fg="#f8fafc",
        bg="#0f172a",
        font=('Segoe UI', 28, 'bold'),
    ).pack(anchor='w')
    tk.Label(
        totales,
        text="Subtotal $",
        fg="#64748b",
        bg="#0f172a",
        font=('Segoe UI', 9),
    ).pack(anchor='w', side='left')
    tk.Label(totales, textvariable=subtotal_var, fg="#64748b", bg="#0f172a", font=('Segoe UI', 9)).pack(
        anchor='w', side='left'
    )

    metodos_frame = tk.Frame(cobro_frame, bg="#0f172a")
    metodos_frame.pack(side='left', expand=True, padx=16)

    def _mk_metodo(texto, valor, color, col):
        b = tk.Button(
            metodos_frame,
            text=texto,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            font=('Segoe UI', 11, 'bold'),
            width=12,
            height=2,
            command=lambda v=valor: cobrar_con_metodo(v),
        )
        b.grid(row=0, column=col, padx=4, pady=2)
        metodo_btns[valor] = b

    _mk_metodo("EFECTIVO\n(F5)", "EFECTIVO", "#15803d", 0)
    _mk_metodo("TARJETA\n(F6)", "TARJETA", "#1d4ed8", 1)
    _mk_metodo("MERCADO PAGO\n(F7)", "MERCADOPAGO", "#0369a1", 2)

    acciones = tk.Frame(cobro_frame, bg="#0f172a")
    acciones.pack(side='right', padx=8)
    cobrar_btn = tk.Button(
        acciones,
        text="COBRAR  $0.00",
        bg="#22c55e",
        fg="white",
        activebackground="#16a34a",
        activeforeground="white",
        font=('Segoe UI', 16, 'bold'),
        width=16,
        height=2,
        command=finalizar_venta,
    )
    cobrar_btn.pack(pady=2)
    tk.Button(
        acciones,
        text="BORRAR TICKET (Esc)",
        bg="#dc2626",
        fg="white",
        font=('Segoe UI', 10, 'bold'),
        width=16,
        command=cancelar_venta,
    ).pack(pady=2)

    status_lbl = tk.Label(
        ventana,
        textvariable=status_var,
        fg="#166534",
        bg="#eaeaea",
        font=('Segoe UI', 11, 'bold'),
        anchor='w',
        padx=14,
        pady=6,
    )
    status_lbl.pack(fill='x')

    resaltar_metodo()

    ventana.bind('<Return>', lambda e: agregar_producto())
    ventana.bind('<F1>', lambda e: agregar_articulo_manual())
    ventana.bind('<F2>', lambda e: elegir_tipo_comprobante(obligatorio=False))
    ventana.bind('<Escape>', cancelar_venta)
    ventana.bind('<Delete>', eliminar_item)
    ventana.bind('<F4>', eliminar_item)
    ventana.bind('<F5>', lambda e: cobrar_con_metodo('EFECTIVO'))
    ventana.bind('<F6>', lambda e: cobrar_con_metodo('TARJETA'))
    ventana.bind('<F7>', lambda e: cobrar_con_metodo('MERCADOPAGO'))

    ventana.after(100, lambda: elegir_tipo_comprobante(obligatorio=True))

    ventana.mainloop()
