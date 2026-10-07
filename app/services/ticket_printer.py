"""
Generación e impresión del ticket interno + boleta.

- Siempre se genera un PDF (80mm, reportlab) que queda guardado en disco para
  descarga/reimpresión desde el historial.
- Si hay una impresora térmica ESC/POS configurada (red o USB), también se envía
  el mismo diseño de 80 mm a la impresora física.
"""
import os
import sys
from datetime import datetime

from reportlab.lib.units import mm as mmU
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
    "efectivo": "Efectivo", "tarjetas": "Tarjetas",
    "debito": "Tarjeta Débito",
    "credito": "Tarjeta Crédito",
    "transferencia": "Transferencia",
}


def ticket_pdf_path(ticket_num: str) -> str:
    return os.path.join(TICKETS_DIR, f"{ticket_num}.pdf")


def generar_ticket_pdf(db: Session, ticket_num: str, servicio_nombre: str, monto: int,
                        forma_pago: str, folio_kame: str | None, estado_kame: str,
                        rut_cliente: str | None, es_pase_libre: bool,
                        creado_en: datetime | None = None, servicio_codigo=None) -> str:
    if es_pase_libre:
        raise ValueError("Los pases libres no generan PDF")
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from app.services.receipt_layout import render_receipt

    receipt = render_receipt(db, ticket_num, servicio_nombre, monto, forma_pago,
                             folio_kame, estado_kame, rut_cliente, es_pase_libre, creado_en, servicio_codigo)
    width = 72 * mmU
    height = receipt.height * width / receipt.width
    path = ticket_pdf_path(ticket_num)
    doc = canvas.Canvas(path, pagesize=(PAGE_WIDTH, height + 2 * MARGIN))
    doc.drawImage(ImageReader(receipt.convert("RGB")), MARGIN, MARGIN,
                  width=width, height=height)
    doc.save()
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
    if kwargs.get("es_pase_libre"):
        return False, "Pase libre: no corresponde imprimir"
    tipo = get_config(db, "impresora_tipo", "ninguna")
    if tipo == "ninguna":
        return False, "Sin impresora térmica configurada"

    try:
        from escpos.printer import Network, Usb
    except ImportError:
        return False, "python-escpos no está instalado"

    printer = None
    try:
        if tipo == "red":
            ip = get_config(db, "impresora_ip", "")
            puerto = int(get_config(db, "impresora_puerto", "9100"))
            if not ip:
                return False, "Falta IP de la impresora de red"
            printer = Network(ip, port=puerto, timeout=5)
        elif tipo == "usb":
            if not Usb.is_usable():
                return False, "Falta el soporte USB. Cierra el servidor y abre iniciar_servidor.bat para instalarlo."
            vendor = get_config(db, "impresora_usb_vendor", "")
            product = get_config(db, "impresora_usb_product", "")
            if not vendor or not product:
                return False, "Faltan los identificadores VID y PID de la impresora USB"
            usb_args = {}
            if sys.platform == "win32":
                try:
                    import libusb_package
                except ImportError:
                    return False, "Falta libusb para Windows. Reinicia desde iniciar_servidor.bat para instalarlo."
                backend = libusb_package.get_libusb1_backend()
                if backend is None:
                    return False, "No se pudo cargar libusb. Reinicia el sistema y revisa la instalación del soporte USB."
                usb_args["backend"] = backend
            printer = Usb(int(vendor, 16), int(product, 16), usb_args=usb_args, timeout=5000)
        elif tipo == "windows":
            from escpos.printer import Win32Raw
            nombre = get_config(db, "impresora_nombre", "")
            if not nombre:
                return False, "Selecciona una impresora instalada en Windows"
            if not Win32Raw.is_usable():
                return False, "Falta el componente de impresión Windows. Reinicia el sistema desde iniciar_servidor.bat para instalarlo."
            printer = Win32Raw(nombre)
        else:
            return False, f"Tipo de impresora desconocido: {tipo}"

        from app.services.receipt_layout import render_receipt
        receipt = render_receipt(db, **kwargs)
        printer.set(align="center")
        printer.image(receipt, impl="bitImageRaster", center=False)
        printer.cut()
        return True, "OK"
    except Exception as e:
        return False, f"Error de impresión ESC/POS: {e}"
    finally:
        if printer is not None:
            try:
                printer.close()
            except Exception:
                pass


def emitir_ticket(db: Session, ticket_num: str, servicio_nombre: str, monto: int,
                   forma_pago: str, folio_kame: str | None, estado_kame: str,
                   rut_cliente: str | None, es_pase_libre: bool,
                   creado_en=None, servicio_codigo=None) -> dict:
    """Genera el PDF (siempre) e intenta imprimir en la térmica (si está configurada)."""
    if es_pase_libre:
        return {"pdf_path": None, "impreso_termica": False,
                "detalle_impresion": "Pase libre registrado sin boleta ni impresión"}
    pdf_path = generar_ticket_pdf(
        db, ticket_num, servicio_nombre, monto, forma_pago,
        folio_kame, estado_kame, rut_cliente, es_pase_libre,
        creado_en=creado_en, servicio_codigo=servicio_codigo,
    )
    if get_config(db, "impresora_automatica", "1") != "1":
        return {"pdf_path": pdf_path, "impreso_termica": False,
                "detalle_impresion": "Pulsa Imprimir boleta para enviarla a la impresora"}
    impreso, detalle = imprimir_escpos(
        db, ticket_num=ticket_num, servicio_nombre=servicio_nombre, monto=monto,
        forma_pago=forma_pago, folio_kame=folio_kame, estado_kame=estado_kame,
        rut_cliente=rut_cliente, es_pase_libre=es_pase_libre,
        creado_en=creado_en, servicio_codigo=servicio_codigo,
    )
    return {"pdf_path": pdf_path, "impreso_termica": impreso, "detalle_impresion": detalle}
