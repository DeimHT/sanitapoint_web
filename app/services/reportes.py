"""Generación de reportes de ventas: por día, por rango de fechas, por servicio y anual.
Cada consulta se puede exportar en PDF (reportlab) o Excel (openpyxl)."""
import io
from calendar import month_name
from datetime import date, datetime, time, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.models import Venta

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _rango_datetime(desde: date | None, hasta: date | None):
    inicio = datetime.combine(desde, time.min) if desde else None
    fin = datetime.combine(hasta + timedelta(days=1), time.min) if hasta else None
    return inicio, fin


def get_ventas(db: Session, desde: date | None = None, hasta: date | None = None,
               servicio_id: int | None = None) -> list[Venta]:
    q = db.query(Venta)
    inicio, fin = _rango_datetime(desde, hasta)
    if inicio:
        q = q.filter(Venta.creado_en >= inicio)
    if fin:
        q = q.filter(Venta.creado_en < fin)
    if servicio_id:
        q = q.filter(Venta.servicio_id == servicio_id)
    return q.order_by(Venta.creado_en).all()


def _totales(ventas: list[Venta]) -> dict:
    totales = {"cantidad": len(ventas), "monto_total": 0,
               "efectivo": 0, "tarjetas": 0, "debito": 0, "credito": 0, "transferencia": 0,
               "pases_libres": 0}
    for v in ventas:
        totales["monto_total"] += v.monto
        if v.forma_pago in totales:
            totales[v.forma_pago] += v.monto
        if v.forma_pago in ("debito", "credito"):
            totales["tarjetas"] += v.monto
        if v.es_pase_libre:
            totales["pases_libres"] += 1
    return totales


# ── Reporte de ventas (día / rango / servicio) ────────────────────────────────

def reporte_ventas_pdf(ventas: list[Venta], titulo: str, subtitulo: str) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(titulo, styles["Title"]), Paragraph(subtitulo, styles["Normal"]),
              Spacer(1, 12)]

    data = [["Ticket", "Fecha", "Servicio", "Monto", "Forma de pago", "RUT", "Boleta"]]
    for v in ventas:
        data.append([
            v.ticket, v.creado_en.strftime("%d/%m/%Y %H:%M"), v.servicio_nombre,
            f"${v.monto:,.0f}".replace(",", "."), v.forma_pago,
            v.rut_cliente or "-", v.folio_kame or "-",
        ])

    tabla = Table(data, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565C0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(tabla)

    t = _totales(ventas)
    story.append(Spacer(1, 16))
    resumen = (
        f"Total transacciones: {t['cantidad']}  |  Monto total: "
        f"${t['monto_total']:,.0f}".replace(",", ".") +
        f"  |  Efectivo: ${t['efectivo']:,.0f}".replace(",", ".") +
        f"  |  Tarjetas: ${t['tarjetas']:,.0f}".replace(",", ".") +
        f"  |  Débito: ${t['debito']:,.0f}".replace(",", ".") +
        f"  |  Crédito: ${t['credito']:,.0f}".replace(",", ".") +
        f"  |  Transferencia: ${t['transferencia']:,.0f}".replace(",", ".") +
        f"  |  Pases libres: {t['pases_libres']}"
    )
    story.append(Paragraph(resumen, styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return buf


def reporte_ventas_excel(ventas: list[Venta], titulo: str, subtitulo: str) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas"

    ws.append([titulo])
    ws.append([subtitulo])
    ws.append([])
    header = ["Ticket", "Fecha", "Hora", "Servicio", "Monto", "Forma de pago",
              "RUT cliente", "Folio KAME", "Estado KAME", "Pase libre"]
    ws.append(header)
    for cell in ws[4]:
        cell.font = Font(bold=True)

    for v in ventas:
        ws.append([
            v.ticket, v.creado_en.strftime("%d/%m/%Y"), v.creado_en.strftime("%H:%M"),
            v.servicio_nombre, v.monto, v.forma_pago, v.rut_cliente or "",
            v.folio_kame or "", v.estado_kame, "Sí" if v.es_pase_libre else "",
        ])

    t = _totales(ventas)
    ws.append([])
    ws.append(["TOTALES", "", "", "", t["monto_total"], "", "", "", "", ""])
    ws.append(["Tarjetas", t["tarjetas"]])
    ws.append(["Efectivo", t["efectivo"], "Débito", t["debito"],
                "Crédito", t["credito"], "Transferencia", t["transferencia"],
                "Pases libres", t["pases_libres"]])

    for i, _ in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 16

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── Reporte anual (resumen por mes y por servicio) ────────────────────────────

def resumen_anual(db: Session, anio: int) -> dict:
    ventas = (
        db.query(Venta)
        .filter(extract("year", Venta.creado_en) == anio)
        .all()
    )
    por_mes = [{"mes": MESES_ES[i], "cantidad": 0, "monto": 0} for i in range(12)]
    por_servicio: dict[str, dict] = {}

    for v in ventas:
        idx = v.creado_en.month - 1
        por_mes[idx]["cantidad"] += 1
        por_mes[idx]["monto"] += v.monto

        srv = por_servicio.setdefault(v.servicio_nombre, {"cantidad": 0, "monto": 0})
        srv["cantidad"] += 1
        srv["monto"] += v.monto

    return {
        "anio": anio,
        "por_mes": por_mes,
        "por_servicio": por_servicio,
        "totales": _totales(ventas),
    }


def reporte_anual_pdf(resumen: dict) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Reporte anual {resumen['anio']}", styles["Title"]), Spacer(1, 12)]

    story.append(Paragraph("Ventas por mes", styles["Heading2"]))
    data_mes = [["Mes", "Transacciones", "Monto"]]
    for m in resumen["por_mes"]:
        data_mes.append([m["mes"], m["cantidad"], f"${m['monto']:,.0f}".replace(",", ".")])
    tabla_mes = Table(data_mes, repeatRows=1)
    tabla_mes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565C0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    story += [tabla_mes, Spacer(1, 20)]

    story.append(Paragraph("Ventas por servicio", styles["Heading2"]))
    data_srv = [["Servicio", "Transacciones", "Monto"]]
    for nombre, s in resumen["por_servicio"].items():
        data_srv.append([nombre, s["cantidad"], f"${s['monto']:,.0f}".replace(",", ".")])
    tabla_srv = Table(data_srv, repeatRows=1)
    tabla_srv.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    story += [tabla_srv, Spacer(1, 20)]

    t = resumen["totales"]
    story.append(Paragraph(
        f"Total anual: {t['cantidad']} transacciones — "
        f"${t['monto_total']:,.0f}".replace(",", "."), styles["Normal"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf


def reporte_anual_excel(resumen: dict) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Anual {resumen['anio']}"

    ws.append([f"Reporte anual {resumen['anio']}"])
    ws.append([])
    ws.append(["Mes", "Transacciones", "Monto"])
    for cell in ws[3]:
        cell.font = Font(bold=True)
    for m in resumen["por_mes"]:
        ws.append([m["mes"], m["cantidad"], m["monto"]])

    ws.append([])
    fila_srv = ws.max_row + 1
    ws.append(["Servicio", "Transacciones", "Monto"])
    for cell in ws[fila_srv]:
        cell.font = Font(bold=True)
    for nombre, s in resumen["por_servicio"].items():
        ws.append([nombre, s["cantidad"], s["monto"]])

    for col in "ABC":
        ws.column_dimensions[col].width = 20

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
