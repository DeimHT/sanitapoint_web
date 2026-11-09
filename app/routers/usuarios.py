from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.deps import get_current_cuenta, require_cap, require_any_cap
from app.models import Pase, Usuario
from app.permissions import EMITIR_BOLETAS, GESTION_CLIENTES
from app.schemas import PaseIn, UsuarioIn, UsuarioOut
from app.services.config_store import get_config

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"],
                   dependencies=[Depends(get_current_cuenta)])


def _max_pases_dia(db: Session) -> int:
    return int(get_config(db, "pases_por_dia", "1"))


def _pases_usados_hoy(db: Session, usuario_id: int) -> int:
    hoy = datetime.now().date()
    return (
        db.query(Pase)
        .filter(Pase.usuario_id == usuario_id)
        .filter(Pase.creado_en >= datetime.combine(hoy, datetime.min.time()))
        .count()
    )


@router.get("", response_model=list[UsuarioOut], dependencies=[Depends(require_any_cap(GESTION_CLIENTES, EMITIR_BOLETAS))])
def listar_usuarios(solo_activos: bool = True, db: Session = Depends(get_db)):
    q = db.query(Usuario)
    if solo_activos:
        q = q.filter(Usuario.activo.is_(True))
    return q.order_by(Usuario.nombre).all()


@router.get("/lector/config", dependencies=[Depends(require_any_cap(GESTION_CLIENTES, EMITIR_BOLETAS))])
def configuracion_lector(db: Session = Depends(get_db)):
    return {"modo": "teclado", "nombre": "USB teclado local", "configuracion": "navegador"}


@router.get("/{usuario_id}", response_model=UsuarioOut, dependencies=[Depends(require_cap(GESTION_CLIENTES))])
def obtener_usuario(usuario_id: int, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    return usuario


@router.post("", response_model=UsuarioOut, dependencies=[Depends(require_cap(GESTION_CLIENTES))])
def crear_usuario(body: UsuarioIn, db: Session = Depends(get_db)):
    rut = body.rut.replace(".", "").replace(" ", "").upper()
    if any((u.rut or "").replace(".", "").replace(" ", "").upper() == rut for u in db.query(Usuario).all()):
        raise HTTPException(409, "Esta persona ya está registrada. Busca su RUT para editarla o revisar su estado.")
    usuario = Usuario(**body.model_dump())
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta persona ya está registrada.")
    db.refresh(usuario)
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioOut, dependencies=[Depends(require_cap(GESTION_CLIENTES))])
def editar_usuario(usuario_id: int, body: UsuarioIn, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    for k, v in body.model_dump().items():
        setattr(usuario, k, v)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/{usuario_id}/desactivar", dependencies=[Depends(require_cap(GESTION_CLIENTES))])
def desactivar_usuario(usuario_id: int, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    usuario.activo = False
    db.commit()
    return {"ok": True}


@router.get("/{usuario_id}/pases", dependencies=[Depends(require_cap(GESTION_CLIENTES))])
def ver_pases(usuario_id: int, db: Session = Depends(get_db)):
    pases = (
        db.query(Pase).filter(Pase.usuario_id == usuario_id).order_by(Pase.id.desc()).all()
    )
    return [
        {
            "fecha": p.creado_en.strftime("%d/%m/%Y"),
            "hora": p.creado_en.strftime("%H:%M"),
            "servicio_nombre": p.servicio.nombre if p.servicio else None,
            "otorgado_por": p.otorgado_por,
        }
        for p in pases
    ]


@router.get("/{usuario_id}/pases/check", dependencies=[Depends(require_any_cap(GESTION_CLIENTES, EMITIR_BOLETAS))])
def check_pase(usuario_id: int, db: Session = Depends(get_db)):
    usados = _pases_usados_hoy(db, usuario_id)
    maximo = _max_pases_dia(db)
    return {"usados": usados, "maximo": maximo, "disponible": maximo == 0 or usados < maximo}
