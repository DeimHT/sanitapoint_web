"""Definición central de roles y permisos (capacidades).

Modelo por capacidades: cada rol tiene un conjunto de acciones permitidas. Las
rutas de la API y las páginas piden una capacidad concreta, no un rol, para que
sea fácil ajustar quién puede hacer qué en un solo lugar.

Grupos (según requerimiento):
- Cajero: emite boletas, abre caja (ingresa Nro de torniquete/aperturas) y cierra
  su turno.
- Supervisor: retiros de caja.
- Contabilidad: ve informes de ventas y cierres, y administra las cuentas/claves.
- Administrador: acceso completo, incluidas las configuraciones.
"""

# ── Capacidades ──────────────────────────────────────────────────────────────
EMITIR_BOLETAS = "emitir_boletas"      # registrar ventas / emitir boleta
CAJA_APERTURA = "caja_apertura"        # abrir caja + Nro de torniquete
CAJA_CIERRE = "caja_cierre"            # cerrar turno
CAJA_RETIRO = "caja_retiro"            # retiro de dinero de caja
VER_HISTORIAL = "ver_historial"        # ver/reimprimir el detalle de ventas
VER_REPORTES = "ver_reportes"          # informes de ventas (PDF/Excel)
VER_CIERRES = "ver_cierres"            # ver los cierres de caja
GESTION_CLIENTES = "gestionar_clientes"  # clientes y pases libres
GESTION_CUENTAS = "gestionar_cuentas"  # administrar cuentas / claves
CONFIGURACION = "configuracion"        # KAME, tarifas, impresora

TODAS = {
    EMITIR_BOLETAS, CAJA_APERTURA, CAJA_CIERRE, CAJA_RETIRO, VER_HISTORIAL,
    VER_REPORTES, VER_CIERRES, GESTION_CLIENTES, GESTION_CUENTAS, CONFIGURACION,
}

# ── Roles ────────────────────────────────────────────────────────────────────
ROLES = ("cajero", "supervisor", "contabilidad", "administrador")

ETIQUETA_ROL = {
    "cajero": "Cajero",
    "supervisor": "Supervisor",
    "contabilidad": "Contabilidad",
    "administrador": "Administrador",
}

CAPS_POR_ROL: dict[str, set[str]] = {
    "cajero": {
        EMITIR_BOLETAS, CAJA_APERTURA, CAJA_CIERRE, VER_HISTORIAL, GESTION_CLIENTES,
    },
    "supervisor": {
        CAJA_RETIRO,
    },
    "contabilidad": {
        VER_REPORTES, VER_CIERRES, VER_HISTORIAL, GESTION_CUENTAS,
    },
    "administrador": set(TODAS),
}


def caps_de(rol: str) -> set[str]:
    return CAPS_POR_ROL.get(rol, set())


def tiene(rol: str, cap: str) -> bool:
    return cap in caps_de(rol)
