import unittest
from datetime import date, datetime
from unittest.mock import patch

from PIL import Image

from app.services import receipt_layout


class BoletaSimpleTests(unittest.TestCase):
    def documento(self, **extra):
        datos = {"rut": "79802720-4", "razon_social": "Empresa de Prueba SA", "giro": "SERVICIOS",
                 "direccion": "Calle 1", "ciudad": "Puerto Montt", "fecha": date(2026, 10, 16),
                 "iva": "80", "neto": "420", "exento": "0", "resolucion_numero": "80",
                 "resolucion_fecha": "2014-08-22", "imagen": Image.new("1", (400, 200), 1)}
        datos.update(extra)
        return datos

    def render(self, **kwargs):
        argumentos = dict(db=None, ticket_num="T000001", servicio_nombre="Uso de Baño", monto=500,
                          forma_pago="efectivo", folio_kame="5007279", estado_kame="ok", rut_cliente=None,
                          es_pase_libre=False, creado_en=datetime(2026, 10, 16, 14, 1, 48),
                          documento_tributario=self.documento())
        argumentos.update(kwargs)
        with patch.object(receipt_layout, "get_config", lambda db, clave, defecto="": defecto):
            return receipt_layout.render_receipt(**argumentos)

    def test_boleta_con_timbre_usa_el_formato_simple(self):
        usado = []
        original = receipt_layout._render_boleta_simple
        with patch.object(receipt_layout, "_render_boleta_simple",
                          lambda *a, **k: usado.append(1) or original(*a, **k)):
            imagen = self.render()
        self.assertEqual(usado, [1])
        self.assertEqual(imagen.width, 576)
        self.assertGreater(imagen.height, 400)

    def test_sin_timbre_o_pase_libre_no_usa_el_formato_simple(self):
        with patch.object(receipt_layout, "_render_boleta_simple", side_effect=AssertionError):
            self.render(documento_tributario=None)
            self.render(es_pase_libre=True)
            self.render(estado_kame="mock")

    def test_timbre_mas_ancho_que_el_papel_se_rechaza(self):
        with self.assertRaises(ValueError):
            self.render(documento_tributario=self.documento(imagen=Image.new("1", (700, 100), 1)))


if __name__ == "__main__":
    unittest.main()
