from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Servicio
from app.permissions import CONFIGURACION
from app.schemas import ServicioOut, ServicioPrecioIn

router = APIRouter(prefix="/api/servicios", tags=["servicios"],
                   dependencies=[Depends(get_current_cuenta)])


@router.get("", response_model=list[ServicioOut])
def listar_servicios(db: Session = Depends(get_db)):
    return db.query(Servicio).filter(Servicio.activo.is_(True)).order_by(Servicio.id).all()


@router.put("/{servicio_id}/precio", response_model=ServicioOut,
            dependencies=[Depends(require_cap(CONFIGURACION))])
def actualizar_precio(servicio_id: int, body: ServicioPrecioIn, db: Session = Depends(get_db)):
    servicio = db.get(Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, "Servicio no encontrado")
    servicio.precio = body.precio
    db.commit()
    db.refresh(servicio)
    return servicio
