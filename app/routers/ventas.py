from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import MovimientoCaja, Servicio, Usuario, Venta
from app.permissions import EMITIR_BOLETAS, VER_HISTORIAL
from app.routers.caja import _caja_abierta
from app.schemas import VentaIn, VentaOut
from app.services import ticket_printer
from app.services.kame_client import emitir_boleta

router = APIRouter(prefix="/api/ventas", tags=["ventas"],
                   dependencies=[Depends(get_current_cuenta)])


def _siguiente_ticket(db: Session) -> str:
    ultimo = db.query(Venta).order_by(Venta.id.desc()).first()
    num = int(ultimo.ticket.replace("T", "")) + 1 if ultimo else 1
    return f"T{num:06d}"


@router.post("", response_model=VentaOut, dependencies=[Depends(require_cap(EMITIR_BOLETAS))])
def registrar_venta(body: VentaIn, db: Session = Depends(get_db)):
    caja = _caja_abierta(db)
    if not caja:
        raise HTTPException(400, "Debes abrir la caja antes de vender")

    servicio = db.get(Servicio, body.servicio_id)
    if not servicio:
        raise HTTPException(404, "Servicio no encontrado")

    if body.es_pase_libre:
        if not body.usuario_id:
            raise HTTPException(400, "El pase libre requiere un usuario")
        usuario = db.get(Usuario, body.usuario_id)
        if not usuario:
            raise HTTPException(404, "Usuario no encontrado")
        from app.routers.usuarios import _pases_usados_hoy, _max_pases_dia
        usados = _pases_usados_hoy(db, usuario.id)
        maximo = _max_pases_dia(db)
        if usados >= maximo:
            raise HTTPException(
                400, f"{usuario.nombre} ya usó {usados} pase(s) libre(s) hoy (límite: {maximo})"
            )
        from app.models import Pase
        db.add(Pase(usuario_id=usuario.id, servicio_id=servicio.id, otorgado_por="operador"))

    ticket = _siguiente_ticket(db)
    monto = 0 if body.es_pase_libre else servicio.precio
    folio_kame, estado_kame = (None, "omitido")
    if not body.es_pase_libre:
        folio_kame, estado_kame = emitir_boleta(
            db, servicio.nombre, monto, body.forma_pago, body.rut_cliente, ticket_num=ticket
        )

    venta = Venta(
        ticket=ticket, servicio_id=servicio.id, servicio_nombre=servicio.nombre,
        monto=monto, forma_pago=body.forma_pago, rut_cliente=body.rut_cliente,
        folio_kame=folio_kame if estado_kame != "error" else None,
        estado_kame=estado_kame, caja_id=caja.id, usuario_id=body.usuario_id,
        es_pase_libre=body.es_pase_libre,
    )
    db.add(venta)

    if not body.es_pase_libre and monto > 0:
        db.add(MovimientoCaja(
            caja_id=caja.id, tipo="ingreso", monto=monto,
            descripcion=f"{servicio.nombre} – {body.forma_pago}",
        ))

    db.commit()
    db.refresh(venta)

    resultado_impresion = ticket_printer.emitir_ticket(
        db, venta.ticket, venta.servicio_nombre, venta.monto, venta.forma_pago,
        venta.folio_kame, venta.estado_kame, venta.rut_cliente, venta.es_pase_libre,
    )

    out = VentaOut.model_validate(venta)
    out.detalle_kame = folio_kame if estado_kame == "error" else ""
    out.impreso_termica = resultado_impresion["impreso_termica"]
    out.detalle_impresion = resultado_impresion["detalle_impresion"]
    return out


@router.get("", response_model=list[VentaOut], dependencies=[Depends(require_cap(VER_HISTORIAL))])
def listar_ventas(desde: date | None = None, hasta: date | None = None,
                   servicio_id: int | None = None, db: Session = Depends(get_db)):
    from app.services.reportes import get_ventas
    return get_ventas(db, desde, hasta, servicio_id)


@router.get("/{ticket}/pdf", dependencies=[Depends(require_cap(VER_HISTORIAL))])
def descargar_ticket_pdf(ticket: str, db: Session = Depends(get_db)):
    venta = db.query(Venta).filter(Venta.ticket == ticket).first()
    if not venta:
        raise HTTPException(404, "Ticket no encontrado")
    path = ticket_printer.ticket_pdf_path(ticket)
    return FileResponse(path, media_type="application/pdf", filename=f"{ticket}.pdf")
