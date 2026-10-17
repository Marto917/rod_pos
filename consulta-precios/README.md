# Consulta de precios

Página mobile para el personal del salón. No reemplaza el POS de escritorio.

El catálogo sale del CSV copiado en `catalogo/articulos.csv` y se carga al arrancar. Usuarios y promociones viven en SQLite (`DATA_DIR`, por defecto `./data`). El CSV no trae promociones: el administrador las carga solo en los productos que correspondan.

De las 618 filas, 300 no tienen código de barras y se buscan por nombre. La app muestra solo artículos con `activo = 1` y solo el precio de venta. No muestra el precio mayorista. Un producto sin código queda identificado por nombre y categoría: si ese nombre cambia en el CSV, hay que volver a cargar sus promociones.

## Correr en local

Hace falta Node 22.

```bash
cd consulta-precios
npm start
```

Abrí http://localhost:3000 . Si no definís variables, el administrador de desarrollo es:

- usuario: `admin`
- contraseña: `admin1357`

Ese acceso solo existe fuera de producción. En el celular, el administrador crea empleados desde **Empleados**. Cada persona entra con su usuario y contraseña.

Para escanear hace falta HTTPS (en el local, `localhost` alcanza). Chrome usa `BarcodeDetector` cuando está; Safari y el resto usan ZXing.

Para dejarla en el inicio: menú del navegador → **Agregar a inicio**. En Safari: Compartir → Agregar a inicio.

## Railway y aquaremates.store

No hay un servicio creado ni cambios de DNS. Para publicarlo:

1. En Railway, **New service** desde este repo.
2. En el servicio, **Root Directory** = `consulta-precios`. Así no se construye el POS.
3. Variables:
   - `ADMIN_USER`
   - `ADMIN_PASSWORD` (una clave distinta de la de desarrollo)
   - `DATA_DIR=/app/data`
4. **Volume** montado en `/app/data`. Sin ese disco, usuarios y promociones se pierden en cada redeploy. El CSV del catálogo va en la imagen, en `catalogo/`, y no está dentro del volume.
5. El servicio escucha `PORT` y responde `GET /health`.
6. En Networking, agregá el dominio `aquaremates.store` y configurá en el DNS el registro que indique Railway. Eso no está hecho acá.

El contenedor corre como root para que el proceso pueda escribir el volume.
