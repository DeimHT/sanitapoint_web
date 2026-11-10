"""Pruebas sin red ni emision real. Los XML y firmas son datos sinteticos."""
import base64
from contextlib import closing
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database import Base
from app.main import _asegurar_columnas
from app.models import Caja, Cuenta, Servicio, Venta
from app.routers.ventas import descargar_ticket_pdf, imprimir_boleta, registrar_venta, vista_impresion
from app.schemas import VentaIn
from app.services import documentos_kame as documentos
from app.services.kame_client import KameAPI, emitir_boleta
from scripts.diagnosticar_kame import cargar_ventas, diagnosticar_venta


TED = ('<TED version="1.0"><DD><RE>76123456-0</RE><TD>39</TD><F>456</F>'
       '<FE>2026-10-15</FE><RR>66666666-6</RR><RSR>Consumidor Final</RSR><MNT>2000</MNT>'
       '<IT1>Ducha &amp; Ba\u00f1o</IT1><CAF version="1.0"><DA>DATOS SINTETICOS</DA>'
       '<FRMA algoritmo="SHA1withRSA">FIRMA-DE-PRUEBA-NO-VALIDA</FRMA></CAF>'
       '<TSTED>2026-10-15T10:20:00</TSTED></DD><FRMT algoritmo="SHA1withRSA">'
       'FIRMA-DE-PRUEBA-NO-VALIDA</FRMT></TED>')
XML = ('<?xml version="1.0" encoding="iso-8859-1"?>'
       '<EnvioBOLETA xmlns="http://www.sii.cl/SiiDte"><SetDTE><Caratula>'
       '<NroResol>80</NroResol><FchResol>2021-02-16</FchResol></Caratula>'
       '<DTE version="1.0"><Documento ID="PRUEBA"><Encabezado><IdDoc><TipoDTE>39</TipoDTE>'
       '<Folio>456</Folio><FchEmis>2026-10-15</FchEmis></IdDoc><Emisor>'
       '<RUTEmisor>76123456-0</RUTEmisor><RznSocEmisor>Empresa de prueba</RznSocEmisor>'
       '<GiroEmisor>Servicios sanitarios</GiroEmisor><DirOrigen>Direccion de prueba</DirOrigen>'
       '<CmnaOrigen>Santiago</CmnaOrigen></Emisor><Receptor><RUTRecep>66666666-6</RUTRecep>'
       '</Receptor><Totales><MntNeto>1681</MntNeto><IVA>319</IVA><MntTotal>2000</MntTotal>'
       '</Totales></Encabezado>' + TED + '</Documento></DTE></SetDTE></EnvioBOLETA>')
PDF = b'%PDF-1.4\n%Documento sintetico para probar transporte\n%%EOF\n'


def respuesta(data, status=200, headers=None):
    r = Mock(status_code=status, headers=headers or {})
    r.json.return_value = data
    r.content = json.dumps(data).encode()
    r.text = json.dumps(data)
    return r


class DocumentosKameTests(unittest.TestCase):
    def setUp(self):
        dormir = patch("app.services.documentos_kame.time.sleep")
        dormir.start()
        self.addCleanup(dormir.stop)
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        cache = patch.object(documentos, "CACHE_DIR", Path(temporal.name))
        cache.start()
        self.addCleanup(cache.stop)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.cuenta = Cuenta(username="ana", nombre="Ana", password_hash="prueba", rol="cajero")
        self.otro = Cuenta(username="otro", nombre="Otro", password_hash="prueba", rol="cajero")
        self.db.add_all([self.cuenta, self.otro])
        self.db.flush()
        self.caja = Caja(operador="Ana", cuenta_id=self.cuenta.id, servicio="Ba\u00f1o 1", estado="abierta")
        self.db.add(self.caja)
        self.db.flush()
        self.venta = Venta(ticket="T000001", servicio_nombre="Ducha", monto=2000, forma_pago="efectivo",
                           caja_id=self.caja.id, estado_kame="ok", folio_kame="456",
                           kame_rut_emisor="76123456-0", kame_tipo_documento="39")
        self.db.add(self.venta)
        self.db.commit()
        env = patch.dict(os.environ, {"KAME_MODO": "real", "KAME_RUT": "76.123.456-0", "KAME_TOKEN": "TOKEN-SINTETICO",
                                      "KAME_RESOLUCION_NUMERO": "80", "KAME_RESOLUCION_FECHA": "2021-02-16", "KAME_USER": "prueba@example.test", "KAME_BASE_URL": "https://kame.example.test"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        dotenv = patch("app.services.kame_client.dotenv_values", return_value={})
        dotenv.start()
        self.addCleanup(dotenv.stop)
        get = patch("app.services.kame_client.requests.get", return_value=respuesta({"Estado": "Ok", "Xml": XML, "Error": ""}))
        self.get = get.start()
        self.addCleanup(get.stop)
        post = patch("app.services.kame_client.requests.post", return_value=respuesta({"Estado": "Ok", "Folio": 456, "Id": 123}))
        self.post = post.start()
        self.addCleanup(post.stop)

    def test_consulta_documentada_autenticada_y_ted_original_sin_reserializar(self):
        info = documentos.preparar_timbre(self.db, self.venta)
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.args[0], 'https://kame.example.test/api/Documento/getDocumentoXML/76123456-0/39/456')
        self.assertEqual(self.get.call_args.kwargs["headers"]["Authorization"], "Bearer TOKEN-SINTETICO")
        self.assertFalse(self.get.call_args.kwargs["allow_redirects"])
        self.assertEqual(info["ted"], TED.encode("iso-8859-1"))
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertLessEqual(info["imagen"].width, 576)
        self.assertEqual(info["imagen"].getpixel((0, 0)), (255, 255, 255))
        documentos.preparar_timbre(self.db, self.venta)
        self.assertEqual(self.get.call_count, 1, "La reimpresion usa el XML validado en cache")
        self.post.assert_not_called()

    def test_cache_conserva_saltos_crlf_y_bytes_del_ted_firmado(self):
        ted = TED.replace("><", ">\r\n<")
        xml = XML.replace(TED, ted)
        self.get.return_value = respuesta({"Estado": "Ok", "Xml": xml})
        primero = documentos.preparar_timbre(self.db, self.venta)
        segundo = documentos.preparar_timbre(self.db, self.venta)
        self.assertEqual(primero["ted"], ted.encode("iso-8859-1"))
        self.assertEqual(segundo["ted"], primero["ted"])
        self.assertEqual(self.get.call_count, 1)

    def test_emision_recupera_timbre_automaticamente_con_el_mismo_cliente(self):
        self.assertEqual(emitir_boleta(self.db, "Ducha", 2000, "efectivo", ticket_num=self.venta.ticket), ("456", "ok"))
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.venta.kame_documento_id, "123")
        self.assertEqual(self.venta.kame_rut_emisor, "76123456-0")
        self.assertTrue(self.venta.kame_timbre_disponible)

    def test_documento_pendiente_no_cambia_emision_ni_repite_addventa(self):
        self.get.return_value = respuesta({}, status=404)
        self.assertEqual(emitir_boleta(self.db, "Ducha", 2000, "efectivo", ticket_num=self.venta.ticket), ("456", "ok"))
        self.assertEqual(self.venta.estado_kame, "ok")
        self.assertFalse(self.venta.kame_timbre_disponible)
        self.assertIn("reintenta", self.venta.kame_error_documento.lower())
        self.assertEqual(self.get.call_count, len(documentos.INTERVALOS_TIMBRE) + 1)
        self.assertLessEqual(sum(self.get.call_args.kwargs['timeout']), 35)
        self.get.return_value = respuesta({"Estado": "Ok", "Xml": XML})
        imprimir_boleta(self.venta.ticket, self.db, self.cuenta)
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertEqual(self.venta.kame_error_documento, "")
        self.assertEqual(self.post.call_count, 1)

    def test_pdf_oficial_base64_se_conserva_exactamente_y_se_cachea(self):
        self.get.return_value = respuesta({"ArchivoBase64PDF": base64.b64encode(PDF).decode()})
        salida = descargar_ticket_pdf(self.venta.ticket, self.db, self.cuenta)
        self.assertEqual(Path(salida.path).read_bytes(), PDF)
        self.assertIn("boleta-456.pdf", salida.headers["content-disposition"])
        self.assertTrue(self.get.call_args.args[0].endswith('/getDocumentoPDF/76123456-0/39/456'))
        documentos.obtener_pdf(self.venta)
        self.assertEqual(self.get.call_count, 1)
        self.post.assert_not_called()
        valor = "ArchivoBase64PDF : " + base64.b64encode(PDF).decode()
        self.assertEqual(documentos.decodificar_pdf(valor), PDF)

    def test_pdf_invalido_nunca_se_usa_como_boleta(self):
        for payload in ({"ArchivoBase64PDF": "no-es-base64"}, {"ArchivoBase64PDF": base64.b64encode(b'<html>Error</html>').decode()},
                        {"ArchivoBase64PDF": base64.b64encode(b'%PDF-1.4 incompleto').decode()}, {}):
            with self.assertRaises(documentos.DocumentoKameError):
                documentos.decodificar_pdf(payload)

    def test_datos_ajenos_xml_malicioso_y_ted_incompleto_se_rechazan(self):
        modificaciones = [XML.replace('<F>456</F>', '<F>999</F>'), XML.replace('76123456-0', '77123456-0'),
                          XML.replace('<MNT>2000</MNT>', '<MNT>500</MNT>'), XML.replace('66666666-6', '11111111-1'),
                          XML.replace(TED, ''), XML.replace('</Documento>', TED + '</Documento>'),
                          '<!DOCTYPE DTE [<!ENTITY x SYSTEM "file:///secreto">]>' + XML,
                          XML.replace('FIRMA-DE-PRUEBA-NO-VALIDA</FRMT>', '</FRMT>')]
        for xml in modificaciones:
            with self.subTest(xml=xml[:60]), self.assertRaises(documentos.DocumentoKameError):
                documentos.leer_xml(xml, ('76123456-0', '39', '456'), self.venta)
        self.post.assert_not_called()

    def test_no_hay_impresion_tributaria_sin_timbre_y_no_hay_fallback_silencioso(self):
        self.get.return_value = respuesta({}, status=404)
        for operacion in (imprimir_boleta, vista_impresion, descargar_ticket_pdf):
            with self.assertRaises(HTTPException) as error:
                operacion(self.venta.ticket, self.db, self.cuenta)
            self.assertEqual(error.exception.status_code, 503)
        self.post.assert_not_called()

    def test_cajero_ajeno_no_dispara_consulta_de_documentos(self):
        for operacion in (imprimir_boleta, vista_impresion, descargar_ticket_pdf):
            with self.assertRaises(HTTPException) as error:
                operacion(self.venta.ticket, self.db, self.otro)
            self.assertEqual(error.exception.status_code, 404)
        self.get.assert_not_called()

    def test_vista_termica_contiene_imagen_con_timbre_y_reutiliza_cache(self):
        imprimir_boleta(self.venta.ticket, self.db, self.cuenta)
        salida = vista_impresion(self.venta.ticket, self.db, self.cuenta)
        self.assertIn(b'data:image/png;base64,', salida.body)
        self.assertIn(b'window.print()', salida.body)
        self.assertEqual(self.get.call_count, 1)

    def test_token_401_se_refresca_una_vez_sin_reemitir(self):
        os.environ.pop("KAME_TOKEN")
        os.environ.update(KAME_CLIENT_ID="cliente", KAME_CLIENT_SECRET="secreto")
        self.post.side_effect = [respuesta({"access_token": "viejo"}), respuesta({"access_token": "nuevo"})]
        self.get.side_effect = [respuesta({}, 401), respuesta({"Estado": "Ok", "Xml": XML})]
        documentos.preparar_timbre(self.db, self.venta)
        self.assertEqual(self.get.call_count, 2)
        self.assertTrue(all(call.args[0].endswith('/oauth/token') for call in self.post.call_args_list))

    def test_rut_emisor_se_conserva_al_cambiar_configuracion(self):
        os.environ["KAME_RUT"] = "77123456-0"
        documentos.preparar_timbre(self.db, self.venta)
        self.assertIn('/76123456-0/39/456', self.get.call_args.args[0])

    def test_falta_resolucion_no_inventa_datos_y_admite_configuracion_explicita(self):
        os.environ.pop("KAME_RESOLUCION_NUMERO", None)
        os.environ.pop("KAME_RESOLUCION_FECHA", None)
        xml = XML.replace('<NroResol>80</NroResol><FchResol>2021-02-16</FchResol>', '')
        self.get.return_value = respuesta({"Estado": "Ok", "Xml": xml})
        with self.assertRaisesRegex(documentos.DocumentoKameError, "RESOLUCION"):
            documentos.preparar_timbre(self.db, self.venta)
        os.environ.update(KAME_RESOLUCION_NUMERO="80", KAME_RESOLUCION_FECHA="2021-02-16")
        self.assertEqual(documentos.preparar_timbre(self.db, self.venta)["resolucion_numero"], "80")
        self.assertEqual(self.get.call_count, 1)

    def test_venta_real_prepara_el_timbre_sin_cambiar_el_cobro(self):
        self.venta.kame_timbre_disponible = True
        self.db.commit()
        servicio = Servicio(nombre="Ducha", precio=2000, activo=True)
        self.db.add(servicio)
        self.db.commit()
        resultado = registrar_venta(VentaIn(servicio_id=servicio.id, forma_pago="efectivo"), self.db, self.cuenta)
        self.assertEqual(resultado.estado_kame, "ok")
        self.assertTrue(resultado.kame_timbre_disponible)
        self.assertEqual(resultado.monto, 2000)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.get.call_count, 1)

    def test_xml_transitorio_se_recupera_al_emitir_sin_reemitir(self):
        self.get.side_effect = [respuesta({}, 404), respuesta({"Estado": "Ok", "Xml": ""}),
                                respuesta({"Estado": "Ok", "Xml": XML})]
        folio, estado = emitir_boleta(self.db, "Ducha", 2000, "efectivo", ticket_num=self.venta.ticket)
        self.assertEqual((folio, estado), ("456", "ok"))
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertEqual(self.get.call_count, 3)
        imprimir_boleta(self.venta.ticket, self.db, self.cuenta)
        self.assertEqual(self.get.call_count, 3, "La impresion reutiliza el timbre recuperado")
        self.assertEqual(self.post.call_count, 1)

    def test_timbre_pendiente_no_bloquea_nuevo_cobro(self):
        servicio = Servicio(nombre="Ducha", precio=2000, activo=True)
        self.db.add(servicio)
        self.db.commit()
        with patch('app.routers.ventas.emitir_boleta', return_value=('457', 'ok')) as emitir:
            resultado = registrar_venta(VentaIn(servicio_id=servicio.id, forma_pago="efectivo"), self.db, self.cuenta)
        self.assertEqual(resultado.folio_kame, '457')
        self.assertEqual(self.db.query(Venta).count(), 2)
        emitir.assert_called_once()
        self.assertEqual(self.venta.folio_kame, '456')
        self.assertFalse(self.venta.kame_timbre_disponible)

    def test_emision_pendiente_bloquea_nuevo_cobro(self):
        self.venta.estado_kame = 'pendiente'
        self.venta.folio_kame = None
        self.db.commit()
        servicio = Servicio(nombre="Ducha", precio=2000, activo=True)
        self.db.add(servicio)
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            registrar_venta(VentaIn(servicio_id=servicio.id, forma_pago="efectivo"), self.db, self.cuenta)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Venta).count(), 1)
        self.post.assert_not_called()

    def test_error_permanente_no_hace_polling(self):
        self.get.return_value = respuesta({}, 403)
        with self.assertRaises(documentos.DocumentoKameError):
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertEqual(self.get.call_count, 1)
        self.post.assert_not_called()

    def test_error_json_200_conserva_motivo_al_agotar_espera_sin_reemitir(self):
        motivo = "Documento : No existe el documento electronico registrado en el ERP"
        self.get.return_value = respuesta({"Estado": "Error", "Error": [
            {"MemberNames": ["Documento"], "ErrorMessage": motivo}]})
        with patch('builtins.print') as salida:
            self.assertEqual(emitir_boleta(self.db, "Ducha", 2000, "efectivo",
                                          ticket_num=self.venta.ticket), ("456", "ok"))
        self.assertIn(motivo, self.venta.kame_error_documento)
        self.assertIn("HTTP 200", self.venta.kame_error_documento)
        self.assertIn("sin volver a cobrar", self.venta.kame_error_documento)
        self.assertEqual(self.get.call_count, len(documentos.INTERVALOS_TIMBRE) + 1)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.venta.estado_kame, 'ok')
        self.assertFalse(self.venta.kame_timbre_disponible)
        self.assertTrue(any(motivo in str(call) for call in salida.call_args_list))

    def test_documento_ausente_en_json_puede_aparecer_sin_nueva_emision(self):
        self.get.side_effect = [respuesta({"Estado": "Error", "Error": [
            {"ErrorMessage": "Documento : No existe el documento electronico registrado en el ERP"}]}),
            respuesta({"Estado": "Ok", "Xml": XML})]
        documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertEqual(self.get.call_count, 2)
        self.post.assert_not_called()

    def test_xml_publicado_despues_de_90_segundos_se_recupera_sin_reemitir(self):
        reloj = [0.0]
        def dormir(segundos):
            reloj[0] += segundos
        def consultar(*args, **kwargs):
            if reloj[0] < 90:
                return respuesta({'Estado': 'Error', 'Error': [
                    {'ErrorMessage': 'No existe el documento electronico registrado en el ERP'}]})
            return respuesta({'Estado': 'Ok', 'Xml': XML})
        self.get.side_effect = consultar
        with patch('app.services.documentos_kame.time.monotonic', side_effect=lambda: reloj[0]), \
             patch('app.services.documentos_kame.time.sleep', side_effect=dormir):
            self.assertEqual(emitir_boleta(self.db, 'Ducha', 2000, 'efectivo',
                                          ticket_num=self.venta.ticket), ('456', 'ok'))
        self.assertGreaterEqual(reloj[0], 90)
        self.assertLessEqual(reloj[0], 120)
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertEqual(self.venta.kame_error_documento, '')
        self.post.assert_called_once()
        consultas = self.get.call_count
        imprimir_boleta(self.venta.ticket, self.db, self.cuenta)
        self.assertEqual(self.get.call_count, consultas, 'La impresion usa el XML recuperado en cache')

    def test_consultas_lentas_agotan_presupuesto_sin_superar_120_segundos(self):
        reloj = [0.0]
        inicios = []
        def dormir(segundos):
            reloj[0] += segundos
        def consultar(*args, **kwargs):
            inicios.append(reloj[0])
            reloj[0] += min(25, sum(kwargs['timeout']))
            return respuesta({}, 404)
        self.get.side_effect = consultar
        with patch('app.services.documentos_kame.time.monotonic', side_effect=lambda: reloj[0]), \
             patch('app.services.documentos_kame.time.sleep', side_effect=dormir):
            with self.assertRaisesRegex(documentos.DocumentoKameError, 'HTTP 404'):
                documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertGreater(reloj[0], 90)
        self.assertLessEqual(reloj[0], 120)
        self.assertTrue(all(inicio < 120 for inicio in inicios))
        self.assertEqual(self.venta.estado_kame, 'ok')
        self.assertEqual(self.venta.folio_kame, '456')
        self.post.assert_not_called()

    def test_consulta_xml_tolera_respuesta_de_25_segundos(self):
        reloj = [0.0]
        def dormir(segundos):
            reloj[0] += segundos
        def consultar(*args, **kwargs):
            espera_lectura = kwargs['timeout'][1]
            reloj[0] += min(25, espera_lectura)
            if espera_lectura < 25:
                raise requests.exceptions.ReadTimeout()
            return respuesta({'Estado': 'Ok', 'Xml': XML})
        self.get.side_effect = consultar
        with patch('app.services.documentos_kame.time.monotonic', side_effect=lambda: reloj[0]), \
             patch('app.services.documentos_kame.time.sleep', side_effect=dormir):
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertEqual(reloj[0], 25)
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.get.assert_called_once()
        self.post.assert_not_called()

    def test_rechazo_json_de_permisos_no_se_confunde_con_preparacion(self):
        self.get.return_value = respuesta({"Estado": "Error", "Error": [
            {"ErrorMessage": "Usuario no autorizado para consultar documentos"}]})
        with self.assertRaisesRegex(documentos.DocumentoKameError, "Usuario no autorizado"):
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertEqual(self.get.call_count, 1)
        self.post.assert_not_called()

    def test_http_403_identifica_acceso_o_limite_sin_reintentos(self):
        self.get.return_value = respuesta({}, 403)
        with self.assertRaisesRegex(documentos.DocumentoKameError, "HTTP 403"):
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertIn("180", self.venta.kame_error_documento)
        self.assertEqual(self.get.call_count, 1)

    def test_error_documento_oculta_credenciales_en_pantalla_y_registro(self):
        self.get.return_value = respuesta({"Estado": "Error", "Error": [
            {"ErrorMessage": "Acceso rechazado Bearer TOKEN-SINTETICO para prueba@example.test"}]})
        with patch('builtins.print') as salida, self.assertRaises(documentos.DocumentoKameError):
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertNotIn("TOKEN-SINTETICO", self.venta.kame_error_documento)
        self.assertNotIn("prueba@example.test", self.venta.kame_error_documento)
        self.assertNotIn("TOKEN-SINTETICO", str(salida.call_args_list))

    def test_retry_after_no_consulta_antes_del_plazo_solicitado(self):
        self.get.side_effect = [respuesta({}, 429, {"Retry-After": "4"}),
                                respuesta({"Estado": "Ok", "Xml": XML})]
        with patch('app.services.documentos_kame.time.sleep') as dormir:
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        dormir.assert_called_once_with(4)
        self.assertEqual(self.get.call_count, 2)
        self.post.assert_not_called()

    def test_retry_after_largo_no_reintenta_dentro_de_atencion(self):
        self.get.return_value = respuesta({}, 503, {"Retry-After": "180"})
        with patch('app.services.documentos_kame.time.sleep') as dormir:
            with self.assertRaisesRegex(documentos.DocumentoKameError, "HTTP 503"):
                documentos.preparar_timbre(self.db, self.venta, esperar=True)
        self.assertEqual(self.get.call_count, 1)
        dormir.assert_not_called()
        self.post.assert_not_called()

    def test_retry_after_de_60_segundos_admite_recuperar_el_mismo_folio(self):
        self.get.side_effect = [respuesta({}, 503, {'Retry-After': '60'}),
                                respuesta({'Estado': 'Ok', 'Xml': XML})]
        with patch('app.services.documentos_kame.time.sleep') as dormir:
            documentos.preparar_timbre(self.db, self.venta, esperar=True)
        dormir.assert_called_once_with(60)
        self.assertTrue(self.venta.kame_timbre_disponible)
        self.assertEqual(self.get.call_count, 2)
        self.post.assert_not_called()

    def test_retry_after_fecha_http_e_invalido(self):
        from email.utils import formatdate
        for valor, pausa in ((formatdate(1005, usegmt=True), 5), ('incorrecto', 1)):
            with self.subTest(valor=valor):
                self.get.side_effect = [respuesta({}, 429, {'Retry-After': valor}),
                                        respuesta({'Estado': 'Ok', 'Xml': XML})]
                ruta = documentos.ruta_cache(('76123456-0', '39', '456'), 'xml')
                ruta.unlink(missing_ok=True)
                with patch('app.services.kame_client.time.time', return_value=1000), \
                     patch('app.services.documentos_kame.time.sleep') as dormir:
                    documentos.preparar_timbre(self.db, self.venta, esperar=True)
                dormir.assert_called_once_with(pausa)

    def test_diagnostico_consulta_xml_pdf_y_registro_sin_escribir_ni_emitir(self):
        self.get.side_effect = [respuesta({'Estado': 'Ok', 'Xml': XML}),
                                respuesta({'ArchivoBase64PDF': base64.b64encode(PDF).decode()}),
                                respuesta({'IdVenta': 123, 'Folio': 456, 'Total': 2000})]
        informe = diagnosticar_venta(KameAPI(None), self.venta)
        self.assertEqual(informe['xml_remoto'], {'disponible': True})
        self.assertEqual(informe['pdf_remoto'], {'disponible': True})
        self.assertEqual(informe['registro_erp'], {'disponible': True, 'folio_y_monto_coinciden': True})
        self.assertEqual(self.get.call_count, 3)
        self.assertIn('/getVenta/Boleta%20Electr%C3%B3nica/456', self.get.call_args.args[0])
        self.assertFalse(documentos.ruta_cache(('76123456-0', '39', '456'), 'xml').exists())
        self.assertFalse(self.venta.kame_timbre_disponible)
        self.assertEqual(self.venta.kame_error_documento, '')
        self.post.assert_not_called()

    def test_diagnostico_distingue_registro_erp_de_documento_electronico(self):
        error = {'Estado': 'Error', 'Error': [{'ErrorMessage': 'No existe el documento electronico registrado en el ERP'}]}
        self.get.side_effect = [respuesta(error), respuesta(error),
                                respuesta({'IdVenta': 123, 'Folio': 456, 'Total': 2000})]
        informe = diagnosticar_venta(KameAPI(None), self.venta)
        self.assertFalse(informe['xml_remoto']['disponible'])
        self.assertFalse(informe['pdf_remoto']['disponible'])
        self.assertIn('No existe el documento', informe['xml_remoto']['motivo'])
        self.assertTrue(informe['registro_erp']['disponible'])
        self.post.assert_not_called()

    def test_lectura_diagnostico_no_crea_base_y_conserva_datos(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / 'solo-lectura.db'
            with self.assertRaises(sqlite3.OperationalError):
                cargar_ventas(ruta)
            self.assertFalse(ruta.exists())
            with closing(sqlite3.connect(ruta)) as db:
                db.execute('CREATE TABLE ventas (id INTEGER PRIMARY KEY, ticket TEXT, estado_kame TEXT, es_pase_libre INTEGER)')
                db.executemany('INSERT INTO ventas VALUES (?, ?, ?, ?)', [
                    (1, 'T1', 'ok', 0), (2, 'T2', 'mock', 0), (3, 'T3', 'ok', 0)])
                db.commit()
            original = ruta.read_bytes()
            self.assertEqual([v.ticket for v in cargar_ventas(ruta, ultimas=1)], ['T3'])
            self.assertEqual([v.ticket for v in cargar_ventas(ruta, ticket='T1')], ['T1'])
            self.assertEqual(ruta.read_bytes(), original)

    def test_pendiente_de_otra_caja_no_bloquea(self):
        from app.routers.ventas import boleta_incompleta, consultar_boleta_en_curso
        self.venta.estado_kame = 'pendiente'
        otra_caja = Caja(operador="Otro", cuenta_id=self.otro.id, servicio="Ba\u00f1o 2", estado="abierta")
        self.db.add(otra_caja)
        self.db.commit()
        self.assertIsNone(boleta_incompleta(self.db, otra_caja.id))
        self.assertEqual(consultar_boleta_en_curso(self.db, self.cuenta).ticket, self.venta.ticket)
        self.assertIsNone(consultar_boleta_en_curso(self.db, self.otro))

    def test_configuracion_incompleta_no_registra_cobro(self):
        servicio = Servicio(nombre="Ducha", precio=2000, activo=True)
        self.db.add(servicio)
        self.db.commit()
        with patch.dict(os.environ, {"KAME_RESOLUCION_NUMERO": ""}):
            with self.assertRaises(HTTPException) as error:
                registrar_venta(VentaIn(servicio_id=servicio.id, forma_pago="efectivo"), self.db, self.cuenta)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.db.query(Venta).count(), 1)
        self.post.assert_not_called()

    def test_migracion_agrega_campos_sin_modificar_ventas_anteriores(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE ventas (id INTEGER PRIMARY KEY, monto INTEGER)"))
            conn.execute(text("INSERT INTO ventas VALUES (1, 2000)"))
        with patch("app.main.engine", engine), patch("app.main.settings") as settings:
            settings.database_url = "sqlite://"
            _asegurar_columnas()
            _asegurar_columnas()
        with engine.connect() as conn:
            fila = conn.execute(text('SELECT monto, kame_timbre_disponible, kame_error_documento FROM ventas')).one()
        self.assertEqual(tuple(fila), (2000, 0, ""))
