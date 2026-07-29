"""Cierre de caja profesional con exportación Excel + PDF."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from ui import dialogs as messagebox

from pos_config import load_config
from services.cierre_caja import cerrar_caja, resumen_pendiente
from ui import theme as ui_theme


def _open_file(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def open_arqueo_panel(user_id, user_name):
    cfg = load_config()
    ventana = tk.Toplevel()
    ventana.title("Cierre de caja — %s" % user_name)
    ventana.geometry("1100x720")
    try:
        ventana.state("zoomed")
    except Exception:
        pass
    ventana.configure(bg=ui_theme.BG)

    fondo_var = tk.DoubleVar(value=0.0)
    efectivo_var = tk.DoubleVar(value=0.0)
    diferencia_var = tk.DoubleVar(value=0.0)
    esperado_var = tk.DoubleVar(value=0.0)
    observaciones_var = tk.StringVar()
    estado_var = tk.StringVar(value="")

    style = ttk.Style(ventana)
    ui_theme.apply_ttk_style(style)

    main = ttk.Frame(ventana, padding=16)
    main.pack(fill="both", expand=True)

    header = ttk.Frame(main)
    header.pack(fill="x", pady=(0, 10))
    ttk.Label(header, text="Cierre de caja", style="Title.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text="%s · Terminal %s · Cajero: %s"
        % (cfg.get("sucursal_nombre"), cfg.get("terminal_id"), user_name),
        style="Muted.TLabel",
    ).pack(anchor="w")

    body = ttk.Frame(main)
    body.pack(fill="both", expand=True)

    left = ttk.LabelFrame(body, text="Ventas pendientes de cierre", padding=10)
    left.pack(side="left", fill="both", expand=True, padx=(0, 8))

    cols = ("metodo", "tickets", "total")
    tree = ttk.Treeview(left, columns=cols, show="headings", height=8)
    tree.heading("metodo", text="Método de pago")
    tree.heading("tickets", text="Tickets")
    tree.heading("total", text="Total ($)")
    tree.column("metodo", width=180)
    tree.column("tickets", width=80, anchor="center")
    tree.column("total", width=120, anchor="e")
    tree.pack(fill="both", expand=True)

    detalle = ttk.Treeview(
        left,
        columns=("id", "hora", "metodo", "total"),
        show="headings",
        height=6,
    )
    detalle.heading("id", text="ID")
    detalle.heading("hora", text="Hora")
    detalle.heading("metodo", text="Método")
    detalle.heading("total", text="Total")
    detalle.column("id", width=60, anchor="center")
    detalle.column("hora", width=140)
    detalle.column("metodo", width=100)
    detalle.column("total", width=100, anchor="e")
    detalle.pack(fill="both", expand=True, pady=(10, 0))

    ttk.Label(left, text="Ajustes de caja (pendientes)", style="Muted.TLabel").pack(
        anchor="w", pady=(10, 2)
    )
    ajustes_tree = ttk.Treeview(
        left,
        columns=("id", "hora", "monto", "desde", "hacia"),
        show="headings",
        height=4,
    )
    ajustes_tree.heading("id", text="ID")
    ajustes_tree.heading("hora", text="Hora")
    ajustes_tree.heading("monto", text="Monto")
    ajustes_tree.heading("desde", text="Desde")
    ajustes_tree.heading("hacia", text="Hacia")
    ajustes_tree.column("id", width=50, anchor="center")
    ajustes_tree.column("hora", width=90)
    ajustes_tree.column("monto", width=80, anchor="e")
    ajustes_tree.column("desde", width=100)
    ajustes_tree.column("hacia", width=100)
    ajustes_tree.pack(fill="both", expand=True)

    right = ttk.LabelFrame(body, text="Arqueo de efectivo", padding=14)
    right.pack(side="right", fill="y", padx=(8, 0))

    stats = {
        "tickets": tk.StringVar(value="0"),
        "ajustes": tk.StringVar(value="0"),
        "sistema": tk.StringVar(value="$0.00"),
        "efectivo": tk.StringVar(value="$0.00"),
        "tarjeta": tk.StringVar(value="$0.00"),
        "mercadopago": tk.StringVar(value="$0.00"),
        "otros": tk.StringVar(value="$0.00"),
    }

    for label, var in [
        ("Tickets del turno", stats["tickets"]),
        ("Ajustes de caja", stats["ajustes"]),
        ("Total sistema", stats["sistema"]),
        ("Efectivo", stats["efectivo"]),
        ("Tarjeta", stats["tarjeta"]),
        ("Mercado Pago", stats["mercadopago"]),
        ("Otros", stats["otros"]),
    ]:
        row = ttk.Frame(right)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=20).pack(side="left")
        ttk.Label(row, textvariable=var, font=("Segoe UI", 10, "bold")).pack(side="right")

    ttk.Separator(right, orient="horizontal").pack(fill="x", pady=12)

    form = ttk.Frame(right)
    form.pack(fill="x")

    ttk.Label(form, text="Fondo inicial ($)").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(form, textvariable=fondo_var, width=14).grid(row=0, column=1, sticky="e", pady=4)

    ttk.Label(form, text="Efectivo contado ($)").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(form, textvariable=efectivo_var, width=14).grid(row=1, column=1, sticky="e", pady=4)

    ttk.Label(form, text="Efectivo esperado").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Label(form, textvariable=esperado_var, font=("Segoe UI", 11, "bold")).grid(
        row=2, column=1, sticky="e", pady=4
    )

    ttk.Label(form, text="Diferencia").grid(row=3, column=0, sticky="w", pady=4)
    diff_label = ttk.Label(form, textvariable=diferencia_var, style="DiffOk.TLabel")
    diff_label.grid(row=3, column=1, sticky="e", pady=4)

    ttk.Label(right, text="Observaciones").pack(anchor="w", pady=(12, 2))
    ttk.Entry(right, textvariable=observaciones_var, width=36).pack(fill="x")

    ttk.Label(right, textvariable=estado_var, style="Muted.TLabel", wraplength=260).pack(
        anchor="w", pady=(10, 0)
    )

    current_resumen = {"data": None}

    def refrescar():
        try:
            data = resumen_pendiente(user_id)
            current_resumen["data"] = data
            tree.delete(*tree.get_children())
            detalle.delete(*detalle.get_children())
            ajustes_tree.delete(*ajustes_tree.get_children())
            for metodo, bucket in sorted(data["por_metodo"].items()):
                tree.insert(
                    "",
                    "end",
                    values=(metodo, bucket["tickets"], "%.2f" % bucket["total"]),
                )
            for v in data["ventas"]:
                hora = str(v.get("fecha") or "")[-8:]
                detalle.insert(
                    "",
                    "end",
                    values=(
                        v["id"],
                        hora,
                        v.get("metodo_label") or v.get("metodo_pago") or "",
                        "%.2f" % float(v["total"] or 0),
                    ),
                )
            for aj in data.get("ajustes") or []:
                hora = str(aj.get("fecha") or "")[-8:]
                ajustes_tree.insert(
                    "",
                    "end",
                    values=(
                        aj.get("id"),
                        hora,
                        "%.2f" % float(aj.get("monto") or 0),
                        aj.get("metodo_desde") or "",
                        aj.get("metodo_hacia") or "",
                    ),
                )
            n_aj = int(data.get("cantidad_ajustes") or 0)
            stats["tickets"].set(str(data["cantidad_tickets"]))
            stats["ajustes"].set(str(n_aj))
            stats["sistema"].set("$%.2f" % data["total_sistema"])
            stats["efectivo"].set("$%.2f" % data["efectivo_sistema"])
            stats["tarjeta"].set("$%.2f" % data["tarjeta_sistema"])
            stats["mercadopago"].set("$%.2f" % data.get("mercadopago_sistema", 0))
            stats["otros"].set("$%.2f" % data["otros_sistema"])
            calcular()
            if data["cantidad_tickets"] == 0 and n_aj == 0:
                estado_var.set("No hay ventas ni ajustes pendientes de cierre.")
            elif n_aj:
                estado_var.set(
                    "%d tickets · %d ajustes listos para cerrar."
                    % (data["cantidad_tickets"], n_aj)
                )
            else:
                estado_var.set("%d tickets listos para cerrar." % data["cantidad_tickets"])
        except Exception as e:
            messagebox.showerror("Error", "No se pudieron cargar las ventas:\n%s" % e, parent=ventana)

    def calcular(*_args):
        data = current_resumen["data"] or {}
        esperado = float(data.get("efectivo_sistema") or 0) + float(fondo_var.get() or 0)
        esperado_var.set(round(esperado, 2))
        diff = float(efectivo_var.get() or 0) - esperado
        diferencia_var.set(round(diff, 2))
        diff_label.configure(style="DiffOk.TLabel" if abs(diff) < 0.01 else "DiffBad.TLabel")

    def confirmar_cierre():
        data = current_resumen["data"]
        n_aj = int((data or {}).get("cantidad_ajustes") or 0)
        if not data or (data["cantidad_tickets"] == 0 and n_aj == 0):
            messagebox.showwarning("Cierre", "No hay ventas ni ajustes para cerrar.", parent=ventana)
            return
        calcular()
        if not messagebox.askyesno(
            "Confirmar cierre",
            "¿Confirmás el cierre de caja?\n\n"
            "Tickets: %d\nAjustes: %d\nTotal sistema: $%.2f\nDiferencia: $%.2f\n\n"
            "Se generará Excel y PDF."
            % (
                data["cantidad_tickets"],
                n_aj,
                data["total_sistema"],
                diferencia_var.get(),
            ),
            parent=ventana,
        ):
            return
        try:
            result = cerrar_caja(
                usuario_id=user_id,
                user_name=user_name,
                efectivo_contado=float(efectivo_var.get() or 0),
                fondo_inicial=float(fondo_var.get() or 0),
                observaciones=observaciones_var.get().strip(),
            )
            msg = (
                "Cierre #%s registrado.\n\nExcel:\n%s\n\nPDF:\n%s"
                % (result["arqueo_id"], result["excel_path"], result["pdf_path"])
            )
            if messagebox.askyesno("Cierre OK", msg + "\n\n¿Abrir el Excel ahora?", parent=ventana):
                _open_file(result["excel_path"])
            fondo_var.set(0.0)
            efectivo_var.set(0.0)
            observaciones_var.set("")
            refrescar()
        except Exception as e:
            messagebox.showerror("Error", "No se pudo cerrar la caja:\n%s" % e, parent=ventana)

    def cancelar():
        if messagebox.askyesno("Salir", "¿Cerrar esta ventana?", parent=ventana):
            ventana.destroy()

    btns = ttk.Frame(main)
    btns.pack(fill="x", pady=(12, 0))
    ttk.Button(btns, text="Actualizar", command=refrescar).pack(side="left", padx=4)
    ttk.Button(btns, text="Calcular diferencia", command=calcular).pack(side="left", padx=4)
    ttk.Button(btns, text="Cerrar caja y exportar Excel", command=confirmar_cierre).pack(
        side="left", padx=4
    )
    ttk.Button(btns, text="Volver al Menú", command=cancelar).pack(side="right", padx=4)

    fondo_var.trace_add("write", calcular)
    efectivo_var.trace_add("write", calcular)

    ventana.bind("<Escape>", lambda e: cancelar())
    ventana.protocol("WM_DELETE_WINDOW", cancelar)
    refrescar()
