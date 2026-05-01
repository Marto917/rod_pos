import tkinter as tk
from tkinter import ttk, messagebox
from .stock_view import open_stock_view
from .recepcion import open_recepcion_panel
from .sales import open_sales_panel
from .arqueo import open_arqueo_panel
from .arca_pendientes import open_arca_pendientes_panel


def open_vendor_panel(user_id, user_name):
    ventana = tk.Tk()
    ventana.title(f"Menú Vendedor - {user_name}")
    ventana.geometry("800x600")
    ventana.state('zoomed')
    ventana.configure(bg='#f0f0f0')

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

    btn_colors = {
        'ticket': '#4CAF50',
        'stock': '#2196F3',
        'recepcion': '#FF9800',
        'arqueo': '#9C27B0',
        'pendientes': '#607D8B',
        'logout': '#F44336'
    }

    def abrir_panel(nombre, abrir_fn):
        try:
            abrir_fn()
        except Exception as e:
            messagebox.showerror(
                "Error",
                "No se pudo abrir %s.\n%s" % (nombre, str(e)),
                parent=ventana,
            )

    main_frame = ttk.Frame(ventana, padding="30")
    main_frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main_frame,
              text="Bienvenido/a %s" % user_name,
              style='Title.TLabel').pack(pady=(0, 30))

    buttons_frame = ttk.Frame(main_frame)
    buttons_frame.pack(pady=20)

    opciones = [
        ("TICKET DE VENTA", lambda: abrir_panel("Ticket de venta", lambda: open_sales_panel(user_id, user_name)), btn_colors['ticket']),
        ("CONSULTAR STOCK", lambda: abrir_panel("Consultar stock", lambda: open_stock_view(user_id, user_name)), btn_colors['stock']),
        ("RECEPCIÓN DE PRODUCTOS", lambda: abrir_panel("Recepción", lambda: open_recepcion_panel(user_id, user_name)), btn_colors['recepcion']),
        ("ARQUEO DE CAJA", lambda: abrir_panel("Arqueo de caja", lambda: open_arqueo_panel(user_id, user_name)), btn_colors['arqueo']),
        ("PENDIENTES ARCA", lambda: abrir_panel("Pendientes ARCA", lambda: open_arca_pendientes_panel(user_id, user_name)), btn_colors['pendientes']),
        ("CERRAR SESIÓN", ventana.destroy, btn_colors['logout'])
    ]

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

    ventana.bind('<Control-t>', lambda e: abrir_panel("Ticket de venta", lambda: open_sales_panel(user_id, user_name)))
    ventana.bind('<Control-l>', lambda e: abrir_panel("Consultar stock", lambda: open_stock_view(user_id, user_name)))
    ventana.bind('<Control-r>', lambda e: abrir_panel("Recepción", lambda: open_recepcion_panel(user_id, user_name)))
    ventana.bind('<Control-p>', lambda e: abrir_panel("Pendientes ARCA", lambda: open_arca_pendientes_panel(user_id, user_name)))
    
    ventana.update_idletasks()
    width = ventana.winfo_width()
    height = ventana.winfo_height()
    x = (ventana.winfo_screenwidth() // 2) - (width // 2)
    y = (ventana.winfo_screenheight() // 2) - (height // 2)
    ventana.geometry("%dx%d+%d+%d" % (width, height, x, y))

    ventana.mainloop()