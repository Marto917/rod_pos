# --- NUEVO: licencia.py ---
# Guardalo como archivo separado en la misma carpeta
import hashlib
import base64
from datetime import datetime
import sys
import os

CLAVE_SECRETA = b"GCNfpGe5KJYzQ8q6h7Kp7bXMtqkEMxi7rbjR6GAI5JE="
ARCHIVO_LICENCIA = "licencia.dat"


if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def obtener_hwid():
    """Obtiene un identificador único del sistema (ej: número de serie del disco)."""
    try:
        import uuid
        return str(uuid.getnode())
    except:
        return "no_hw_id"


def verificar_licencia():
    if not os.path.exists(ARCHIVO_LICENCIA):
        return False

    try:
        with open(ARCHIVO_LICENCIA, 'r') as f:
            contenido = f.read().strip()

        decodificado = base64.b64decode(contenido.encode()).decode()
        hwid, fecha, firma = decodificado.split('|')

        if hwid != obtener_hwid():
            return False

        # Verificar firma
        datos = f"{hwid}|{fecha}|".encode() + CLAVE_SECRETA
        hash_valido = hashlib.sha256(datos).hexdigest()

        if hash_valido != firma:
            return False

        # Verificar fecha
        fecha_exp = datetime.strptime(fecha, "%Y-%m-%d")
        return datetime.now() <= fecha_exp

    except Exception as e:
        print("Error al verificar licencia:", e)
        return False


def activar_licencia(codigo):
    try:
        with open(ARCHIVO_LICENCIA, 'w') as f:
            f.write(codigo.strip())
        return verificar_licencia()
    except:
        return False
def obtener_fecha_vencimiento():
    if not os.path.exists(ARCHIVO_LICENCIA):
        return None
    try:
        with open(ARCHIVO_LICENCIA, 'r') as f:
            contenido = f.read().strip()
        decodificado = base64.b64decode(contenido.encode()).decode()
        _, fecha, _ = decodificado.split('|')
        return fecha
    except:
        return None
ARCHIVO_HASH = os.path.join(BASE_DIR, "licencia_usada.hash")

def activar_licencia(codigo):
    try:
        # Verificar si ya fue usado
        codigo_hash = hashlib.sha256(codigo.strip().encode()).hexdigest()
        if os.path.exists(ARCHIVO_HASH):
            with open(ARCHIVO_HASH, "r") as f:
                if f.read().strip() == codigo_hash:
                    return False  # ya se usó este código

        with open(ARCHIVO_LICENCIA, 'w') as f:
            f.write(codigo.strip())

        with open(ARCHIVO_HASH, "w") as f:
            f.write(codigo_hash)

        return verificar_licencia()
    except:
        return False
def obtener_dias_restantes():
    if not os.path.exists(ARCHIVO_LICENCIA):
        return None
    try:
        with open(ARCHIVO_LICENCIA, 'r') as f:
            contenido = f.read().strip()
        decodificado = base64.b64decode(contenido.encode()).decode()
        _, fecha, _ = decodificado.split('|')
        fecha_exp = datetime.strptime(fecha, "%Y-%m-%d")
        delta = (fecha_exp - datetime.now()).days
        return delta if delta >= 0 else 0
    except:
        return None
