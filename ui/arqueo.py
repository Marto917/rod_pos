import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os

def open_arqueo_panel(user_id, user_name):
    # Conexión a BD
    conn = sqlite3.connect('db/pos.db')
    c = conn.cursor()

    # Configuración de ventana
    ventana = tk.Toplevel()
    ventana.title(f"Arqueo de Caja - {user_name}")
    ventana.geometry("1000x700")
    ventana.state('zoomed')
    ventana.configure(bg='#f0f0f0')

    # Variables
    efectivo_var = tk.DoubleVar(value=0.0)
    diferencia_var = tk.DoubleVar(value=0.0)
    observaciones_var = tk.StringVar()

    # Función para limpiar datos SIN cerrar
    def limpiar_datos():
        efectivo_var.set(0.0)
        diferencia_var.set(0.0)
        observaciones_var.set("")
        tree_ventas.delete(*tree_ventas.get_children())
        cargar_ventas()  # Recargar ventas frescas
        ventana.update()

    # Función para cancelar (solo cierra)
    def cancelar_arqueo():
        if messagebox.askyesno("Cancelar", "¿Está seguro que desea cancelar este arqueo?", parent=ventana):
            conn.close()
            ventana.destroy()

    # Cargar ventas del día
    def cargar_ventas():
        try:
            hoy = datetime.now().strftime('%Y-%m-%d')
            c.execute("""
                SELECT metodo_pago, COUNT(*), SUM(total)
                FROM ventas 
                WHERE date(fecha)=? AND usuario_id=? AND es_ajuste=0
                GROUP BY metodo_pago
            """, (hoy, user_id))
            
            # Primero limpiar el treeview
            tree_ventas.delete(*tree_ventas.get_children())
            
            # Luego insertar los nuevos datos
            for row in c.fetchall():
                tree_ventas.insert('', 'end', values=row)
                
        except sqlite3.Error as e:
            messagebox.showerror("Error BD", f"Error al cargar ventas:\n{str(e)}", parent=ventana)

    # Calcular diferencia
    def calcular_diferencia():
        try:
            c.execute("""
                SELECT SUM(total) FROM ventas 
                WHERE date(fecha)=date('now') 
                AND usuario_id=? 
                AND es_ajuste=0
                AND metodo_pago='EFECTIVO'
            """, (user_id,))
            
            total_efectivo = c.fetchone()[0] or 0.0
            diferencia = efectivo_var.get() - total_efectivo
            diferencia_var.set(round(diferencia, 2))
            
        except Exception as e:
            messagebox.showerror("Error", f"Error en cálculo:\n{str(e)}", parent=ventana)

    # Función para generar comprobante y limpiar datos
    def generar_comprobante():
        try:
            # Verificar que hay datos
            if not tree_ventas.get_children():
                messagebox.showwarning("Advertencia", "No hay ventas registradas hoy", parent=ventana)
                return

            # Calcular totales
            total_efectivo = sum(
                float(tree_ventas.item(item, 'values')[2]) 
                for item in tree_ventas.get_children() 
                if 'EFECTIVO' in tree_ventas.item(item, 'values')[0]
            )
            
            total_tarjeta = sum(
                float(tree_ventas.item(item, 'values')[2]) 
                for item in tree_ventas.get_children() 
                if 'TARJETA' in tree_ventas.item(item, 'values')[0]
            )

            # Guardar en BD
            c.execute("""
                INSERT INTO arqueos_caja (
                    usuario_id, fecha, efectivo, tarjeta, otros,
                    total_sistema, diferencia, observaciones
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                total_efectivo,
                total_tarjeta,
                0.0, 
                total_efectivo + total_tarjeta,
                diferencia_var.get(),
                observaciones_var.get() or "Ninguna"
            ))
            conn.commit()

            # Generar PDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            
            # Cabecera
            pdf.cell(200, 10, txt="COMPROBANTE DE ARQUEO", ln=1, align='C')
            pdf.cell(200, 10, txt=f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=1, align='C')
            pdf.cell(200, 10, txt=f"Vendedor: {user_name}", ln=1, align='C')
            pdf.ln(15)
            
            # Detalle de ventas
            pdf.set_font("Arial", size=10)
            pdf.cell(120, 8, txt="Método de pago", border=1)
            pdf.cell(30, 8, txt="Transacciones", border=1)
            pdf.cell(40, 8, txt="Total", border=1, ln=1)
            
            for item in tree_ventas.get_children():
                metodo, trans, total = tree_ventas.item(item, 'values')
                pdf.cell(120, 8, txt=metodo, border=1)
                pdf.cell(30, 8, txt=trans, border=1)
                pdf.cell(40, 8, txt=f"${float(total):.2f}", border=1, ln=1)
            
            # Totales
            pdf.ln(10)
            pdf.cell(120, 8, txt="Efectivo contado:", border=1)
            pdf.cell(70, 8, txt=f"${efectivo_var.get():.2f}", border=1, ln=1)
            
            pdf.cell(120, 8, txt="Diferencia:", border=1)
            pdf.cell(70, 8, txt=f"${diferencia_var.get():.2f}", border=1, ln=1)
            
            # Guardar PDF
            os.makedirs("reportes", exist_ok=True)
            filename = f"reportes/arqueo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf.output(filename)

            # 1. Marcar ventas como arqueadas (nuevo)
            hoy = datetime.now().strftime('%Y-%m-%d')
            c.execute("""
                UPDATE ventas 
                SET es_ajuste=1 
                WHERE date(fecha)=? AND usuario_id=? AND es_ajuste=0
            """, (hoy, user_id))
            conn.commit()

            # 2. Limpiar la interfaz
            limpiar_datos()
            
            messagebox.showinfo(
                "Éxito", 
                f"Comprobante generado:\n{filename}\n\nVentas marcadas como arqueadas.",
                parent=ventana
            )
            
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Error al generar comprobante:\n{str(e)}", parent=ventana)

    # Interfaz gráfica
    main_frame = ttk.Frame(ventana, padding=20)
    main_frame.pack(fill='both', expand=True)

    # Treeview
    tree_ventas = ttk.Treeview(main_frame, columns=('Método', 'Transacciones', 'Total'), show='headings')
    tree_ventas.heading('Método', text='Método de Pago')
    tree_ventas.heading('Transacciones', text='Transacciones')
    tree_ventas.heading('Total', text='Total ($)')
    tree_ventas.pack(fill='both', expand=True, pady=10)

    # Controles
    control_frame = ttk.Frame(main_frame)
    control_frame.pack(fill='x', pady=10)

    ttk.Label(control_frame, text="Efectivo contado:").grid(row=0, column=0, sticky='e')
    ttk.Entry(control_frame, textvariable=efectivo_var, width=15).grid(row=0, column=1, padx=5)
    ttk.Button(control_frame, text="Calcular Diferencia", command=calcular_diferencia).grid(row=0, column=2, padx=10)

    ttk.Label(control_frame, text="Diferencia:").grid(row=1, column=0, sticky='e')
    ttk.Label(control_frame, textvariable=diferencia_var, font=('Arial', 12, 'bold')).grid(row=1, column=1, sticky='w')

    ttk.Label(main_frame, text="Observaciones:").pack()
    ttk.Entry(main_frame, textvariable=observaciones_var, width=50).pack()

    # Botones
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(pady=20)

    ttk.Button(btn_frame, text="Generar Comprobante", 
              command=generar_comprobante,
              style='Accent.TButton').pack(side='left', padx=10)
              
    ttk.Button(btn_frame, text="Cancelar", 
              command=cancelar_arqueo).pack(side='left', padx=10)

    # Carga inicial
    cargar_ventas()

    # Configurar cierre seguro
    ventana.protocol("WM_DELETE_WINDOW", cancelar_arqueo)
    ventana.mainloop()