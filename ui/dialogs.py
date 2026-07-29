"""Diálogos modales con la estética dark de ROD POS."""
from __future__ import annotations

import tkinter as tk


def _center_on_parent(win, parent=None):
    win.update_idletasks()
    w = win.winfo_width() or 420
    h = win.winfo_height() or 200
    if parent is not None:
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            win.geometry("+%d+%d" % (x, y))
            return
        except Exception:
            pass
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry("+%d+%d" % ((sw - w) // 2, (sh - h) // 2))


def _dialog(title, message, *, kind="info", buttons=None, parent=None, default=None):
    """
    kind: info | error | warning | question
    buttons: list of (label, value, kind_btn)
    """
    from ui import theme as ui_theme

    root = parent
    if root is None:
        try:
            root = tk._default_root
        except Exception:
            root = None

    top = tk.Toplevel(root) if root is not None else tk.Tk()
    top.title(title or "ROD POS")
    top.configure(bg=ui_theme.BG)
    top.resizable(False, False)
    try:
        top.transient(root)
    except Exception:
        pass
    top.grab_set()
    top.attributes("-topmost", True)
    top.after(80, lambda: top.attributes("-topmost", False))

    result = {"value": default}

    accent = {
        "info": ui_theme.ACCENT,
        "error": ui_theme.DANGER,
        "warning": ui_theme.WARNING,
        "question": ui_theme.ACCENT,
    }.get(kind, ui_theme.ACCENT)

    wrap = tk.Frame(top, bg=ui_theme.BG, padx=22, pady=18)
    wrap.pack(fill="both", expand=True)

    header = tk.Frame(wrap, bg=ui_theme.BG)
    header.pack(fill="x", pady=(0, 12))
    tk.Frame(header, bg=accent, width=4, height=22).pack(side="left", padx=(0, 10))
    tk.Label(
        header,
        text=title or "",
        bg=ui_theme.BG,
        fg=ui_theme.FG,
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).pack(side="left", fill="x", expand=True)

    card = tk.Frame(wrap, bg=ui_theme.BG_CARD, padx=18, pady=16)
    card.pack(fill="both", expand=True)
    tk.Label(
        card,
        text=message or "",
        bg=ui_theme.BG_CARD,
        fg=ui_theme.FG_SOFT,
        font=("Segoe UI", 11),
        justify="left",
        wraplength=380,
        anchor="w",
    ).pack(fill="x")

    btns = tk.Frame(wrap, bg=ui_theme.BG)
    btns.pack(fill="x", pady=(16, 0))

    def choose(val):
        result["value"] = val
        top.destroy()

    if not buttons:
        buttons = [("OK", True, "accent")]

    # Derecha → izquierda visual: primer botón a la derecha suele ser el primario
    for i, (label, value, bkind) in enumerate(reversed(buttons)):
        b = ui_theme.make_button(
            btns,
            label,
            lambda v=value: choose(v),
            kind=bkind,
            width=max(12, min(22, len(str(label)) + 2)),
            height=1,
            font_size=10,
        )
        b.pack(side="right", padx=(8, 0) if i else 0)
        if i == 0:
            top.after(30, b.focus_set)

    def on_escape(_e=None):
        # Escape = último valor "cancel/no" si existe, si no cierra
        for _label, value, _k in buttons:
            if value in (False, None):
                choose(value)
                return
        choose(buttons[-1][1])

    def on_return(_e=None):
        # Enter = primer botón (primario)
        choose(buttons[0][1])

    top.bind("<Escape>", on_escape)
    top.bind("<Return>", on_return)
    top.protocol("WM_DELETE_WINDOW", on_escape)

    _center_on_parent(top, root)
    top.wait_window()
    return result["value"]


def showinfo(title, message, parent=None, **_kwargs):
    return _dialog(title, message, kind="info", parent=parent, buttons=[("OK", True, "accent")])


def showerror(title, message, parent=None, **_kwargs):
    return _dialog(title, message, kind="error", parent=parent, buttons=[("OK", True, "danger")])


def showwarning(title, message, parent=None, **_kwargs):
    return _dialog(title, message, kind="warning", parent=parent, buttons=[("OK", True, "warning")])


def askyesno(title, message, parent=None, **_kwargs):
    return bool(
        _dialog(
            title,
            message,
            kind="question",
            parent=parent,
            default=False,
            buttons=[("Sí", True, "success"), ("No", False, "neutral")],
        )
    )


def askretrycancel(title, message, parent=None, **_kwargs):
    return bool(
        _dialog(
            title,
            message,
            kind="warning",
            parent=parent,
            default=False,
            buttons=[("Reintentar", True, "accent"), ("Cancelar", False, "neutral")],
        )
    )


def askyesnocancel(title, message, parent=None, **_kwargs):
    return _dialog(
        title,
        message,
        kind="question",
        parent=parent,
        default=None,
        buttons=[
            ("Sí", True, "success"),
            ("No", False, "danger"),
            ("Cancelar", None, "neutral"),
        ],
    )


def askchoice(title, message, choices, parent=None, default=None):
    """
    choices: lista de (etiqueta, valor, kind_btn)
    Devuelve el valor elegido (o default si cierra).
    """
    return _dialog(
        title,
        message,
        kind="question",
        parent=parent,
        default=default,
        buttons=list(choices),
    )


def prompt_textos(title, campos, parent=None):
    """
    Formulario modal simple.
    campos: lista de (label, valor_inicial)
    Devuelve lista de strings o None si cancela.
    """
    from ui import theme as ui_theme

    root = parent
    if root is None:
        try:
            root = tk._default_root
        except Exception:
            root = None

    top = tk.Toplevel(root) if root is not None else tk.Tk()
    top.title(title or "ROD POS")
    top.configure(bg=ui_theme.BG)
    top.resizable(False, False)
    try:
        top.transient(root)
    except Exception:
        pass
    top.grab_set()

    result = {"ok": False, "values": None}

    wrap = tk.Frame(top, bg=ui_theme.BG, padx=22, pady=18)
    wrap.pack(fill="both", expand=True)
    tk.Label(
        wrap,
        text=title or "",
        bg=ui_theme.BG,
        fg=ui_theme.FG,
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(0, 12))

    card = tk.Frame(wrap, bg=ui_theme.BG_CARD, padx=16, pady=14)
    card.pack(fill="both", expand=True)
    entries = []
    for i, (lab, inicial) in enumerate(campos or []):
        fila = tk.Frame(card, bg=ui_theme.BG_CARD)
        fila.pack(fill="x", pady=5)
        tk.Label(
            fila,
            text=lab,
            bg=ui_theme.BG_CARD,
            fg=ui_theme.FG_SOFT,
            font=("Segoe UI", 10),
            width=14,
            anchor="e",
        ).pack(side="left")
        e = tk.Entry(fila, font=("Segoe UI", 12), width=28)
        e.pack(side="left", padx=8)
        e.insert(0, str(inicial or ""))
        entries.append(e)
        if i == 0:
            top.after(40, e.focus_set)

    def aceptar(_e=None):
        result["ok"] = True
        result["values"] = [e.get() for e in entries]
        top.destroy()

    def cancelar(_e=None):
        result["ok"] = False
        result["values"] = None
        top.destroy()

    btns = tk.Frame(wrap, bg=ui_theme.BG)
    btns.pack(fill="x", pady=(14, 0))
    ui_theme.make_button(
        btns, "Cancelar", cancelar, kind="neutral", width=12, height=1, font_size=10
    ).pack(side="right", padx=(8, 0))
    ui_theme.make_button(
        btns, "Continuar", aceptar, kind="success", width=12, height=1, font_size=10
    ).pack(side="right")

    top.bind("<Return>", aceptar)
    top.bind("<Escape>", cancelar)
    top.protocol("WM_DELETE_WINDOW", cancelar)
    _center_on_parent(top, root)
    top.wait_window()
    return result["values"] if result["ok"] else None


def load_logo(parent, *, width=200, height=68, bg=None):
    """Carga el logo en un Label; None si no está disponible."""
    import os
    import sys

    from ui import theme as ui_theme

    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None

    candidates = []
    try:
        candidates.append(os.path.join(sys._MEIPASS, "ui", "images", "logopos.png"))  # type: ignore[attr-defined]
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "images", "logopos.png"))
    candidates.append(os.path.join(os.path.abspath("."), "ui", "images", "logopos.png"))

    path = next((p for p in candidates if os.path.isfile(p)), None)
    if not path:
        return None
    try:
        img = Image.open(path)
        try:
            img = img.resize((width, height), Image.LANCZOS)
        except AttributeError:
            img = img.resize((width, height), Image.ANTIALIAS)
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(parent, image=photo, bg=bg or ui_theme.BG)
        lbl.image = photo
        return lbl
    except Exception:
        return None
