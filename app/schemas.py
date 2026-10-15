from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Autenticación y cuentas de acceso ────────────────────────────────────────

ServicioLogin = Literal["Baño 1", "Baño 2"]


class LoginIn(BaseModel):
    servicio: ServicioLogin
    username: str
    password: str


class MeOut(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    caps: list[str] = []
    servicio: ServicioLogin | None = None


class CuentaOut(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    activo: bool
    creado_en: datetime

    class Config:
        from_attributes = True


class CuentaCrearIn(BaseModel):
    username: str
    password: str
    nombre: str = ""
    rol: str = "cajero"  # cajero | supervisor | contabilidad | administrador


class CuentaEditarIn(BaseModel):
    nombre: str
    rol: str
    activo: bool = True
    password: str | None = None  # si viene no vacío, cambia la contraseña


class ServicioOut(BaseModel):
    id: int
    nombre: str
    precio: int
    activo: bool

    class Config:
        from_attributes = True


class ServicioPrecioIn(BaseModel):
    precio: int


class CajaOut(BaseModel):
    servicio: ServicioLogin | None = None
    id: int
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    operador: str
    cuenta_id: int | None = None
    saldo_inicial: int
    saldo_final: int | None
    estado: str
    nro_apertura: int | None = None
    nro_cierre: int | None = None
    torniquete_bano_inicial: int | None = None
    torniquete_ducha_inicial: int | None = None
    torniquete_bano_final: int | None = None
    torniquete_ducha_final: int | None = None
    contador_bano: int = 0
    contador_ducha: int = 0
    ventas_bano: int = 0
    ventas_ducha: int = 0
    pases_bano: int = 0
    total_ventas: int = 0
    ventas_efectivo: int = 0
    total_retiros: int = 0
    n_ventas: int = 0
    saldo_esperado: int = 0
    cambio_dinero: int | None = None
    ingreso_ajustado_retiros: int | None = None
    diferencia_dinero: int | None = None
    personas_bano: int | None = None
    personas_ducha: int | None = None
    diferencia_bano: int | None = None
    diferencia_ducha: int | None = None

    class Config:
        from_attributes = True


class AbrirCajaIn(BaseModel):
    saldo_inicial: int = Field(ge=0)
    torniquete_bano_inicial: int = Field(ge=0)
    torniquete_ducha_inicial: int | None = Field(default=None, ge=0)


class CerrarCajaIn(BaseModel):
    saldo_final: int = Field(ge=0)
    torniquete_bano_final: int = Field(ge=0)
    torniquete_ducha_final: int | None = Field(default=None, ge=0)


class MovimientoIn(BaseModel):
    tipo: str  # ingreso | retiro
    monto: int = Field(gt=0)
    descripcion: str = ""
    caja_id: int | None = None


class MovimientoOut(BaseModel):
    id: int
    caja_id: int
    tipo: str
    monto: int
    descripcion: str
    creado_en: datetime

    class Config:
        from_attributes = True


class VentaIn(BaseModel):
    servicio_id: int
    forma_pago: Literal["efectivo", "tarjetas"]
    rut_cliente: str | None = None
    usuario_id: int | None = None
    es_pase_libre: bool = False


class VentaOut(BaseModel):
    kame_timbre_disponible: bool = False
    kame_error_documento: str = ""
    cajero: str = ""
    cuenta_id: int | None = None
    servicio_caja: str | None = None
    id: int
    ticket: str
    creado_en: datetime
    servicio_nombre: str
    monto: int
    forma_pago: str
    rut_cliente: str | None
    folio_kame: str | None
    estado_kame: str
    es_pase_libre: bool
    impreso_termica: bool = False
    detalle_impresion: str = ""
    detalle_kame: str = ""

    class Config:
        from_attributes = True


class UsuarioIn(BaseModel):
    nombre: str
    rut: str
    telefono: str = ""
    email: str = ""
    tipo: Literal["empleado", "locatario", "empleado_publico"] = "empleado"
    notas: str = ""


class UsuarioOut(BaseModel):
    id: int
    nombre: str
    rut: str | None
    telefono: str
    email: str
    tipo: str
    activo: bool
    fecha_registro: datetime
    notas: str

    class Config:
        from_attributes = True


class PaseIn(BaseModel):
    usuario_id: int
    servicio_id: int
    otorgado_por: str = "operador"


class ConfigIn(BaseModel):
    valores: dict[str, str]
