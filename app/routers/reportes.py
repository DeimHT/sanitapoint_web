from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_cap
from app.permissions import VER_REPORTES
from app.services import reportes as svc

router = APIRouter(prefix="/api/reportes", tags=["reportes"],
                   dependencies=[Depends(require_cap(VER_REPORTES))])

MIME = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _titulo_subtitulo(desde: date | None, hasta: date | None, servicio_id: int | None,
                       db: Session) -> tuple[str, str]:
    titulo = "Reporte de ventas"
    partes = []
    if desde and hasta and desde == hasta:
        partes.append(f"Día: {desde.strftime('%d/%m/%Y')}")
    else:
        if desde:
            partes.append(f"Desde: {desde.strftime('%d/%m/%Y')}")
        if hasta:
            partes.append(f"Hasta: {hasta.strftime('%d/%m/%Y')}")
    if servicio_id:
        from app.models import Servicio
        servicio = db.get(Servicio, servicio_id)
        if servicio:
            partes.append(f"Servicio: {servicio.nombre}")
    subtitulo = "  |  ".join(partes) if partes else "Todas las fechas y servicios"
    return titulo, subtitulo


@router.get("/ventas")
def reporte_ventas(
    desde: date | None = None,
    hasta: date | None = None,
    servicio_id: int | None = None,
    formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    db: Session = Depends(get_db),
):
    ventas = svc.get_ventas(db, desde, hasta, servicio_id)
    titulo, subtitulo = _titulo_subtitulo(desde, hasta, servicio_id, db)

    if formato == "pdf":
        buf = svc.reporte_ventas_pdf(ventas, titulo, subtitulo)
        filename = "reporte_ventas.pdf"
    else:
        buf = svc.reporte_ventas_excel(ventas, titulo, subtitulo)
        filename = "reporte_ventas.xlsx"

    return StreamingResponse(
        buf, media_type=MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/anual")
def reporte_anual(
    anio: int = Query(..., ge=2000, le=2100),
    formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    db: Session = Depends(get_db),
):
    resumen = svc.resumen_anual(db, anio)
    if formato == "pdf":
        buf = svc.reporte_anual_pdf(resumen)
        filename = f"reporte_anual_{anio}.pdf"
    else:
        buf = svc.reporte_anual_excel(resumen)
        filename = f"reporte_anual_{anio}.xlsx"

    return StreamingResponse(
        buf, media_type=MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
