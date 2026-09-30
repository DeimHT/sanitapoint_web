from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Caja, Cuenta, MovimientoCaja, Venta
from app.permissions import (
    CAJA_APERTURA, CAJA_CIERRE, CAJA_RETIRO, VER_CIERRES, caps_de,
)
from app.schemas import (
    AbrirCajaIn, CajaOut, CerrarCajaIn, MovimientoIn, MovimientoOut,
)
from app.services.cuadre import resumen_caja

# El router exige estar autenticado; cada acción pide además su capacidad.
router = APIRouter(prefix="/api/caja", tags=["caja"],
                   dependencies=[Depends(get_current_cuenta)])


def _caja_abierta(db: Session, cuenta_id: int) -> Caja | None:
    return (
        db.query(Caja)
        .filter(Caja.estado == "abierta", Caja.cuenta_id == cuenta_id)
        .order_by(Caja.id.desc())
        .first()
    )


def _ultima_caja_cerrada(db: Session, cuenta_id: int) -> Caja | None:
    return (
        db.query(Caja)
        .filter(Caja.estado == "cerrada", Caja.cuenta_id == cuenta_id)
        .order_by(Caja.id.desc())
        .first()
    )


@router.get("", response_model=CajaOut | None)
def obtener_caja_abierta(db: Session = Depends(get_db),
                         cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = _caja_abierta(db, cuenta.id)
    return resumen_caja(db, caja) if caja else None


def bloquear_caja(db: Session, caja_id: int) -> Caja:
    # UPDATE adquiere el bloqueo también en SQLite (FOR UPDATE no lo hace).
    resultado = db.execute(update(Caja).where(
        Caja.id == caja_id, Caja.estado == "abierta"
    ).values(estado="abierta"))
    if resultado.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "La caja ya no está abierta")
    return db.query(Caja).filter(Caja.id == caja_id).populate_existing().one()


@router.get("/abiertas", response_model=list[CajaOut],
            dependencies=[Depends(require_cap(CAJA_RETIRO))])
def cajas_para_retiro(db: Session = Depends(get_db)):
    return [resumen_caja(db, c) for c in db.query(Caja).filter(Caja.estado == "abierta").all()]


@router.get("/ultimo-cierre", response_model=CajaOut | None)
def ultimo_cierre(db: Session = Depends(get_db), cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = _ultima_caja_cerrada(db, cuenta.id)
    return resumen_caja(db, caja) if caja else None


@router.get("/sugerencia-apertura", dependencies=[Depends(require_cap(CAJA_APERTURA))])
def sugerencia_apertura(db: Session = Depends(get_db), cuenta: Cuenta = Depends(get_current_cuenta)):
    """Lecturas finales del último turno del usuario, como referencia."""
    ultima = _ultima_caja_cerrada(db, cuenta.id)
    return {
        "torniquete_bano_inicial": ultima.torniquete_bano_final if ultima else None,
        "torniquete_ducha_inicial": ultima.torniquete_ducha_final if ultima else None,
    }


@router.post("/abrir", response_model=CajaOut, dependencies=[Depends(require_cap(CAJA_APERTURA))])
def abrir_caja(body: AbrirCajaIn, db: Session = Depends(get_db),
               cuenta: Cuenta = Depends(get_current_cuenta)):
    # Serializa aperturas del mismo usuario sin bloquear a otros en PostgreSQL.
    db.execute(update(Cuenta).where(Cuenta.id == cuenta.id).values(username=Cuenta.username))
    if _caja_abierta(db, cuenta.id):
        db.rollback()
        raise HTTPException(400, "Ya hay una caja abierta")
    caja = Caja(
        cuenta_id=cuenta.id,
        operador=cuenta.nombre.strip() or cuenta.username,
        saldo_inicial=body.saldo_inicial,
        torniquete_bano_inicial=body.torniquete_bano_inicial,
        torniquete_ducha_inicial=body.torniquete_ducha_inicial,
        estado="abierta",
    )
    db.add(caja)
    db.commit()
    db.refresh(caja)
    return resumen_caja(db, caja)


@router.post("/cerrar", response_model=CajaOut, dependencies=[Depends(require_cap(CAJA_CIERRE))])
def cerrar_caja(body: CerrarCajaIn, db: Session = Depends(get_db),
                cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = _caja_abierta(db, cuenta.id)
    if not caja:
        raise HTTPException(400, "No hay caja abierta")

    caja = bloquear_caja(db, caja.id)
    for tipo, etiqueta in (("bano", "baño"), ("ducha", "ducha")):
        inicial = getattr(caja, f"torniquete_{tipo}_inicial")
        final = getattr(body, f"torniquete_{tipo}_final")
        if inicial is not None and final < inicial:
            db.rollback()
            raise HTTPException(400, f"El torniquete de {etiqueta} final no puede ser menor que el inicial ({inicial}).")
        setattr(caja, f"torniquete_{tipo}_final", final)

    caja.fecha_cierre = datetime.now()
    caja.saldo_final = body.saldo_final
    caja.estado = "cerrada"
    db.commit()
    db.refresh(caja)
    return resumen_caja(db, caja)


@router.post("/movimiento", response_model=MovimientoOut,
             dependencies=[Depends(require_cap(CAJA_RETIRO))])
def registrar_movimiento(body: MovimientoIn, db: Session = Depends(get_db),
                          cuenta: Cuenta = Depends(get_current_cuenta)):
    # Este endpoint es el retiro de dinero de caja (los ingresos por venta se
    # registran automáticamente al vender). Solo Supervisor y Administrador.
    caja = db.get(Caja, body.caja_id) if body.caja_id else _caja_abierta(db, cuenta.id)
    if not caja:
        raise HTTPException(400, "No hay caja abierta")
    if body.tipo != "retiro":
        raise HTTPException(400, "Este endpoint solo registra retiros")
    caja = bloquear_caja(db, caja.id)
    mov = MovimientoCaja(caja_id=caja.id, tipo="retiro", monto=body.monto,
                         descripcion=body.descripcion)
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov


@router.get("/{caja_id}/movimientos", response_model=list[MovimientoOut])
def listar_movimientos(caja_id: int, db: Session = Depends(get_db),
                        cuenta: Cuenta = Depends(get_current_cuenta)):
    caja = db.get(Caja, caja_id)
    if not caja or (caja.cuenta_id != cuenta.id and not
                    (caps_de(cuenta.rol) & {CAJA_RETIRO, VER_CIERRES})):
        raise HTTPException(404, "Caja no encontrada")
    return (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.caja_id == caja_id)
        .order_by(MovimientoCaja.id.desc())
        .all()
    )


@router.get("/cierres", response_model=list[CajaOut], dependencies=[Depends(require_cap(VER_CIERRES))])
def listar_cierres(db: Session = Depends(get_db)):
    """Lista los cierres de caja (cajas cerradas) con sus totales. Contabilidad."""
    cajas = (
        db.query(Caja)
        .filter(Caja.estado == "cerrada")
        .order_by(Caja.id.desc())
        .all()
    )
    return [resumen_caja(db, c) for c in cajas]


@router.get("/resumen/hoy")
def resumen_hoy(db: Session = Depends(get_db), cuenta: Cuenta = Depends(get_current_cuenta)):
    hoy = datetime.now().date()
    ventas = (
        db.query(Venta).join(Caja, Venta.caja_id == Caja.id)
        .filter(Caja.cuenta_id == cuenta.id)
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
