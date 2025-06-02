import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from PIL import Image, ImageTk
import os
import sys

def resource_path(relative_path):
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
    
    # Configurar ícono de la ventana
    try:
        ventana.iconbitmap(resource_path("ui/images/logo.ico"))
    except Exception as e:
        print(f"No se pudo cargar el ícono: {str(e)}")

    # Variable para el campo de código
    codigo_var = tk.StringVar()

    # Función para iniciar sesión
    def iniciar_sesion():
        codigo = codigo_var.get().strip()
        
        if not codigo:
            messagebox.showwarning("Error", "Ingrese un código")
            return
            
        try:
            conn = sqlite3.connect(resource_path('db/pos.db'))
            c = conn.cursor()
            
            c.execute("SELECT id, nombre, es_admin FROM usuarios WHERE codigo = ? AND activo = 1", (codigo,))
            usuario = c.fetchone()
            
            if usuario:
                ventana.destroy()
                if usuario[2]:  # es_admin
                    callback_admin(usuario[0], usuario[1])
                else:
                    from ui.menu_vendedor import open_vendor_panel
                    open_vendor_panel(usuario[0], usuario[1])
            else:
                messagebox.showerror("Error", "Código inválido")
                
        except sqlite3.Error as e:
            messagebox.showerror("Error BD", str(e))
        finally:
            if 'conn' in locals():
                conn.close()

    # Contenedor principal
    main_frame = ttk.Frame(ventana)
    main_frame.pack(pady=20, padx=20, fill='both', expand=True)


    ttk.Label(main_frame, text="Ingrese su código:", font=('Arial', 10)).pack()
    codigo_entry = ttk.Entry(main_frame, textvariable=codigo_var, font=('Arial', 12), width=15)
    codigo_entry.pack(pady=5)
    codigo_entry.focus()

    # Botón de ingreso
    ttk.Button(
        main_frame, 
        text="Ingresar", 
        command=iniciar_sesion, 
        style='TButton',
        width=15
    ).pack(pady=10)

    # Cargar y mostrar logo
    try:
        logo_path = resource_path("ui/images/logopos.png")
        img = Image.open(logo_path)
        img = img.resize((180, 60), Image.LANCZOS)
        logo_img = ImageTk.PhotoImage(img)
        
        logo_label = ttk.Label(main_frame, image=logo_img)
        logo_label.image = logo_img  
        logo_label.pack(pady=(0, 15))
    except Exception as e:
        print(f"Error cargando logo: {str(e)}")
      
        ttk.Label(main_frame, text="ROD POS", font=('Arial', 14, 'bold')).pack(pady=(0, 15))

   
    ventana.bind('<Return>', lambda e: iniciar_sesion())
    ventana.eval('tk::PlaceWindow . center')
    ventana.mainloop()