from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Cuenta, MovimientoCaja, Servicio, Usuario, Venta
from app.permissions import EMITIR_BOLETAS, VER_HISTORIAL
from app.routers.caja import _caja_abierta, bloquear_caja
from app.schemas import VentaIn, VentaOut
from app.services import ticket_printer
from app.services.kame_client import emitir_boleta
from app.services.cuadre import tipo_acceso

router = APIRouter(prefix="/api/ventas", tags=["ventas"],
                   dependencies=[Depends(get_current_cuenta)])


@router.post("", response_model=VentaOut, dependencies=[Depends(require_cap(EMITIR_BOLETAS))])
def registrar_venta(body: VentaIn, db: Session = Depends(get_db),
                    cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = _caja_abierta(db, cuenta.id)
    if not caja:
        raise HTTPException(400, "Debes abrir la caja antes de vender")

    servicio = db.get(Servicio, body.servicio_id)
    if not servicio or not servicio.activo:
        raise HTTPException(404, "Servicio no encontrado")

    tipo = tipo_acceso(servicio.nombre)
    if tipo is None:
        raise HTTPException(400, "El servicio debe corresponder a baño o ducha")
    if body.es_pase_libre and tipo != "bano":
        raise HTTPException(400, "El pase libre corresponde al servicio de baño")
    caja = bloquear_caja(db, caja.id)

    if body.es_pase_libre:
        if not body.usuario_id:
            raise HTTPException(400, "El pase libre requiere un usuario")
        usuario = db.get(Usuario, body.usuario_id)
        if not usuario or not usuario.activo:
            raise HTTPException(404, "Usuario no encontrado")
        db.execute(update(Usuario).where(Usuario.id == usuario.id).values(nombre=Usuario.nombre))
        from app.routers.usuarios import _pases_usados_hoy, _max_pases_dia
        usados = _pases_usados_hoy(db, usuario.id)
        maximo = _max_pases_dia(db)
        if usados >= maximo:
            raise HTTPException(
                400, f"{usuario.nombre} ya usó {usados} pase(s) libre(s) hoy (límite: {maximo})"
            )
        from app.models import Pase
        db.add(Pase(usuario_id=usuario.id, servicio_id=servicio.id, otorgado_por=cuenta.username))

    monto = 0 if body.es_pase_libre else servicio.precio
    venta = Venta(
        ticket=f"pendiente-{uuid4().hex}", tipo_acceso=tipo, servicio_id=servicio.id, servicio_nombre=servicio.nombre,
        monto=monto, forma_pago=body.forma_pago, rut_cliente=body.rut_cliente,
        caja_id=caja.id, usuario_id=body.usuario_id,
        estado_kame="omitido" if body.es_pase_libre else "pendiente",
        es_pase_libre=body.es_pase_libre,
    )
    db.add(venta)
    db.flush()
    # La base asigna el ID para evitar tickets duplicados entre cajas simultáneas.
    venta.ticket = f"T{venta.id:06d}"
    if not body.es_pase_libre and monto > 0 and body.forma_pago == "efectivo":
        db.add(MovimientoCaja(
            caja_id=caja.id, tipo="ingreso", monto=monto,
            descripcion=f"{servicio.nombre} – {body.forma_pago}",
        ))

    db.commit()
    db.refresh(venta)

    # La venta y su acceso ya están confirmados. No mantener bloqueada la caja
    # durante la llamada externa a KAME: otros usuarios pueden seguir atendiendo.
    folio_kame, estado_kame = (None, "omitido")
    if not body.es_pase_libre:
        folio_kame, estado_kame = emitir_boleta(
            db, venta.servicio_nombre, monto, body.forma_pago, body.rut_cliente, ticket_num=venta.ticket
        )
        venta.folio_kame = folio_kame if estado_kame != "error" else None
        venta.estado_kame = estado_kame
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
    path = ticket_printer.generar_ticket_pdf(
        db, venta.ticket, venta.servicio_nombre, venta.monto, venta.forma_pago,
        venta.folio_kame, venta.estado_kame, venta.rut_cliente, venta.es_pase_libre,
        creado_en=venta.creado_en,
    )
    return FileResponse(path, media_type="application/pdf", filename=f"{ticket}.pdf",
                        headers={"Cache-Control": "no-store"})
