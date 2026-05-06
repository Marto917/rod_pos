from db_init import init_db
from ui.login import open_login
from ui.menu_vendedor import open_vendor_panel
from tkinter import messagebox


def open_admin_panel_lazy(user_id, user_name):
    try:
        from ui.admin import open_admin_panel
        open_admin_panel(user_id, user_name)
    except Exception as e:
        messagebox.showerror(
            "Error",
            "No se pudo abrir el panel admin en esta PC.\n%s" % str(e),
        )

if __name__ == "__main__":
    init_db()
    open_login(
        callback_vendedor=open_vendor_panel,
        callback_admin=open_admin_panel_lazy,
    )