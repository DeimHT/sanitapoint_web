from datetime import date, datetime
import time
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap, require_any_cap
from app.models import Caja, Cuenta, MovimientoCaja, Servicio, Usuario, Venta
from app.permissions import EMITIR_BOLETAS, VER_HISTORIAL
from app.routers.caja import _caja_abierta, bloquear_caja, comprobar_servicio
from app.schemas import VentaIn, VentaOut
from app.services import ticket_printer
from app.services.kame_client import emitir_boleta, verificar_configuracion_punto_venta
from app.services.documentos_kame import DocumentoKameError, obtener_pdf, preparar_timbre
from app.services.cuadre import tipo_acceso

router = APIRouter(prefix="/api/ventas", tags=["ventas"],
                   dependencies=[Depends(get_current_cuenta)])


def boleta_incompleta(db, caja_id):
    return db.query(Venta).filter(Venta.caja_id == caja_id, Venta.es_pase_libre == False,
        Venta.estado_kame == "pendiente").order_by(Venta.id).first()


@router.get("/boleta-en-curso", response_model=VentaOut | None,
            dependencies=[Depends(require_cap(EMITIR_BOLETAS))])
def consultar_boleta_en_curso(db: Session = Depends(get_db), cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = _caja_abierta(db, cuenta.id)
    return boleta_incompleta(db, caja.id) if caja else None


@router.post("", response_model=VentaOut, dependencies=[Depends(require_cap(EMITIR_BOLETAS))])
def registrar_venta(body: VentaIn, db: Session = Depends(get_db),
                    cuenta: Cuenta = Depends(get_current_cuenta), request: Request = None):
    caja = _caja_abierta(db, cuenta.id)
    if not caja:
        raise HTTPException(400, "Debes abrir la caja antes de vender")

    if request and not caja.servicio:
        raise HTTPException(409, "Cierra el turno anterior sin servicio y abre una caja nueva antes de vender.")
    comprobar_servicio(caja, request)
    servicio = db.get(Servicio, body.servicio_id)
    if not servicio or not servicio.activo:
        raise HTTPException(404, "Servicio no encontrado")

    tipo = tipo_acceso(servicio.nombre)
    if caja.servicio == "Baño 2" and tipo == "ducha":
        raise HTTPException(400, "Baño 2 no tiene servicio de duchas")
    if tipo is None:
        raise HTTPException(400, "El servicio debe corresponder a baño o ducha")
    if body.es_pase_libre and tipo != "bano":
        raise HTTPException(400, "El pase libre corresponde al servicio de baño")
    if not body.es_pase_libre:
        try:
            verificar_configuracion_punto_venta(db)
        except DocumentoKameError as error:
            raise HTTPException(503, f"No se registro la venta: {error}")
    caja = bloquear_caja(db, caja.id)
    pendiente = boleta_incompleta(db, caja.id)
    if pendiente:
        raise HTTPException(409, f"Completa primero la boleta del ticket {pendiente.ticket}. No se registro otra venta.")

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
        if maximo != 0 and usados >= maximo:
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

    if venta.es_pase_libre:
        out = VentaOut.model_validate(venta)
        out.detalle_impresion = "Pase libre registrado sin boleta ni impresión"
        return out

    # La venta y su acceso ya están confirmados. No mantener bloqueada la caja
    # durante la llamada externa a KAME: otros usuarios pueden seguir atendiendo.
    folio_kame, estado_kame = (None, "omitido")
    if not body.es_pase_libre:
        inicio_kame = time.monotonic()
        print(f'[VENTA] Enviando a KAME ticket={venta.ticket}', flush=True)
        folio_kame, estado_kame = emitir_boleta(
            db, venta.servicio_nombre, monto, body.forma_pago, body.rut_cliente, ticket_num=venta.ticket
        )
        print(f'[VENTA] Respuesta KAME ticket={venta.ticket} estado={estado_kame} '
              f'duracion={time.monotonic() - inicio_kame:.1f}s', flush=True)
        venta.folio_kame = folio_kame if estado_kame != "error" else None
        venta.estado_kame = estado_kame
        db.commit()
        db.refresh(venta)

    out = VentaOut.model_validate(venta)
    out.detalle_kame = folio_kame if estado_kame == "error" else ""
    out.detalle_impresion = (venta.kame_error_documento or "Timbre disponible para imprimir en este computador."
                             if venta.estado_kame == "ok" else "Comprobante de prueba o venta sin timbre.")
    return out


@router.get("", response_model=list[VentaOut], dependencies=[Depends(require_cap(VER_HISTORIAL))])
def listar_ventas(desde: date | None = None, hasta: date | None = None,
                   servicio_id: int | None = None, db: Session = Depends(get_db),
                   cuenta: Cuenta = Depends(get_current_cuenta)):
    from app.services.reportes import get_ventas
    ventas = get_ventas(db, desde, hasta, servicio_id,
                        cuenta_id=cuenta.id if cuenta.rol == "cajero" else None)
    return [VentaOut.model_validate(v).model_copy(update={
        "cajero": v.caja.operador if v.caja else "Sin asignar",
        "cuenta_id": v.caja.cuenta_id if v.caja else None,
        "servicio_caja": v.caja.servicio if v.caja else None,
    }) for v in ventas]


def venta_autorizada(ticket: str, db: Session, cuenta: Cuenta) -> Venta:
    q = db.query(Venta).filter(Venta.ticket == ticket)
    if cuenta.rol == "cajero":
        q = q.join(Caja).filter(Caja.cuenta_id == cuenta.id)
    venta = q.first()
    if not venta:
        raise HTTPException(404, "Ticket no encontrado")
    return venta


@router.get("/{ticket}/pdf", dependencies=[Depends(require_any_cap(VER_HISTORIAL, EMITIR_BOLETAS))])
def descargar_ticket_pdf(ticket: str, db: Session = Depends(get_db),
                         cuenta: Cuenta = Depends(get_current_cuenta)):
    venta = venta_autorizada(ticket, db, cuenta)
    if venta.es_pase_libre:
        raise HTTPException(400, "Los pases libres no generan boleta ni PDF")
    if venta.estado_kame == "ok":
        try:
            path = obtener_pdf(venta)
        except (DocumentoKameError, OSError) as error:
            raise HTTPException(503, str(error) if isinstance(error, DocumentoKameError) else
                                "No se pudo recuperar el PDF de KAME. Reintenta sin registrar otra venta.")
        return FileResponse(path, media_type="application/pdf", filename=f"boleta-{venta.folio_kame}.pdf",
                            headers={"Cache-Control": "no-store"})
    path = ticket_printer.generar_ticket_pdf(
        db, venta.ticket, venta.servicio_nombre, venta.monto, venta.forma_pago,
        venta.folio_kame, venta.estado_kame, venta.rut_cliente, venta.es_pase_libre,
        creado_en=venta.creado_en,
        servicio_codigo=venta.servicio_id,
    )
    return FileResponse(path, media_type="application/pdf", filename=f"{ticket}.pdf",
                        headers={"Cache-Control": "no-store"})


@router.post("/{ticket}/imprimir", dependencies=[Depends(require_any_cap(VER_HISTORIAL, EMITIR_BOLETAS))])
def imprimir_boleta(ticket: str, db: Session = Depends(get_db),
                    cuenta: Cuenta = Depends(get_current_cuenta)):
    venta = venta_autorizada(ticket, db, cuenta)
    if venta.es_pase_libre:
        raise HTTPException(400, "Los pases libres no generan impresion")
    if venta.estado_kame == "pendiente":
        raise HTTPException(409, "La emision sigue en curso. Actualiza para consultar esta misma venta; no vuelvas a cobrar.")
    if venta.estado_kame == "ok":
        try:
            preparar_timbre(db, venta, esperar=True)
        except DocumentoKameError as error:
            print(f'[IMPRESION] Bloqueada ticket={venta.ticket} folio={venta.folio_kame}: {error}', flush=True)
            raise HTTPException(503, str(error))
    print(f'[IMPRESION] Preparada ticket={venta.ticket} folio={venta.folio_kame} caja={venta.caja_id}', flush=True)
    return {"ok": True, "mensaje": "Imprime desde el navegador de este computador.", "venta": VentaOut.model_validate(venta)}


@router.post("/{ticket}/impresion-eventos/{evento}",
             dependencies=[Depends(require_any_cap(VER_HISTORIAL, EMITIR_BOLETAS))])
def registrar_evento_impresion(ticket: str, evento: Literal["solicitada", "dialogo_cerrado", "error"],
                              db: Session = Depends(get_db),
                              cuenta: Cuenta = Depends(get_current_cuenta)):
    venta = venta_autorizada(ticket, db, cuenta)
    mensajes = {
        "solicitada": "Navegador solicito imprimir",
        "dialogo_cerrado": "Dialogo de impresion cerrado (puede haberse impreso o cancelado; papel no confirmado)",
        "error": "Error del navegador al cargar o solicitar la impresion",
    }
    print(f'[IMPRESION] {mensajes[evento]} ticket={venta.ticket} '
          f'folio={venta.folio_kame} caja={venta.caja_id} cuenta={cuenta.id}', flush=True)
    return {"ok": True}


@router.get("/{ticket}/imprimir", response_class=HTMLResponse,
            dependencies=[Depends(require_any_cap(VER_HISTORIAL, EMITIR_BOLETAS))])
def vista_impresion(ticket: str, db: Session = Depends(get_db),
                    cuenta: Cuenta = Depends(get_current_cuenta)):
    import base64
    import io
    from app.services.receipt_layout import render_receipt
    venta = venta_autorizada(ticket, db, cuenta)
    if venta.es_pase_libre:
        raise HTTPException(400, "Los pases libres no generan impresion")
    if venta.estado_kame == "pendiente":
        raise HTTPException(409, "La emision sigue en curso. Actualiza para consultar esta misma venta; no vuelvas a cobrar.")
    documento = None
    if venta.estado_kame == "ok":
        try:
            documento = preparar_timbre(db, venta)
        except DocumentoKameError as error:
            raise HTTPException(503, str(error))
    imagen = render_receipt(db, ticket_num=venta.ticket, servicio_nombre=venta.servicio_nombre,
        monto=venta.monto, forma_pago=venta.forma_pago, folio_kame=venta.folio_kame,
        estado_kame=venta.estado_kame, rut_cliente=venta.rut_cliente,
        es_pase_libre=False, creado_en=venta.creado_en, servicio_codigo=venta.servicio_id,
        documento_tributario=documento)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    datos = base64.b64encode(buffer.getvalue()).decode("ascii")
    alto_mm = imagen.height * 72 / imagen.width + 2
    print(f'[IMPRESION] Documento servido al navegador ticket={venta.ticket} folio={venta.folio_kame}', flush=True)
    return HTMLResponse('<!doctype html><html lang="es"><meta charset="utf-8">'
        f'<title>Imprimir ticket</title><style>@page{{size:80mm {alto_mm:.1f}mm;margin:0}}'
        'body{margin:0}img{display:block;width:72mm;margin:0 4mm;max-width:100%}</style>'
        '<script src="/static/js/impresion.js?v=1" defer></script>'
        f'<img id="ticket" data-eventos="/api/ventas/{venta.ticket}/impresion-eventos/" '
        'alt="Ticket" src="data:image/png;base64,' + datos + '"></html>',
        headers={"Cache-Control": "no-store"})
