"""Acceso a la tabla `configuracion` (clave/valor) usada por KAME, ticket, impresora, etc."""
from sqlalchemy.orm import Session

from app.models import Configuracion


def get_config(db: Session, clave: str, default: str = "") -> str:
    row = db.get(Configuracion, clave)
    return row.valor if row else default


def get_all_config(db: Session) -> dict:
    return {c.clave: c.valor for c in db.query(Configuracion).all()}


def set_config(db: Session, clave: str, valor: str) -> None:
    row = db.get(Configuracion, clave)
    if row:
        row.valor = valor
    else:
        db.add(Configuracion(clave=clave, valor=valor))
    db.commit()
