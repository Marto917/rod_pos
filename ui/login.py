import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import sys
from licencia import verificar_licencia
from db_init import get_db_path
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
    ventana.geometry("300x210")
    ventana.resizable(False, False)

    try:
        ventana.iconbitmap(resource_path("ui/images/logo.ico"))
    except Exception:
        pass

    codigo_var = tk.StringVar()

    def iniciar_sesion():
        codigo = codigo_var.get().strip()
        if not codigo:
            messagebox.showwarning("Error", "Ingrese un código")
            return

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
            messagebox.showerror("Error BD", "No se pudo conectar con la base de datos.\n" + str(e))
            return
        finally:
            if conn is not None:
                conn.close()

        if not usuario:
            messagebox.showerror("Error", "Código inválido")
            return

        user_id, nombre, es_admin = usuario

        if es_admin:
            ventana.destroy()
            try:
                callback_admin(user_id, nombre)
            except Exception as e:
                messagebox.showerror("Error", "No se pudo abrir el panel de administración.\n" + str(e))
                open_login(callback_vendedor=callback_vendedor, callback_admin=callback_admin)
            return

        if not verificar_licencia():
            messagebox.showerror(
                "Licencia inválida",
                "La licencia está vencida o no es válida.\nContactá al administrador.",
            )
            return

        ventana.destroy()
        try:
            callback_vendedor(user_id, nombre)
        except Exception as e:
            messagebox.showerror("Error", "No se pudo abrir el menú.\n" + str(e))
            open_login(callback_vendedor=callback_vendedor, callback_admin=callback_admin)

    main_frame = ttk.Frame(ventana)
    main_frame.pack(pady=20, padx=20, fill='both', expand=True)

    ttk.Label(main_frame, text="Ingrese su código:", font=('Arial', 10)).pack()
    codigo_entry = ttk.Entry(main_frame, textvariable=codigo_var, font=('Arial', 12), width=15)
    codigo_entry.pack(pady=5)
    codigo_entry.focus()

    ttk.Button(
        main_frame, 
        text="Ingresar", 
        command=iniciar_sesion, 
        style='TButton',
        width=15
    ).pack(pady=10)

    try:
        if Image is not None and ImageTk is not None:
            logo_path = resource_path("ui/images/logopos.png")
            img = Image.open(logo_path)
            try:
                img = img.resize((180, 60), Image.LANCZOS)
            except AttributeError:
                img = img.resize((180, 60), Image.ANTIALIAS)
            logo_img = ImageTk.PhotoImage(img)
            logo_label = ttk.Label(main_frame, image=logo_img)
            logo_label.image = logo_img
            logo_label.pack(pady=(0, 15))
        else:
            ttk.Label(main_frame, text="ROD POS", font=('Arial', 14, 'bold')).pack(pady=(0, 15))
    except Exception:
        ttk.Label(main_frame, text="ROD POS", font=('Arial', 14, 'bold')).pack(pady=(0, 15))

    ventana.bind('<Return>', lambda e: iniciar_sesion())
    ventana.eval('tk::PlaceWindow . center')
    ventana.mainloop()
