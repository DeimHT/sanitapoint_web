from datetime import datetime

from pydantic import BaseModel


# ── Autenticación y cuentas de acceso ────────────────────────────────────────

class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    caps: list[str] = []


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
    id: int
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    operador: str
    saldo_inicial: int
    saldo_final: int | None
    estado: str
    nro_apertura: int | None = None
    nro_cierre: int | None = None

    class Config:
        from_attributes = True


class AbrirCajaIn(BaseModel):
    operador: str
    saldo_inicial: int = 0
    nro_apertura: int = 0


class CerrarCajaIn(BaseModel):
    saldo_final: int
    nro_cierre: int  # obligatorio: "Nro de aperturas" al cierre


class MovimientoIn(BaseModel):
    tipo: str  # ingreso | retiro
    monto: int
    descripcion: str = ""


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
    forma_pago: str
    rut_cliente: str | None = None
    usuario_id: int | None = None
    es_pase_libre: bool = False


class VentaOut(BaseModel):
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
    tipo: str = "cliente"
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
