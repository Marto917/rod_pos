import threading
import tkinter as tk

from .stock_view import open_stock_view
from .recepcion import open_recepcion_panel
from .sales import open_sales_panel
from .arqueo import open_arqueo_panel
from .arca_pendientes import open_arca_pendientes_panel
from ui import theme as ui_theme
from ui import dialogs as messagebox
from ui.dialogs import load_logo
from services.arca_status import consultar_estado_arca


def open_vendor_panel(user_id, user_name):
    ventana = tk.Tk()
    ventana.title("Menú Vendedor - %s" % user_name)
    ventana.geometry("900x700")
    ui_theme.apply_window(ventana, zoomed=True)

    nav = {"index": 0, "buttons": []}

    def abrir_panel(nombre, abrir_fn):
        try:
            ventana.configure(cursor="watch")
            ventana.update_idletasks()
        except Exception:
            pass

        def _go():
            try:
                abrir_fn()
            except Exception as e:
                messagebox.showerror(
                    "Error",
                    "No se pudo abrir %s.\n%s" % (nombre, str(e)),
                    parent=ventana,
                )
            finally:
                try:
                    ventana.configure(cursor="")
                    ventana.lift()
                    ventana.focus_force()
                    _resaltar_nav()
                except Exception:
                    pass

        ventana.after(10, _go)

    # Indicador ARCA (esquina superior derecha)
    arca_bar = tk.Frame(ventana, bg=ui_theme.BG)
    arca_bar.place(relx=1.0, y=14, anchor="ne", x=-18)

    arca_canvas = tk.Canvas(
        arca_bar,
        width=14,
        height=14,
        bg=ui_theme.BG,
        highlightthickness=0,
        bd=0,
    )
    arca_dot = arca_canvas.create_oval(2, 2, 12, 12, fill=ui_theme.NEUTRAL, outline="")
    arca_canvas.pack(side="left", padx=(0, 6))
    arca_label = tk.Label(
        arca_bar,
        text="ARCA",
        font=("Segoe UI", 10, "bold"),
        bg=ui_theme.BG,
        fg=ui_theme.FG_MUTED,
    )
    arca_label.pack(side="left")

    arca_state = {"job": None, "alive": True}

    def _aplicar_estado_arca(ok, detalle=""):
        color = ui_theme.SUCCESS if ok else ui_theme.DANGER
        try:
            arca_canvas.itemconfigure(arca_dot, fill=color)
            tip = "ARCA operativo" if ok else "ARCA con problemas"
            if detalle:
                tip = "%s\n%s" % (tip, detalle)
            arca_label.configure(fg=ui_theme.FG_SOFT if ok else ui_theme.DANGER)
            arca_bar.configure(cursor="hand2")
            arca_canvas.configure(cursor="hand2")
            arca_label.configure(cursor="hand2")
            arca_bar._tip = tip  # noqa: SLF001
        except Exception:
            pass

    def _tick_arca():
        if not arca_state["alive"]:
            return

        def work():
            try:
                res = consultar_estado_arca()
                ok = bool(res.get("ok"))
                detalle = res.get("detalle") or ""
            except Exception as e:
                ok = False
                detalle = str(e)

            def apply():
                if not arca_state["alive"]:
                    return
                _aplicar_estado_arca(ok, detalle)
                arca_state["job"] = ventana.after(120000, _tick_arca)

            try:
                ventana.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _mostrar_detalle_arca(_event=None):
        tip = getattr(arca_bar, "_tip", None) or "Consultando estado ARCA…"
        messagebox.showinfo(
            "Estado ARCA",
            tip + "\n\nFuente: gestioncomercio.com.ar/statusarca/",
            parent=ventana,
        )

    arca_bar.bind("<Button-1>", _mostrar_detalle_arca)
    arca_canvas.bind("<Button-1>", _mostrar_detalle_arca)
    arca_label.bind("<Button-1>", _mostrar_detalle_arca)

    wrap = tk.Frame(ventana, bg=ui_theme.BG)
    wrap.place(relx=0.5, rely=0.45, anchor="center")

    logo = load_logo(wrap, width=220, height=74, bg=ui_theme.BG)
    if logo is not None:
        logo.pack(pady=(0, 18))
    else:
        tk.Label(
            wrap,
            text="ROD POS",
            font=("Segoe UI", 32, "bold"),
            bg=ui_theme.BG,
            fg=ui_theme.FG,
        ).pack(pady=(0, 8))

    tk.Label(
        wrap,
        text="Bienvenido/a %s" % user_name,
        font=("Segoe UI", 14),
        bg=ui_theme.BG,
        fg=ui_theme.FG_MUTED,
    ).pack(pady=(0, 22))

    def cerrar_sesion():
        if messagebox.askyesno("Cerrar sesión", "¿Salir al login?", parent=ventana):
            _on_close()

    opciones = [
        ("TICKET DE VENTA", lambda: abrir_panel("Ticket de venta", lambda: open_sales_panel(user_id, user_name)), "success"),
        ("CONSULTAR STOCK", lambda: abrir_panel("Consultar stock", lambda: open_stock_view(user_id, user_name)), "accent"),
        ("RECEPCIÓN DE PRODUCTOS", lambda: abrir_panel("Recepción", lambda: open_recepcion_panel(user_id, user_name)), "warning"),
        ("CIERRE DE CAJA", lambda: abrir_panel("Cierre de caja", lambda: open_arqueo_panel(user_id, user_name)), "neutral"),
        ("PENDIENTES ARCA", lambda: abrir_panel("Pendientes ARCA", lambda: open_arca_pendientes_panel(user_id, user_name)), "neutral"),
        ("CERRAR SESIÓN", cerrar_sesion, "danger"),
    ]

    for texto, comando, kind in opciones:
        btn = ui_theme.make_button(
            wrap,
            texto,
            comando,
            kind=kind,
            width=36,
            height=2,
            font_size=13,
        )
        btn.pack(pady=7)
        nav["buttons"].append(btn)

    hint = tk.Label(
        wrap,
        text="↑↓ navegar · Enter abrir · 1-6 atajo · Esc salir",
        font=("Segoe UI", 10),
        bg=ui_theme.BG,
        fg=ui_theme.NEUTRAL,
    )
    hint.pack(pady=(16, 0))

    def _resaltar_nav():
        buttons = nav["buttons"]
        if not buttons:
            return
        nav["index"] = max(0, min(nav["index"], len(buttons) - 1))
        for i, btn in enumerate(buttons):
            if i == nav["index"]:
                btn.configure(highlightthickness=2, highlightbackground="white", highlightcolor="white")
            else:
                btn.configure(highlightthickness=0)

    def _nav_move(delta):
        nav["index"] = (nav["index"] + delta) % len(nav["buttons"])
        _resaltar_nav()
        try:
            nav["buttons"][nav["index"]].focus_set()
        except Exception:
            pass

    def _nav_activate(_e=None):
        try:
            nav["buttons"][nav["index"]].invoke()
        except Exception:
            pass
        return "break"

    ventana.bind("<Up>", lambda e: (_nav_move(-1), "break")[1])
    ventana.bind("<Down>", lambda e: (_nav_move(1), "break")[1])
    ventana.bind("<Return>", _nav_activate)
    ventana.bind("<Escape>", lambda e: cerrar_sesion())

    def _goto(idx):
        nav["index"] = idx
        _resaltar_nav()
        _nav_activate()

    for i in range(6):
        ventana.bind(str(i + 1), lambda e, idx=i: _goto(idx))

    ventana.bind("<Control-t>", lambda e: abrir_panel("Ticket de venta", lambda: open_sales_panel(user_id, user_name)))
    ventana.bind("<Control-l>", lambda e: abrir_panel("Consultar stock", lambda: open_stock_view(user_id, user_name)))
    ventana.bind("<Control-r>", lambda e: abrir_panel("Recepción", lambda: open_recepcion_panel(user_id, user_name)))
    ventana.bind("<Control-p>", lambda e: abrir_panel("Pendientes ARCA", lambda: open_arca_pendientes_panel(user_id, user_name)))

    def _on_close():
        arca_state["alive"] = False
        job = arca_state.get("job")
        if job:
            try:
                ventana.after_cancel(job)
            except Exception:
                pass
        ventana.destroy()

    ventana.protocol("WM_DELETE_WINDOW", _on_close)
    _resaltar_nav()
    _tick_arca()
    ventana.after(80, lambda: nav["buttons"][0].focus_set() if nav["buttons"] else None)
    ventana.mainloop()
