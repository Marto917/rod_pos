# Multi-caja LAN y cierre profesional

## Cierre de caja (Excel)

1. Menú vendedor → **CIERRE DE CAJA**
2. Revisá totales por método y el detalle de tickets
3. Ingresá **fondo inicial** y **efectivo contado**
4. **Cerrar caja y exportar Excel**
5. Se generan en `reportes/`:
   - `cierre_YYYYMMDD_HHMMSS_Nombre.xlsx` (hojas Resumen + Detalle ventas)
   - PDF de respaldo

## Red LAN (2 PCs, stock compartido)

### PC principal (Servidor)

1. Admin → pestaña **Red LAN**
2. Modo: `servidor`
3. Terminal: `CAJA-1`
4. Puerto: `8765` (por defecto)
5. Guardar → reiniciar ROD POS
6. Anotá la IP local de esa PC (`ipconfig` → IPv4, ej. `192.168.0.25`)
7. Firewall de Windows: permitir Python/RodPOS en red privada, puerto 8765

### PC secundaria (Cliente)

1. Misma app instalada
2. Admin → **Red LAN**
3. Modo: `cliente`
4. IP del servidor: la IP de la PC principal
5. Terminal: `CAJA-2`
6. Guardar → reiniciar
7. **Probar conexión**

A partir de ahí, ventas, stock y recepción de la caja 2 van a la base de la PC principal.

## Notas

- En modo `local` (default) todo sigue como antes, una sola PC.
- No compartas el archivo `pos.db` por carpeta de red: corrompe la base.
- Usá el servidor LAN incluido para compartir stock de forma segura.
