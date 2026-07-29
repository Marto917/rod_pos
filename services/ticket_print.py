"""Impresión térmica RAW (ESC/POS) sin PDF ni Acrobat.

El PDF se guarda solo como archivo en comprobantes/.
Al papel se manda texto ESC/POS / TEXT directo al spooler.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Iterable


_THERMAL_KEYWORDS = (
    "xp-58",
    "xp-80",
    "xp58",
    "xp80",
    "pos-58",
    "pos58",
    "pos-80",
    "xprinter",
    "rongta",
    "gprinter",
    "thermal",
    "termica",
    "térmica",
    "receipt",
    "ticket",
    "epson tm",
    "tm-t",
    "citiz",
    "bixolon",
)


def _encode_line(text: str) -> bytes:
    """CP850 cubre ñ/á típicos en impresoras térmicas AR."""
    raw = (text or "").replace("\r", "").replace("\n", "")
    return raw.encode("cp850", errors="replace")


def build_escpos(lineas: Iterable[str], *, cut: bool = True, feed_lines: int = 3) -> bytes:
    """Arma un ticket ESC/POS mínimo (init + líneas + avance + corte)."""
    out = bytearray()
    out.extend(b"\x1b\x40")  # ESC @ init
    out.extend(b"\x1b\x74\x02")  # code page 850
    out.extend(b"\x1b\x61\x00")  # left align
    for ln in lineas:
        out.extend(_encode_line(str(ln)))
        out.extend(b"\n")
    out.extend(b"\n" * max(0, int(feed_lines)))
    if cut:
        out.extend(b"\x1d\x56\x01")  # corte parcial
    return bytes(out)


def build_plain_text(lineas: Iterable[str], *, feed_lines: int = 4) -> bytes:
    lista = [str(x) for x in lineas]
    body = "\r\n".join(lista) + ("\r\n" * max(1, int(feed_lines)))
    return body.encode("cp850", errors="replace")


def es_impresora_virtual(nombre: str | None) -> bool:
    n = (nombre or "").lower()
    claves = (
        "pdf",
        "onenote",
        "xps",
        "fax",
        "microsoft print to",
        "send to onenote",
        "microsoft xps",
    )
    return any(k in n for k in claves)


def _parece_termica(nombre: str | None) -> bool:
    n = (nombre or "").lower()
    return any(k in n for k in _THERMAL_KEYWORDS)


def list_printers() -> list[str]:
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    # LOCAL | CONNECTIONS
    flags = 0x2 | 0x4
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)
    winspool.EnumPrintersW(flags, None, 1, None, 0, ctypes.byref(needed), ctypes.byref(returned))
    if needed.value <= 0:
        return []

    class PRINTER_INFO_1(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("pDescription", wintypes.LPWSTR),
            ("pName", wintypes.LPWSTR),
            ("pComment", wintypes.LPWSTR),
        ]

    buf = ctypes.create_string_buffer(needed.value)
    ok = winspool.EnumPrintersW(
        flags, None, 1, buf, needed.value, ctypes.byref(needed), ctypes.byref(returned)
    )
    if not ok:
        return []
    arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_1))
    names: list[str] = []
    for i in range(int(returned.value or 0)):
        name = (arr[i].pName or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def get_default_printer() -> str:
    if sys.platform != "win32":
        raise RuntimeError("Impresión solo disponible en Windows")
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    GetDefaultPrinterW = winspool.GetDefaultPrinterW
    GetDefaultPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    GetDefaultPrinterW.restype = wintypes.BOOL

    needed = wintypes.DWORD(0)
    GetDefaultPrinterW(None, ctypes.byref(needed))
    if needed.value <= 0:
        raise RuntimeError("No hay impresora predeterminada en Windows")
    buf = ctypes.create_unicode_buffer(needed.value)
    if not GetDefaultPrinterW(buf, ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    name = (buf.value or "").strip()
    if not name:
        raise RuntimeError("No hay impresora predeterminada en Windows")
    return name


def resolve_printer(preferred: str | None = None) -> str:
    """
    Elige impresora real para el ticket:
    1) Nombre configurado (si existe en el sistema)
    2) Predeterminada de Windows, si no es virtual
    3) Primera térmica detectada (XP-58, Xprinter, etc.)
    4) Primera no virtual
    """
    printers = list_printers()
    preferred = (preferred or "").strip()

    if preferred:
        for p in printers:
            if p.lower() == preferred.lower():
                return p
        # Si el nombre exacto no está, igual lo intentamos (a veces Enum no lista USB)
        if not es_impresora_virtual(preferred):
            return preferred

    try:
        default = get_default_printer()
    except Exception:
        default = ""

    if default and not es_impresora_virtual(default):
        return default

    for p in printers:
        if _parece_termica(p) and not es_impresora_virtual(p):
            return p

    for p in printers:
        if not es_impresora_virtual(p):
            return p

    disponibles = ", ".join(printers) if printers else "(ninguna)"
    raise RuntimeError(
        "No hay una impresora térmica usable.\n"
        "Predeterminada actual: %s\n"
        "Disponibles: %s\n\n"
        "Solución: en Windows poné la XP-58 (u otra térmica) como predeterminada,\n"
        "o carga su nombre exacto en Admin -> ARCA/Ticket -> Impresora termica."
        % (default or "(sin predeterminada)", disponibles)
    )


def _job_count(printer_name: str) -> int:
    """Cantidad de trabajos en cola (best-effort). -1 si no se pudo leer."""
    try:
        import ctypes
        from ctypes import wintypes

        winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
        OpenPrinter = winspool.OpenPrinterW
        ClosePrinter = winspool.ClosePrinter
        EnumJobsW = winspool.EnumJobsW

        h = wintypes.HANDLE()
        if not OpenPrinter(printer_name, ctypes.byref(h), None):
            return -1
        try:
            needed = wintypes.DWORD(0)
            returned = wintypes.DWORD(0)
            EnumJobsW(h, 0, 64, 1, None, 0, ctypes.byref(needed), ctypes.byref(returned))
            if needed.value <= 0:
                return 0
            buf = ctypes.create_string_buffer(needed.value)
            ok = EnumJobsW(
                h,
                0,
                64,
                1,
                buf,
                needed.value,
                ctypes.byref(needed),
                ctypes.byref(returned),
            )
            if not ok:
                return -1
            return int(returned.value)
        finally:
            ClosePrinter(h)
    except Exception:
        return -1


def esperar_cola_impresora(printer_name: str, timeout_s: float = 12.0) -> None:
    """Espera a que baje la cola (o un mínimo seguro)."""
    t0 = time.time()
    time.sleep(0.4)
    while time.time() - t0 < timeout_s:
        n = _job_count(printer_name)
        if n == 0:
            time.sleep(0.3)
            return
        if n < 0:
            time.sleep(1.0)
            return
        time.sleep(0.35)


def print_raw(
    data: bytes,
    printer_name: str | None = None,
    datatype: str = "RAW",
    doc_name: str = "ROD POS",
    wait: bool = True,
) -> str:
    """Envía bytes a la impresora (RAW ESC/POS o TEXT según el driver)."""
    if not data:
        raise ValueError("No hay datos para imprimir")
    if sys.platform != "win32":
        raise RuntimeError("Impresión solo disponible en Windows")

    import ctypes
    from ctypes import wintypes

    printer = resolve_printer(printer_name)
    if es_impresora_virtual(printer):
        raise RuntimeError(
            "La impresora elegida es virtual (%s). "
            "Poné la térmica (XP-58) como destino." % printer
        )

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    OpenPrinter = winspool.OpenPrinterW
    OpenPrinter.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
    OpenPrinter.restype = wintypes.BOOL

    ClosePrinter = winspool.ClosePrinter
    ClosePrinter.argtypes = [wintypes.HANDLE]
    ClosePrinter.restype = wintypes.BOOL

    StartDocPrinter = winspool.StartDocPrinterW
    StartDocPrinter.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    StartDocPrinter.restype = wintypes.DWORD

    EndDocPrinter = winspool.EndDocPrinter
    EndDocPrinter.argtypes = [wintypes.HANDLE]
    EndDocPrinter.restype = wintypes.BOOL

    StartPagePrinter = winspool.StartPagePrinter
    StartPagePrinter.argtypes = [wintypes.HANDLE]
    StartPagePrinter.restype = wintypes.BOOL

    EndPagePrinter = winspool.EndPagePrinter
    EndPagePrinter.argtypes = [wintypes.HANDLE]
    EndPagePrinter.restype = wintypes.BOOL

    WritePrinter = winspool.WritePrinter
    WritePrinter.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    WritePrinter.restype = wintypes.BOOL

    hprinter = wintypes.HANDLE()
    if not OpenPrinter(printer, ctypes.byref(hprinter), None):
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        doc = DOC_INFO_1(
            pDocName=str(doc_name or "ROD POS")[:120],
            pOutputFile=None,
            pDatatype=str(datatype or "RAW"),
        )
        job_id = StartDocPrinter(hprinter, 1, ctypes.byref(doc))
        if not job_id:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not StartPagePrinter(hprinter):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                written = wintypes.DWORD(0)
                buf = ctypes.create_string_buffer(data)
                if not WritePrinter(hprinter, buf, len(data), ctypes.byref(written)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if int(written.value or 0) <= 0:
                    raise RuntimeError("La impresora no aceptó datos (0 bytes escritos)")
            finally:
                EndPagePrinter(hprinter)
        finally:
            EndDocPrinter(hprinter)
    finally:
        ClosePrinter(hprinter)

    if wait:
        esperar_cola_impresora(printer)
    return printer


def _imprimir_archivo_texto(lineas: list[str], doc_name: str, printer_name: str | None) -> str:
    """Fallback: imprime un .txt con el verbo 'print' de Windows y espera."""
    import ctypes

    printer = resolve_printer(printer_name)
    if es_impresora_virtual(printer):
        raise RuntimeError(
            "La impresora elegida es virtual (%s). "
            "Poné la térmica (XP-58) como destino." % printer
        )

    fd, path = tempfile.mkstemp(prefix="rodpos_ticket_", suffix=".txt")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(build_plain_text(lineas, feed_lines=5))
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "print", path, None, None, 0
        )
        if int(rc) <= 32:
            raise RuntimeError("ShellExecute print falló (código %s)" % rc)
        time.sleep(1.2)
        esperar_cola_impresora(printer, timeout_s=15.0)
        return printer
    finally:
        try:
            def _cleanup(p=path):
                time.sleep(8)
                try:
                    os.remove(p)
                except Exception:
                    pass

            import threading

            threading.Thread(target=_cleanup, daemon=True).start()
        except Exception:
            pass


def imprimir_lineas(
    lineas: Iterable[str],
    *,
    cut: bool = True,
    doc_name: str = "ROD POS",
    wait: bool = True,
    printer_name: str | None = None,
) -> str:
    """
    Imprime el ticket intentando varios métodos (en orden):
    1) RAW ESC/POS
    2) TEXT plano al spooler
    3) Archivo .txt + verbo print de Windows
    Nunca imprime el PDF (evita Acrobat / metros de papel en blanco).
    """
    lista = [str(x) for x in lineas]
    if not lista:
        raise ValueError("Ticket vacío: no hay líneas para imprimir")

    errors: list[str] = []
    preferred = (printer_name or "").strip() or None

    try:
        return print_raw(
            build_escpos(lista, cut=cut),
            printer_name=preferred,
            datatype="RAW",
            doc_name=doc_name,
            wait=wait,
        )
    except Exception as e:
        errors.append("RAW: %s" % e)

    try:
        return print_raw(
            build_plain_text(lista),
            printer_name=preferred,
            datatype="TEXT",
            doc_name=doc_name,
            wait=wait,
        )
    except Exception as e:
        errors.append("TEXT: %s" % e)

    try:
        return _imprimir_archivo_texto(lista, doc_name, preferred)
    except Exception as e:
        errors.append("FILE: %s" % e)

    raise RuntimeError("No se pudo imprimir el ticket. " + " | ".join(errors))
