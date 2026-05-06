import json
import os
import re
import sqlite3
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from db_init import get_base_dir, get_db_path

_DEBUG_MAX_WRITE = 800000


def _texto_debug(contenido):
    if contenido is None:
        return ""
    if isinstance(contenido, bytes):
        return contenido.decode("utf-8", errors="replace")
    return str(contenido)


def _debug_afip_log(etiqueta, contenido_crudo):
    """
    Guarda respuesta cruda en debug_afip.txt y muestra los primeros 500 caracteres por consola.
    No lanza excepciones (fallos silenciosos si no hay permiso de escritura).
    """
    texto = _texto_debug(contenido_crudo)
    preview = texto[:500]
    try:
        print(
            "[AFIP DEBUG] %s — primeros 500 caracteres:\n%s"
            % (etiqueta, preview),
            flush=True,
        )
    except Exception:
        try:
            print(
                "[AFIP DEBUG] %s — (preview no imprimible en consola, ver debug_afip.txt)"
                % etiqueta,
                flush=True,
            )
        except Exception:
            pass

    path = os.path.join(get_base_dir(), "debug_afip.txt")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bloque = texto if len(texto) <= _DEBUG_MAX_WRITE else texto[:_DEBUG_MAX_WRITE] + "\n...[truncado en %d chars]\n" % _DEBUG_MAX_WRITE
    try:
        with open(path, "a", encoding="utf-8", errors="replace") as f:
            f.write("\n" + "=" * 72 + "\n")
            f.write("%s | %s\n" % (ts, etiqueta))
            f.write(bloque)
            if texto and len(set(texto[:200]) - set("\r\n\t ")) == 0:
                f.write("\n[nota: contenido parece solo espacios/saltos]\n")
    except OSError as e:
        try:
            print("[AFIP DEBUG] No se pudo escribir debug_afip.txt: %s" % e, flush=True)
        except Exception:
            pass


def _et_parse_notificar_si_falla(xml_str, contexto):
    """
    Intenta parsear con ElementTree; si falla, informa sin detener el programa.
    """
    if not (xml_str or "").strip():
        return
    try:
        ET.fromstring(xml_str)
    except ET.ParseError as pe:
        try:
            print(
                "[AFIP] xml.etree.ElementTree.ParseError (%s): %s"
                % (contexto, pe),
                flush=True,
            )
            print(
                "[AFIP] Recibido (repr primeros 600 chars): %r"
                % (xml_str[:600],),
                flush=True,
            )
        except Exception:
            pass
        _debug_afip_log("ParseError ET — %s — XML completo" % contexto, xml_str)


def _descargar_wsdl_saneado(url, cache_dir, nombre_archivo):
    """
    Descarga el WSDL crudo, lo guarda para debug y extrae solo el primer bloque
    <definitions>...</definitions> para evitar basura agregada por proxy/portal.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RodPOS/1.0",
            "Accept": "text/xml,application/xml,*/*;q=0.8",
        },
    )

    raw = None
    # Intento normal (seguro)
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read()
    except Exception as e1:
        # Fallback para servidores legacy con DH débil (caso reportado: DH_KEY_TOO_SMALL)
        msg = str(e1)
        if "DH_KEY_TOO_SMALL" in msg or "dh key too small" in msg.lower():
            _debug_afip_log(
                "WSDL descarga fallback SSL legacy",
                "Primer intento fallo con '%s'. Reintentando con SECLEVEL=1." % msg,
            )
            ctx2 = ssl.create_default_context()
            try:
                ctx2.set_ciphers("DEFAULT:@SECLEVEL=1")
            except Exception:
                pass
            with urllib.request.urlopen(req, timeout=20, context=ctx2) as resp:
                raw = resp.read()
        else:
            raise

    txt = _texto_debug(raw).replace("\x00", "").lstrip("\ufeff")
    _debug_afip_log("WSDL crudo descargado (%s)" % url, txt)

    m = re.search(
        r"(<\?xml[^>]*\?>\s*)?<(?:(?:\w+):)?definitions\b[\s\S]*?</(?:(?:\w+):)?definitions>",
        txt,
        flags=re.IGNORECASE,
    )
    saneado = m.group(0).strip() if m else txt.strip()

    if (not saneado) or (not saneado.startswith("<")):
        raise RuntimeError(
            "WSDL inválido para %s: respuesta vacía o no XML." % url
        )

    # Validación XML (informativa, sin abortar por esta vía).
    _et_parse_notificar_si_falla(saneado, "WSDL saneado %s" % url)

    wsdl_path = os.path.join(cache_dir, nombre_archivo)
    with open(wsdl_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(saneado)
    return wsdl_path


CONFIG_KEYS = [
    "empresa_razon_social",
    "empresa_cuit",
    "empresa_iibb",
    "empresa_inicio_actividades",
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


def _purge_ta_xml_files(cache_dir):
    """Borra tickets WSAA cacheados (TA-*.xml) para forzar uno nuevo."""
    if not os.path.isdir(cache_dir):
        return
    for fn in os.listdir(cache_dir):
        if fn.startswith("TA-") and fn.lower().endswith(".xml"):
            try:
                os.remove(os.path.join(cache_dir, fn))
            except OSError:
                pass


def _sanear_xml_ticket_acceso(ta):
    """
    El TA de WSAA a veces trae dos XML, texto extra o CRLF raro → 'junk after document element'.
    Extraemos solo el bloque loginTicketResponse y validamos con ElementTree.
    """
    if not ta or not str(ta).strip():
        return ta
    s = str(ta).replace("\x00", "")
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("\ufeff")

    m = re.search(
        r"(<\?xml\s+version\s*=\s*[\"']1\.0[\"'][^?]*\?>\s*)?"
        r"<\s*loginTicketResponse\b[^>]*>.*?</\s*loginTicketResponse\s*>",
        s,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if m:
        cand = m.group(0).strip()
        _et_parse_notificar_si_falla(cand, "TA candidato regex loginTicketResponse")
        return cand

    low = s.lower()
    end_tag = "</loginticketresponse>"
    k = low.find(end_tag)
    if k != -1:
        s = s[: k + len("</loginTicketResponse>")]
    elif low.count("<?xml") > 1:
        segundo = low.find("<?xml", 5)
        if segundo > 0:
            s = s[:segundo].strip()

    s = s.strip()
    if s:
        _et_parse_notificar_si_falla(s, "TA tras recorte por </loginTicketResponse>")
    return s


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


def _cuit_solo_digitos(cuit):
    return "".join(c for c in (cuit or "") if c.isdigit())


def _normalizar_tipo_comprobante_por_emisor(tipo_solicitado, cfg):
    """
    Ajusta el tipo de comprobante según condición IVA del emisor.
    Si el emisor es monotributista y se pide A/B, se emite C.
    """
    tipo = (tipo_solicitado or "B").strip().upper()
    cond = (cfg.get("empresa_condicion_iva") or "").strip().lower()
    es_mono = "monotrib" in cond
    if es_mono and tipo in ("A", "B"):
        return "C", (
            "Emisor configurado como monotributista: se reemplazó comprobante %s por C."
            % tipo
        )
    return tipo, ""


def _es_error_xml_corrupto(msg):
    m = (msg or "").lower()
    return (
        "junk after document" in m
        or "syntax error" in m
        or "not well-formed" in m
        or "mismatched tag" in m
        or "expat" in m
    )


def _emitir_arca_wsfe(payload, cfg):
    """
    Intenta emitir comprobante con PyAfipWs.
    Si no está instalada o falta config, lanza excepción para encolar.
    """
    faltantes = _validar_config_minima(cfg)
    if faltantes:
        raise RuntimeError("Falta configuración ARCA: " + ", ".join(faltantes))

    cuit_rep = _cuit_solo_digitos(cfg.get("arca_cuit_representada", ""))
    if len(cuit_rep) != 11:
        raise RuntimeError("CUIT representada ARCA debe tener 11 digitos (sin guiones).")

    try:
        from pyafipws.wsaa import WSAA
        from pyafipws.wsfev1 import WSFEv1
    except Exception:
        raise RuntimeError(
            "PyAfipWs no instalado. Instalá: python -m pip install pyafipws"
        )

    ambiente = (cfg.get("arca_ambiente") or "").strip().lower()
    # Producción: servicios1.afip.gov.ar (WSFE) y wsaa.afip.gov.ar (WSAA).
    # Homologación: wswhomo / wsaahomo — certificado de producción NO sirve ahí.
    if ambiente == "produccion":
        wsdl_fe = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
        wsdl_aa = "https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL"
    else:
        wsdl_fe = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
        wsdl_aa = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL"

    cert = cfg["arca_cert_path"].strip()
    key = cfg["arca_key_path"].strip()
    if not cert or not os.path.isfile(cert):
        raise FileNotFoundError(
            "No existe el archivo .crt configurado para ARCA: %s" % (cert or "<vacio>")
        )
    if not key or not os.path.isfile(key):
        raise FileNotFoundError(
            "No existe el archivo .key configurado para ARCA: %s" % (key or "<vacio>")
        )
    cache_dir = os.path.join(get_base_dir(), "cache_arca")
    os.makedirs(cache_dir, exist_ok=True)
    wsaa_wsdl_local = None
    wsfe_wsdl_local = None
    try:
        wsaa_wsdl_local = _descargar_wsdl_saneado(wsdl_aa, cache_dir, "wsaa_wsdl_saneado.xml")
    except Exception as e:
        _debug_afip_log("Error descargando/saneando WSDL WSAA", str(e))
        raise RuntimeError(
            "Error leyendo WSDL WSAA de ARCA. Posible proxy/firewall/portal cautivo inyectando contenido. Detalle: %s"
            % e
        ) from e
    try:
        wsfe_wsdl_local = _descargar_wsdl_saneado(wsdl_fe, cache_dir, "wsfe_wsdl_saneado.xml")
    except Exception as e:
        _debug_afip_log(
            "Error descargando/saneando WSDL WSFE (se usa URL directa como fallback)",
            str(e),
        )
        wsfe_wsdl_local = None

    _debug_afip_log(
        "URLs y ambiente ARCA (una vez por emision)",
        "arca_ambiente configurado: %r\n"
        "WSFE WSDL: %s\n"
        "WSAA WSDL: %s\n"
        "Produccion usa servicios1.afip.gov.ar + wsaa.afip.gov.ar.\n"
        "Homologacion usa wswhomo + wsaahomo (cert distinto al de produccion)."
        % (cfg.get("arca_ambiente"), wsdl_fe, wsdl_aa),
    )
    if ambiente != "produccion":
        try:
            print(
                "[AFIP] ADVERTENCIA: ambiente NO es produccion (%r). "
                "Certificado de PRODUCCION no sirve contra wswhomo/wsaahomo."
                % ambiente,
                flush=True,
            )
        except Exception:
            pass

    def _soap_crudo(obj):
        """Une XmlResponse del wrapper y del cliente SOAP (pysimplesoap)."""
        partes = []
        x1 = getattr(obj, "XmlResponse", None)
        partes.append("XmlResponse (wrapper): %s" % (len(_texto_debug(x1)) if x1 else 0))
        cli = getattr(obj, "client", None)
        if cli is not None:
            cr = getattr(cli, "xml_response", None)
            cq = getattr(cli, "xml_request", None)
            partes.append(
                "client.xml_response len=%s"
                % (len(_texto_debug(cr)) if cr else 0)
            )
            partes.append(
                "client.xml_request len=%s"
                % (len(_texto_debug(cq)) if cq else 0)
            )
            if cr:
                partes.append("--- client.xml_response ---\n%s" % _texto_debug(cr))
            elif cq:
                partes.append("(solo hay request reciente; response vacio)")
        return "\n".join(partes)

    def emitir_intento(numero=1):
        _debug_afip_log(
            "=== Inicio intento de emision fiscal #%d ===" % numero,
            "Si ves este bloque dos veces, hubo reintento automatico tras error XML en cache.",
        )

        wsaa = WSAA()
        wsaa.LanzarExcepciones = True
        try:
            ta = wsaa.Autenticar(
                "wsfe",
                cert,
                key,
            wsdl=wsaa_wsdl_local or wsdl_aa,
                cacert=True,
                cache=cache_dir,
            )
        except Exception as e_wsaa:
            detalle = "%s: %s" % (e_wsaa.__class__.__name__, str(e_wsaa))
            _debug_afip_log(
                "WSAA exception exacta",
                "Excepcion Python: %s\nWSAA.Excepcion: %s\nWSAA.Traceback: %s"
                % (detalle, getattr(wsaa, "Excepcion", ""), getattr(wsaa, "Traceback", "")),
            )
            raise RuntimeError("Error de Autenticación WSAA: %s" % detalle) from e_wsaa
        _debug_afip_log(
            "WSAA despues de Autenticar (SOAP / TA)",
            "%s\n%s"
            % (
                _soap_crudo(wsaa),
                (
                    "\nNOTA: Si XmlResponse esta vacio pero el TA (siguiente bloque) tiene contenido, "
                    "WSAA leyo el ticket desde archivo en cache_arca (sin llamada HTTP nueva)."
                    if not (getattr(wsaa, "XmlResponse", None) or getattr(getattr(wsaa, "client", None), "xml_response", None))
                    and ta
                    else ""
                ),
            ),
        )
        if not ta:
            raise RuntimeError(wsaa.Excepcion or "WSAA no devolvio ticket de acceso.")

        ta_raw = _texto_debug(ta).strip()
        if (not ta_raw) or (not ta_raw.startswith("<")):
            _debug_afip_log(
                "Error de Autenticacion WSAA — respuesta no XML",
                ta,
            )
            raise RuntimeError(
                "Error de Autenticación WSAA: respuesta vacía o no XML válido."
            )

        _debug_afip_log(
            "TA devuelto por WSAA.Autenticar (antes de sanear / antes de SetTicketAcceso)",
            ta,
        )

        ta_limpio = _sanear_xml_ticket_acceso(ta)
        ta_limpio_txt = _texto_debug(ta_limpio).strip()
        if (not ta_limpio_txt) or (not ta_limpio_txt.startswith("<")):
            _debug_afip_log(
                "Error de Autenticacion WSAA — TA saneado invalido",
                ta_limpio,
            )
            raise RuntimeError(
                "Error de Autenticación WSAA: ticket inválido luego de saneo."
            )
        _debug_afip_log("TA despues de _sanear_xml_ticket_acceso", ta_limpio)

        ws = WSFEv1()
        ws.LanzarExcepciones = True
        ok = ws.Conectar(cache_dir, wsfe_wsdl_local or wsdl_fe, "", None, True)
        _debug_afip_log(
            "WSFE despues de Conectar (intento %d)" % numero,
            "WSDL WSFE: %s\n%s"
            % ((wsfe_wsdl_local or wsdl_fe), _soap_crudo(ws)),
        )
        if not ok:
            raise RuntimeError(ws.Excepcion or "No se pudo conectar a WSFE (ARCA).")

        try:
            ws.SetTicketAcceso(ta_limpio)
        except Exception as exc_set:
            _debug_afip_log("ERROR en SetTicketAcceso — excepcion: %s" % exc_set, ta_limpio)
            raise

        ta = ta_limpio
        ws.Cuit = cuit_rep

        pto_vta = int(cfg["arca_punto_venta"] or "1")
        _debug_afip_log(
            "Punto de venta utilizado en emision",
            "arca_punto_venta=%s (configurado)"
            % pto_vta,
        )
        tipo_emitir, aviso_tipo = _normalizar_tipo_comprobante_por_emisor(
            payload["tipo_comprobante"], cfg
        )
        cbte_tipo_map = {"A": 1, "B": 6, "C": 11}
        cbte_tipo = cbte_tipo_map.get(tipo_emitir, 6)
        tipo_doc = 80 if tipo_emitir == "A" else 99
        nro_doc = int(payload["cliente_doc"]) if tipo_emitir == "A" else 0
        # RG 5616 / WSFE: obligatorio CondicionIVAReceptorId (error 10242 si falta).
        # B/C + CF Doc 99/0 → 5 Consumidor Final. A + CUIT → 1 RI.
        cond_iva_rec = 1 if tipo_emitir == "A" else 5
        imp_total_d = Decimal(str(payload["total"])).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        # Factura C (cbte_tipo 11): AFIP exige ImpIVA=0 y NO informar objeto IVA.
        if cbte_tipo == 11:
            imp_neto_d = imp_total_d
            imp_iva_d = Decimal("0.00")
        else:
            imp_neto_d = (imp_total_d / Decimal("1.21")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            imp_iva_d = (imp_total_d - imp_neto_d).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        imp_total = float(imp_total_d)
        imp_neto = float(imp_neto_d)
        imp_iva = float(imp_iva_d)

        ultimo = ws.CompUltimoAutorizado(cbte_tipo, pto_vta) or 0
        _debug_afip_log(
            "WSFE tras CompUltimoAutorizado",
            _soap_crudo(ws),
        )
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
            condicion_iva_receptor_id=cond_iva_rec,
        )
        if cbte_tipo != 11:
            ws.AgregarIva(5, imp_neto, imp_iva)  # 21%

        ok_cae = ws.CAESolicitar()
        _debug_afip_log("WSFE tras CAESolicitar", _soap_crudo(ws))
        if not ok_cae:
            raise RuntimeError(ws.ErrMsg or ws.Obs or "ARCA rechazo el comprobante")

        return {
            "cae": ws.CAE,
            "vto_cae": ws.Vencimiento,
            "numero": str(cbte_nro),
            "pto_vta": str(pto_vta),
            "tipo": tipo_emitir,
            "aviso_tipo": aviso_tipo,
        }

    try:
        return emitir_intento(1)
    except Exception as e1:
        if _es_error_xml_corrupto(str(e1)):
            _purge_ta_xml_files(cache_dir)
            try:
                return emitir_intento(2)
            except Exception as e2:
                raise RuntimeError(
                    "ARCA: ticket XML invalido incluso tras limpiar cache. "
                    "Borre manualmente la carpeta 'cache_arca' junto al .exe y reintente. "
                    "Detalle: %s" % e2
                ) from e2
        raise


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
                ("EMITIDO", result.get("tipo", payload["tipo_comprobante"]), result["cae"], result["numero"], "", venta_id),
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
                "SELECT id FROM fiscal_pendientes WHERE venta_id=? AND estado='PENDIENTE'",
                (venta_id,),
            )
            pend_row = cur.fetchone()
            if pend_row:
                cur.execute(
                    "UPDATE fiscal_pendientes SET payload_json=?, error_ultimo=? WHERE id=?",
                    (json.dumps(payload), err, pend_row[0]),
                )
            else:
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
