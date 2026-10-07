import os
import unittest
from unittest.mock import patch, Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Configuracion, Venta
from app.services.kame_client import KameAPI, emitir_boleta
from app.routers.config import guardar_config, probar_kame
from app.schemas import ConfigIn


def response(data, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


class KameTests(unittest.TestCase):
    @patch('app.services.kame_client.requests.post')
    def test_document_id_is_kept_for_future_document_download(self, post):
        self.configure(modo='real', token='token', user='cashier@example.com')
        venta = Venta(ticket='T000001', servicio_nombre='Ducha', monto=2000, forma_pago='debito')
        self.db.add(venta)
        self.db.commit()
        post.return_value = response({'Estado': 'OK', 'Folio': 456, 'Id': 'document-123'})
        self.assertEqual(self.emit(), ('456', 'ok'))
        self.db.refresh(venta)
        self.assertEqual(venta.kame_documento_id, 'document-123')

    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.dotenv = patch('app.services.kame_client.dotenv_values', return_value={})
        self.dotenv.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.dotenv.stop)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def configure(self, **values):
        names = {'url': 'KAME_BASE_URL'}
        for key, value in values.items():
            os.environ[names.get(key, 'KAME_' + key.upper())] = value

    def emit(self):
        return emitir_boleta(self.db, 'Ducha', 2000, 'debito', ticket_num='T000001')

    @patch('app.services.kame_client.requests.post')
    def test_mock_is_explicit_and_unique(self, post):
        self.configure(modo='mock')
        first, status = self.emit()
        self.assertEqual(status, 'mock')
        self.assertNotEqual(first, self.emit()[0])
        post.assert_not_called()

    @patch('app.services.kame_client.requests.post')
    def test_default_mode_issues_through_kame(self, post):
        self.configure(client_id='client', client_secret='secret', user='cashier@example.com')
        post.side_effect = [response({'access_token': 'token', 'expires_in': 3600}),
                            response({'Estado': 'OK', 'Folio': 456})]
        self.assertEqual(self.emit(), ('456', 'ok'))
        self.assertEqual(post.call_count, 2)
        self.assertTrue(post.call_args.args[0].endswith('/api/Documento/addVenta'))

    @patch('app.services.kame_client.requests.post')
    def test_default_without_credentials_never_simulates(self, post):
        self.assertEqual(self.emit()[1], 'error')
        post.assert_not_called()

    @patch('app.services.kame_client.requests.post')
    def test_real_missing_credentials_never_simulates(self, post):
        self.configure(modo='real')
        self.assertEqual(self.emit()[1], 'error')
        post.assert_not_called()

    @patch('app.services.kame_client.requests.post')
    def test_oauth_payload_and_response(self, post):
        self.configure(modo='real', client_id='client', client_secret='secret', user='cashier@example.com')
        post.side_effect = [response({'access_token': 'token', 'expires_in': 3600}), response({'Estado': 'OK', 'Folio': 123})]
        self.assertEqual(self.emit(), ('123', 'ok'))
        self.assertTrue(post.call_args_list[0].args[0].endswith('/oauth/token'))
        call = post.call_args_list[1]
        self.assertTrue(call.args[0].endswith('/api/Documento/addVenta'))
        payload = call.kwargs['json']
        self.assertEqual(payload['Afecto'], 1681)
        self.assertEqual(payload['ValorImpto1'], 319)
        self.assertEqual(payload['Detalle'][0]['PrecioUnitario'], 2000)
        self.assertEqual(payload['Detalle'][0]['Exento'], '')
        self.assertEqual(payload['Comentario'], 'Venta SanitaPoint T000001')
        self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer token')

    @patch('app.services.kame_client.requests.post')
    def test_rejection_or_missing_folio_is_error(self, post):
        self.configure(modo='real', token='token', user='cashier@example.com')
        for data in ({'Estado': 'OK'}, {'Estado': 'OK', 'Folio': 1, 'Error': ['rechazado']}, {'Estado': 'ERROR'}, []):
            post.return_value = response(data)
            self.assertEqual(self.emit()[1], 'error')

    @patch('app.services.kame_client.requests.post')
    def test_refresh_only_on_unauthorized(self, post):
        self.configure(modo='real', client_id='client', client_secret='secret', user='cashier@example.com')
        post.side_effect = [response({'access_token': 'old'}), response({}, 401), response({'access_token': 'new'}), response({'Estado': 'OK', 'Folio': 5})]
        self.assertEqual(self.emit(), ('5', 'ok'))
        self.assertEqual(post.call_count, 4)

    @patch('app.services.kame_client.requests.post')
    def test_timeout_does_not_retry(self, post):
        import requests
        self.configure(modo='real', token='token', user='cashier@example.com')
        post.side_effect = requests.exceptions.Timeout()
        self.assertEqual(self.emit()[1], 'error')
        self.assertEqual(post.call_count, 1)

    @patch('app.services.kame_client.requests.post')
    def test_environment_precedence_and_static_token(self, post):
        self.configure(modo='mock', client_id='client', client_secret='secret')
        with patch.dict(os.environ, {'KAME_MODO': 'real', 'KAME_TOKEN': 'env-token', 'KAME_USER': 'user', 'KAME_BASE_URL': 'https://example.test'}):
            post.return_value = response({'Estado': 'OK', 'Folio': 8})
            self.assertEqual(self.emit(), ('8', 'ok'))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], 'https://example.test/api/Documento/addVenta')

    def test_web_config_cannot_store_kame_values(self):
        guardar_config(ConfigIn(valores={'kame_token': 'token', 'empresa_nombre': 'Empresa'}), self.db)
        self.assertIsNone(self.db.get(Configuracion, 'kame_token'))
        self.assertEqual(self.db.get(Configuracion, 'empresa_nombre').valor, 'Empresa')

    @patch('app.services.kame_client.requests.post')
    def test_connection_test_validates_oauth_without_issuing_sale(self, post):
        self.configure(client_id='client', client_secret='secret')
        post.return_value = response({'access_token': 'token', 'expires_in': 3600})
        self.assertTrue(probar_kame(self.db)['ok'])
        self.assertEqual(post.call_count, 1)
        self.assertTrue(post.call_args.args[0].endswith('/oauth/token'))

    @patch('app.services.kame_client.requests.post')
    def test_connection_test_does_not_claim_static_token_is_valid(self, post):
        self.configure(token='unverifiable-token')
        result = KameAPI(self.db).ping()
        self.assertFalse(result['ok'])
        self.assertIn('no existe una operación segura', result['mensaje'])
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
