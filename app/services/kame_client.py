"""
Módulo de integración con la API de KAME (kame.cl)
Emite boletas electrónicas tipo 39 (boleta de venta) ante el SII.
"""
import os
import time
from decimal import Decimal, ROUND_HALF_UP
import requests
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from dotenv import dotenv_values
from app.services.config_store import get_config


class KameAPI:
    def __init__(self, db):
        self.db = db
        self.env = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
        # Una instancia por operación evita compartir credenciales entre solicitudes.
        self.base_url  = ''
        self.token     = ''
        self.client_id = ''
        self.client_secret = ''
        self.usuario   = ''
        self.rut       = ''
        self.razon     = ''
        self.timeout   = 15
        self._token_expires_at = 0

    def _config(self, key, default=None):
        """Lee KAME exclusivamente desde el entorno o el archivo .env."""
        names = ('KAME_BASE_URL', 'KAME_URL') if key == 'KAME_BASE_URL' else (key,)
        for source in (os.environ, self.env):
            for name in names:
                if source.get(name) is not None:
                    return source[name]
        return default

    def _headers(self):
        return {
            'Content-Type':  'application/json',
            'Authorization': f'Bearer {self.token}',
            'Accept':        'application/json',
        }

    @staticmethod
    def _extraer_errores(error) -> list:
        """Convierte los distintos formatos de error de KAME en textos."""
        if not error:
            return []
        if isinstance(error, list):
            textos = []
            for item in error:
                if isinstance(item, dict):
                    textos.append(str(item.get('ErrorMessage') or item.get('mensaje') or item))
                else:
                    textos.append(str(item))
            return textos
        if isinstance(error, dict):
            return [str(error.get('ErrorMessage') or error.get('mensaje') or error)]
        return [str(error)]

    @classmethod
    def _mensaje_usuario(cls, error, status_code=None) -> str:
        """Traduce la respuesta técnica de KAME a un mensaje para caja."""
        detalle = ' '.join(cls._extraer_errores(error))
        detalle_lower = detalle.lower()

        if status_code == 401:
            return 'No fue posible autenticar la aplicación con KAME.'
        if status_code == 403:
            return 'KAME rechazó el acceso. Revisa los permisos o espera unos minutos.'
        if 'direccion' in detalle_lower or 'dirección' in detalle_lower:
            return ('KAME rechazó la dirección. '
                    'Revisa Dirección en Configuración > Datos de la empresa.')
        if 'exento' in detalle_lower:
            return ('KAME rechazó la configuración tributaria del servicio. '
                    'Revisa KAME_DETALLE_EXENTO o contacta a soporte KAME.')
        if 'unidadnegocio' in detalle_lower or 'unidad de negocio' in detalle_lower:
            return 'La unidad de negocio configurada no es válida o no está activa en KAME.'
        if 'usuario' in detalle_lower:
            return 'El correo configurado no está habilitado como usuario en KAME.'
        if 'iva' in detalle_lower or 'afecto' in detalle_lower or 'total' in detalle_lower:
            return 'KAME rechazó el cálculo tributario de la boleta.'
        if status_code:
            return f'KAME rechazó la boleta (código HTTP {status_code}). Revisa la configuración KAME.'
        return 'KAME no pudo emitir la boleta. Revisa el documento en KAME.'

    def _unidad_negocio(self, servicio_nombre):
        """Unidad de negocio por tipo de acceso (KAME_UNIDAD_NEGOCIO_BANO / _DUCHA);
        si no está definida, usa KAME_UNIDAD_NEGOCIO."""
        from app.services.cuadre import tipo_acceso
        tipo = tipo_acceso(servicio_nombre)
        especifica = self._config(f'KAME_UNIDAD_NEGOCIO_{tipo.upper()}', '') if tipo else ''
        return especifica or self._config('KAME_UNIDAD_NEGOCIO', 'CASA MATRIZ')

    def _reload(self):
        """Recarga credenciales; el entorno tiene prioridad sobre SQLite."""
        self.base_url = self._config(
            'KAME_BASE_URL',
            self._config('KAME_URL', 'https://api.kameone.cl')
        ).rstrip('/')
        configured_token = self._config('KAME_TOKEN', '')
        self.client_id = self._config('KAME_CLIENT_ID', '')
        self.client_secret = self._config('KAME_CLIENT_SECRET', '')
        self.usuario   = self._config('KAME_USER', '')
        self._static_token = bool(configured_token)
        if configured_token:
            self.token = configured_token
            self._token_expires_at = float('inf')
        elif not (self.client_id and self.client_secret):
            self.token = ''
            self._token_expires_at = 0
        self.rut      = self._config('KAME_RUT', '')
        self.razon    = self._config('KAME_RAZON_SOCIAL', '')

    def _obtener_token(self, force=False, timeout=None) -> str:
        """Obtiene y conserva el token Auth0 hasta poco antes de que expire."""
        self._reload()
        if self._static_token:
            return self.token
        if not (self.client_id and self.client_secret):
            return ''
        if not force and self.token and time.time() < self._token_expires_at:
            return self.token

        response = requests.post(
            f"{self.base_url}/oauth/token",
            headers={'Content-Type': 'application/json'},
            json={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'audience': f'{self.base_url}/api',
                'grant_type': 'client_credentials',
            },
            timeout=self.timeout if timeout is None else timeout,
        )
        response.raise_for_status()
        data = response.json()
        self.token = data['access_token']
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError('Token KAME vacío')
        expires_in = int(data.get('expires_in', 86400))
        self._token_expires_at = time.time() + max(expires_in - 60, 0)
        return self.token

    def disponible(self) -> bool:
        self._reload()
        return bool(self.base_url and (self.token or (self.client_id and self.client_secret)))

    def ping(self) -> dict:
        """Prueba las credenciales solicitando un token a Auth0."""
        if not self.disponible():
            return {'ok': False, 'mensaje': 'Faltan credenciales KAME en el archivo .env.'}
        if self._static_token:
            return {
                'ok': False,
                'mensaje': ('Hay un KAME_TOKEN configurado, pero no existe una operación segura '
                            'para validarlo sin emitir una boleta. Configura KAME_CLIENT_ID y '
                            'KAME_CLIENT_SECRET para comprobar la conexión.'),
            }
        try:
            if self._obtener_token(force=True):
                return {'ok': True, 'mensaje': 'Credenciales KAME válidas'}
            return {'ok': False, 'mensaje': 'Faltan credenciales KAME'}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 'HTTP'
            return {'ok': False, 'mensaje': f'No fue posible autenticar con KAME (HTTP {status}).'}
        except requests.exceptions.ConnectionError:
            return {'ok': False, 'mensaje': 'No se pudo conectar al servidor KAME'}
        except requests.exceptions.Timeout:
            return {'ok': False, 'mensaje': 'Tiempo de espera agotado'}
        except Exception as e:
            return {'ok': False, 'mensaje': 'Respuesta de autenticación KAME inválida'}

    def obtener_documento(self, rut_emisor: str, tipo: str, folio: str, formato: str):
        """Consulta un documento existente; nunca invoca addVenta.

        Contrato: https://mzujlb48px.apidog.io/obtener-xml-registro-de-ventas-38233649e0
        y obtener-pdf-registro-de-ventas-38139918e0. Reutiliza el token de emision.
        """
        from app.services.documentos_kame import DocumentoKameError, DocumentoKameTemporal, normalizar_rut
        import re
        rut_emisor = normalizar_rut(rut_emisor)
        if tipo not in ("39", "41") or not re.fullmatch(r"[1-9][0-9]*", str(folio)) or formato not in ("XML", "PDF"):
            raise DocumentoKameError("Los datos del documento KAME no son válidos.")
        if not self.disponible():
            raise DocumentoKameError("Faltan credenciales KAME para recuperar la boleta emitida.")
        def tiempo_disponible():
            limite = getattr(self, "_documento_deadline", None)
            if limite is None:
                return self.timeout
            restante = limite - time.monotonic()
            if restante <= 0:
                raise DocumentoKameTemporal("Se agoto la espera del timbre de esta boleta.")
            return (min(3, restante / 2), min(5, restante / 2))
        try:
            self.token = self._obtener_token(timeout=tiempo_disponible())
            url = f"{self.base_url}/api/Documento/getDocumento{formato}/{rut_emisor}/{tipo}/{folio}"
            respuesta = requests.get(url, headers=self._headers(), timeout=tiempo_disponible(), allow_redirects=False)
            if respuesta.status_code == 401 and self.client_id and not self._static_token:
                self.token = self._obtener_token(force=True, timeout=tiempo_disponible())
                respuesta = requests.get(url, headers=self._headers(), timeout=tiempo_disponible(), allow_redirects=False)
            if respuesta.status_code != 200:
                print(f'[KAME] Consulta {formato} folio={folio}: HTTP {respuesta.status_code}', flush=True)
                mensaje = ("KAME aún no entrega el documento emitido. Reintenta Imprimir sin registrar otra venta."
                           if respuesta.status_code in (404, 409, 202) else
                           "No se pudo recuperar el documento de KAME. Reintenta Imprimir sin registrar otra venta.")
                error = DocumentoKameTemporal if respuesta.status_code in (202, 404, 409, 429, 500, 502, 503, 504) else DocumentoKameError
                raise error(mensaje)
            if len(respuesta.content) > 16 * 1024 * 1024:
                raise DocumentoKameError("El documento de KAME supera el tamaño permitido.")
            try:
                datos = respuesta.json()
            except ValueError:
                # El ejemplo PDF publicado es un texto con etiqueta, no un JSON.
                if formato != "PDF" or not respuesta.text.lstrip().startswith("ArchivoBase64PDF"):
                    raise DocumentoKameError("KAME devolvio un documento con formato no reconocido.")
                datos = respuesta.text
            if isinstance(datos, dict) and (datos.get("Error") or (
                    datos.get("Estado") and str(datos["Estado"]).lower() != "ok")):
                raise DocumentoKameTemporal("KAME todavía no tiene disponible el documento. Reintenta Imprimir.")
            return datos
        except requests.RequestException as error_red:
            print(f'[KAME] Consulta {formato} folio={folio}: {type(error_red).__name__}', flush=True)
            clase = DocumentoKameError if (error_red.response is not None and
                    error_red.response.status_code in (400, 401, 403, 404)) else DocumentoKameTemporal
            raise clase("No se pudo conectar con KAME para recuperar el documento. La venta no debe repetirse.") from None

    def emitir_boleta(self, venta: dict, servicio: dict) -> dict:
        """
        Emite una boleta electrónica tipo 39.

        Payload compatible con la API REST de KAME / Siigo.
        Ref: https://www.kame.cl/sistema-de-facturacion-electronica/

        Returns:
            {'ok': bool, 'folio': str|None, 'id': str|None,
             'pdf_url': str|None, 'mensaje': str}
        """
        if not self.disponible():
            return {'ok': False, 'folio': None, 'id': None,
                    'pdf_url': None, 'mensaje': 'KAME no configurado'}

        if not self.usuario:
            return {'ok': False, 'folio': None, 'id': None, 'pdf_url': None,
                    'mensaje': 'Falta KAME_USER en el archivo .env'}

        rut_receptor = venta.get('rut_cliente') or '66666666-6'
        razon_receptor = 'Cliente' if venta.get('rut_cliente') else 'Consumidor Final'

        total = int(Decimal(str(venta['total'])).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        cantidad = int(venta.get('cantidad', 1))
        precio_unitario_bruto = int((Decimal(total) / Decimal(cantidad)).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP))
        afecto = int((Decimal(total) / Decimal('1.19')).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP))
        iva = total - afecto
        fecha = datetime.now().strftime('%Y-%m-%dT00:00:00')

        payload = {
            'Usuario': self.usuario,
            'Documento': 'Boleta Electrónica',
            'Sucursal': self._config('KAME_SUCURSAL', ''),
            'Rut': rut_receptor,
            'TipoDocumento': 'VENTA',
            'Folio': '',
            'RznSocial': razon_receptor,
            'Giro': 'Particular',
            # El punto de venta utiliza los datos guardados en Configuración.
            'Direccion': ((get_config(self.db, 'empresa_direccion') if self.db is not None else '') or '').strip() or 'Sin dirección',
            'Ciudad': ((get_config(self.db, 'empresa_ciudad') if self.db is not None else '') or '').strip(),
            'Comuna': '',
            'Telefono': '',
            'Email': '',
            'Fecha': fecha,
            'Comentario': f"Venta SanitaPoint {venta.get('ticket_num', '')}",
            'FormaPago': '1',
            'Afecto': afecto,
            'Exento': 0,
            'Descuento': 0,
            'TipoImpto1': 'IVA',
            'ValorImpto1': iva,
            'total': total,
            'FechaVencimiento': fecha,
            'Bodega': '',
            'EsInventariable': '',
            'Vendedor': '',
            'Recargo': 0,
            'PorcDescuento': 0,
            'PorcRecargo': 0,
            'Contacto': '',
            'Comision': None,
            'FormaCredito': '',
            'Detalle': [
                {
                    'Descripcion': servicio.get('nombre', ''),
                    # En boletas KAME exige montos brutos en cada línea.
                    'Cantidad': cantidad,
                    'PrecioUnitario': precio_unitario_bruto,
                    'Descuento': 0,
                    'Total': total,
                    'UnidadMedida': self._config('KAME_UNIDAD_MEDIDA', 'UN'),
                    'UnidadNegocio': self._unidad_negocio(servicio.get('nombre', '')),
                    'Articulo': '',
                    'PorcDescuento': 0,
                    'DescripcionDetallada': servicio.get('descripcion', ''),
                    'TipoArticulo': 'SERVICIO',
                    # KAME valida este texto como un enumerado. Se permite
                    # sobrescribirlo desde .env debido a diferencias entre
                    # versiones de su API de pruebas.
                    # KAME usa '' para una línea afecta y 'S' para una exenta.
                    'Exento': self._config('KAME_DETALLE_EXENTO', ''),
                }
            ],
            'Cuotas': [],
            'Referencias': [],
        }

        try:
            self.token = self._obtener_token()
            endpoint = f"{self.base_url}/api/Documento/addVenta"
            r = requests.post(
                endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout
            )
            if r.status_code == 401 and self.client_id and not self._static_token:
                self.token = self._obtener_token(force=True)
                r = requests.post(
                    endpoint,
                    headers=self._headers(), json=payload, timeout=self.timeout)
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError('Respuesta KAME inválida')

            if r.status_code in (200, 201):
                ok = str(data.get('Estado', '')).lower() == 'ok' and not data.get('Error') and bool(data.get('Folio'))
                error = data.get('Error')
                if not ok:
                    print(f'[KAME] addVenta sin folio (Estado={data.get("Estado")}): {str(error)[:500]}', flush=True)
                else:
                    print(f'[KAME] Emisión confirmada ticket={venta.get("ticket_num", "")} folio={data.get("Folio")}', flush=True)
                return {
                    'ok':      ok,
                    'folio':   str(data.get('Folio') or ''),
                    'id':      str(data.get('Id') or ''),
                    'pdf_url': '',
                    'mensaje': ('Boleta emitida exitosamente' if ok else
                                self._mensaje_usuario(error or data.get('Estado'))),
                    'detalle_tecnico': error,
                }
            error = data.get('Error') or data.get('message') or r.text[:1000]
            print(f'[KAME] addVenta rechazada (HTTP {r.status_code}): {str(error)[:500]}', flush=True)
            return {
                'ok':      False,
                'folio':   None, 'id': None, 'pdf_url': None,
                'mensaje': self._mensaje_usuario(error, r.status_code),
                'detalle_tecnico': error,
            }
        except requests.exceptions.ConnectionError:
            print('[KAME] Error de conexión al emitir la boleta.', flush=True)
            return {'ok': False, 'folio': None, 'id': None,
                    'pdf_url': None, 'mensaje': 'Sin conexión con KAME'}
        except requests.exceptions.Timeout:
            print('[KAME] Tiempo de espera agotado al emitir la boleta.', flush=True)
            return {'ok': False, 'folio': None, 'id': None,
                    'pdf_url': None, 'mensaje': 'KAME tardó demasiado en responder. Verifica en KAME si se emitió antes de repetir la venta.'}
        except Exception as e:
            print(f'[KAME] Respuesta inválida o error de comunicación: {type(e).__name__}: {str(e)[:300]}', flush=True)
            return {'ok': False, 'folio': None, 'id': None,
                    'pdf_url': None,
                    'mensaje': 'Ocurrió un error al comunicarse con KAME. Revisa la configuración KAME.'}


def verificar_configuracion_punto_venta(db):
    """Detecta configuraciones incompletas antes de registrar un cobro."""
    from app.services.documentos_kame import DocumentoKameError, normalizar_rut
    from datetime import date
    client = KameAPI(db)
    modo = client._config("KAME_MODO", "real").strip().lower()
    if modo == "mock":
        return
    if modo != "real":
        raise DocumentoKameError("Configura KAME_MODO como real o mock antes de vender.")
    if not client.disponible() or not client.usuario:
        raise DocumentoKameError("Completa las credenciales y KAME_USER antes de vender.")
    normalizar_rut(client._config("KAME_RUT", ""))
    numero = str(client._config("KAME_RESOLUCION_NUMERO", ""))
    if not numero.isascii() or not numero.isdigit():
        raise DocumentoKameError("Configura KAME_RESOLUCION_NUMERO antes de vender para entregar la boleta completa.")
    try:
        date.fromisoformat(client._config("KAME_RESOLUCION_FECHA", ""))
    except (ValueError, TypeError):
        raise DocumentoKameError("Configura KAME_RESOLUCION_FECHA con formato AAAA-MM-DD antes de vender.") from None


def emitir_boleta(db, servicio_nombre, monto_total, forma_pago, rut_cliente=None, ticket_num=""):
    """Mantiene el contrato del POS; solo simula en modo mock explícito."""
    client = KameAPI(db)
    modo = client._config('KAME_MODO', 'real').strip().lower()
    if modo == 'mock':
        return f"MOCK-{uuid4().hex[:12].upper()}", 'mock'
    if modo != 'real':
        return 'Modo KAME inválido', 'error'
    if monto_total <= 0:
        return 'El monto de la boleta debe ser mayor que cero', 'error'
    result = client.emitir_boleta(
        {'total': monto_total, 'cantidad': 1, 'rut_cliente': rut_cliente,
         'ticket_num': ticket_num, 'forma_pago': forma_pago},
        {'nombre': servicio_nombre},
    )
    if result['ok'] and ticket_num:
        from app.models import Venta
        from app.services.documentos_kame import preparar_timbre
        venta = db.query(Venta).filter(Venta.ticket == ticket_num).first()
        if venta is not None:
            venta.kame_documento_id = result.get('id') or None
            venta.kame_rut_emisor = client._config('KAME_RUT', '') or None
            venta.kame_tipo_documento = '39'
            venta.folio_kame = result['folio']
            venta.estado_kame = 'ok'
            db.commit()
            # Una falla al obtener el timbre nunca convierte una emision en fallida.
            anterior = getattr(client, '_documento_deadline', None)
            client._documento_deadline = time.monotonic() + 3
            try:
                # Una consulta breve. Los reintentos largos quedan para Imprimir.
                preparar_timbre(db, venta, client=client, exigir=False, esperar=False)
            except Exception:
                # La emision confirmada no se repite por un fallo local de impresion.
                import logging
                logging.getLogger(__name__).exception("No se pudo preparar la impresion de la boleta emitida")
                db.rollback()
            finally:
                client._documento_deadline = anterior
    return (result['folio'], 'ok') if result['ok'] else (result['mensaje'], 'error')
