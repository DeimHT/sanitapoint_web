"""Shared 576-dot layout for the R200 and the downloadable PDF."""
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from app.services.config_store import get_config


def _font(size, bold=False):
    windows = os.environ.get("WINDIR", "C:/Windows")
    for path in (os.path.join(windows, "Fonts", "arialbd.ttf" if bold else "arial.ttf"),
                 "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def render_receipt(db, ticket_num, servicio_nombre, monto, forma_pago, folio_kame,
                   estado_kame, rut_cliente, es_pase_libre, creado_en=None, servicio_codigo=None):
    image = Image.new("RGB", (576, 12000), "white")
    draw = ImageDraw.Draw(image)
    y = 16
    left, right = 16, 560

    def text(value, size=23, bold=False, align="center", gap=10):
        nonlocal y
        font = _font(size, bold)
        lines = []
        for paragraph in str(value).splitlines() or [""]:
            line = ""
            for word in paragraph.split():
                # Split long identifiers too; never clip at the paper edge.
                for char in word:
                    candidate = line + char
                    if draw.textlength(candidate, font=font) > right - left:
                        lines.append(line.rstrip())
                        line = char
                    else:
                        line = candidate
                line += " "
            lines.append(line.rstrip())
        for line in lines:
            width = draw.textlength(line, font=font)
            x = left if align == "left" else right - width if align == "right" else (576 - width) / 2
            draw.text((x, y), line, font=font, fill="black")
            y += size + 8
        y += gap

    def rule():
        nonlocal y
        draw.line((left, y, right, y), fill="black", width=2)
        y += 12

    box_top = y
    y += 18
    text(get_config(db, "empresa_rut", "") or "RUT no configurado", 27, True)
    title = "PASE LIBRE" if es_pase_libre else (
        "BOLETA ELECTRÓNICA" if estado_kame == "ok" and folio_kame else
        "BOLETA DE PRUEBA" if estado_kame == "mock" else "COMPROBANTE DE VENTA")
    text(title, 28, True)
    text(str(folio_kame or ticket_num), 28, True, gap=18)
    draw.rectangle((left, box_top, right, y), outline="black", width=3)
    y += 20
    office = get_config(db, "empresa_oficina_sii", "")
    if office:
        text("S.I.I. - " + office.upper(), 24, True)
    text(get_config(db, "empresa_nombre", "Servicios Sanitarios").upper())
    for key in ("empresa_giro", "empresa_direccion", "empresa_ciudad"):
        value = get_config(db, key, "")
        if value:
            text(value.upper())
    date = creado_en or datetime.now()
    days = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
    months = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
    y += 12
    text(f"{days[date.weekday()]}, {date.day:02d} de {months[date.month - 1]} de {date.year}", 23, True, "left")
    y += 10
    font = _font(23, True)
    for label, x in (("CÓDIGO", left), ("NOMBRE", 225), ("TOTAL", 480)):
        draw.text((x, y), label, font=font, fill="black")
    y += 38
    rule()
    text(servicio_nombre.upper(), align="left")
    if servicio_codigo is not None:
        text(f"COD. {servicio_codigo}", 20, align="left", gap=0)
    total = 0 if es_pase_libre else monto
    amount = f"{total:,}".replace(",", ".")
    text(f"1 UNID    x ${amount}    ${amount}", 23, align="right")
    rule()
    text(f"TOTAL: ${amount}", 38, True, "right", gap=18)
    text(f"Ticket: {ticket_num} · {date:%H:%M}", 19, align="left")
    if not es_pase_libre:
        payments = {"efectivo": "Efectivo", "tarjetas": "Tarjetas", "transferencia": "Transferencia", "debito": "Débito", "credito": "Crédito"}
        text("Pago: " + payments.get(forma_pago, forma_pago), 19, align="left")
    if rut_cliente:
        text("RUT cliente: " + rut_cliente, 19, align="left")
    if es_pase_libre:
        text("Acceso gratuito", 21, True)
    elif estado_kame == "mock":
        text("MODO PRUEBA - Sin emisión real", 21, True)
    elif estado_kame != "ok" or not folio_kame:
        text("Boleta pendiente de emisión", 21, True)
    else:
        text("Copia de venta sin timbre electrónico.\nDocumento tributario disponible en KAME.", 19)
    footer = get_config(db, "ticket_pie", "")
    if footer:
        y += 10
        text(footer, 21)
    return image.crop((0, 0, 576, y + 24)).convert("1")
