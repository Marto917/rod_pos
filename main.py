from db_init import init_db
from ui.login import open_login
from ui.admin import open_admin_panel
from ui.menu_vendedor import open_vendor_panel

if __name__ == "__main__":
    init_db()
    open_login(
        callback_vendedor=open_vendor_panel,
        callback_admin=open_admin_panel,
    )