"""
Herramienta para generar códigos de licencia ROD POS.
Uso: ejecutá este script cuando un cliente te envíe su HWID;
     ingresá el HWID, generá licencia perpetua y copiala/guardala para enviarla al cliente.
"""
import hashlib
import base64
import tkinter as tk
from tkinter import ttk, messagebox

CLAVE_SECRETA = b"GCNfpGe5KJYzQ8q6h7Kp7bXMtqkEMxi7rbjR6GAI5JE="


def generar_licencia(hwid):
    """Genera licencia perpetua atada al HWID."""
    hwid = (hwid or "").strip()
    if not hwid:
        return None
    fecha = "PERPETUA"
    datos = f"{hwid}|{fecha}|".encode() + CLAVE_SECRETA
    firma = hashlib.sha256(datos).hexdigest()
    licencia = f"{hwid}|{fecha}|{firma}"
    return base64.b64encode(licencia.encode()).decode()


def main():
    ventana = tk.Tk()
    ventana.title("ROD POS - Generar licencia para cliente")
    ventana.resizable(True, False)
    ventana.minsize(480, 320)

    # Instrucciones
    inst = ttk.Label(
        ventana,
        text="Ingresá el HWID que te envió el cliente.\n"
             "Se generará una licencia PERPETUA para ese equipo.",
        justify="center",
        font=("Segoe UI", 10),
    )
    inst.pack(pady=(15, 20))

    # HWID
    f_hwid = ttk.Frame(ventana, padding=5)
    f_hwid.pack(fill="x", padx=15)
    ttk.Label(f_hwid, text="HWID del cliente:", width=18).pack(side="left", padx=(0, 8))
    entry_hwid = ttk.Entry(f_hwid, width=45)
    entry_hwid.pack(side="left", fill="x", expand=True)
    entry_hwid.focus_set()

    # Código generado
    f_code = ttk.Frame(ventana, padding=5)
    f_code.pack(fill="x", padx=15, pady=(20, 0))
    ttk.Label(f_code, text="Código generado:", width=18).pack(side="left", padx=(0, 8), anchor="n")
    text_code = tk.Text(f_code, height=4, width=50, wrap="word", font=("Consolas", 9))
    text_code.pack(side="left", fill="x", expand=True)

    def do_generar():
        hwid = entry_hwid.get().strip()
        if not hwid:
            messagebox.showwarning("Falta HWID", "Ingresá el HWID del cliente.", parent=ventana)
            entry_hwid.focus_set()
            return
        codigo = generar_licencia(hwid)
        if codigo:
            text_code.delete("1.0", tk.END)
            text_code.insert("1.0", codigo)
            ventana.clipboard_clear()
            ventana.clipboard_append(codigo)
            messagebox.showinfo(
                "Listo",
                "Código generado y copiado al portapapeles.\nPodés pegarlo en un mensaje o archivo para enviar al cliente.",
                parent=ventana,
            )
        else:
            messagebox.showerror("Error", "No se pudo generar el código.", parent=ventana)

    def do_copiar():
        codigo = text_code.get("1.0", tk.END).strip()
        if not codigo:
            messagebox.showwarning("Sin código", "Generá primero un código.", parent=ventana)
            return
        ventana.clipboard_clear()
        ventana.clipboard_append(codigo)
        messagebox.showinfo("Copiado", "Código copiado al portapapeles.", parent=ventana)

    def do_guardar():
        codigo = text_code.get("1.0", tk.END).strip()
        if not codigo:
            messagebox.showwarning("Sin código", "Generá primero un código.", parent=ventana)
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Archivo de texto", "*.txt"), ("Todos", "*.*")],
            initialfile=f"licencia_{entry_hwid.get().strip()[:10]}.txt",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(codigo)
                messagebox.showinfo("Guardado", f"Guardado en:\n{path}", parent=ventana)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=ventana)

    # Botones
    btn_frame = ttk.Frame(ventana, padding=15)
    btn_frame.pack(fill="x")
    ttk.Button(btn_frame, text="Generar licencia (y copiar)", command=do_generar).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Copiar al portapapeles", command=do_copiar).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Guardar en archivo...", command=do_guardar).pack(side="left", padx=5)

    ventana.bind("<Return>", lambda e: do_generar())
    ventana.mainloop()


if __name__ == "__main__":
    main()
