from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta
from app.models import Caja, Cuenta
from app.permissions import caps_de
from app.schemas import LoginIn, MeOut, ServicioLogin
from app.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _me(cuenta: Cuenta, servicio: ServicioLogin | None = None) -> MeOut:
    return MeOut(
        id=cuenta.id, username=cuenta.username, nombre=cuenta.nombre,
        rol=cuenta.rol, caps=sorted(caps_de(cuenta.rol)),
        servicio=servicio,
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    cuenta = db.query(Cuenta).filter(Cuenta.username == body.username).first()
    if not cuenta or not cuenta.activo or not verify_password(body.password, cuenta.password_hash):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    abierta = db.query(Caja).filter(Caja.cuenta_id == cuenta.id, Caja.estado == "abierta").first()
    if abierta and abierta.servicio and abierta.servicio != body.servicio:
        raise HTTPException(409, f"Tienes una caja abierta en {abierta.servicio}. Cierra ese turno antes de cambiar de servicio.")
    request.session.clear()
    request.session["uid"] = cuenta.id
    request.session["servicio"] = body.servicio
    return _me(cuenta, body.servicio)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(request: Request, cuenta: Cuenta = Depends(get_current_cuenta)):
    return _me(cuenta, request.session.get("servicio"))
