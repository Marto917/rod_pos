import tkinter as tk
from tkinter import ttk, messagebox

from fiscal_service import obtener_pendientes, reintentar_pendiente


def open_arca_pendientes_panel(user_id, user_name):
    ventana = tk.Toplevel()
    ventana.title("Pendientes ARCA - %s" % user_name)
    ventana.geometry("900x500")
    ventana.state("zoomed")

    frame = ttk.Frame(ventana, padding=10)
    frame.pack(fill="both", expand=True)

    tree = ttk.Treeview(
        frame,
        columns=("ID", "Venta", "Fecha", "Ultimo Error"),
        show="headings",
    )
    for col in ("ID", "Venta", "Fecha", "Ultimo Error"):
        tree.heading(col, text=col)
    tree.column("ID", width=70, anchor="center")
    tree.column("Venta", width=90, anchor="center")
    tree.column("Fecha", width=180, anchor="center")
    tree.column("Ultimo Error", width=500)
    tree.pack(fill="both", expand=True)

    def cargar():
        tree.delete(*tree.get_children())
        for row in obtener_pendientes():
            tree.insert("", "end", values=row)

    def reintentar_sel():
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Pendientes", "Seleccioná un pendiente.")
            return
        pid = tree.item(sel[0], "values")[0]
        ok, msg = reintentar_pendiente(int(pid))
        if ok:
            messagebox.showinfo("Pendientes", "Comprobante emitido correctamente.")
        else:
            messagebox.showerror("Pendientes", "No se pudo emitir:\n%s" % msg)
        cargar()

    def reintentar_todos():
        ids = [tree.item(item, "values")[0] for item in tree.get_children()]
        if not ids:
            messagebox.showinfo("Pendientes", "No hay pendientes para reintentar.")
            return
        ok_count = 0
        err_count = 0
        last_error = ""
        for pid in ids:
            ok, msg = reintentar_pendiente(int(pid))
            if ok:
                ok_count += 1
            else:
                err_count += 1
                last_error = msg
        cargar()
        if err_count == 0:
            messagebox.showinfo("Pendientes", "Se emitieron todos los pendientes (%d)." % ok_count)
        else:
            messagebox.showwarning(
                "Pendientes",
                "Emitidos: %d\nCon error: %d\nUltimo error: %s" % (ok_count, err_count, last_error),
            )

    btns = ttk.Frame(frame)
    btns.pack(fill="x", pady=10)
    ttk.Button(btns, text="Actualizar", command=cargar).pack(side="left", padx=4)
    ttk.Button(btns, text="Reintentar seleccionado", command=reintentar_sel).pack(side="left", padx=4)
    ttk.Button(btns, text="Reintentar todos", command=reintentar_todos).pack(side="left", padx=4)
    ttk.Button(btns, text="Cerrar", command=ventana.destroy).pack(side="right", padx=4)

    cargar()
