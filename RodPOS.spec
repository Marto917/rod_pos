# -*- mode: python ; coding: utf-8 -*-
# Empaqueta PyAfipWs y datos dentro del .exe para que funcione sin instalar Python en la PC cliente.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

try:
    _pyafip_datas = collect_data_files("pyafipws")
except Exception:
    _pyafip_datas = []

try:
    _pyafip_hidden = collect_submodules("pyafipws")
except Exception:
    _pyafip_hidden = []

# Reportes ya no usan matplotlib; excluir reduce tamaño y evita errores de numpy en otras PCs.
_excludes = ["matplotlib", "mpl_toolkits"]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("ui", "ui"), ("db", "db")] + _pyafip_datas,
    hiddenimports=_pyafip_hidden
    + [
        "pyafipws.wsfev1",
        "pyafipws.wsaa",
        "pyafipws.utils",
        "cryptography",
        "certifi",
        "pysimplesoap",
        "httplib2",
        "dbf",
        "fpdf",
        "qrcode",
        "PIL",
        "db",
        "db_init",
        "pos_config",
        "lan_server",
        "fiscal_service",
        "services",
        "services.stock_ops",
        "services.cierre_caja",
        "services.ajuste_caja",
        "services.ticket_print",
        "services.xlsx_writer",
        "services.arca_status",
        "ui.sales",
        "ui.arqueo",
        "ui.admin",
        "ui.recepcion",
        "ui.stock_view",
        "ui.menu_vendedor",
        "ui.login",
        "ui.theme",
        "ui.dialogs",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RodPOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["ui\\images\\logo.ico"],
)
