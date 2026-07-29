import tkinter as tk
from tkinter import ttk
from ui import dialogs as messagebox

from services.stock_ops import StockError, list_products
from ui import theme as ui_theme


def open_stock_view(user_id, user_name):
    ventana = tk.Toplevel() if tk._default_root else tk.Tk()
    ventana.title("Stock - %s" % user_name)
    ventana.geometry("1000x600")
    try:
        ventana.state("zoomed")
    except Exception:
        pass
    ui_theme.apply_window(ventana)

    style = ttk.Style(ventana)
    ui_theme.apply_ttk_style(style)

    main_frame = ttk.Frame(ventana, padding=20)
    main_frame.pack(fill="both", expand=True)

    search_frame = ttk.Frame(main_frame)
    search_visible = False

    ttk.Label(search_frame, text="Buscar:").pack(side="left")
    entry_busqueda = ttk.Entry(search_frame, width=50)
    entry_busqueda.pack(side="left", padx=5)
    btn_buscar = ttk.Button(search_frame, text="Buscar")
    btn_buscar.pack(side="left", padx=5)

    def toggle_search():
        nonlocal search_visible
        if search_visible:
            search_frame.pack_forget()
            search_visible = False
        else:
            search_frame.pack(fill="x", pady=10)
            entry_busqueda.focus()
            search_visible = True

    def buscar_productos(event=None):
        texto_busqueda = entry_busqueda.get().strip()
        try:
            tree.delete(*tree.get_children())
            productos = list_products(texto_busqueda)
            for p in productos:
                tree.insert(
                    "",
                    "end",
                    values=(
                        p.get("id"),
                        p.get("codigo_barras"),
                        p.get("nombre"),
                        p.get("categoria"),
                        p.get("cantidad"),
                        p.get("precio_lista"),
                        p.get("precio_publico"),
                    ),
                )
        except StockError as e:
            messagebox.showerror("Error LAN", str(e), parent=ventana)
        except Exception as e:
            messagebox.showerror("Error", "Error al buscar productos:\n%s" % e, parent=ventana)

    btn_buscar.config(command=buscar_productos)
    entry_busqueda.bind("<KeyRelease>", buscar_productos)

    tree = ttk.Treeview(
        main_frame,
        columns=("ID", "Código", "Nombre", "Categoría", "Stock", "P. Lista", "P. Efectivo"),
        show="headings",
    )
    tree.heading("ID", text="ID")
    tree.heading("Código", text="Código Barras")
    tree.heading("Nombre", text="Nombre")
    tree.heading("Categoría", text="Categoría")
    tree.heading("Stock", text="Stock")
    tree.heading("P. Lista", text="Precio Lista (Crédito)")
    tree.heading("P. Efectivo", text="Precio Efectivo/Débito")

    tree.column("ID", width=50, anchor="center")
    tree.column("Código", width=120, anchor="center")
    tree.column("Nombre", width=300)
    tree.column("Categoría", width=150)
    tree.column("Stock", width=80, anchor="center")
    tree.column("P. Lista", width=120, anchor="e")
    tree.column("P. Efectivo", width=140, anchor="e")
    tree.pack(fill="both", expand=True)

    scrollbar = ttk.Scrollbar(tree, orient="vertical", command=tree.yview)
    scrollbar.pack(side="right", fill="y")
    tree.configure(yscrollcommand=scrollbar.set)

    def volver():
        ventana.destroy()

    btns = ttk.Frame(main_frame)
    btns.pack(fill="x", pady=(12, 0))
    ttk.Button(btns, text="Volver al Menú", command=volver).pack(side="right")

    ventana.bind("<Control-L>", lambda e: toggle_search())
    ventana.bind("<Control-l>", lambda e: toggle_search())
    ventana.bind("<Escape>", lambda e: volver())
    ventana.protocol("WM_DELETE_WINDOW", volver)
    buscar_productos()
