"""Modelos ORM. Migra el esquema de sanitapoint_3/db/database.py a PostgreSQL."""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base

# Los timestamps se generan en la aplicación (hora local del servidor), no con
# server_default=func.now() de PostgreSQL: el contenedor/servidor de base de
# datos suele correr en UTC, lo que desalinea la hora que ve el navegador
# (interpreta el ISO string como hora local) respecto a la hora real.


class Cuenta(Base):
    """Cuenta de acceso al sistema (login). Distinta de `Usuario`, que son los
    clientes para pases libres."""
    __tablename__ = "cuentas"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    nombre = Column(String, nullable=False, default="")
    rol = Column(String, nullable=False, default="operador")  # operador | administrador
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, default=datetime.now)


class Configuracion(Base):
    __tablename__ = "configuracion"

    clave = Column(String, primary_key=True)
    valor = Column(Text, default="")


class Servicio(Base):
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    precio = Column(Integer, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)


class Caja(Base):
    __tablename__ = "cajas"

    id = Column(Integer, primary_key=True)
    fecha_apertura = Column(DateTime, default=datetime.now)
    fecha_cierre = Column(DateTime, nullable=True)
    operador = Column(String, nullable=False)
    cuenta_id = Column(Integer, ForeignKey("cuentas.id"), nullable=True, index=True)
    servicio = Column(String, nullable=True)
    saldo_inicial = Column(Integer, default=0)
    saldo_final = Column(Integer, nullable=True)
    estado = Column(String, default="abierta", nullable=False)  # abierta | cerrada
    # Campos históricos: los turnos nuevos usan las lecturas separadas de abajo.
    nro_apertura = Column(Integer, nullable=True)
    nro_cierre = Column(Integer, nullable=True)
    torniquete_bano_inicial = Column(Integer, nullable=True)
    torniquete_ducha_inicial = Column(Integer, nullable=True)
    torniquete_bano_final = Column(Integer, nullable=True)
    torniquete_ducha_final = Column(Integer, nullable=True)

    movimientos = relationship("MovimientoCaja", back_populates="caja")
    ventas = relationship("Venta", back_populates="caja")


class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"

    id = Column(Integer, primary_key=True)
    caja_id = Column(Integer, ForeignKey("cajas.id"), nullable=False)
    tipo = Column(String, nullable=False)  # ingreso | retiro
    monto = Column(Integer, nullable=False)
    descripcion = Column(String, default="")
    creado_en = Column(DateTime, default=datetime.now)

    caja = relationship("Caja", back_populates="movimientos")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    rut = Column(String, unique=True, nullable=True)
    telefono = Column(String, default="")
    email = Column(String, default="")
    tipo = Column(String, default="cliente")  # cliente | empleado | vip
    activo = Column(Boolean, default=True, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.now)
    notas = Column(Text, default="")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True)
    ticket = Column(String, unique=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.now)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=True)
    servicio_nombre = Column(String, nullable=False)
    tipo_acceso = Column(String, nullable=True)  # bano | ducha; snapshot del acceso
    monto = Column(Integer, nullable=False)
    forma_pago = Column(String, nullable=False)  # efectivo | debito | credito | transferencia
    rut_cliente = Column(String, nullable=True)
    folio_kame = Column(String, nullable=True)
    kame_documento_id = Column(String, nullable=True)
    estado_kame = Column(String, default="omitido")  # ok | error | omitido
    caja_id = Column(Integer, ForeignKey("cajas.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    es_pase_libre = Column(Boolean, default=False, nullable=False)

    caja = relationship("Caja", back_populates="ventas")
    servicio = relationship("Servicio")
    usuario = relationship("Usuario")


class Pase(Base):
    __tablename__ = "pases"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    creado_en = Column(DateTime, default=datetime.now)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=True)
    otorgado_por = Column(String, default="operador")

    usuario = relationship("Usuario")
    servicio = relationship("Servicio")
