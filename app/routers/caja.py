from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Caja, MovimientoCaja, Venta
from app.permissions import (
    CAJA_APERTURA, CAJA_CIERRE, CAJA_RETIRO, VER_CIERRES,
)
from app.schemas import (
    AbrirCajaIn, CajaOut, CerrarCajaIn, MovimientoIn, MovimientoOut,
)

# El router exige estar autenticado; cada acción pide además su capacidad.
router = APIRouter(prefix="/api/caja", tags=["caja"],
                   dependencies=[Depends(get_current_cuenta)])


def _caja_abierta(db: Session) -> Caja | None:
    return (
        db.query(Caja)
        .filter(Caja.estado == "abierta")
        .order_by(Caja.id.desc())
        .first()
    )


def _ultima_caja_cerrada(db: Session) -> Caja | None:
    return (
        db.query(Caja)
        .filter(Caja.estado == "cerrada")
        .order_by(Caja.id.desc())
        .first()
    )


@router.get("", response_model=CajaOut | None)
def obtener_caja_abierta(db: Session = Depends(get_db)):
    return _caja_abierta(db)


@router.get("/sugerencia-apertura", dependencies=[Depends(require_cap(CAJA_APERTURA))])
def sugerencia_apertura(db: Session = Depends(get_db)):
    """Sugiere el 'Nro de aperturas' inicial tomando el del último cierre.

    El valor es solo una sugerencia: el operador puede modificarlo al abrir.
    """
    ultima = _ultima_caja_cerrada(db)
    sugerido = ultima.nro_cierre if ultima and ultima.nro_cierre is not None else 0
    return {"nro_apertura_sugerido": sugerido}


@router.post("/abrir", response_model=CajaOut, dependencies=[Depends(require_cap(CAJA_APERTURA))])
def abrir_caja(body: AbrirCajaIn, db: Session = Depends(get_db)):
    if _caja_abierta(db):
        raise HTTPException(400, "Ya hay una caja abierta")
    caja = Caja(
        operador=body.operador,
        saldo_inicial=body.saldo_inicial,
        nro_apertura=body.nro_apertura,
        estado="abierta",
    )
    db.add(caja)
    db.commit()
    db.refresh(caja)
    return caja


@router.post("/cerrar", response_model=CajaOut, dependencies=[Depends(require_cap(CAJA_CIERRE))])
def cerrar_caja(body: CerrarCajaIn, db: Session = Depends(get_db)):
    caja = _caja_abierta(db)
    if not caja:
        raise HTTPException(400, "No hay caja abierta")

    # El "Nro de aperturas" del cierre debe ser >= al de la apertura del día.
    if caja.nro_apertura is not None and body.nro_cierre < caja.nro_apertura:
        raise HTTPException(
            400,
            f"El Nro de aperturas al cierre ({body.nro_cierre}) no puede ser menor "
            f"que el de apertura del día ({caja.nro_apertura}).",
        )

    caja.fecha_cierre = datetime.now()
    caja.saldo_final = body.saldo_final
    caja.nro_cierre = body.nro_cierre
    caja.estado = "cerrada"
    db.commit()
    db.refresh(caja)
    return caja


@router.post("/movimiento", response_model=MovimientoOut,
             dependencies=[Depends(require_cap(CAJA_RETIRO))])
def registrar_movimiento(body: MovimientoIn, db: Session = Depends(get_db)):
    # Este endpoint es el retiro de dinero de caja (los ingresos por venta se
    # registran automáticamente al vender). Solo Supervisor y Administrador.
    caja = _caja_abierta(db)
    if not caja:
        raise HTTPException(400, "No hay caja abierta")
    if body.tipo != "retiro":
        raise HTTPException(400, "Este endpoint solo registra retiros")
    mov = MovimientoCaja(caja_id=caja.id, tipo="retiro", monto=body.monto,
                         descripcion=body.descripcion)
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov


@router.get("/{caja_id}/movimientos", response_model=list[MovimientoOut])
def listar_movimientos(caja_id: int, db: Session = Depends(get_db)):
    return (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.caja_id == caja_id)
        .order_by(MovimientoCaja.id.desc())
        .all()
    )


@router.get("/cierres", dependencies=[Depends(require_cap(VER_CIERRES))])
def listar_cierres(db: Session = Depends(get_db)):
    """Lista los cierres de caja (cajas cerradas) con sus totales. Contabilidad."""
    cajas = (
        db.query(Caja)
        .filter(Caja.estado == "cerrada")
        .order_by(Caja.id.desc())
        .all()
    )
    out = []
    for c in cajas:
        total_ventas = db.query(func.coalesce(func.sum(Venta.monto), 0)).filter(
            Venta.caja_id == c.id).scalar() or 0
        total_retiros = db.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)).filter(
            MovimientoCaja.caja_id == c.id, MovimientoCaja.tipo == "retiro").scalar() or 0
        n_ventas = db.query(func.count(Venta.id)).filter(Venta.caja_id == c.id).scalar() or 0
        out.append({
            "id": c.id,
            "operador": c.operador,
            "fecha_apertura": c.fecha_apertura,
            "fecha_cierre": c.fecha_cierre,
            "saldo_inicial": c.saldo_inicial,
            "saldo_final": c.saldo_final,
            "nro_apertura": c.nro_apertura,
            "nro_cierre": c.nro_cierre,
            "total_ventas": total_ventas,
            "n_ventas": n_ventas,
            "total_retiros": total_retiros,
        })
    return out


@router.get("/resumen/hoy")
def resumen_hoy(db: Session = Depends(get_db)):
    hoy = datetime.now().date()
    ventas = (
        db.query(Venta)
        .filter(Venta.creado_en >= datetime.combine(hoy, datetime.min.time()))
        .all()
    )
    resumen = {
        "total_transacciones": len(ventas),
        "total_monto": sum(v.monto for v in ventas),
        "efectivo": sum(v.monto for v in ventas if v.forma_pago == "efectivo"),
        "debito": sum(v.monto for v in ventas if v.forma_pago == "debito"),
        "credito": sum(v.monto for v in ventas if v.forma_pago == "credito"),
        "transferencia": sum(v.monto for v in ventas if v.forma_pago == "transferencia"),
        "pases_gratis": sum(1 for v in ventas if v.es_pase_libre),
    }
    return resumen
