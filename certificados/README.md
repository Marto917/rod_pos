# Certificados ARCA (AFIP)

Colocá acá los archivos del certificado digital del contribuyente:

- `empresa.crt` — certificado público
- `empresa.key` — clave privada

Si tenés un `.pfx` / `.p12`, exportalo antes a `.crt` + `.key`.

El cargador `cargar_arca_config.py` y la configuración fiscal usan por defecto estas rutas relativas a la carpeta del EXE/script:

- `certificados/empresa.crt`
- `certificados/empresa.key`

**No subas** `.crt`, `.key` ni `.pfx` al repositorio (están en `.gitignore`).
