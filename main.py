from db_init import init_db
from ui.login import open_login
from ui.admin import open_admin_panel

# Importación condicional para evitar errores
try:
    from ui.sales import open_sales_panel
except ImportError:
    # Función de respaldo si sales.py no tiene la función
    def open_sales_panel(user_id, user_name):
        import tkinter as tk
        from tkinter import messagebox
        messagebox.showinfo("Info", "Módulo de ventas no disponible")
        return

if __name__ == "__main__":
    init_db()
    open_login(
        callback_vendedor=open_sales_panel,
        callback_admin=open_admin_panel
    )