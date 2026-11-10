r"""Consulta boletas existentes sin emitir ni modificar ventas o documentos en cache.

Desde la carpeta del servidor:
  .venv\Scripts\python.exe -X utf8 scripts\diagnosticar_kame.py --ultimas 4
El informe JSON no incluye credenciales, RUT ni contenido de los documentos.
"""
import argparse
from contextlib import closing, redirect_stdout
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

import requests
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.services.documentos_kame import (
    DocumentoKameError, decodificar_pdf, identidad, leer_xml, ruta_cache,
)
from app.services.kame_client import KameAPI


def cargar_ventas(ruta, ticket=None, ultimas=4):
    """mode=ro impide crear una base nueva o escribir en la existente."""
    with closing(sqlite3.connect(Path(ruta).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        filtro = "ticket = ?" if ticket else "estado_kame = 'ok' AND es_pase_libre = 0"
        valores = (ticket, ultimas) if ticket else (ultimas,)
        filas = db.execute(f'SELECT * FROM ventas WHERE {filtro} ORDER BY id DESC LIMIT ?', valores)
        return [SimpleNamespace(**dict(fila)) for fila in filas]


def consultar_registro(client, venta):
    documento = 'Boleta Exenta Electrónica' if venta.kame_tipo_documento == '41' else 'Boleta Electrónica'
    client.token = client._obtener_token()
    url = f'{client.base_url}/api/Documento/getVenta/{quote(documento, safe="")}/{quote(venta.folio_kame, safe="")}'
    respuesta = requests.get(url, headers=client._headers(), timeout=client.timeout, allow_redirects=False)
    if respuesta.status_code != 200:
        return {'disponible': False, 'motivo': f'Consulta registro ERP: HTTP {respuesta.status_code}'}
    if len(respuesta.content) > 16 * 1024 * 1024:
        return {'disponible': False, 'motivo': 'Respuesta del ERP demasiado grande'}
    datos = respuesta.json()
    if not isinstance(datos, dict):
        return {'disponible': False, 'motivo': 'Formato de respuesta del ERP no reconocido'}
    if datos.get('Error') or 'IdVenta' not in datos:
        return {'disponible': False, 'motivo': client._detalle_error_documento(datos)}
    try:
        coincide = (Decimal(str(datos.get('Folio'))) == Decimal(venta.folio_kame) and
                    Decimal(str(datos.get('Total'))) == venta.monto)
    except InvalidOperation:
        coincide = False
    return {'disponible': True, 'folio_y_monto_coinciden': coincide}


def diagnosticar_venta(client, venta):
    informe = {'ticket': venta.ticket, 'folio': venta.folio_kame,
               'estado_local': venta.estado_kame}
    try:
        clave = identidad(venta, client)
    except DocumentoKameError as error:
        informe['error_local'] = str(error)
        return informe
    cache = ruta_cache(clave, 'xml')
    informe['xml_en_cache'] = cache.exists()
    if cache.exists():
        try:
            leer_xml(cache.read_text(encoding='utf-8'), clave, venta)
            informe['xml_en_cache_valido'] = True
        except (DocumentoKameError, OSError, UnicodeError):
            informe['xml_en_cache_valido'] = False
    # Se consulta a KAME aunque exista cache, para comparar remoto y local.
    for formato in ('XML', 'PDF'):
        try:
            datos = client.obtener_documento(*clave, formato)
            if formato == 'XML':
                leer_xml(datos.get('Xml') if isinstance(datos, dict) else None, clave, venta)
            else:
                decodificar_pdf(datos)
            informe[formato.lower() + '_remoto'] = {'disponible': True}
        except DocumentoKameError as error:
            informe[formato.lower() + '_remoto'] = {'disponible': False, 'motivo': str(error)}
        except (requests.RequestException, ValueError, KeyError):
            informe[formato.lower() + '_remoto'] = {
                'disponible': False, 'motivo': 'Fallo de red, autenticación o formato en la respuesta de KAME'}
    try:
        informe['registro_erp'] = consultar_registro(client, venta)
    except (requests.RequestException, ValueError, KeyError):
        informe['registro_erp'] = {'disponible': False, 'motivo': 'Fallo de red, autenticación o formato al consultar el ERP'}
    return informe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticket', help='Revisar un ticket concreto en vez de las últimas boletas')
    parser.add_argument('--ultimas', type=int, choices=range(1, 11), default=4, metavar='1-10')
    parser.add_argument('--base-datos', type=Path, help='Ruta SQLite; por defecto usa DATABASE_URL o data/sanitapoint.db')
    args = parser.parse_args(argv)
    env = dotenv_values(RAIZ / '.env')
    ruta = args.base_datos
    if ruta is None:
        url = make_url(os.environ.get('DATABASE_URL', env.get('DATABASE_URL') or
                       f'sqlite:///{(RAIZ / "data/sanitapoint.db").as_posix()}'))
        if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
            parser.error('Este diagnóstico requiere una base SQLite existente. Usa --base-datos RUTA.')
        ruta = Path(url.database)
        if not ruta.is_absolute():
            ruta = RAIZ / ruta
    try:
        ventas = cargar_ventas(ruta, args.ticket, args.ultimas)
    except sqlite3.Error:
        parser.error('No se pudo leer la base SQLite existente. Comprueba la ruta y la versión del servidor.')
    client = KameAPI(None)
    host = urlsplit(client._config('KAME_BASE_URL', 'https://api.kameone.cl'))
    if host.scheme != 'https' or not host.hostname or host.username or host.password:
        parser.error('KAME_BASE_URL debe ser HTTPS y no contener credenciales en la URL.')
    with redirect_stdout(sys.stderr):
        resultados = [diagnosticar_venta(client, venta) for venta in ventas]
    print(json.dumps({'modo_configurado': client._config('KAME_MODO', 'real'),
                      'servidor_kame': host.hostname, 'ventas': resultados}, ensure_ascii=False, indent=2))
    return 0 if resultados else 1


if __name__ == '__main__':
    raise SystemExit(main())
