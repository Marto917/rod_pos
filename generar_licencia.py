import hashlib
import base64
from datetime import datetime, timedelta

CLAVE_SECRETA = b"GCNfpGe5KJYzQ8q6h7Kp7bXMtqkEMxi7rbjR6GAI5JE="

def generar_licencia(hwid, dias=31):
    fecha = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    datos = f"{hwid}|{fecha}|".encode() + CLAVE_SECRETA
    firma = hashlib.sha256(datos).hexdigest()
    licencia = f"{hwid}|{fecha}|{firma}"
    return base64.b64encode(licencia.encode()).decode()

# --- USO ---
hwid_cliente = input("HWID del cliente: ").strip()
licencia = generar_licencia(hwid_cliente)
print("\nLicencia generada:\n", licencia)
