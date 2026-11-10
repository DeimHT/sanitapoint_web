"""Recuperacion de documentos existentes y timbre original de KAME.

KAME entrega el XML firmado (Xml) y el PDF en Base64 (ArchivoBase64PDF).
No genera CAF, firmas, folios ni timbres de prueba para documentos reales.
"""
import base64
import binascii
from datetime import date
import hashlib
import math
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "documentos_kame"


class DocumentoKameError(ValueError):
    pass


class DocumentoKameTemporal(DocumentoKameError):
    """Solo la consulta de un documento existente admite reintentos automaticos."""

    def __init__(self, mensaje, reintentar_en=0):
        super().__init__(mensaje)
        self.reintentar_en = reintentar_en


ESPERA_TIMBRE_SEGUNDOS = 20
INTERVALOS_TIMBRE = (1, 2, 3, 5, 5)


def normalizar_rut(rut):
    rut = str(rut or "").replace(".", "").replace(" ", "").upper()
    if not re.fullmatch(r"[0-9]{7,8}-[0-9K]", rut):
        raise DocumentoKameError("Configura KAME_RUT con el RUT de la empresa emisora para recuperar el timbre.")
    return rut


def identidad(venta, client):
    if venta.es_pase_libre or venta.estado_kame != "ok" or not venta.folio_kame:
        raise DocumentoKameError("La venta no tiene una boleta real emitida en KAME.")
    rut = normalizar_rut(venta.kame_rut_emisor or client._config("KAME_RUT", ""))
    tipo = venta.kame_tipo_documento or "39"
    folio = str(venta.folio_kame)
    if tipo not in ("39", "41") or not re.fullmatch(r"[1-9][0-9]*", folio):
        raise DocumentoKameError("La boleta no tiene un folio o tipo de documento válido.")
    return rut, tipo, folio


def ruta_cache(clave, extension):
    nombre = hashlib.sha256("|".join(clave).encode("ascii")).hexdigest()
    return CACHE_DIR / f"{nombre}.{extension}"


def guardar_cache(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + "." + uuid4().hex + ".tmp")
    try:
        temporal.write_bytes(contenido)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def leer_xml(xml, clave, venta):
    if not isinstance(xml, str) or len(xml.encode("utf-8")) > 2 * 1024 * 1024:
        raise DocumentoKameError("KAME no entrego un XML válido para esta boleta.")
    try:
        # Unicode evita reinterpretar el texto JSON segun la declaracion del XML.
        raiz = ElementTree.fromstring(xml, forbid_dtd=True)
        nombre = lambda nodo: nodo.tag.rsplit("}", 1)[-1]
        documentos = [n for n in raiz.iter() if nombre(n) == "Documento"]
        if len(documentos) != 1:
            raise ValueError("Documento ambiguo")
        documento = documentos[0]
        def hijo(nodo, etiqueta):
            return next((n for n in nodo if nombre(n) == etiqueta), None) if nodo is not None else None
        def valor(nodo, etiqueta):
            n = hijo(nodo, etiqueta)
            return (n.text or "").strip() if n is not None else ""
        encabezado = hijo(documento, "Encabezado")
        id_doc = hijo(encabezado, "IdDoc")
        emisor = hijo(encabezado, "Emisor")
        totales = hijo(encabezado, "Totales")
        ted = hijo(documento, "TED")
        dd = hijo(ted, "DD")
        rut, tipo, folio = clave
        if (normalizar_rut(valor(emisor, "RUTEmisor")) != rut or
                valor(id_doc, "TipoDTE") != tipo or valor(id_doc, "Folio") != folio or
                int(valor(totales, "MntTotal")) != venta.monto or
                normalizar_rut(valor(dd, "RE")) != rut or valor(dd, "TD") != tipo or
                valor(dd, "F") != folio or int(valor(dd, "MNT")) != venta.monto or
                valor(dd, "FE") != valor(id_doc, "FchEmis") or not valor(ted, "FRMT") or hijo(dd, "CAF") is None):
            raise ValueError("Identidad del documento no coincide")
        for campo in ("MntNeto", "IVA", "MntExe"):
            if valor(totales, campo) and not re.fullmatch(r"[0-9]+", valor(totales, campo)):
                raise ValueError("Totales invalidos")
        if valor(totales, "MntNeto") and valor(totales, "IVA") and sum(
                int(valor(totales, campo) or "0") for campo in ("MntNeto", "IVA", "MntExe")) != venta.monto:
            raise ValueError("Totales no coinciden")
        receptor = hijo(encabezado, "Receptor")
        rut_receptor = normalizar_rut(venta.rut_cliente or "66666666-6")
        if (normalizar_rut(valor(receptor, "RUTRecep")) != rut_receptor or
                normalizar_rut(valor(dd, "RR")) != rut_receptor):
            raise ValueError("Receptor no coincide")
        # Extraer los bytes del TED sin reserializar ni modificar datos o firma.
        bloques = re.findall(r"<TED\b[^>]*>.*?</TED\s*>", xml, flags=re.DOTALL)
        if len(bloques) != 1:
            raise ValueError("TED ausente o ambiguo")
        ted_original = bloques[0].encode("iso-8859-1")
        fecha = date.fromisoformat(valor(id_doc, "FchEmis"))
        caratula = next((n for n in raiz.iter() if nombre(n) == "Caratula"), None)
        return {"ted": ted_original, "rut": rut, "tipo": tipo, "folio": folio,
                "fecha": fecha, "razon_social": valor(emisor, "RznSoc") or valor(emisor, "RznSocEmisor"),
                "giro": valor(emisor, "GiroEmis") or valor(emisor, "GiroEmisor"),
                "direccion": valor(emisor, "DirOrigen"), "ciudad": valor(emisor, "CiudadOrigen") or valor(emisor, "CmnaOrigen"),
                "resolucion_numero": valor(caratula, "NroResol"), "resolucion_fecha": valor(caratula, "FchResol"),
                "neto": valor(totales, "MntNeto"), "iva": valor(totales, "IVA"), "exento": valor(totales, "MntExe")}
    except (ElementTree.ParseError, DefusedXmlException, ValueError, TypeError, OverflowError):
        raise DocumentoKameError("El XML o timbre recibido no corresponde a esta venta o no es válido. No se imprimió una boleta sin timbre.") from None


def imagen_timbre(ted):
    # pdf417gen 0.8.1 no expone force_binary. Se utilizan sus primitivas,
    # fijadas por version, sin parches globales que interfieran con otras cajas.
    from pdf417gen.compaction.byte import compact_bytes
    from pdf417gen.encoding import encode_rows, get_padding
    from pdf417gen.error_correction import compute_error_correction_code_words
    from pdf417gen.util import chunks
    from pdf417gen import render_image
    # 12 columnas a modulo 2 llenan los 72 mm utiles; el margen de 10 px (1,25 mm) supera
    # los 2 modulos de zona de silencio. Verificado con un lector independiente.
    columnas, nivel = 12, 5
    palabras = [924 if len(ted) % 6 == 0 else 901, *compact_bytes(ted)]
    relleno = get_padding(len(palabras), 2 ** (nivel + 1), columnas)
    # Minimo 20 mm de alto para el simbolo, a 8 pixeles/mm, modulo 2 y ratio 3.
    filas = max(27, math.ceil((1 + len(palabras) + len(relleno) + 64) / columnas))
    if filas > 90 or filas * columnas > 928:
        raise DocumentoKameError("El timbre excede el ancho térmico disponible. Descarga el PDF oficial de KAME.")
    relleno = [900] * (filas * columnas - 1 - len(palabras) - 64)
    datos = [1 + len(palabras) + len(relleno), *palabras, *relleno]
    datos += compute_error_correction_code_words(datos, nivel)
    codigos = list(encode_rows(list(chunks(datos, columnas)), columnas, nivel))
    return render_image(codigos, scale=2, ratio=3, padding=10).convert("RGB")


def obtener_timbre(venta, client=None):
    from app.services.kame_client import KameAPI
    client = client or KameAPI(None)
    clave = identidad(venta, client)
    ruta = ruta_cache(clave, "xml")
    if ruta.exists():
        try:
            info = leer_xml(ruta.read_bytes().decode("utf-8"), clave, venta)
            info["imagen"] = imagen_timbre(info["ted"])
            return info
        except (OSError, UnicodeError, DocumentoKameError):
            pass
    respuesta = client.obtener_documento(*clave, "XML")
    if not isinstance(respuesta, dict):
        raise DocumentoKameError("KAME no entrego el XML firmado de la boleta.")
    xml = respuesta.get("Xml")
    if not xml:
        raise DocumentoKameTemporal("KAME aun esta preparando el XML de la boleta emitida.")
    info = leer_xml(xml, clave, venta)
    info["imagen"] = imagen_timbre(info["ted"])
    guardar_cache(ruta, xml.encode("utf-8"))
    return info


def preparar_timbre(db, venta, client=None, exigir=True, esperar=False):
    from app.services.kame_client import KameAPI
    client = client or KameAPI(db)
    try:
        if esperar:
            limite = time.monotonic() + ESPERA_TIMBRE_SEGUNDOS
            anterior = getattr(client, "_documento_deadline", None)
            client._documento_deadline = limite
            try:
                for intento in range(len(INTERVALOS_TIMBRE) + 1):
                    try:
                        info = obtener_timbre(venta, client)
                        break
                    except DocumentoKameTemporal as error:
                        restante = limite - time.monotonic()
                        pausa = max(INTERVALOS_TIMBRE[min(intento, len(INTERVALOS_TIMBRE) - 1)],
                                    error.reintentar_en)
                        if intento == len(INTERVALOS_TIMBRE) or pausa >= restante:
                            raise DocumentoKameError(
                                "KAME no entrego el timbre dentro de la espera de esta atencion. "
                                "La boleta ya fue emitida: reintenta completar esta misma boleta, sin volver a cobrar. "
                                f"Último motivo: {error}") from None
                        time.sleep(pausa)
            finally:
                client._documento_deadline = anterior
        else:
            info = obtener_timbre(venta, client)
        # El numero y fecha no vienen siempre en un XML DTE individual.
        info["resolucion_numero"] = info["resolucion_numero"] or client._config("KAME_RESOLUCION_NUMERO", "")
        info["resolucion_fecha"] = info["resolucion_fecha"] or client._config("KAME_RESOLUCION_FECHA", "")
        if not re.fullmatch(r"[0-9]+", str(info["resolucion_numero"])):
            raise DocumentoKameError("Configura KAME_RESOLUCION_NUMERO para imprimir la boleta con su resolución.")
        try:
            date.fromisoformat(info["resolucion_fecha"])
        except (ValueError, TypeError):
            raise DocumentoKameError("Configura KAME_RESOLUCION_FECHA con formato AAAA-MM-DD para imprimir la boleta.") from None
        venta.kame_timbre_disponible = True
        venta.kame_error_documento = ""
        venta.kame_rut_emisor, venta.kame_tipo_documento = info["rut"], info["tipo"]
        db.commit()
        return info
    except (DocumentoKameError, OSError, ImportError) as error:
        mensaje = (str(error) if isinstance(error, DocumentoKameError) else
                   "Reinicia el servidor después de instalar las dependencias de impresión." if isinstance(error, ImportError) else
                   "No se pudo guardar el documento de la boleta. Reintenta Imprimir.")
        venta.kame_timbre_disponible = False
        venta.kame_error_documento = mensaje
        db.commit()
        print(f'[KAME] Timbre no disponible ticket={venta.ticket} folio={venta.folio_kame}: {mensaje}', flush=True)
        if exigir:
            raise DocumentoKameError(mensaje) from None
        return None


def decodificar_pdf(respuesta):
    if isinstance(respuesta, dict):
        valor = respuesta.get("ArchivoBase64PDF")
    elif isinstance(respuesta, str) and respuesta.lstrip().startswith("ArchivoBase64PDF"):
        valor = respuesta.partition(":")[2]
    else:
        valor = None
    if not isinstance(valor, str) or len(valor) > 16 * 1024 * 1024:
        raise DocumentoKameError("KAME no entrego ArchivoBase64PDF.")
    try:
        datos = base64.b64decode(re.sub(r"\s+", "", valor), validate=True)
    except (ValueError, binascii.Error):
        raise DocumentoKameError("El PDF entregado por KAME no es válido.") from None
    if not datos.startswith(b"%PDF-") or b"%%EOF" not in datos[-2048:]:
        raise DocumentoKameError("El PDF entregado por KAME esta incompleto o no es un PDF.")
    return datos


def obtener_pdf(venta, client=None):
    from app.services.kame_client import KameAPI
    client = client or KameAPI(None)
    clave = identidad(venta, client)
    ruta = ruta_cache(clave, "pdf")
    if ruta.exists():
        datos = ruta.read_bytes()
        if datos.startswith(b"%PDF-") and b"%%EOF" in datos[-2048:]:
            return ruta
    datos = decodificar_pdf(client.obtener_documento(*clave, "PDF"))
    guardar_cache(ruta, datos)
    return ruta
