# Sistema de licencia ROD POS - verificación y activación en el equipo del cliente
import hashlib
import base64
from datetime import datetime
import sys
import os

CLAVE_SECRETA = b"GCNfpGe5KJYzQ8q6h7Kp7bXMtqkEMxi7rbjR6GAI5JE="

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ARCHIVO_LICENCIA = os.path.join(BASE_DIR, "licencia.dat")
ARCHIVO_HASH = os.path.join(BASE_DIR, "licencia_usada.hash")


def obtener_hwid():
    """Identificador único del equipo (para vincular la licencia a esta máquina)."""
    try:
        import uuid
        return str(uuid.getnode())
    except Exception:
        return "no_hw_id"


def verificar_licencia():
    """Comprueba si existe licencia válida, para este equipo (perpetua o por fecha)."""
    if not os.path.exists(ARCHIVO_LICENCIA):
        return False
    try:
        with open(ARCHIVO_LICENCIA, 'r', encoding='utf-8') as f:
            contenido = f.read().strip()
        if not contenido:
            return False
        decodificado = base64.b64decode(contenido.encode()).decode()
        partes = decodificado.split('|')
        if len(partes) != 3:
            return False
        hwid, fecha, firma = partes
        if hwid != obtener_hwid():
            return False
        datos = f"{hwid}|{fecha}|".encode() + CLAVE_SECRETA
        hash_valido = hashlib.sha256(datos).hexdigest()
        if hash_valido != firma:
            return False
        if fecha == "PERPETUA":
            return True
        fecha_exp = datetime.strptime(fecha, "%Y-%m-%d")
        return datetime.now().date() <= fecha_exp.date()
    except Exception as e:
        print("Error al verificar licencia:", e)
        return False


def activar_licencia(codigo):
    """Activa una licencia con el código recibido. Evita reutilizar el mismo código."""
    codigo = (codigo or "").strip()
    if not codigo:
        return False
    try:
        codigo_hash = hashlib.sha256(codigo.encode()).hexdigest()
        if os.path.exists(ARCHIVO_HASH):
            with open(ARCHIVO_HASH, "r", encoding='utf-8') as f:
                if f.read().strip() == codigo_hash:
                    return False  # ya se usó este código en este equipo
        with open(ARCHIVO_LICENCIA, 'w', encoding='utf-8') as f:
            f.write(codigo)
        with open(ARCHIVO_HASH, "w", encoding='utf-8') as f:
            f.write(codigo_hash)
        return verificar_licencia()
    except Exception as e:
        print("Error al activar licencia:", e)
        return False


def obtener_fecha_vencimiento():
    """Devuelve la fecha de vencimiento, PERPETUA o None."""
    if not os.path.exists(ARCHIVO_LICENCIA):
        return None
    try:
        with open(ARCHIVO_LICENCIA, 'r', encoding='utf-8') as f:
            contenido = f.read().strip()
        decodificado = base64.b64decode(contenido.encode()).decode()
        partes = decodificado.split('|')
        if len(partes) != 3:
            return None
        return partes[1]
    except Exception:
        return None


def obtener_dias_restantes():
    """Días restantes (None en licencia perpetua o sin licencia)."""
    fecha_str = obtener_fecha_vencimiento()
    if not fecha_str:
        return None
    if fecha_str == "PERPETUA":
        return None
    try:
        fecha_exp = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        delta = (fecha_exp - datetime.now().date()).days
        return max(0, delta)
    except Exception:
        return None
