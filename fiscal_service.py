import json
import sqlite3
from datetime import datetime

from db_init import get_db_path


CONFIG_KEYS = [
    "empresa_razon_social",
    "empresa_cuit",
    "empresa_iibb",
    "empresa_domicilio",
    "empresa_condicion_iva",
    "arca_punto_venta",
    "arca_ambiente",
    "arca_cert_path",
    "arca_key_path",
    "arca_cuit_representada",
    "ticket_logo_path",
    "ticket_pie_texto",
    "ticket_ancho_mm",
    "ticket_incluir_logo",
    "ticket_auto_imprimir",
]


def _connect():
    return sqlite3.connect(get_db_path())


def get_fiscal_config():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT clave, valor FROM fiscal_config")
        data = {k: v for k, v in cur.fetchall()}
        for k in CONFIG_KEYS:
            data.setdefault(k, "")
        return data
    finally:
        conn.close()


def save_fiscal_config(data):
    conn = _connect()
    try:
        cur = conn.cursor()
        for k in CONFIG_KEYS:
            cur.execute(
                "INSERT INTO fiscal_config (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (k, str(data.get(k, ""))),
            )
        conn.commit()
    finally:
        conn.close()


def _validar_config_minima(cfg):
    faltantes = []
    for key, label in [
        ("empresa_razon_social", "Razon social"),
        ("empresa_cuit", "CUIT empresa"),
        ("arca_punto_venta", "Punto de venta"),
        ("arca_cuit_representada", "CUIT representada"),
        ("arca_cert_path", "Ruta certificado CRT"),
        ("arca_key_path", "Ruta clave privada KEY"),
    ]:
        if not (cfg.get(key) or "").strip():
            faltantes.append(label)
    return faltantes


def _emitir_arca_wsfe(payload, cfg):
    """
    Intenta emitir comprobante con PyAfipWs.
    Si no está instalada o falta config, lanza excepción para encolar.
    """
    faltantes = _validar_config_minima(cfg)
    if faltantes:
        raise RuntimeError("Falta configuración ARCA: " + ", ".join(faltantes))

    try:
        from pyafipws.wsfev1 import WSFEv1
    except Exception:
        raise RuntimeError(
            "PyAfipWs no instalado. Instalá: python -m pip install pyafipws"
        )

    ws = WSFEv1()
    cache = ""
    ws.Cuit = int(cfg["arca_cuit_representada"])
    ws.SetTicketAcceso(cache, cfg["arca_cert_path"], cfg["arca_key_path"])
    ws.Conectar()

    pto_vta = int(cfg["arca_punto_venta"] or "1")
    cbte_tipo = 6 if payload["tipo_comprobante"] == "B" else 1
    tipo_doc = 99 if payload["tipo_comprobante"] == "B" else 80
    nro_doc = 0 if payload["tipo_comprobante"] == "B" else int(payload["cliente_doc"])
    imp_total = float(payload["total"])
    imp_neto = round(imp_total / 1.21, 2)
    imp_iva = round(imp_total - imp_neto, 2)

    ultimo = ws.CompUltimoAutorizado(cbte_tipo, pto_vta) or 0
    cbte_nro = int(ultimo) + 1
    fecha = datetime.now().strftime("%Y%m%d")

    ws.CrearFactura(
        concepto=1,
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        tipo_cbte=cbte_tipo,
        punto_vta=pto_vta,
        cbt_desde=cbte_nro,
        cbt_hasta=cbte_nro,
        imp_total=imp_total,
        imp_tot_conc=0.0,
        imp_neto=imp_neto,
        imp_iva=imp_iva,
        imp_trib=0.0,
        imp_op_ex=0.0,
        fecha_cbte=fecha,
    )
    ws.AgregarIva(5, imp_neto, imp_iva)  # 21%

    ok = ws.CAESolicitar()
    if not ok:
        raise RuntimeError(ws.ErrMsg or ws.Obs or "ARCA rechazo el comprobante")

    return {
        "cae": ws.CAE,
        "vto_cae": ws.Vencimiento,
        "numero": str(cbte_nro),
        "pto_vta": str(pto_vta),
        "tipo": payload["tipo_comprobante"],
    }


def emitir_o_encolar(venta_id, payload):
    cfg = get_fiscal_config()
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            result = _emitir_arca_wsfe(payload, cfg)
            cur.execute(
                "UPDATE ventas SET fiscal_estado=?, fiscal_tipo=?, fiscal_cae=?, "
                "fiscal_numero=?, fiscal_error=? WHERE id=?",
                ("EMITIDO", payload["tipo_comprobante"], result["cae"], result["numero"], "", venta_id),
            )
            conn.commit()
            return True, result
        except Exception as e:
            err = str(e)
            cur.execute(
                "UPDATE ventas SET fiscal_estado=?, fiscal_tipo=?, fiscal_error=? WHERE id=?",
                ("PENDIENTE", payload["tipo_comprobante"], err, venta_id),
            )
            cur.execute(
                "INSERT INTO fiscal_pendientes (venta_id, payload_json, estado, error_ultimo) "
                "VALUES (?, ?, 'PENDIENTE', ?)",
                (venta_id, json.dumps(payload), err),
            )
            conn.commit()
            return False, {"error": err}
    finally:
        conn.close()


def obtener_pendientes():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, venta_id, fecha_creado, error_ultimo FROM fiscal_pendientes "
            "WHERE estado='PENDIENTE' ORDER BY id"
        )
        return cur.fetchall()
    finally:
        conn.close()


def reintentar_pendiente(pendiente_id):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT venta_id, payload_json FROM fiscal_pendientes WHERE id=? AND estado='PENDIENTE'",
            (pendiente_id,),
        )
        row = cur.fetchone()
        if not row:
            return False, "Pendiente no encontrado"
        venta_id, payload_json = row
        payload = json.loads(payload_json)
        ok, res = emitir_o_encolar(venta_id, payload)
        if ok:
            cur.execute(
                "UPDATE fiscal_pendientes SET estado='EMITIDO', fecha_ultimo_intento=?, error_ultimo='' "
                "WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pendiente_id),
            )
            conn.commit()
            return True, "Emitido OK"
        cur.execute(
            "UPDATE fiscal_pendientes SET fecha_ultimo_intento=?, error_ultimo=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), res.get("error", "Error"), pendiente_id),
        )
        conn.commit()
        return False, res.get("error", "Error")
    finally:
        conn.close()
