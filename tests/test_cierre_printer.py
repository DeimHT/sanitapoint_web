import base64
from datetime import datetime
import io
import re
import unittest

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Caja, Cuenta, Configuracion, MovimientoCaja, Venta
from app.routers.caja import imprimir_cierre
from app.services.cierre_printer import render_cierre
from app.services.cuadre import resumen_caja


class CierrePrinterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.cajero = Cuenta(username='ana', nombre='Ana Pérez', password_hash='test', rol='cajero')
        self.otro = Cuenta(username='otro', password_hash='test', rol='cajero')
        self.contabilidad = Cuenta(username='contabilidad', password_hash='test', rol='contabilidad')
        self.db.add_all([self.cajero, self.otro, self.contabilidad])
        self.db.flush()
        self.caja = Caja(cuenta_id=self.cajero.id, operador='Ana Pérez', servicio='Baño 1',
                         estado='cerrada', saldo_inicial=10000, saldo_final=10500,
                         fecha_apertura=datetime(2026, 11, 6, 8), fecha_cierre=datetime(2026, 11, 6, 16),
                         torniquete_bano_inicial=100, torniquete_bano_final=102,
                         torniquete_ducha_inicial=50, torniquete_ducha_final=51)
        self.db.add(self.caja)
        self.db.flush()
        self.db.add_all([
            Configuracion(clave='empresa_nombre', valor='Empresa de prueba'),
            Venta(caja_id=self.caja.id, ticket='T1', servicio_nombre='Baño', monto=500, forma_pago='efectivo'),
            Venta(caja_id=self.caja.id, ticket='T2', servicio_nombre='Ducha', monto=2000, forma_pago='tarjetas'),
            Venta(caja_id=self.caja.id, ticket='T3', servicio_nombre='Baño', monto=0, forma_pago='efectivo', es_pase_libre=True),
            MovimientoCaja(caja_id=self.caja.id, tipo='retiro', monto=100, descripcion='Retiro'),
        ])
        self.db.commit()

    def test_cierre_propio_tiene_formato_termico_e_imagen(self):
        cierre = resumen_caja(self.db, self.caja)
        self.assertEqual((cierre.total_ventas, cierre.saldo_esperado, cierre.diferencia_dinero), (2500, 10400, 100))
        respuesta = imprimir_cierre(self.caja.id, self.db, self.cajero)
        html = respuesta.body.decode()
        self.assertIn('@page{size:80mm ', html)
        self.assertIn('width:72mm', html)
        self.assertIn('window.print()', html)
        self.assertEqual(respuesta.headers['cache-control'], 'no-store')
        datos = base64.b64decode(re.search(r'base64,([^" ]+)', html)[1])
        with Image.open(io.BytesIO(datos)) as imagen:
            self.assertEqual(imagen.width, 576)
            self.assertGreater(imagen.height, 1000)

    def test_contabilidad_puede_reimprimir_y_otro_cajero_no(self):
        self.assertEqual(imprimir_cierre(self.caja.id, self.db, self.contabilidad).status_code, 200)
        with self.assertRaises(HTTPException) as error:
            imprimir_cierre(self.caja.id, self.db, self.otro)
        self.assertEqual(error.exception.status_code, 404)

    def test_caja_abierta_y_cierre_inexistente(self):
        self.caja.estado = 'abierta'
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            imprimir_cierre(self.caja.id, self.db, self.cajero)
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException) as error:
            imprimir_cierre(999, self.db, self.contabilidad)
        self.assertEqual(error.exception.status_code, 404)

    def test_texto_largo_y_lecturas_antiguas_no_recortan_comprobante(self):
        normal = render_cierre(self.db, resumen_caja(self.db, self.caja))
        self.caja.operador = 'Nombre muy largo ' * 20
        self.caja.torniquete_ducha_inicial = None
        self.caja.torniquete_ducha_final = None
        largo = render_cierre(self.db, resumen_caja(self.db, self.caja))
        self.assertEqual(largo.width, 576)
        self.assertGreater(largo.height, normal.height)


if __name__ == '__main__':
    unittest.main()
