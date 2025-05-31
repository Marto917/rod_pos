# ui/login.py
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from PIL import Image, ImageTk  # Necesitarás instalar Pillow: pip install Pillow

def open_login(callback_vendedor, callback_admin):
    ventana = tk.Tk()
    ventana.title("ROD POS - Login")
    ventana.geometry("300x200")
    
    # Variable
    codigo_var = tk.StringVar()
    
    def iniciar_sesion():
        codigo = codigo_var.get().strip()
        
        if not codigo:
            messagebox.showwarning("Error", "Ingrese un código")
            return
            
        try:
            conn = sqlite3.connect('db/pos.db')
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
            conn.close()
    
    # Interfaz
    ttk.Label(ventana, text="Ingrese su código:").pack(pady=10)
    ttk.Entry(ventana, textvariable=codigo_var).pack()
    ttk.Button(ventana, text="Ingresar", command=iniciar_sesion).pack(pady=10)
    
    # Cargar y mostrar la imagen del logo
    try:
        # Asegúrate de tener la imagen en ui/images/logo.png (crea la carpeta si no existe)
        image = Image.open("ui/images/logo.png")
        # Redimensionar manteniendo aspect ratio para que quepa en el espacio disponible
        image.thumbnail((150, 60))  # Tamaño máximo aproximado para que quepa
        logo = ImageTk.PhotoImage(image)
        
        logo_label = ttk.Label(ventana, image=logo)
        logo_label.image = logo  # Mantener referencia
        logo_label.pack(pady=5)
    except Exception as e:
        print(f"No se pudo cargar la imagen del logo: {str(e)}")
        # Si hay error, no mostramos nada pero el sistema sigue funcionando
    
    ventana.bind('<Return>', lambda e: iniciar_sesion())
    ventana.mainloop()