from db_init import init_db
from ui.login import open_login
from ui.menu_vendedor import open_vendor_panel
from tkinter import messagebox
from pos_config import is_server_mode, load_config


def open_admin_panel_lazy(user_id, user_name):
    try:
        from ui.admin import open_admin_panel
        open_admin_panel(user_id, user_name)
    except Exception as e:
        messagebox.showerror(
            "Error",
            "No se pudo abrir el panel admin en esta PC.\n%s" % str(e),
        )


def _maybe_start_lan_server():
    cfg = load_config()
    if not is_server_mode(cfg):
        return
    if not cfg.get("auto_iniciar_servidor", True):
        return
    try:
        from lan_server import start_lan_server

        host, port = start_lan_server()
        print("[ROD POS] Servidor LAN activo en puerto %s" % port)
    except Exception as e:
        print("[ROD POS] No se pudo iniciar servidor LAN: %s" % e)


if __name__ == "__main__":
    init_db()
    _maybe_start_lan_server()
    open_login(
        callback_vendedor=open_vendor_panel,
        callback_admin=open_admin_panel_lazy,
    )
