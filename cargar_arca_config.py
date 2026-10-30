#!/usr/bin/env python3
"""
Carga datos fiscales ARCA en la base del POS.

Uso:
  1) Copiá arca_datos.ejemplo.json -> arca_datos.json y completá CUIT, IIBB, etc.
  2) Poné empresa.crt y empresa.key en certificados/
  3) Ejecutá:  py cargar_arca_config.py

Opciones:
  py cargar_arca_config.py --json ruta/arca_datos.json
  py cargar_arca_config.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from db_init import get_base_dir, init_db
from fiscal_service import CONFIG_KEYS, get_fiscal_config, save_fiscal_config, validar_cuit_digito


PLACEHOLDERS = {
    "XXXXXXXXXXX",
    "DD/MM/AAAA",
    "Calle Nro, Localidad, Provincia",
}


def _abs_under_base(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(get_base_dir(), path))


def _es_placeholder(valor: str) -> bool:
    v = (valor or "").strip()
    if not v:
        return True
    if v in PLACEHOLDERS:
        return True
    if "XXXX" in v.upper():
        return True
    return False


def _cargar_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("El JSON debe ser un objeto {clave: valor}.")
    return {str(k): "" if v is None else str(v).strip() for k, v in data.items()}


def _copiar_cert_si_hace_falta(src: str, dest_rel: str) -> str:
    """Si src existe y dest_rel está vacío/distinto, copia a certificados/."""
    if not src or not os.path.isfile(src):
        return dest_rel
    dest_abs = _abs_under_base(dest_rel or os.path.join("certificados", os.path.basename(src)))
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
    src_abs = os.path.abspath(src)
    if os.path.abspath(dest_abs) != src_abs:
        shutil.copy2(src_abs, dest_abs)
    return os.path.relpath(dest_abs, get_base_dir()).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cargar configuración ARCA en Rod POS")
    parser.add_argument(
        "--json",
        default=os.path.join(get_base_dir(), "arca_datos.json"),
        help="Ruta al JSON con datos fiscales (default: arca_datos.json)",
    )
    parser.add_argument(
        "--cert",
        default="",
        help="Ruta opcional a un .crt para copiar a certificados/empresa.crt",
    )
    parser.add_argument(
        "--key",
        default="",
        help="Ruta opcional a un .key para copiar a certificados/empresa.key",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo valida y muestra qué se guardaría, sin escribir en la BD",
    )
    args = parser.parse_args()

    init_db()
    base = get_base_dir()
    json_path = args.json if os.path.isabs(args.json) else os.path.join(base, args.json)

    if not os.path.isfile(json_path):
        ejemplo = os.path.join(base, "arca_datos.ejemplo.json")
        print("No encontré %s" % json_path)
        print("Copiá el ejemplo y completá los datos reales:")
        print("  copy arca_datos.ejemplo.json arca_datos.json   (Windows)")
        print("  cp arca_datos.ejemplo.json arca_datos.json     (Linux/Mac)")
        if os.path.isfile(ejemplo):
            print("Ejemplo disponible en: %s" % ejemplo)
        return 1

    data = _cargar_json(json_path)
    actual = get_fiscal_config()
    merged = dict(actual)
    for k in CONFIG_KEYS:
        if k in data and data[k] != "":
            merged[k] = data[k]

    # Certificados: argumentos CLI o valores del JSON
    cert_src = args.cert or merged.get("arca_cert_path", "")
    key_src = args.key or merged.get("arca_key_path", "")
    if args.cert:
        merged["arca_cert_path"] = _copiar_cert_si_hace_falta(
            _abs_under_base(args.cert), "certificados/empresa.crt"
        )
    elif cert_src and not os.path.isabs(cert_src):
        merged["arca_cert_path"] = cert_src.replace("\\", "/")
    elif cert_src and os.path.isfile(cert_src):
        merged["arca_cert_path"] = _copiar_cert_si_hace_falta(
            cert_src, "certificados/empresa.crt"
        )

    if args.key:
        merged["arca_key_path"] = _copiar_cert_si_hace_falta(
            _abs_under_base(args.key), "certificados/empresa.key"
        )
    elif key_src and not os.path.isabs(key_src):
        merged["arca_key_path"] = key_src.replace("\\", "/")
    elif key_src and os.path.isfile(key_src):
        merged["arca_key_path"] = _copiar_cert_si_hace_falta(
            key_src, "certificados/empresa.key"
        )

    # Defaults relativos si siguen vacíos
    if not (merged.get("arca_cert_path") or "").strip():
        merged["arca_cert_path"] = "certificados/empresa.crt"
    if not (merged.get("arca_key_path") or "").strip():
        merged["arca_key_path"] = "certificados/empresa.key"

    errores = []
    cuit = "".join(ch for ch in merged.get("empresa_cuit", "") if ch.isdigit())
    cuit_rep = "".join(ch for ch in merged.get("arca_cuit_representada", "") if ch.isdigit())
    merged["empresa_cuit"] = cuit
    merged["arca_cuit_representada"] = cuit_rep or cuit

    if _es_placeholder(merged.get("empresa_razon_social", "")):
        errores.append("Falta razon social real (no dejes el ejemplo).")
    if len(cuit) != 11 or not validar_cuit_digito(cuit) or _es_placeholder(data.get("empresa_cuit", "")):
        errores.append("CUIT empresa inválido o incompleto (11 dígitos con digito verificador).")
    if len(merged["arca_cuit_representada"]) != 11 or not validar_cuit_digito(
        merged["arca_cuit_representada"]
    ):
        errores.append("CUIT representada ARCA inválido.")
    if _es_placeholder(merged.get("empresa_iibb", "")):
        errores.append("Falta IIBB.")
    if _es_placeholder(merged.get("empresa_inicio_actividades", "")):
        errores.append("Falta inicio de actividades.")
    if _es_placeholder(merged.get("empresa_domicilio", "")):
        errores.append("Falta domicilio.")

    pto = merged.get("arca_punto_venta", "")
    if not str(pto).isdigit() or int(pto) <= 0:
        errores.append("Punto de venta debe ser numérico > 0.")

    ambiente = (merged.get("arca_ambiente") or "").lower()
    if ambiente not in ("produccion", "homologacion"):
        errores.append("Ambiente debe ser produccion u homologacion.")
    merged["arca_ambiente"] = ambiente

    cond = (merged.get("empresa_condicion_iva") or "").strip().upper()
    if not cond or _es_placeholder(cond):
        errores.append("Falta condicion IVA (ej. MONOTRIBUTO o RESPONSABLE INSCRIPTO).")
    else:
        merged["empresa_condicion_iva"] = cond
        if "MONOTRIB" in cond:
            merged["fiscal_tipo_default"] = "C"
        elif (merged.get("fiscal_tipo_default") or "C").upper() not in ("A", "B", "C"):
            merged["fiscal_tipo_default"] = "B"

    cert_abs = _abs_under_base(merged["arca_cert_path"])
    key_abs = _abs_under_base(merged["arca_key_path"])
    if not os.path.isfile(cert_abs):
        errores.append("No está el certificado CRT: %s" % cert_abs)
    if not os.path.isfile(key_abs):
        errores.append("No está la clave KEY: %s" % key_abs)

    print("=== Resumen configuración ARCA ===")
    for k in (
        "empresa_razon_social",
        "empresa_cuit",
        "empresa_iibb",
        "empresa_inicio_actividades",
        "empresa_domicilio",
        "empresa_condicion_iva",
        "arca_punto_venta",
        "arca_ambiente",
        "arca_cuit_representada",
        "arca_cert_path",
        "arca_key_path",
        "fiscal_tipo_default",
    ):
        print("  %s = %s" % (k, merged.get(k, "")))

    if errores:
        print("\nNo se guardó. Completá / corregí:")
        for e in errores:
            print("  - %s" % e)
        return 2

    if args.dry_run:
        print("\nDry-run OK: la configuración es válida (no se escribió nada).")
        return 0

    save_fiscal_config(merged)
    print("\nConfiguración ARCA guardada en la base del POS.")
    print("Podés verificarla en Admin -> ARCA/Ticket.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
