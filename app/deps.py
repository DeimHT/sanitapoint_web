"""Dependencias de autenticación y autorización para las rutas de la API."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cuenta
from app.permissions import caps_de


def get_current_cuenta(request: Request, db: Session = Depends(get_db)) -> Cuenta:
    """Devuelve la cuenta de la sesión actual o lanza 401 si no hay sesión."""
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401, "No autenticado")
    cuenta = db.get(Cuenta, uid)
    if not cuenta or not cuenta.activo:
        raise HTTPException(401, "Sesión inválida o cuenta inactiva")
    return cuenta


def require_cap(cap: str):
    """Fabrica una dependencia que exige una capacidad concreta (403 si falta)."""
    def dep(cuenta: Cuenta = Depends(get_current_cuenta)) -> Cuenta:
        if cap not in caps_de(cuenta.rol):
            raise HTTPException(403, "No tienes permiso para esta acción")
        return cuenta
    return dep
