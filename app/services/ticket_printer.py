"""
Generación e impresión del ticket interno + boleta.

- Siempre se genera un PDF (80mm, reportlab) que queda guardado en disco para
  descarga/reimpresión desde el historial.
- Si hay una impresora térmica ESC/POS configurada (red o USB), también se envía
  una copia de texto plano a la impresora física.
"""
import os
from datetime import datetime

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm as mmU
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.services.config_store import get_config

TICKETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "tickets",
)
os.makedirs(TICKETS_DIR, exist_ok=True)

PAGE_WIDTH = 80 * mmU
PAGE_HEIGHT = 200 * mmU
MARGIN = 4 * mmU

FORMAS_LABEL = {
    "efectivo": "Efectivo",
    "debito": "Tarjeta Débito",
    "credito": "Tarjeta Crédito",
    "transferencia": "Transferencia",
}


def ticket_pdf_path(ticket_num: str) -> str:
    return os.path.join(TICKETS_DIR, f"{ticket_num}.pdf")


def generar_ticket_pdf(db: Session, ticket_num: str, servicio_nombre: str, monto: int,
                        forma_pago: str, folio_kame: str | None, estado_kame: str,
                        rut_cliente: str | None, es_pase_libre: bool) -> str:
    styles = getSampleStyleSheet()
    center = ParagraphStyle("center", parent=styles["Normal"],
                             alignment=TA_CENTER, fontSize=8, leading=10)
    center_b = ParagraphStyle("center_b", parent=center,
                               fontName="Helvetica-Bold", fontSize=9)

    path = ticket_pdf_path(ticket_num)
    doc = SimpleDocTemplate(
        path, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )

    now = datetime.now()
    story = [
        Paragraph(get_config(db, "empresa_nombre", "Servicios Sanitarios"), center_b),
        Paragraph(f"RUT: {get_config(db, 'empresa_rut', '')}", center),
    ]
    direccion = get_config(db, "empresa_direccion")
    if direccion:
        story.append(Paragraph(direccion, center))
    telefono = get_config(db, "empresa_telefono")
    if telefono:
        story.append(Paragraph(f"Tel: {telefono}", center))

    story += [Spacer(1, 2 * mmU), HRFlowable(width="100%", thickness=0.5), Spacer(1, 1 * mmU)]

    if es_pase_libre:
        story.append(Paragraph("★  PASE LIBRE  ★", center_b))
        story.append(Spacer(1, 1 * mmU))

    story.append(Paragraph(f"TICKET  {ticket_num}", center_b))
    story.append(Paragraph(now.strftime("%d/%m/%Y  %H:%M"), center))
    story += [Spacer(1, 2 * mmU), HRFlowable(width="100%", thickness=0.5), Spacer(1, 1 * mmU)]

    story.append(Paragraph(servicio_nombre, center_b))
    story.append(Spacer(1, 1 * mmU))

    if es_pase_libre:
        story.append(Paragraph("MONTO:  $ 0  (Pase Libre)", center_b))
    else:
        story.append(Paragraph(f"MONTO:  ${monto:,.0f}".replace(",", "."), center_b))
        story.append(Paragraph(f"Forma de pago: {FORMAS_LABEL.get(forma_pago, forma_pago)}", center))

    if rut_cliente:
        story.append(Paragraph(f"RUT: {rut_cliente}", center))

    story += [Spacer(1, 2 * mmU), HRFlowable(width="100%", thickness=0.5), Spacer(1, 1 * mmU)]

    if not es_pase_libre:
        if estado_kame == "mock":
            story.append(Paragraph(f"Boleta (MODO PRUEBA) N° {folio_kame}", center))
        elif folio_kame and estado_kame == "ok":
            story.append(Paragraph(f"Boleta Electrónica N° {folio_kame}", center))
            story.append(Paragraph("Documento tributario válido SII", center))
        else:
            story.append(Paragraph("(Boleta pendiente de emisión)", center))

    story.append(Spacer(1, 2 * mmU))
    pie = get_config(db, "ticket_pie", "¡Gracias por su visita!")
    if pie:
        story.append(Paragraph(pie, center))

    doc.build(story)
    return path


def _lineas_escpos(ticket_num, servicio_nombre, monto, forma_pago, folio_kame,
                    estado_kame, rut_cliente, es_pase_libre, empresa_nombre, ticket_pie):
    now = datetime.now()
    yield ("center", True, empresa_nombre)
    yield ("center", False, now.strftime("%d/%m/%Y %H:%M"))
    yield ("center", True, f"TICKET {ticket_num}")
    if es_pase_libre:
        yield ("center", True, "*** PASE LIBRE ***")
    yield ("center", True, servicio_nombre)
    if es_pase_libre:
        yield ("center", True, "MONTO: $0 (Pase Libre)")
    else:
        yield ("center", True, f"MONTO: ${monto:,.0f}".replace(",", "."))
        yield ("center", False, f"Pago: {FORMAS_LABEL.get(forma_pago, forma_pago)}")
        if rut_cliente:
            yield ("center", False, f"RUT: {rut_cliente}")
        if estado_kame == "ok" and folio_kame:
            yield ("center", False, f"Boleta N {folio_kame}")
        elif estado_kame == "mock":
            yield ("center", False, f"Boleta PRUEBA {folio_kame}")
    if ticket_pie:
        yield ("center", False, ticket_pie)


def imprimir_escpos(db: Session, **kwargs) -> tuple[bool, str]:
    """Envía el ticket a la impresora térmica ESC/POS configurada. No lanza excepción."""
    tipo = get_config(db, "impresora_tipo", "ninguna")
    if tipo == "ninguna":
        return False, "Sin impresora térmica configurada"

    try:
        from escpos.printer import Network, Usb
    except ImportError:
        return False, "python-escpos no está instalado"

    try:
        if tipo == "red":
            ip = get_config(db, "impresora_ip", "")
            puerto = int(get_config(db, "impresora_puerto", "9100"))
            if not ip:
                return False, "Falta IP de la impresora de red"
            printer = Network(ip, port=puerto, timeout=5)
        elif tipo == "usb":
            vendor = get_config(db, "impresora_usb_vendor", "0x04b8")
            product = get_config(db, "impresora_usb_product", "0x0202")
            printer = Usb(int(vendor, 16), int(product, 16))
        else:
            return False, f"Tipo de impresora desconocido: {tipo}"

        empresa_nombre = get_config(db, "empresa_nombre", "Servicios Sanitarios")
        ticket_pie = get_config(db, "ticket_pie", "")
        for align, bold, texto in _lineas_escpos(
            empresa_nombre=empresa_nombre, ticket_pie=ticket_pie, **kwargs
        ):
            printer.set(align=align, bold=bold)
            printer.text(texto + "\n")
        printer.cut()
        printer.close()
        return True, "OK"
    except Exception as e:
        return False, f"Error de impresión ESC/POS: {e}"


def emitir_ticket(db: Session, ticket_num: str, servicio_nombre: str, monto: int,
                   forma_pago: str, folio_kame: str | None, estado_kame: str,
                   rut_cliente: str | None, es_pase_libre: bool) -> dict:
    """Genera el PDF (siempre) e intenta imprimir en la térmica (si está configurada)."""
    pdf_path = generar_ticket_pdf(
        db, ticket_num, servicio_nombre, monto, forma_pago,
        folio_kame, estado_kame, rut_cliente, es_pase_libre,
    )
    impreso, detalle = imprimir_escpos(
        db, ticket_num=ticket_num, servicio_nombre=servicio_nombre, monto=monto,
        forma_pago=forma_pago, folio_kame=folio_kame, estado_kame=estado_kame,
        rut_cliente=rut_cliente, es_pase_libre=es_pase_libre,
    )
    return {"pdf_path": pdf_path, "impreso_termica": impreso, "detalle_impresion": detalle}
