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


LOGO_TICKET = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "img", "logo_ticket.png")


def _lineas(draw, value, font, width):
    """Parte el texto por palabras (y por caracteres si una palabra no cabe)."""
    lines = []
    for paragraph in str(value).splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=font) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ""
            for char in word:
                if draw.textlength(line + char, font=font) > width:
                    lines.append(line)
                    line = char
                else:
                    line += char
        lines.append(line)
    return lines


def _logo():
    try:
        with Image.open(LOGO_TICKET) as original:
            logo = original.convert("RGBA")
    except OSError:
        return None
    logo = Image.alpha_composite(Image.new("RGBA", logo.size, "white"), logo).convert("RGB")
    logo.thumbnail((210, 110))
    return logo


def _render_boleta_simple(db, servicio_nombre, monto, folio_kame, creado_en, tributario):
    """Boleta electrónica en el formato 'Simple' de KAME, armada con el XML emitido."""
    ancho, left, right = 576, 16, 560
    image = Image.new("RGB", (ancho, 6000), "white")
    draw = ImageDraw.Draw(image)
    y = 16

    def escribir(value, size=21, bold=False, x=left, max_x=right, gap=6, align="left"):
        nonlocal y
        font = _font(size, bold)
        for line in _lineas(draw, value, font, max_x - x):
            w = draw.textlength(line, font=font)
            xx = x if align == "left" else (x + max_x - w) / 2 if align == "center" else max_x - w
            draw.text((xx, y), line, font=font, fill="black")
            y += size + gap

    def regla():
        nonlocal y
        draw.line((left, y, right, y), fill="black", width=2)
        y += 14

    def moneda(valor):
        return "$" + f"{int(valor):,}".replace(",", ".")

    rut = tributario.get("rut") or ""
    if "-" in rut and rut.split("-")[0].isdigit():
        cuerpo, dv = rut.rsplit("-", 1)
        rut = f"{int(cuerpo):,}".replace(",", ".") + "-" + dv

    # Cabecera: logo a la izquierda y recuadro con RUT, tipo y folio.
    logo = _logo()
    caja_x0, caja_x1 = (250, right) if logo else (88, 488)
    caja_top = y
    y += 12
    escribir(f"RUT   {rut}", 25, True, caja_x0 + 6, caja_x1 - 6, align="center")
    escribir("BOLETA ELECTRÓNICA", 24, True, caja_x0 + 6, caja_x1 - 6, align="center")
    escribir(f"Nº {folio_kame}", 25, True, caja_x0 + 6, caja_x1 - 6, align="center", gap=2)
    y += 10
    caja_bottom = y
    draw.rectangle((caja_x0, caja_top, caja_x1, caja_bottom), outline="black", width=3)
    if logo:
        image.paste(logo, (left, caja_top + (caja_bottom - caja_top - logo.height) // 2))
    y = caja_bottom + 12
    oficina = get_config(db, "empresa_oficina_sii", "")
    if oficina:
        escribir("S.I.I. - " + oficina.upper(), 23, True, align="center", gap=8)

    # Datos del emisor y fechas.
    emisor_top = y
    y += 10
    x = left + 8
    escribir(tributario.get("razon_social") or get_config(db, "empresa_nombre", ""), 24, True, x, right - 8, gap=8)
    for etiqueta, valor in (("Giro", tributario.get("giro")), ("Dirección", tributario.get("direccion")),
                            ("Ciudad", tributario.get("ciudad")),
                            ("Fono", get_config(db, "empresa_telefono", ""))):
        if valor:
            escribir(f"{etiqueta}: {valor}", 21, False, x, right - 8, gap=8)
    emision = creado_en or datetime.now()
    fecha = tributario.get("fecha") or emision.date()
    escribir(f"Fecha Documento: {fecha:%d/%m/%Y}", 21, False, x, right - 8, gap=8)
    escribir(f"Fecha Emisión: {emision:%d/%m/%Y - %H:%M:%S}", 21, False, x, right - 8, gap=8)
    y += 6
    draw.rectangle((left, emisor_top, right, y), outline="black", width=2)
    y += 22

    # Detalle.
    regla()
    cabecera = _font(17, True)
    draw.text((left + 6, y), "SKU", font=cabecera, fill="black")
    for etiqueta, borde in (("CANT.", 300), ("VALOR U.", 400), ("DESC.", 478), ("SUB.", right)):
        draw.text((borde - draw.textlength(etiqueta, font=cabecera), y), etiqueta, font=cabecera, fill="black")
    y += 30
    regla()
    escribir(servicio_nombre, 21, False, left + 8, right - 8, gap=8)
    fila = _font(21)
    for texto, borde in (("1", 300), (moneda(monto), 400), ("$0", 478), (moneda(monto), right)):
        draw.text((borde - draw.textlength(texto, font=fila), y), texto, font=fila, fill="black")
    y += 36
    regla()

    # Totales.
    y += 6
    total_font = _font(28, True)
    draw.text((110, y), "TOTAL:", font=total_font, fill="black")
    draw.text((330, y), moneda(monto), font=total_font, fill="black")
    y += 44
    if tributario.get("iva"):
        escribir(f"El IVA incluido en esta boleta es de : {moneda(tributario['iva'])}", 21, True, gap=8)
    y += 6

    # Timbre y datos de verificación.
    timbre = tributario["imagen"]
    if timbre.width > ancho:
        raise ValueError("El timbre no cabe en el ancho del ticket")
    image.paste(timbre, ((ancho - timbre.width) // 2, y))
    y += timbre.height + 4
    escribir("Timbre Electrónico S.I.I.", 22, True, align="center", gap=4)
    numero, resolucion = tributario.get("resolucion_numero"), str(tributario.get("resolucion_fecha") or "")
    if numero and resolucion:
        try:
            resolucion = datetime.strptime(resolucion, "%Y-%m-%d").strftime("%d-%m-%Y")
        except ValueError:
            pass
        escribir(f"Res. {numero} del {resolucion}", 19, False, align="center", gap=14)
    escribir("Documento electrónico emitido en www.kame.cl", 19, True, align="center", gap=4)
    escribir("Verifique el documento en sii.cl", 19, True, align="center", gap=4)
    return image.crop((0, 0, ancho, y + 24)).convert("1")


def render_receipt(db, ticket_num, servicio_nombre, monto, forma_pago, folio_kame,
                   estado_kame, rut_cliente, es_pase_libre, creado_en=None, servicio_codigo=None,
                   documento_tributario=None):
    if documento_tributario and estado_kame == "ok" and folio_kame and not es_pase_libre:
        return _render_boleta_simple(db, servicio_nombre, monto, folio_kame, creado_en, documento_tributario)
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

    tributario = documento_tributario or {}
    def empresa(clave, defecto=""):
        campos = {"empresa_rut": "rut", "empresa_nombre": "razon_social", "empresa_giro": "giro",
                  "empresa_direccion": "direccion", "empresa_ciudad": "ciudad"}
        return tributario.get(campos.get(clave)) or get_config(db, clave, defecto)

    box_top = y
    y += 18
    text(empresa("empresa_rut", "") or "RUT no configurado", 27, True)
    title = "PASE LIBRE" if es_pase_libre else (
        "BOLETA ELECTRÓNICA" if estado_kame == "ok" and folio_kame and documento_tributario else
        "BOLETA DE PRUEBA" if estado_kame == "mock" else "COMPROBANTE DE VENTA")
    text(title, 28, True)
    text(str(folio_kame or ticket_num), 28, True, gap=18)
    draw.rectangle((left, box_top, right, y), outline="black", width=3)
    y += 20
    office = get_config(db, "empresa_oficina_sii", "")
    if office:
        text("S.I.I. - " + office.upper(), 24, True)
    text(empresa("empresa_nombre", "Servicios Sanitarios").upper())
    for key in ("empresa_giro", "empresa_direccion", "empresa_ciudad"):
        value = empresa(key, "")
        if value:
            text(value.upper())
    date = tributario.get("fecha") or creado_en or datetime.now()
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
    for campo, etiqueta in (("neto", "Neto"), ("iva", "IVA"), ("exento", "Exento")):
        if tributario.get(campo):
            valor = f"{int(tributario[campo]):,}".replace(",", ".")
            text(f"{etiqueta}: ${valor}", 21, align="right", gap=0)
    text(f"TOTAL: ${amount}", 38, True, "right", gap=18)
    text(f"Ticket: {ticket_num} · {(creado_en or datetime.now()):%H:%M}", 19, align="left")
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
    elif documento_tributario:
        timbre = tributario["imagen"]
        if timbre.width > 576:
            raise ValueError("El timbre no cabe en el ancho del ticket")
        y += 10
        image.paste(timbre, ((576 - timbre.width) // 2, y))
        y += timbre.height
        text("Timbre Electrónico SII", 19)
        numero, fecha_resolucion = tributario.get("resolucion_numero"), tributario.get("resolucion_fecha")
        if numero and fecha_resolucion:
            text(f"Resolución N° {numero} de {fecha_resolucion}", 18)
        text("Verifique documento: www.sii.cl", 18)
    else:
        text("Copia de venta sin timbre electrónico.\nDocumento tributario disponible en KAME.", 19)
    footer = get_config(db, "ticket_pie", "")
    if footer:
        y += 10
        text(footer, 21)
    return image.crop((0, 0, 576, y + 24)).convert("1")
