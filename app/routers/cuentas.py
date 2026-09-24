"""Gestión de cuentas de acceso (login). Contabilidad y Administrador.

Salvaguarda contra escalada de privilegios: solo un administrador puede crear o
modificar cuentas con rol administrador. Contabilidad puede administrar las
demás cuentas y restablecer contraseñas, pero no otorgarse el rol admin.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Cuenta
from app.permissions import GESTION_CUENTAS, ROLES
from app.schemas import CuentaCrearIn, CuentaEditarIn, CuentaOut
from app.security import hash_password

router = APIRouter(prefix="/api/cuentas", tags=["cuentas"],
                   dependencies=[Depends(require_cap(GESTION_CUENTAS))])


def _admins_activos(db: Session, excluir_id: int | None = None) -> int:
    q = db.query(Cuenta).filter(Cuenta.rol == "administrador", Cuenta.activo.is_(True))
    if excluir_id is not None:
        q = q.filter(Cuenta.id != excluir_id)
    return q.count()


@router.get("", response_model=list[CuentaOut])
def listar_cuentas(db: Session = Depends(get_db)):
    return db.query(Cuenta).order_by(Cuenta.username).all()


@router.post("", response_model=CuentaOut)
def crear_cuenta(body: CuentaCrearIn, db: Session = Depends(get_db),
                 actual: Cuenta = Depends(get_current_cuenta)):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(400, "Usuario y contraseña son obligatorios")
    if body.rol not in ROLES:
        raise HTTPException(400, "Rol inválido")
    if body.rol == "administrador" and actual.rol != "administrador":
        raise HTTPException(403, "Solo un administrador puede crear cuentas administradoras")
    if db.query(Cuenta).filter(Cuenta.username == username).first():
        raise HTTPException(400, "Ya existe una cuenta con ese usuario")
    cuenta = Cuenta(
        username=username,
        password_hash=hash_password(body.password),
        nombre=body.nombre.strip(),
        rol=body.rol,
        activo=True,
    )
    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.put("/{cuenta_id}", response_model=CuentaOut)
def editar_cuenta(cuenta_id: int, body: CuentaEditarIn, db: Session = Depends(get_db),
                  actual: Cuenta = Depends(get_current_cuenta)):
    cuenta = db.get(Cuenta, cuenta_id)
    if not cuenta:
        raise HTTPException(404, "Cuenta no encontrada")
    if body.rol not in ROLES:
        raise HTTPException(400, "Rol inválido")

    # Solo un administrador puede tocar cuentas admin o asignar el rol admin.
    if actual.rol != "administrador" and (cuenta.rol == "administrador" or body.rol == "administrador"):
        raise HTTPException(403, "Solo un administrador puede gestionar cuentas administradoras")

    # No dejar el sistema sin ningún administrador activo.
    quita_admin = cuenta.rol == "administrador" and (body.rol != "administrador" or not body.activo)
    if quita_admin and _admins_activos(db, excluir_id=cuenta.id) == 0:
        raise HTTPException(400, "Debe quedar al menos un administrador activo")

    cuenta.nombre = body.nombre.strip()
    cuenta.rol = body.rol
    cuenta.activo = body.activo
    if body.password:
        cuenta.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.post("/{cuenta_id}/desactivar")
def desactivar_cuenta(cuenta_id: int, db: Session = Depends(get_db),
                      actual: Cuenta = Depends(get_current_cuenta)):
    cuenta = db.get(Cuenta, cuenta_id)
    if not cuenta:
        raise HTTPException(404, "Cuenta no encontrada")
    if cuenta.id == actual.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta")
    if actual.rol != "administrador" and cuenta.rol == "administrador":
        raise HTTPException(403, "Solo un administrador puede desactivar cuentas administradoras")
    if cuenta.rol == "administrador" and _admins_activos(db, excluir_id=cuenta.id) == 0:
        raise HTTPException(400, "Debe quedar al menos un administrador activo")
    cuenta.activo = False
    db.commit()
    return {"ok": True}
