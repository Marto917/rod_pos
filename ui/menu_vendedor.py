# ui/menu_vendedor.py
import tkinter as tk
from tkinter import ttk, messagebox
from .stock_view import open_stock_view
from .recepcion import open_recepcion_panel
from .sales import open_sales_panel  
from .arqueo import open_arqueo_panel 

def open_vendor_panel(user_id, user_name):
    ventana = tk.Tk()
    ventana.title(f"Menú Vendedor - {user_name}")
    ventana.geometry("800x600")
    ventana.state('zoomed')
    ventana.configure(bg='#f0f0f0')
    
    # Estilos mejorados
    style = ttk.Style()
    style.configure('Title.TLabel', 
                  font=('Helvetica', 18, 'bold'), 
                  foreground='#333333',
                  background='#f0f0f0')
    
    style.configure('Menu.TButton', 
                  font=('Helvetica', 14),
                  width=25,
                  padding=12,
                  borderwidth=3,
                  relief='raised')
    
    # Colores para los botones
    btn_colors = {
        'ticket': '#4CAF50',  # Verde
        'stock': '#2196F3',   # Azul
        'recepcion': '#FF9800', # Naranja
        'arqueo': '#9C27B0',  # Morado
        'logout': '#F44336'   # Rojo
    }
    
    # Marco principal
    main_frame = ttk.Frame(ventana, padding="30")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Título con nombre de usuario
    ttk.Label(main_frame, 
             text=f"Bienvenido/a {user_name}",
             style='Title.TLabel').pack(pady=(0, 30))
    
    # Marco de botones (centrado)
    buttons_frame = ttk.Frame(main_frame)
    buttons_frame.pack(pady=20)
    
    # Definición de opciones (Ticket primero)
    opciones = [
        ("🎫 TICKET DE VENTA", lambda: open_sales_panel(user_id, user_name), btn_colors['ticket']),
        ("📦 CONSULTAR STOCK", lambda: open_stock_view(user_id, user_name), btn_colors['stock']),
        ("📥 RECEPCIÓN DE PRODUCTOS", lambda: open_recepcion_panel(user_id, user_name), btn_colors['recepcion']),
        ("💰 ARQUEO DE CAJA", lambda: open_arqueo_panel(user_id, user_name), btn_colors['arqueo']),
        ("🚪 CERRAR SESIÓN", ventana.destroy, btn_colors['logout'])
    ]
    
    # Crear botones con estilo
    for texto, comando, color in opciones:
        btn = tk.Button(buttons_frame,
                      text=texto,
                      command=comando,
                      bg=color,
                      fg='white',
                      activebackground=color,
                      activeforeground='white',
                      font=('Helvetica', 12, 'bold'),
                      borderwidth=0,
                      highlightthickness=3,
                      highlightbackground=color,
                      highlightcolor='white',
                      width=30,
                      height=2)
        btn.pack(pady=12, ipadx=10)
    
    # Atajos de teclado
    ventana.bind('<Control-t>', lambda e: open_sales_panel(user_id, user_name))
    ventana.bind('<Control-l>', lambda e: open_stock_view(user_id, user_name))
    ventana.bind('<Control-r>', lambda e: open_recepcion_panel(user_id, user_name))
    
    # Centrar ventana
    ventana.update_idletasks()
    width = ventana.winfo_width()
    height = ventana.winfo_height()
    x = (ventana.winfo_screenwidth() // 2) - (width // 2)
    y = (ventana.winfo_screenheight() // 2) - (height // 2)
    ventana.geometry(f'{width}x{height}+{x}+{y}')
    
    ventana.mainloop()