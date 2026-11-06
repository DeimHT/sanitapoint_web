"""Comprobante de cierre para el mismo rollo térmico de 80 mm de las boletas."""
import base64
import io

from PIL import Image, ImageDraw

from app.services.config_store import get_config
from app.services.receipt_layout import _font, _lineas


def render_cierre(db, cierre):
    filas = []
    def texto(valor, size=23, bold=False, center=False):
        filas.append((str(valor), size, bold, center))
    def moneda(valor):
        return "—" if valor is None else "$" + f"{int(valor):,}".replace(",", ".")
    def fecha(valor):
        return valor.strftime("%d-%m-%Y %H:%M") if valor else "No registrada"
    texto(get_config(db, "empresa_nombre", "SanitaPoint"), 27, True, True)
    for clave in ("empresa_rut", "empresa_direccion", "empresa_ciudad"):
        valor = get_config(db, clave)
        if valor:
            texto(valor, 21, center=True)
    texto("CIERRE DE CAJA", 30, True, True)
    texto(f"Turno #{cierre.id}", 24, True, True)
    texto(f"Cajero: {cierre.operador}")
    texto(f"Servicio: {cierre.servicio or 'Sin asignar'}")
    texto(f"Apertura: {fecha(cierre.fecha_apertura)}", 21)
    texto(f"Cierre: {fecha(cierre.fecha_cierre)}", 21)
    texto("RESUMEN DEL TURNO", 25, True)
    for etiqueta, valor in (("Ventas pagadas", cierre.n_ventas),
                            ("Accesos baño pagados", cierre.ventas_bano),
                            ("Pases libres baño", cierre.pases_bano)):
        texto(f"{etiqueta}: {valor}")
    if cierre.servicio != "Baño 2":
        texto(f"Accesos ducha: {cierre.ventas_ducha}")
    texto(f"Total ventas: {moneda(cierre.total_ventas)}", 26, True)
    texto(f"Ventas efectivo: {moneda(cierre.ventas_efectivo)}")
    texto(f"Otros medios de pago: {moneda(cierre.total_ventas - cierre.ventas_efectivo)}")
    texto("CUADRE DE EFECTIVO", 25, True)
    for etiqueta, valor in (("Caja inicial", cierre.saldo_inicial),
                            ("Ventas efectivo (+)", cierre.ventas_efectivo),
                            ("Retiros (-)", cierre.total_retiros),
                            ("Efectivo esperado", cierre.saldo_esperado),
                            ("Efectivo contado", cierre.saldo_final)):
        texto(f"{etiqueta}: {moneda(valor)}")
    texto(f"Diferencia: {moneda(cierre.diferencia_dinero)}", 27, True)
    texto("Positivo: sobrante / Negativo: faltante", 19)
    texto("TORNIQUETES", 25, True)
    for tipo, nombre in (("bano", "Baño"), ("ducha", "Ducha")):
        if tipo == "ducha" and cierre.servicio == "Baño 2":
            continue
        texto(nombre.upper(), 23, True)
        for campo, etiqueta in ((f"torniquete_{tipo}_inicial", "Lectura inicial"),
                                 (f"torniquete_{tipo}_final", "Lectura final"),
                                 (f"personas_{tipo}", "Accesos por torniquete"),
                                 (f"contador_{tipo}", "Accesos registrados"),
                                 (f"diferencia_{tipo}", "Diferencia")):
            valor = getattr(cierre, campo)
            texto(f"{etiqueta}: {valor if valor is not None else 'No registrado'}", 22)
    texto("Diferencia = torniquete - registrados", 19)
    texto("Firma cajero: ____________________", 22)
    texto("Comprobante interno de cierre", 20, center=True)

    # Medir primero evita recortar nombres largos o cierres con más filas.
    medida = ImageDraw.Draw(Image.new("RGB", (576, 1)))
    lineas = []
    for valor, size, bold, center in filas:
        font = _font(size, bold)
        for linea in _lineas(medida, valor, font, 544):
            lineas.append((linea, font, size, center))
    imagen = Image.new("RGB", (576, 32 + sum(size + 10 for _, _, size, _ in lineas)), "white")
    draw = ImageDraw.Draw(imagen)
    y = 16
    for linea, font, size, center in lineas:
        x = (576 - draw.textlength(linea, font=font)) / 2 if center else 16
        draw.text((x, y), linea, font=font, fill="black")
        y += size + 10
    return imagen


def html_cierre(db, cierre):
    imagen = render_cierre(db, cierre)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    datos = base64.b64encode(buffer.getvalue()).decode("ascii")
    alto = imagen.height * 72 / imagen.width + 2
    return ('<!doctype html><html lang="es"><meta charset="utf-8">'
            f'<title>Cierre de caja {cierre.id}</title><style>'
            f'@page{{size:80mm {alto:.2f}mm;margin:0}}'
            'body{margin:0}img{display:block;width:72mm;margin:0 4mm;max-width:100%}'
            '</style><img alt="Comprobante de cierre" src="data:image/png;base64,' + datos + '" '
            'onload="window.focus();window.print()"></html>')
