"""
Generación e impresión del ticket interno + boleta.

- Siempre se genera un PDF (80mm, reportlab) que queda guardado en disco para
  descarga/reimpresión desde el historial.
- Si hay una impresora térmica ESC/POS configurada (red o USB), también se envía
  una copia de texto plano a la impresora física.
"""
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm as mmU
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
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
                        rut_cliente: str | None, es_pase_libre: bool,
                        creado_en: datetime | None = None) -> str:
    # Tipografía monoespaciada y bloques como un comprobante térmico.
    estilos = {
        (align, bold): ParagraphStyle(
            f"{align}-{bold}", fontName="Courier-Bold" if bold else "Courier",
            fontSize=10 if bold else 9, leading=13,
            alignment=TA_CENTER if align == "center" else TA_LEFT,
        )
        for align in ("center", "left") for bold in (False, True)
    }
    total_style = ParagraphStyle("total", parent=estilos[("left", True)],
                                 fontSize=16, leading=21)
    story = []
    for align, bold, texto in _lineas_escpos(
        ticket_num, servicio_nombre, monto, forma_pago, folio_kame,
        estado_kame, rut_cliente, es_pase_libre,
        get_config(db, "empresa_nombre", "Servicios Sanitarios"),
        get_config(db, "ticket_pie", "¡Gracias por su visita!"),
        empresa_rut=get_config(db, "empresa_rut", ""),
        empresa_direccion=get_config(db, "empresa_direccion", ""),
        empresa_telefono=get_config(db, "empresa_telefono", ""),
        creado_en=creado_en,
    ):
        if not texto:
            story.append(Spacer(1, 3 * mmU))
            continue
        style = total_style if texto.startswith("TOTAL:") else estilos[(align, bold)]
        story.append(Paragraph(escape(texto).replace("\n", "<br/>"), style))
    # Altura ajustada al contenido: evita una cola de papel vacía y permite
    # nombres/direcciones largos sin recortar campos ni dividir la boleta.
    ancho = PAGE_WIDTH - 2 * MARGIN - 12
    alto = sum(item.wrap(ancho, 10000)[1] for item in story)
    path = ticket_pdf_path(ticket_num)
    doc = SimpleDocTemplate(
        path, pagesize=(PAGE_WIDTH, max(100 * mmU, alto + 2 * MARGIN + 14)),
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    doc.build(story)
    return path


def _lineas_escpos(ticket_num, servicio_nombre, monto, forma_pago, folio_kame,
                    estado_kame, rut_cliente, es_pase_libre, empresa_nombre, ticket_pie,
                    empresa_rut="", empresa_direccion="", empresa_telefono="", creado_en=None):
    now = creado_en or datetime.now()
    yield ("center", True, empresa_nombre.upper())
    if es_pase_libre:
        titulo = "PASE LIBRE"
    elif estado_kame == "ok" and folio_kame:
        titulo = "BOLETA ELECTRÓNICA"
    elif estado_kame == "mock":
        titulo = "BOLETA DE PRUEBA"
    else:
        titulo = "COMPROBANTE DE VENTA"
    yield ("center", True, titulo)
    if not es_pase_libre and folio_kame and estado_kame in ("ok", "mock"):
        yield ("center", True, f"N° {folio_kame}")
    yield ("center", False, "")
    if empresa_rut:
        yield ("center", False, f"RUT: {empresa_rut}")
    if empresa_direccion:
        yield ("center", False, empresa_direccion)
    if empresa_telefono:
        yield ("center", False, f"Tel: {empresa_telefono}")
    yield ("center", False, "")
    yield ("center", True, "*****")
    yield ("center", False, "")
    yield ("left", False, f"Ticket: {ticket_num}")
    yield ("left", False, now.strftime("Fecha: %d/%m/%Y  %H:%M"))
    yield ("left", False, "")
    yield ("left", True, servicio_nombre)
    if not es_pase_libre:
        yield ("left", False, f"Pago: {FORMAS_LABEL.get(forma_pago, forma_pago)}")
    if rut_cliente:
        yield ("left", False, f"RUT cliente: {rut_cliente}")
    yield ("left", False, "")
    total = 0 if es_pase_libre else monto
    yield ("left", True, f"TOTAL: ${total:,.0f}".replace(",", "."))
    if es_pase_libre:
        yield ("left", False, "Acceso gratuito")
    yield ("left", False, "")
    if not es_pase_libre:
        if estado_kame == "ok" and folio_kame:
            yield ("left", False, f"Folio KAME: {folio_kame}")
        elif estado_kame == "mock":
            yield ("left", True, "MODO PRUEBA - Sin emisión real")
        else:
            yield ("left", True, "Boleta pendiente de emisión")
    if ticket_pie:
        yield ("center", False, "")
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
            empresa_nombre=empresa_nombre, ticket_pie=ticket_pie,
            empresa_rut=get_config(db, "empresa_rut", ""),
            empresa_direccion=get_config(db, "empresa_direccion", ""),
            empresa_telefono=get_config(db, "empresa_telefono", ""), **kwargs
        ):
            printer.set(align=align, bold=bold, double_height=texto.startswith("TOTAL:"),
                        double_width=texto.startswith("TOTAL:"))
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
