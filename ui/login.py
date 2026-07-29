import tkinter as tk
from ui import dialogs as messagebox
import sqlite3
import os
import sys
from licencia import verificar_licencia
from db_init import get_db_path
from ui import theme as ui_theme

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


def resource_path(relative_path):
    """Para archivos empaquetados (imágenes, etc.) dentro del exe."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def open_login(callback_vendedor, callback_admin):
    ventana = tk.Tk()
    ventana.title("ROD POS - Login")
    ventana.geometry("420x400")
    ventana.resizable(False, False)
    ui_theme.apply_window(ventana)

    try:
        ventana.iconbitmap(resource_path("ui/images/logo.ico"))
    except Exception:
        pass

    codigo_var = tk.StringVar()
    status_var = tk.StringVar(value="")
    busy = {"on": False}

    wrap = tk.Frame(ventana, bg=ui_theme.BG)
    wrap.place(relx=0.5, rely=0.5, anchor="center")

    logo_holder = tk.Frame(wrap, bg=ui_theme.BG)
    logo_holder.pack(pady=(0, 22))

    try:
        if Image is not None and ImageTk is not None:
            logo_path = resource_path("ui/images/logopos.png")
            img = Image.open(logo_path)
            try:
                img = img.resize((200, 68), Image.LANCZOS)
            except AttributeError:
                img = img.resize((200, 68), Image.ANTIALIAS)
            logo_img = ImageTk.PhotoImage(img)
            logo_label = tk.Label(logo_holder, image=logo_img, bg=ui_theme.BG)
            logo_label.image = logo_img
            logo_label.pack()
    except Exception:
        pass

    card = tk.Frame(wrap, bg=ui_theme.BG_CARD, padx=28, pady=24)
    card.pack(fill="x")

    # Contenedor del campo para centrar visualmente el input
    entry_wrap = tk.Frame(card, bg=ui_theme.BG_INPUT, padx=2, pady=2)
    entry_wrap.pack(fill="x", pady=(0, 16))

    codigo_entry = tk.Entry(
        entry_wrap,
        textvariable=codigo_var,
        font=("Segoe UI", 18),
        show="*",
        justify="center",
        bg=ui_theme.BG_INPUT,
        fg=ui_theme.FG,
        insertbackground=ui_theme.FG,
        relief="flat",
        highlightthickness=0,
        bd=0,
    )
    codigo_entry.pack(fill="x", ipady=10, padx=8)

    status_lbl = tk.Label(
        card,
        textvariable=status_var,
        bg=ui_theme.BG_CARD,
        fg=ui_theme.FG_MUTED,
        font=("Segoe UI", 9),
        wraplength=280,
    )
    status_lbl.pack(pady=(0, 10))

    def set_status(msg, ok=True):
        status_var.set(msg or "")
        status_lbl.configure(fg=ui_theme.SUCCESS if ok else ui_theme.DANGER)

    def iniciar_sesion(_event=None):
        if busy["on"]:
            return "break"
        codigo = codigo_var.get().strip()
        if not codigo:
            set_status("Ingresá tu código", ok=False)
            codigo_entry.focus_set()
            return "break"

        busy["on"] = True
        btn_ingresar.configure(state="disabled", text="INGRESANDO…")
        set_status("Validando…", ok=True)
        ventana.update_idletasks()

        conn = None
        try:
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute(
                "SELECT id, nombre, es_admin FROM usuarios WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            usuario = c.fetchone()
        except sqlite3.Error as e:
            busy["on"] = False
            btn_ingresar.configure(state="normal", text="INGRESAR")
            set_status("Error de base de datos", ok=False)
            messagebox.showerror("Error BD", "No se pudo conectar con la base de datos.\n" + str(e), parent=ventana)
            return "break"
        finally:
            if conn is not None:
                conn.close()

        if not usuario:
            busy["on"] = False
            btn_ingresar.configure(state="normal", text="INGRESAR")
            codigo_var.set("")
            set_status("Código inválido", ok=False)
            codigo_entry.focus_set()
            return "break"

        user_id, nombre, es_admin = usuario

        if es_admin:
            ventana.destroy()
            try:
                callback_admin(user_id, nombre)
            except Exception as e:
                messagebox.showerror("Error", "No se pudo abrir el panel de administración.\n" + str(e))
                open_login(callback_vendedor=callback_vendedor, callback_admin=callback_admin)
            return "break"

        if not verificar_licencia():
            busy["on"] = False
            btn_ingresar.configure(state="normal", text="INGRESAR")
            messagebox.showerror(
                "Licencia inválida",
                "La licencia está vencida o no es válida.\nContactá al administrador.",
                parent=ventana,
            )
            return "break"

        set_status("Bienvenido/a %s" % nombre, ok=True)
        ventana.after(120, lambda: _entrar_vendedor(user_id, nombre))
        return "break"

    def _entrar_vendedor(user_id, nombre):
        ventana.destroy()
        try:
            callback_vendedor(user_id, nombre)
        except Exception as e:
            messagebox.showerror("Error", "No se pudo abrir el menú.\n" + str(e))
            open_login(callback_vendedor=callback_vendedor, callback_admin=callback_admin)

    btn_ingresar = ui_theme.make_button(
        card, "INGRESAR", iniciar_sesion, kind="accent", width=20, height=2, font_size=12
    )
    btn_ingresar.pack()

    # Focus ring suave al entrar/salir del campo
    def on_focus_in(_e=None):
        entry_wrap.configure(bg=ui_theme.ACCENT)

    def on_focus_out(_e=None):
        entry_wrap.configure(bg=ui_theme.BG_INPUT)

    codigo_entry.bind("<FocusIn>", on_focus_in)
    codigo_entry.bind("<FocusOut>", on_focus_out)
    codigo_entry.bind("<Return>", iniciar_sesion)
    ventana.bind("<Return>", iniciar_sesion)
    ventana.bind("<Escape>", lambda e: ventana.destroy())

    codigo_entry.focus_set()
    ventana.after(30, lambda: ventana.eval("tk::PlaceWindow . center"))
    ventana.mainloop()
