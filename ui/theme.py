"""Tema visual unificado ROD POS (estética slate del ticket de venta)."""
from __future__ import annotations

BG = "#0f172a"
BG_CARD = "#1e293b"
BG_INPUT = "#334155"
FG = "#f8fafc"
FG_MUTED = "#94a3b8"
FG_SOFT = "#e2e8f0"
ACCENT = "#2563eb"
SUCCESS = "#16a34a"
DANGER = "#dc2626"
WARNING = "#f59e0b"
NEUTRAL = "#64748b"
OK_GREEN = "#166534"
ERR_RED = "#b91c1c"


def apply_window(win, *, zoomed: bool = False) -> None:
    win.configure(bg=BG)
    if zoomed:
        try:
            win.state("zoomed")
        except Exception:
            pass


def apply_ttk_style(style) -> None:
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_INPUT, borderwidth=0)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI", 18, "bold"))
    style.configure("Header.TLabel", background=BG, foreground=FG, font=("Segoe UI", 14, "bold"))
    style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=BG_CARD, foreground=FG)
    style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
    style.map(
        "TButton",
        background=[("active", ACCENT), ("!disabled", BG_CARD)],
        foreground=[("!disabled", FG)],
    )
    style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=10)
    style.map(
        "Accent.TButton",
        background=[("active", "#1d4ed8"), ("!disabled", ACCENT)],
        foreground=[("!disabled", "white")],
    )
    style.configure("Success.TButton", font=("Segoe UI", 11, "bold"), padding=10)
    style.map(
        "Success.TButton",
        background=[("active", "#15803d"), ("!disabled", SUCCESS)],
        foreground=[("!disabled", "white")],
    )
    style.configure("Danger.TButton", font=("Segoe UI", 11, "bold"), padding=10)
    style.map(
        "Danger.TButton",
        background=[("active", "#b91c1c"), ("!disabled", DANGER)],
        foreground=[("!disabled", "white")],
    )
    style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG, insertcolor=FG)
    style.configure("TCombobox", fieldbackground=BG_INPUT, foreground=FG, background=BG_INPUT)
    style.map("TCombobox", fieldbackground=[("readonly", BG_INPUT)], foreground=[("readonly", FG)])
    style.configure(
        "Treeview",
        background=BG_CARD,
        foreground=FG,
        fieldbackground=BG_CARD,
        rowheight=28,
        borderwidth=0,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Treeview.Heading",
        background=BG_INPUT,
        foreground=FG,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
    )
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
    style.configure("TLabelframe", background=BG, foreground=FG)
    style.configure("TLabelframe.Label", background=BG, foreground=FG_MUTED, font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_MUTED, padding=[14, 8])
    style.map(
        "TNotebook.Tab",
        background=[("selected", ACCENT)],
        foreground=[("selected", "white")],
    )
    style.configure("TSeparator", background=BG_INPUT)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG_CARD)
    style.configure("DiffOk.TLabel", background=BG, foreground=SUCCESS, font=("Segoe UI", 12, "bold"))
    style.configure("DiffBad.TLabel", background=BG, foreground=DANGER, font=("Segoe UI", 12, "bold"))


def make_button(parent, text, command, *, kind="neutral", width=28, height=2, font_size=12):
    import tkinter as tk

    colors = {
        "accent": (ACCENT, "#1d4ed8"),
        "success": (SUCCESS, "#15803d"),
        "danger": (DANGER, "#b91c1c"),
        "neutral": (NEUTRAL, "#475569"),
        "warning": (WARNING, "#d97706"),
    }
    bg, hover = colors.get(kind, colors["neutral"])
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg="white",
        activebackground=hover,
        activeforeground="white",
        disabledforeground="#cbd5e1",
        font=("Segoe UI", font_size, "bold"),
        borderwidth=0,
        highlightthickness=0,
        width=width,
        height=height,
        cursor="hand2",
        relief="flat",
        padx=4,
        pady=2,
    )

    def on_enter(_e=None):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=hover)

    def on_leave(_e=None):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def fade_in(widget, steps: int = 8, delay_ms: int = 18) -> None:
    """Aparece el widget con un pequeño escalonado (sensación más fluida)."""
    try:
        widget.lift()
    except Exception:
        pass
    # En Tk no hay alpha real en widgets hijos; usamos un reveal por after.
    try:
        widget.update_idletasks()
    except Exception:
        pass
    # No-op visual seguro: deja el hook por si se quiere expandir.
    _ = (steps, delay_ms)


def stagger_show(widgets, *, start_ms: int = 40, step_ms: int = 45) -> None:
    """Muestra widgets en cascada para que el panel no 'salte' de golpe."""
    for i, w in enumerate(widgets):
        try:
            w.pack_forget()
        except Exception:
            pass

        def _show(widget=w, delay=start_ms + i * step_ms):
            def _do():
                try:
                    widget.pack(**getattr(widget, "_pack_opts", {}))
                except Exception:
                    try:
                        widget.pack()
                    except Exception:
                        pass

            widget.after(delay, _do)

        _show()
