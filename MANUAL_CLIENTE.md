# Manual Cliente - ROD POS

Guia simple para usar el sistema dia a dia en el local.

---

## 1) Ingreso al sistema

1. Abri `RodPOS.exe`.
2. Ingresa tu codigo de usuario.
3. Si sos vendedor, vas al menu de ventas.
4. Si sos administrador, vas al panel admin.

---

## 2) Como vender

1. Entrar a `TICKET DE VENTA`.
2. Escanear codigo de barras o agregar articulo manual.
3. Revisar total y metodo de pago.
4. Presionar `PAGAR`.
5. Elegir si queres emitir comprobante fiscal ARCA.
6. Se genera el ticket y puede imprimirse.

---

## 3) Si falla ARCA en el momento

No se pierde la venta.

- La venta queda guardada.
- El comprobante queda en `Pendientes ARCA`.
- Luego se puede reintentar desde el panel correspondiente.

---

## 4) Impresion de ticket

- Usar impresora termica 58mm como predeterminada en Windows.
- Si no imprime automatico, abrir el PDF del ticket y probar manual.
- Los tickets se guardan en la carpeta `comprobantes`.

---

## 5) Que puede tocar cada rol

- **Vendedor**: vender, consultar stock, recepcion, arqueo, pendientes ARCA.
- **Administrador**: configuracion general, usuarios, productos, reportes, ARCA.

---

## 6) Recomendaciones importantes

- Hacer backup frecuente desde el panel admin.
- No borrar la carpeta `db`.
- No mover certificados `.crt`/`.key` sin actualizar rutas en ARCA/Ticket.
- Mantener la hora/fecha de Windows correctas.

---

## 7) Soporte rapido

Si aparece un error:

1. Anotar mensaje exacto.
2. Si es fiscal, revisar `debug_afip.txt` junto al exe.
3. Reintentar desde `Pendientes ARCA`.

