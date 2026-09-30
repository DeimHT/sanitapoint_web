"""Contadores y conciliación del turno, calculados desde sus ventas confirmadas.

No se mantiene una segunda copia mutable del contador: cada venta o pase aporta
un acceso. Así no se pierden incrementos con solicitudes simultáneas.
"""
import unicodedata

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Caja, MovimientoCaja, Venta
from app.schemas import CajaOut


def tipo_acceso(nombre: str, es_pase_libre: bool = False) -> str | None:
    if es_pase_libre:
        return "bano"
    normalizado = "".join(c for c in unicodedata.normalize("NFKD", nombre.casefold())
                          if not unicodedata.combining(c))
    if "ducha" in normalizado:
        return "ducha"
    if "bano" in normalizado:
        return "bano"
    return None


def resumen_caja(db: Session, caja: Caja) -> CajaOut:
    out = CajaOut.model_validate(caja)
    ventas = db.query(Venta).filter(Venta.caja_id == caja.id).all()
    for venta in ventas:
        tipo = venta.tipo_acceso or tipo_acceso(venta.servicio_nombre, venta.es_pase_libre)
        if tipo == "bano":
            out.contador_bano += 1
            if venta.es_pase_libre:
                out.pases_bano += 1
            else:
                out.ventas_bano += 1
        elif tipo == "ducha":
            out.contador_ducha += 1
            out.ventas_ducha += 1
        if not venta.es_pase_libre:
            out.total_ventas += venta.monto
            out.n_ventas += 1
            if venta.forma_pago == "efectivo":
                out.ventas_efectivo += venta.monto
    out.total_retiros = db.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)).filter(
        MovimientoCaja.caja_id == caja.id, MovimientoCaja.tipo == "retiro").scalar()
    out.saldo_esperado = caja.saldo_inicial + out.ventas_efectivo - out.total_retiros
    if caja.saldo_final is not None:
        out.cambio_dinero = caja.saldo_final - caja.saldo_inicial
        out.ingreso_ajustado_retiros = out.cambio_dinero + out.total_retiros
        out.diferencia_dinero = caja.saldo_final - out.saldo_esperado
    for tipo in ("bano", "ducha"):
        inicial = getattr(caja, f"torniquete_{tipo}_inicial")
        final = getattr(caja, f"torniquete_{tipo}_final")
        if inicial is not None and final is not None:
            personas = final - inicial
            setattr(out, f"personas_{tipo}", personas)
            setattr(out, f"diferencia_{tipo}", personas - getattr(out, f"contador_{tipo}"))
    return out
