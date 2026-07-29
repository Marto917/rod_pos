import tkinter as tk
from tkinter import ttk
from ui import dialogs as messagebox
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
from ui import theme as ui_theme


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
    ventana.configure(bg=ui_theme.BG)
    try:
        ventana.lift()
        ventana.focus_force()
        ventana.attributes("-topmost", True)
        ventana.after(200, lambda: ventana.attributes("-topmost", False))
    except Exception:
        pass
    style_sales = ttk.Style(ventana)
    ui_theme.apply_ttk_style(style_sales)
    style_sales.configure("Header.TLabel", background=ui_theme.BG, foreground=ui_theme.FG, font=("Segoe UI", 14, "bold"))

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
    style.configure('TLabel', background=ui_theme.BG, foreground=ui_theme.FG, font=('Segoe UI', 11))
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

    def _impresora_ticket():
        try:
            return (get_fiscal_config() or {}).get("ticket_impresora") or ""
        except Exception:
            return ""

    def imprimir_ticket_termico(lineas, doc_name="ROD POS", wait=True):
        """Manda el ticket por ESC/POS a la térmica (nunca PDF/Acrobat)."""
        from services.ticket_print import imprimir_lineas

        return imprimir_lineas(
            lineas,
            doc_name=doc_name,
            wait=wait,
            printer_name=_impresora_ticket(),
        )

    def imprimir_factura_y_esperar(lineas, doc_name, venta_id):
        """Imprime Factura C (solo con CAE) de forma bloqueante."""
        while True:
            flash_status("Imprimiendo Factura C · venta #%s…" % venta_id, ok=True)
            try:
                ventana.update_idletasks()
                ventana.update()
            except Exception:
                pass
            try:
                printer = imprimir_ticket_termico(lineas, doc_name=doc_name, wait=True)
                flash_status("Ticket enviado a: %s" % printer, ok=True)
            except Exception as e:
                reintentar = messagebox.askretrycancel(
                    "Impresión",
                    "No se pudo imprimir la Factura C.\n\n%s\n\n"
                    "Reintentar = vuelve a mandar a la térmica\n"
                    "Cancelar = dejar de intentar imprimir"
                    % e,
                    parent=ventana,
                )
                if reintentar:
                    continue
                return False

            ok = messagebox.askyesno(
                "Ticket Factura C",
                "¿Salió el ticket en la térmica?\n\n"
                "Sí = continuar\n"
                "No = reimprimir\n\n"
                "Importante: no imprimas el PDF desde Acrobat\n"
                "(ahí la XP-58 gasta metros de papel en blanco).",
                parent=ventana,
            )
            if ok:
                return True

    def _emitir_fiscal_con_espera(venta_id, payload):
        """
        Emite Factura C. Si ARCA falla o no hay CAE, espera y reintenta.
        Devuelve:
          (True, info)       → CAE OK
          ("interno", info)  → cajero eligió ticket interno
          (False, None)      → venta anulada
        """
        import time
        from services.stock_ops import anular_venta, enqueue_fiscal

        espera_bloque_s = 40
        poll_s = 4

        while True:
            flash_status("Emitiendo Factura C en ARCA…", ok=True)
            try:
                ventana.update_idletasks()
                ventana.update()
            except Exception:
                pass

            try:
                if is_client_mode():
                    fiscal_res = enqueue_fiscal(venta_id, payload)
                    ok_fiscal = bool(fiscal_res.get("ok"))
                    res_fiscal = fiscal_res.get("result") or {}
                else:
                    c.execute(
                        "UPDATE ventas SET fiscal_solicitado=1, fiscal_tipo=?, fiscal_estado='EN_PROCESO' WHERE id=?",
                        (payload.get("tipo_comprobante") or "C", venta_id),
                    )
                    conn.commit()
                    ok_fiscal, res_fiscal = emitir_o_encolar(venta_id, payload)
            except Exception as e_fiscal:
                ok_fiscal = False
                res_fiscal = {"error": str(e_fiscal)}

            cae = str((res_fiscal or {}).get("cae") or "").strip()
            if ok_fiscal and cae:
                info = {
                    "estado": "EMITIDO",
                    "cae": cae,
                    "vto_cae": res_fiscal.get("vto_cae", ""),
                    "tipo": res_fiscal.get("tipo", payload.get("tipo_comprobante") or "C"),
                    "numero": res_fiscal.get("numero", ""),
                    "pto_vta": res_fiscal.get("pto_vta", ""),
                    "cliente_doc": res_fiscal.get("cliente_doc") or payload.get("cliente_doc") or "",
                    "cliente_nombre": res_fiscal.get("cliente_nombre") or payload.get("cliente_nombre") or "",
                    "tipo_doc_rec": res_fiscal.get("tipo_doc_rec"),
                    "nro_doc_rec": res_fiscal.get("nro_doc_rec"),
                }
                return True, info

            err = str((res_fiscal or {}).get("error") or "")
            if ok_fiscal and not cae:
                err = err or "ARCA respondió sin CAE"

            err_l = err.lower()
            es_error_definitivo = (
                "10015" in err
                or "padron" in err_l
                or "padrón" in err_l
                or "no se encuentra registrado" in err_l
                or "digito verificador" in err_l
                or "cuit/cuil invalido" in err_l
                or "cuit invalido" in err_l
                or "factura a requiere cuit" in err_l
            )

            # Errores de datos del cliente: no tiene sentido esperar 40s
            if not es_error_definitivo:
                flash_status(
                    "ARCA pendiente%s · esperando…" % ((" · " + err[:35]) if err else ""),
                    ok=False,
                )
                t0 = time.time()
                while time.time() - t0 < espera_bloque_s:
                    restante = int(espera_bloque_s - (time.time() - t0))
                    flash_status(
                        "Esperando ARCA… %ss · venta #%s" % (max(restante, 0), venta_id),
                        ok=False,
                    )
                    try:
                        ventana.update_idletasks()
                        ventana.update()
                    except Exception:
                        pass
                    time.sleep(min(poll_s, max(0.5, espera_bloque_s - (time.time() - t0))))

                    try:
                        if is_client_mode():
                            fiscal_res = enqueue_fiscal(venta_id, payload)
                            ok_fiscal = bool(fiscal_res.get("ok"))
                            res_fiscal = fiscal_res.get("result") or {}
                        else:
                            ok_fiscal, res_fiscal = emitir_o_encolar(venta_id, payload)
                    except Exception as e_retry:
                        ok_fiscal = False
                        res_fiscal = {"error": str(e_retry)}

                    cae = str((res_fiscal or {}).get("cae") or "").strip()
                    if ok_fiscal and cae:
                        info = {
                            "estado": "EMITIDO",
                            "cae": cae,
                            "vto_cae": res_fiscal.get("vto_cae", ""),
                            "tipo": res_fiscal.get("tipo", payload.get("tipo_comprobante") or "C"),
                            "numero": res_fiscal.get("numero", ""),
                            "pto_vta": res_fiscal.get("pto_vta", ""),
                            "cliente_doc": res_fiscal.get("cliente_doc") or payload.get("cliente_doc") or "",
                            "cliente_nombre": res_fiscal.get("cliente_nombre") or payload.get("cliente_nombre") or "",
                            "tipo_doc_rec": res_fiscal.get("tipo_doc_rec"),
                            "nro_doc_rec": res_fiscal.get("nro_doc_rec"),
                        }
                        return True, info

                    err = str((res_fiscal or {}).get("error") or err or "Sin respuesta de ARCA")
                    err_l = err.lower()
                    if (
                        "10015" in err
                        or "padron" in err_l
                        or "padrón" in err_l
                        or "no se encuentra registrado" in err_l
                    ):
                        es_error_definitivo = True
                        break

            err = str((res_fiscal or {}).get("error") or err or "Sin respuesta de ARCA")
            err_l = err.lower()
            es_padron = (
                "10015" in err
                or "padron" in err_l
                or "padrón" in err_l
                or "no se encuentra registrado" in err_l
                or "digito verificador" in err_l
                or "cuit/cuil invalido" in err_l
            )

            if es_padron:
                while True:
                    eleccion = messagebox.askchoice(
                        "Documento rechazado por AFIP",
                        "No se pudo emitir la Factura C con esos datos.\n\n"
                        "Detalle: %s\n\n"
                        "¿Qué querés hacer?"
                        % err[:220],
                        choices=[
                            ("Corregir CUIT/DNI", "corregir", "accent"),
                            ("Ticket interno", "interno", "warning"),
                            ("Anular venta", "anular", "danger"),
                        ],
                        parent=ventana,
                        default="anular",
                    )
                    if eleccion == "corregir":
                        from fiscal_service import validar_cuit_digito

                        valores = messagebox.prompt_textos(
                            "Corregir datos del cliente",
                            [
                                ("DNI o CUIT", payload.get("cliente_doc") or ""),
                                ("Nombre", payload.get("cliente_nombre") or ""),
                            ],
                            parent=ventana,
                        )
                        if valores is None:
                            continue  # vuelve a las 3 opciones
                        doc = "".join(ch for ch in (valores[0] or "") if ch.isdigit())
                        nom = (valores[1] or "").strip()
                        if doc and not (7 <= len(doc) <= 8 or len(doc) == 11):
                            messagebox.showwarning(
                                "Cliente",
                                "DNI (7-8) o CUIT (11 dígitos). También podés dejarlo vacío.",
                                parent=ventana,
                            )
                            continue
                        if len(doc) == 11 and not validar_cuit_digito(doc):
                            messagebox.showwarning(
                                "Cliente",
                                "Ese CUIT/CUIL no es válido (dígito verificador).",
                                parent=ventana,
                            )
                            continue
                        if doc and not nom:
                            messagebox.showwarning(
                                "Cliente",
                                "Si hay DNI/CUIT, poné el nombre.",
                                parent=ventana,
                            )
                            continue
                        if nom and not doc:
                            messagebox.showwarning(
                                "Cliente",
                                "Si hay nombre, poné DNI o CUIT (o borrá el nombre).",
                                parent=ventana,
                            )
                            continue
                        payload["cliente_doc"] = doc
                        payload["cliente_nombre"] = nom
                        payload["tipo_doc_rec"] = (
                            80 if len(doc) == 11 else (96 if doc else 99)
                        )
                        payload["nro_doc_rec"] = int(doc) if doc.isdigit() else 0
                        tipo_sesion["cliente_doc"] = doc
                        tipo_sesion["cliente_nombre"] = nom
                        cliente_doc_var.set(doc)
                        cliente_nombre_var.set(nom)
                        if doc:
                            cliente_resumen_var.set("Cliente: %s · %s" % (nom, doc))
                        else:
                            cliente_resumen_var.set(
                                "Cliente: Consumidor Final · Factura C"
                            )
                        break  # sale del menú → reintenta emisión abajo
                    if eleccion == "interno":
                        try:
                            if not is_client_mode():
                                c.execute(
                                    "UPDATE ventas SET fiscal_solicitado=0, "
                                    "fiscal_estado='NO_SOLICITADO', fiscal_tipo=NULL WHERE id=?",
                                    (venta_id,),
                                )
                                conn.commit()
                        except Exception:
                            pass
                        tipo_sesion["modo"] = "interno"
                        flash_status(
                            "Se cobra como ticket interno · #%s" % venta_id,
                            ok=True,
                        )
                        return "interno", {
                            "ticket_negro": True,
                            "cliente_doc": "",
                            "cliente_nombre": "",
                            "tipo_doc_rec": 99,
                            "nro_doc_rec": 0,
                        }
                    # Anular venta
                    try:
                        anular_venta(
                            venta_id,
                            usuario_id=user_id,
                            motivo="ANULACION_FISCAL_SIN_CAE",
                        )
                    except Exception as e_anular:
                        messagebox.showerror(
                            "Error",
                            "No se pudo anular la venta #%s.\n%s\n"
                            "Revisá stock manualmente."
                            % (venta_id, e_anular),
                            parent=ventana,
                        )
                    flash_status("Venta #%s anulada (sin CAE)." % venta_id, ok=False)
                    return False, None
                continue  # reintentar emisión con CUIT corregido

            reintentar = messagebox.askyesno(
                "ARCA pendiente",
                "No se pudo obtener CAE para la Factura C.\n\n"
                "Detalle: %s\n\n"
                "Sí = reintentar (espera de nuevo)\n"
                "No = CANCELAR la venta (borra la operación y devuelve el stock)"
                % err[:180],
                parent=ventana,
            )
            if reintentar:
                continue

            try:
                anular_venta(
                    venta_id,
                    usuario_id=user_id,
                    motivo="ANULACION_FISCAL_SIN_CAE",
                )
            except Exception as e_anular:
                messagebox.showerror(
                    "Error",
                    "No se pudo anular la venta #%s.\n%s\n"
                    "Revisá stock manualmente."
                    % (venta_id, e_anular),
                    parent=ventana,
                )
            flash_status("Venta #%s anulada (sin CAE)." % venta_id, ok=False)
            return False, None

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
            titulo = result.get("titulo") or ("Ajuste de caja %s" % (result.get("nro_dia") or ""))
            lineas_aj = result.get("lineas") or [
                titulo,
                "Cajero: %s" % user_name,
                "Monto: $%.2f" % (result.get("monto") or monto),
                "Desde: %s" % (result.get("metodo_desde") or ""),
                "Hacia: %s" % (result.get("metodo_hacia") or ""),
            ]
            try:
                imprimir_ticket_termico(lineas_aj, doc_name=titulo)
            except Exception as e:
                messagebox.showwarning(
                    "Ajuste",
                    "Ajuste guardado, pero no se pudo imprimir en la térmica:\n%s\n\n"
                    "El PDF quedó en comprobantes (no lo imprimas desde Acrobat:\n"
                    "ahí la XP-58 usa ~3 metros de papel en blanco)."
                    % e,
                    parent=ventana,
                )
            messagebox.showinfo(
                "Ajuste OK",
                "%s\n$%.2f de %s → %s\n\nPDF:\n%s"
                % (
                    titulo,
                    result.get("monto") or monto,
                    result.get("metodo_desde"),
                    result.get("metodo_hacia"),
                    pdf_path or "-",
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
        """Cartel fullscreen: T = interno ya; C = pantalla de datos cliente."""
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

        pantalla = {"modo": "elegir"}  # elegir | cliente

        titulo = tk.Label(
            wrap,
            text="Que tipo de ticket vas a emitir?",
            font=("Segoe UI", 28, "bold"),
            bg="#0f172a",
            fg="#f8fafc",
        )
        titulo.pack(pady=(0, 8))
        subtitulo = tk.Label(
            wrap,
            text="T = Ticket interno  ·  C = Factura C (datos del cliente)",
            font=("Segoe UI", 14),
            bg="#0f172a",
            fg="#94a3b8",
        )
        subtitulo.pack(pady=(0, 24))

        panel_elegir = tk.Frame(wrap, bg="#0f172a")
        panel_cliente = tk.Frame(wrap, bg="#1e293b", padx=24, pady=20)

        tk.Label(
            panel_cliente,
            text="Datos del cliente — Factura C",
            font=("Segoe UI", 16, "bold"),
            bg="#1e293b",
            fg="#f8fafc",
        ).pack(anchor="w")
        tk.Label(
            panel_cliente,
            text="Si no pone DNI/CUIT = Consumidor Final. Esos datos salen en el ticket.",
            font=("Segoe UI", 11),
            bg="#1e293b",
            fg="#94a3b8",
        ).pack(anchor="w", pady=(0, 12))

        fila = tk.Frame(panel_cliente, bg="#1e293b")
        fila.pack(fill="x", pady=6)
        tk.Label(fila, text="DNI o CUIT:", bg="#1e293b", fg="#e2e8f0", width=14, anchor="e").pack(
            side="left"
        )
        doc_e = tk.Entry(fila, width=28, font=("Segoe UI", 16))
        doc_e.pack(side="left", padx=6)

        fila2 = tk.Frame(panel_cliente, bg="#1e293b")
        fila2.pack(fill="x", pady=6)
        tk.Label(fila2, text="Nombre:", bg="#1e293b", fg="#e2e8f0", width=14, anchor="e").pack(
            side="left"
        )
        nom_e = tk.Entry(fila2, width=28, font=("Segoe UI", 16))
        nom_e.pack(side="left", padx=6)

        def aplicar_interno():
            tipo_sesion["modo"] = "interno"
            tipo_sesion["cliente_doc"] = ""
            tipo_sesion["cliente_nombre"] = ""
            limpiar_cliente()
            cliente_resumen_var.set("Ticket interno (sin factura)")
            resultado["ok"] = True
            top.destroy()
            flash_status("Listo: Ticket interno · ahora escanea y cobra", ok=True)
            codigo_entry.focus_set()

        def aplicar_factura():
            doc = "".join(ch for ch in doc_e.get() if ch.isdigit())
            nom = nom_e.get().strip()
            if doc and not (7 <= len(doc) <= 8 or len(doc) == 11):
                messagebox.showwarning("Cliente", "DNI (7-8) o CUIT (11 digitos).", parent=top)
                return
            if len(doc) == 11:
                from fiscal_service import validar_cuit_digito

                if not validar_cuit_digito(doc):
                    messagebox.showwarning(
                        "Cliente",
                        "Ese CUIT/CUIL no es válido (dígito verificador).\n"
                        "Revisalo o dejalo vacío para Consumidor Final.",
                        parent=top,
                    )
                    return
            if doc and not nom:
                messagebox.showwarning("Cliente", "Si hay DNI/CUIT, pone el nombre.", parent=top)
                return
            if nom and not doc:
                messagebox.showwarning("Cliente", "Si hay nombre, pone DNI o CUIT.", parent=top)
                return
            tipo_sesion["modo"] = "factura_c"
            tipo_sesion["cliente_doc"] = doc
            tipo_sesion["cliente_nombre"] = nom
            cliente_doc_var.set(doc)
            cliente_nombre_var.set(nom)
            if doc:
                cliente_resumen_var.set("Cliente: %s · %s" % (nom, doc))
            else:
                cliente_resumen_var.set("Cliente: Consumidor Final · Factura C")
            resultado["ok"] = True
            top.destroy()
            flash_status("Listo: Factura C · ahora escanea y cobra", ok=True)
            codigo_entry.focus_set()

        def mostrar_elegir():
            pantalla["modo"] = "elegir"
            panel_cliente.pack_forget()
            titulo.configure(text="Que tipo de ticket vas a emitir?")
            subtitulo.configure(text="T = Ticket interno  ·  C = Factura C (datos del cliente)")
            panel_elegir.pack(pady=12)

        def mostrar_cliente(event=None):
            pantalla["modo"] = "cliente"
            panel_elegir.pack_forget()
            titulo.configure(text="Factura C")
            subtitulo.configure(text="Completa el cliente y confirma (Enter)")
            panel_cliente.pack(fill="x", pady=8)
            doc_e.focus_set()

        def on_enter(event=None):
            if pantalla["modo"] == "cliente":
                aplicar_factura()

        def on_key_c(event=None):
            if pantalla["modo"] == "elegir":
                mostrar_cliente()

        def on_key_t(event=None):
            if pantalla["modo"] == "elegir":
                aplicar_interno()

        def cancelar(event=None):
            # En pantalla cliente, Esc vuelve a elegir.
            if pantalla["modo"] == "cliente":
                mostrar_elegir()
                return
            # Si ya había tipo elegido (ej. F2), solo cerrar el cartel.
            if tipo_sesion.get("modo"):
                top.destroy()
                return
            # Sin tipo aún: salir del ticket de venta.
            top.destroy()
            al_cerrar()

        def salir_click():
            cancelar()

        btns = tk.Frame(panel_elegir, bg="#0f172a")
        btns.pack(pady=12)
        tk.Button(
            btns,
            text="FACTURA C\nAtajo: tecla C",
            bg="#2563eb",
            fg="white",
            font=("Segoe UI", 18, "bold"),
            width=22,
            height=4,
            command=mostrar_cliente,
        ).pack(side="left", padx=16)
        tk.Button(
            btns,
            text="TICKET INTERNO\nAtajo: tecla T",
            bg="#64748b",
            fg="white",
            font=("Segoe UI", 18, "bold"),
            width=22,
            height=4,
            command=aplicar_interno,
        ).pack(side="left", padx=16)

        acciones_cli = tk.Frame(panel_cliente, bg="#1e293b")
        acciones_cli.pack(pady=(18, 0))
        tk.Button(
            acciones_cli,
            text="CONFIRMAR FACTURA C  (Enter)",
            bg="#16a34a",
            fg="white",
            font=("Segoe UI", 14, "bold"),
            width=28,
            height=2,
            command=aplicar_factura,
        ).pack(side="left", padx=8)
        tk.Button(
            acciones_cli,
            text="Volver",
            bg="#64748b",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=12,
            height=2,
            command=mostrar_elegir,
        ).pack(side="left", padx=8)

        panel_elegir.pack(pady=12)

        tk.Button(
            wrap,
            text="SALIR DEL TICKET  (Esc)",
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=28,
            height=2,
            command=salir_click,
        ).pack(pady=(20, 0))

        tk.Label(
            wrap,
            text="T = interno · C = Factura C · Esc = salir",
            font=("Segoe UI", 12),
            bg="#0f172a",
            fg="#64748b",
        ).pack(pady=(12, 0))

        top.bind("c", on_key_c)
        top.bind("C", on_key_c)
        top.bind("t", on_key_t)
        top.bind("T", on_key_t)
        top.bind("<Return>", on_enter)
        top.bind("<Escape>", cancelar)
        top.protocol("WM_DELETE_WINDOW", cancelar)
        top.wait_window()
        return resultado["ok"]

    def generar_comprobante(
        venta_id,
        total,
        fiscal_info=None,
        *,
        generar_pdf=True,
        productos=None,
        cfg=None,
    ):
        """
        Arma líneas del ticket y opcionalmente el PDF.
        Para ticket interno: generar_pdf=False en el hilo UI (rápido) y PDF en background.
        """
        if cfg is None:
            try:
                cfg = get_fiscal_config() or {}
            except Exception as e_cfg:
                print("[PDF DEBUG] Error leyendo config fiscal: %r" % e_cfg, flush=True)
                cfg = {}
        productos_src = productos if productos is not None else productos_vendidos
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

        # Nombre con fecha+hora para buscar en el Explorador (ej. 2026-07-26)
        stamp_arch = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fecha_arch = datetime.now().strftime("%d%m%Y")
        nombre_archivo = os.path.join(
            comprobantes_dir,
            "ticket_%s_v%06d.pdf" % (stamp_arch, venta_id),
        )
        _log_ticket_debug("%s generar_comprobante inicio venta_id=%s archivo=%s" % (debug_marker, venta_id, nombre_archivo))

        # Layout térmico: ancho configurable (default 58mm), alto = contenido exacto.
        try:
            ancho_mm = float(str(cfg.get("ticket_ancho_mm") or "58").replace(",", "."))
        except Exception:
            ancho_mm = 58.0
        if ancho_mm < 40:
            ancho_mm = 58.0
        W = 32 if ancho_mm < 70 else 42
        usable = max(36.0, ancho_mm - 4.0)
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
        _log_ticket_debug(
            "%s datos CAE=%r nro=%r CUIT=%r IIBB=%r"
            % (debug_marker, cae, nro_factura, cuit, iibb)
        )

        fecha_now = datetime.now()
        fecha_h = fecha_now.strftime("%d/%m/%Y")
        hora_h = fecha_now.strftime("%H:%M")

        items_ok = []
        subtotal = 0.0
        for p in productos_src:
            if p.get("codigo") == "105":
                continue
            cant = 1
            precio = float(p.get("precio", 0.0))
            sub = round(cant * precio, 2)
            subtotal += sub
            items_ok.append((cant, precio, sub, (p.get("nombre") or "").strip()))
        try:
            total_num = float(total)
        except Exception:
            try:
                total_num = float(str(total_var.get()).replace(",", "."))
            except Exception:
                total_num = 0.0

        es_negro = bool((fiscal_info or {}).get("ticket_negro"))
        titulo_cmp = "TICKET INTERNO" if es_negro else "FACTURA C (Cod. 011)"
        tipo_arch = "ticket_interno" if es_negro else "factura_c"
        nombre_archivo = os.path.join(
            comprobantes_dir,
            "%s_%s_v%06d.pdf" % (tipo_arch, stamp_arch, venta_id),
        )

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
        pagos_info = (fiscal_info or {}).get("pagos") or []
        if pagos_info:
            lineas.append("-" * W)
            lineas.append(pad32("PAGO:"))
            for p in pagos_info:
                met = str(p.get("metodo") or "").strip().upper()
                try:
                    mon = float(p.get("monto") or 0)
                except Exception:
                    mon = 0.0
                if met and mon > 0:
                    label = {
                        "EFECTIVO": "EFECTIVO",
                        "TARJETA": "TARJETA",
                        "MERCADOPAGO": "MERCADO PAGO",
                    }.get(met, met)
                    lineas.append(pad32("%s $%.2f" % (label, mon)))
        lineas.append("=" * W)
        if es_negro:
            lineas.append(center32("Comprobante interno"))
            lineas.append(center32("Sin CAE / no fiscal"))
        else:
            lineas.append(pad32("CAE: %s" % (cae if str(cae).strip() else "VACIO")))
            lineas.append(pad32("Vto. CAE: %s" % (vto_cae if str(vto_cae).strip() else "-")))

        # Camino rápido (ticket interno): devolver líneas ya; PDF en background.
        if not generar_pdf:
            _log_ticket_debug(
                "%s solo_lineas=%d venta_id=%s" % (debug_marker, len(lineas), venta_id)
            )
            return {"pdf_path": None, "lineas": lineas}

        logo_path = (cfg.get("ticket_logo_path") or "").strip()
        has_logo = ((cfg.get("ticket_incluir_logo") or "0") == "1") and bool(logo_path) and os.path.isfile(logo_path)
        include_qr = (not es_negro) and bool(
            str(cae).strip() and str((fiscal_info or {}).get("numero") or "").strip()
        )

        # Alto = solo el contenido. Nunca más de ~220 mm (evita PDFs de 3 metros).
        margen_sup = 1.5
        margen_inf = 4.0
        logo_h = 11.0 if has_logo else 0.0
        qr_h = 16.0 if include_qr else 0.0
        # +1 línea de aire inicial (mismo offset que el render)
        contenido_h = margen_sup + logo_h + line_h + (len(lineas) * line_h) + qr_h + margen_inf
        page_h = max(35.0, min(220.0, float(contenido_h)))
        # Ancho útil de rollo 58 mm suele ser ~48 mm imprimibles
        if ancho_mm > 58:
            ancho_mm = 58.0
        ancho_mm = max(40.0, min(80.0, float(ancho_mm)))

        def _pdf_alto_mm(path_pdf):
            """Lee MediaBox y devuelve alto en mm (o None)."""
            try:
                import re

                data = open(path_pdf, "rb").read()
                m = re.search(rb"/MediaBox\s*\[\s*([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)\s*\]", data)
                if not m:
                    return None
                y1 = float(m.group(2))
                y2 = float(m.group(4))
                return abs(y2 - y1) * 25.4 / 72.0
            except Exception:
                return None

        try:
            pdf = FPDF(orientation="P", unit="mm", format=(ancho_mm, page_h))
            pdf.set_margins(1.5, 1.5, 1.5)
            pdf.set_auto_page_break(auto=False, margin=0)
            pdf.add_page()
            pdf.set_xy(1.5, margen_sup)

            if has_logo:
                try:
                    size_logo = 10.0
                    x_logo = (ancho_mm - size_logo) / 2.0
                    y_logo = pdf.get_y()
                    pdf.image(logo_path, x=x_logo, y=y_logo, w=size_logo, h=size_logo)
                    pdf.set_y(y_logo + size_logo + 0.8)
                except Exception:
                    pdf.set_font("Courier", "", 7)
                    pdf.cell(usable, line_h, "LOGO NO DISPONIBLE", align="C", ln=1)

            y_text = float(pdf.get_y()) + line_h
            for ln in lineas:
                es_total = ln.strip().startswith("TOTAL:")
                es_titulo = "FACTURA C" in ln or "TICKET INTERNO" in ln or ln.strip() == razon[:W]
                pdf.set_font("Courier", "B" if (es_total or es_titulo) else "", 7)
                pdf.set_text_color(0, 0, 0)
                # text() usa coordenadas absolutas; no agranda la página
                if y_text < page_h - 2.0:
                    pdf.text(1.5, y_text, ln[:W])
                y_text += line_h

            pdf.set_y(min(y_text, page_h - (qr_h + 1.0 if include_qr else 2.0)))

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
                    y_qr = min(float(pdf.get_y()) + 0.5, page_h - size_qr - 1.0)
                    pdf.image(qr_path, x=x_qr, y=y_qr, w=size_qr, h=size_qr)
                except Exception:
                    pdf.set_font("Courier", "", 7)
                    pdf.cell(usable, line_h, "QR NO DISPONIBLE", align="C", ln=1)

            # classic FPDF: output(name, dest)
            try:
                pdf.output(nombre_archivo, "F")
            except TypeError:
                pdf.output(nombre_archivo)

            alto_real = _pdf_alto_mm(nombre_archivo)
            if alto_real is not None and alto_real > 250.0:
                # Defensa: si por algún bug quedó un PDF de metros, reescribir corto
                _log_ticket_debug(
                    "%s PDF alto anormal=%.1fmm → reescribir" % (debug_marker, alto_real)
                )
                pdf2 = FPDF(orientation="P", unit="mm", format=(ancho_mm, page_h))
                pdf2.set_margins(1.5, 1.5, 1.5)
                pdf2.set_auto_page_break(auto=False, margin=0)
                pdf2.add_page()
                pdf2.set_font("Courier", "", 7)
                y = 4.0
                for ln in lineas[:60]:
                    pdf2.text(1.5, y, ln[:W])
                    y += line_h
                    if y > page_h - 3:
                        break
                try:
                    pdf2.output(nombre_archivo, "F")
                except TypeError:
                    pdf2.output(nombre_archivo)

            _log_ticket_debug(
                "%s pdf OK alto_pedido=%.1fmm alto_real=%s lineas=%d archivo=%s"
                % (
                    debug_marker,
                    page_h,
                    ("%.1f" % alto_real) if alto_real is not None else "?",
                    len(lineas),
                    nombre_archivo,
                )
            )
        except Exception as e_pdf:
            # Fallback de emergencia: ticket mínimo para no bloquear ventas.
            _log_ticket_debug("%s ERROR render principal: %r" % (debug_marker, e_pdf))
            pdf = FPDF(orientation="P", unit="mm", format=(58, max(40.0, min(180.0, 8 + len(lineas) * 3.2))))
            pdf.set_margins(1.5, 1.5, 1.5)
            pdf.set_auto_page_break(auto=False, margin=0)
            pdf.add_page()
            pdf.set_xy(1.5, 1.5)
            pdf.set_font("Courier", "B", 8)
            pdf.cell(54, 3.2, "TICKET RECUPERADO", align="C", ln=1)
            pdf.set_font("Courier", "", 7)
            pdf.cell(54, 3.2, "Error render PDF: %s" % str(e_pdf)[:32], align="L", ln=1)
            pdf.cell(54, 3.2, "CUIT: %s" % cuit, align="L", ln=1)
            pdf.cell(54, 3.2, "IIBB: %s" % iibb, align="L", ln=1)
            pdf.cell(54, 3.2, "TOTAL: $%.2f" % total_num, align="L", ln=1)
            try:
                pdf.output(nombre_archivo, "F")
            except TypeError:
                pdf.output(nombre_archivo)
            _log_ticket_debug("%s pdf fallback generado: %s" % (debug_marker, nombre_archivo))
        return {"pdf_path": nombre_archivo, "lineas": lineas}

    def _pdf_en_background(venta_id, total, fiscal_info, productos_snap, cfg_snap):
        """Genera el PDF fuera del hilo de cobro para no frenar la caja."""
        import threading

        def _run():
            try:
                generar_comprobante(
                    venta_id,
                    total,
                    fiscal_info=fiscal_info,
                    generar_pdf=True,
                    productos=productos_snap,
                    cfg=cfg_snap,
                )
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def finalizar_venta(event=None):
        cobrar_con_metodo(metodo_pago_var.get())

    def _parse_monto(txt):
        t = (txt or "").strip().replace(",", ".")
        if not t:
            return None
        try:
            return round(float(t), 2)
        except Exception:
            return None

    def _normalizar_pagos(pagos_raw, total):
        """Filtra montos > 0 y valida suma == total. Devuelve lista o lanza ValueError."""
        pagos = []
        for p in pagos_raw or []:
            met = str(p.get("metodo") or "").strip().upper()
            try:
                mon = round(float(p.get("monto") or 0), 2)
            except Exception:
                mon = 0.0
            if met and mon > 0:
                pagos.append({"metodo": met, "monto": mon})
        if not pagos:
            raise ValueError("Ingresá al menos un monto de pago.")
        suma = round(sum(p["monto"] for p in pagos), 2)
        total_r = round(float(total), 2)
        if abs(suma - total_r) > 0.01:
            raise ValueError(
                "La suma de pagos ($%.2f) debe ser igual al total ($%.2f)."
                % (suma, total_r)
            )
        return pagos

    def pedir_pago_mixto():
        """Diálogo F8: montos por método. Devuelve (metodo_label, pagos) o None."""
        if not productos_vendidos:
            flash_status("No hay productos. Escaneá antes de cobrar.", ok=False)
            return None
        try:
            total = float(str(total_var.get()).replace(",", "."))
        except Exception:
            total = 0.0
        if total <= 0:
            flash_status("Total inválido.", ok=False)
            return None

        top = tk.Toplevel(ventana)
        top.title("Pago mixto")
        top.configure(bg="#0f172a")
        top.transient(ventana)
        top.grab_set()
        top.resizable(False, False)

        wrap = tk.Frame(top, bg="#0f172a", padx=18, pady=16)
        wrap.pack(fill="both", expand=True)
        tk.Label(
            wrap,
            text="Pago mixto",
            bg="#0f172a",
            fg="#f8fafc",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            wrap,
            text="Total a cobrar: $%.2f" % total,
            bg="#0f172a",
            fg="#94a3b8",
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(4, 12))

        vars_m = {
            "EFECTIVO": tk.StringVar(value=""),
            "TARJETA": tk.StringVar(value=""),
            "MERCADOPAGO": tk.StringVar(value=""),
        }
        labels = [
            ("EFECTIVO", "Efectivo"),
            ("TARJETA", "Tarjeta"),
            ("MERCADOPAGO", "Mercado Pago"),
        ]
        entries = {}
        for key, lab in labels:
            fila = tk.Frame(wrap, bg="#0f172a")
            fila.pack(fill="x", pady=4)
            tk.Label(
                fila,
                text=lab + ":",
                bg="#0f172a",
                fg="#e2e8f0",
                width=14,
                anchor="e",
                font=("Segoe UI", 11),
            ).pack(side="left")
            e = tk.Entry(fila, textvariable=vars_m[key], font=("Segoe UI", 14), width=12)
            e.pack(side="left", padx=8)
            entries[key] = e

        resto_var = tk.StringVar(value="Resta: $%.2f" % total)

        def _actualizar_resto(*_a):
            usados = 0.0
            for v in vars_m.values():
                m = _parse_monto(v.get())
                if m is not None and m > 0:
                    usados += m
            resta = round(total - usados, 2)
            if abs(resta) < 0.01:
                resto_var.set("OK · suma = total")
            elif resta > 0:
                resto_var.set("Resta: $%.2f" % resta)
            else:
                resto_var.set("Sobran: $%.2f" % abs(resta))

        for v in vars_m.values():
            v.trace_add("write", _actualizar_resto)
        tk.Label(
            wrap,
            textvariable=resto_var,
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(8, 4))
        tk.Label(
            wrap,
            text="Dejá un campo vacío y al confirmar se completa con el resto.",
            bg="#0f172a",
            fg="#64748b",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        resultado = {"ok": False, "metodo": None, "pagos": None}

        def confirmar(_e=None):
            montos = {}
            vacios = []
            for key in ("EFECTIVO", "TARJETA", "MERCADOPAGO"):
                raw = (vars_m[key].get() or "").strip()
                if not raw:
                    vacios.append(key)
                    continue
                m = _parse_monto(raw)
                if m is None or m < 0:
                    messagebox.showwarning(
                        "Pago mixto",
                        "Monto inválido en %s." % key,
                        parent=top,
                    )
                    return
                montos[key] = m
            suma = round(sum(montos.values()), 2)
            resta = round(total - suma, 2)
            if len(vacios) == 1 and resta > 0.009:
                montos[vacios[0]] = resta
            elif len(vacios) > 1 and resta > 0.009:
                messagebox.showwarning(
                    "Pago mixto",
                    "Completá los montos (podés dejar un solo campo vacío para el resto).",
                    parent=top,
                )
                return
            try:
                pagos = _normalizar_pagos(
                    [{"metodo": k, "monto": v} for k, v in montos.items()],
                    total,
                )
            except ValueError as e:
                messagebox.showwarning("Pago mixto", str(e), parent=top)
                return
            if len(pagos) == 1:
                resultado["metodo"] = pagos[0]["metodo"]
            else:
                resultado["metodo"] = "MIXTO"
            resultado["pagos"] = pagos
            resultado["ok"] = True
            top.destroy()

        def cancelar(_e=None):
            top.destroy()

        btns = tk.Frame(wrap, bg="#0f172a")
        btns.pack(fill="x", pady=(14, 0))
        tk.Button(
            btns,
            text="Cancelar",
            command=cancelar,
            bg="#475569",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=12,
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            btns,
            text="Cobrar",
            command=confirmar,
            bg="#22c55e",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            width=12,
        ).pack(side="right")

        top.bind("<Return>", confirmar)
        top.bind("<Escape>", cancelar)
        top.protocol("WM_DELETE_WINDOW", cancelar)
        entries["EFECTIVO"].focus_set()
        top.wait_window()
        if not resultado["ok"]:
            return None
        return resultado["metodo"], resultado["pagos"]

    def cobrar_mixto(event=None):
        res = pedir_pago_mixto()
        if not res:
            return
        metodo, pagos = res
        # Precios: si hay efectivo en el mixto usamos precio público; si solo tarjeta, lista
        if any(p["metodo"] == "TARJETA" for p in pagos) and not any(
            p["metodo"] == "EFECTIVO" for p in pagos
        ):
            metodo_pago_var.set("TARJETA")
        else:
            metodo_pago_var.set("EFECTIVO")
        recalcular_precios_por_metodo()
        # Revalidar suma contra total recalculado
        try:
            total = float(str(total_var.get()).replace(",", "."))
            pagos = _normalizar_pagos(pagos, total)
        except ValueError as e:
            messagebox.showwarning("Pago mixto", str(e), parent=ventana)
            return
        if len(pagos) == 1:
            metodo = pagos[0]["metodo"]
        else:
            metodo = "MIXTO"
        cobrar_con_metodo(metodo, pagos=pagos)

    def cobrar_con_metodo(metodo, event=None, pagos=None):
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

        if metodo == "MIXTO" and not pagos:
            cobrar_mixto()
            return

        if metodo != "MIXTO":
            metodo_pago_var.set(metodo)
            recalcular_precios_por_metodo()
            resaltar_metodo()
            if not pagos:
                try:
                    total_tmp = float(str(total_var.get()).replace(",", "."))
                except Exception:
                    total_tmp = 0.0
                pagos = [{"metodo": metodo, "monto": round(total_tmp, 2)}]
        else:
            metodo_pago_var.set("MIXTO")
            resaltar_metodo()

        emitir_fiscal = tipo_sesion["modo"] == "factura_c"
        cli_doc = (tipo_sesion.get("cliente_doc") or "").strip()
        cli_nom = (tipo_sesion.get("cliente_nombre") or "").strip()

        total = float(total_var.get())
        try:
            pagos = _normalizar_pagos(pagos, total)
        except ValueError as e:
            messagebox.showwarning("Pago", str(e), parent=ventana)
            return
        if len(pagos) == 1:
            metodo = pagos[0]["metodo"]
        elif len(pagos) > 1:
            metodo = "MIXTO"

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
                pagos=pagos,
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
                "pagos": pagos,
            }

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
                ok_cae, info_cae = _emitir_fiscal_con_espera(venta_id, payload)
                if ok_cae == "interno":
                    emitir_fiscal = False
                    fiscal_info = {
                        "ticket_negro": True,
                        "cliente_doc": "",
                        "cliente_nombre": "",
                        "tipo_doc_rec": 99,
                        "nro_doc_rec": 0,
                        "pagos": pagos,
                    }
                    if isinstance(info_cae, dict):
                        fiscal_info.update(info_cae)
                        fiscal_info["pagos"] = pagos
                elif not ok_cae:
                    # Venta anulada: limpiar carrito y volver a elegir tipo
                    resetear_ticket()
                    tipo_sesion["modo"] = None
                    tipo_sesion["cliente_doc"] = ""
                    tipo_sesion["cliente_nombre"] = ""
                    ventana.after(150, lambda: elegir_tipo_comprobante(obligatorio=True))
                    return
                else:
                    fiscal_info.update(info_cae or {})
                    fiscal_info["pagos"] = pagos
                    if not fiscal_info.get("tipo_doc_rec"):
                        fiscal_info["tipo_doc_rec"] = (
                            80 if len(cli_doc) == 11 else (96 if cli_doc else 99)
                        )
                    if fiscal_info.get("nro_doc_rec") in (None, ""):
                        fiscal_info["nro_doc_rec"] = (
                            int(cli_doc) if cli_doc.isdigit() else 0
                        )
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

            pdf_path = None
            lineas_ticket = []
            auto_flag = str(cfg.get("ticket_auto_imprimir") or "1").strip()
            fue_interno = not emitir_fiscal

            if fue_interno:
                # Interno: solo PDF (sin térmica). PDF en background para no frenar la caja.
                snap = [dict(p) for p in productos_vendidos]
                _pdf_en_background(venta_id, total, dict(fiscal_info), snap, dict(cfg))
                flash_status(
                    "LISTO · $%s · %s · interno · PDF · #%s · escaneá el siguiente"
                    % (("%.2f" % total), metodo, venta_id),
                    ok=True,
                )

                resetear_ticket()
                # Seguir en ticket interno: no reabrir el cartel T/C
                tipo_sesion["modo"] = "interno"
                tipo_sesion["cliente_doc"] = ""
                tipo_sesion["cliente_nombre"] = ""
                cliente_resumen_var.set("Ticket interno (sin factura)")
                try:
                    codigo_entry.focus_set()
                except Exception:
                    pass
            else:
                try:
                    comp = generar_comprobante(
                        venta_id,
                        total,
                        fiscal_info=fiscal_info,
                        generar_pdf=True,
                        cfg=cfg,
                    )
                    pdf_path = comp.get("pdf_path")
                    lineas_ticket = comp.get("lineas") or []
                except Exception as e:
                    flash_status("Venta OK. Falló PDF: %s" % str(e)[:60], ok=False)

                # Solo imprime Factura C si hay CAE real
                tiene_cae = bool(str(fiscal_info.get("cae") or "").strip())
                auto_print = (
                    emitir_fiscal
                    and tiene_cae
                    and auto_flag == "1"
                    and bool(lineas_ticket)
                )
                if auto_print:
                    doc_name = "Factura C %s" % (fiscal_info.get("numero") or venta_id)
                    imprimir_factura_y_esperar(lineas_ticket, doc_name, venta_id)
                    flash_status(
                        "LISTO · $%s · %s · Factura C · #%s"
                        % (("%.2f" % total), metodo, venta_id),
                        ok=True,
                    )
                elif emitir_fiscal and tiene_cae and lineas_ticket:
                    # CAE OK pero auto-imprimir desactivado: preguntar
                    if messagebox.askyesno(
                        "Imprimir Factura C",
                        "La Factura C se emitió con CAE, pero la auto-impresión está en 0.\n\n"
                        "¿Imprimir ahora en la térmica?",
                        parent=ventana,
                    ):
                        doc_name = "Factura C %s" % (fiscal_info.get("numero") or venta_id)
                        imprimir_factura_y_esperar(lineas_ticket, doc_name, venta_id)
                    flash_status(
                        "LISTO · $%s · %s · Factura C · #%s"
                        % (("%.2f" % total), metodo, venta_id),
                        ok=True,
                    )
                elif emitir_fiscal:
                    flash_status(
                        "LISTO · Factura C sin imprimir (sin CAE) · #%s" % venta_id,
                        ok=False,
                    )

                resetear_ticket()
                tipo_sesion["modo"] = None
                tipo_sesion["cliente_doc"] = ""
                tipo_sesion["cliente_nombre"] = ""
                ventana.after(150, lambda: elegir_tipo_comprobante(obligatorio=True))
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
        # Si ya hay tipo de ticket elegido (o hay ítems), pedir confirmación.
        if tipo_sesion.get("modo") or productos_vendidos:
            if not messagebox.askyesno(
                "Cancelar venta",
                "¿Estás seguro de cancelar esta venta?",
                parent=ventana,
            ):
                return
            resetear_ticket()
            tipo_sesion["modo"] = None
            tipo_sesion["cliente_doc"] = ""
            tipo_sesion["cliente_nombre"] = ""
            cliente_resumen_var.set("Cliente: Consumidor Final")
            flash_status("Venta cancelada.", ok=False)
            ventana.after(150, lambda: elegir_tipo_comprobante(obligatorio=True))
            return
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

    cliente_resumen_var = tk.StringVar(value="Cliente: Consumidor Final")

    def volver_al_menu(event=None):
        if tipo_sesion.get("modo") or productos_vendidos:
            if not messagebox.askyesno(
                "Volver al menú",
                "Hay una venta en curso. ¿Salir y cancelar el ticket?",
                parent=ventana,
            ):
                return
        al_cerrar()

    ventana.protocol("WM_DELETE_WINDOW", volver_al_menu)

    # Layout
    top_frame = ttk.Frame(ventana, padding=10)
    top_frame.pack(fill='x')
    ttk.Label(top_frame, text="POS Venta - %s" % user_name, style="Header.TLabel").pack(side='left')
    ttk.Label(
        top_frame,
        text="  Primero tipo de ticket · F1 manual · F5/F6/F7 cobrar · F8 mixto",
        foreground="#475569",
    ).pack(side='left', padx=12)
    ttk.Button(top_frame, text="Volver al Menú", command=volver_al_menu).pack(side='right')

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
    b_mixto = tk.Button(
        metodos_frame,
        text="MIXTO\n(F8)",
        bg="#7c3aed",
        fg="white",
        activebackground="#6d28d9",
        activeforeground="white",
        font=("Segoe UI", 11, "bold"),
        width=12,
        height=2,
        command=cobrar_mixto,
    )
    b_mixto.grid(row=0, column=3, padx=4, pady=2)
    metodo_btns["MIXTO"] = b_mixto

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
        fg=ui_theme.SUCCESS,
        bg=ui_theme.BG,
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
    ventana.bind('<F8>', cobrar_mixto)

    ventana.after(100, lambda: elegir_tipo_comprobante(obligatorio=True))

    ventana.mainloop()
