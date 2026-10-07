import asyncio
import io
import unittest

from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Cuenta
from app.routers.cuentas import importar_cuentas
from app.security import verify_password


class BulkAccountsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.actual = Cuenta(username='admin', nombre='Admin', rol='administrador', password_hash='hash')
        self.db.add(self.actual)
        self.db.commit()

    def upload(self, rows, confirmar=False):
        wb = Workbook()
        wb.active.title = 'Cuentas'
        wb.active.append(['usuario', 'nombre', 'rol', 'contrasena'])
        for row in rows:
            wb.active.append(row)
        file = io.BytesIO()
        wb.save(file)
        file.seek(0)
        return asyncio.run(importar_cuentas(UploadFile(file=file, filename='cuentas.xlsx'),
                                           confirmar, self.db, self.actual))

    def test_preview_then_create_without_exposing_passwords(self):
        rows = [['ana', 'Ana', 'cajero', 'secret-123'], ['juan', 'Juan', 'supervisor', 'secret-456']]
        preview = self.upload(rows)
        self.assertTrue(preview['ok'])
        self.assertNotIn('secret-123', str(preview))
        self.assertEqual(self.db.query(Cuenta).count(), 1)
        result = self.upload(rows, True)
        self.assertEqual(result['creadas'], 2)
        ana = self.db.query(Cuenta).filter_by(username='ana').one()
        self.assertTrue(verify_password('secret-123', ana.password_hash))

    def test_any_invalid_row_prevents_entire_import(self):
        result = self.upload([['ana', 'Ana', 'cajero', 'secret'], ['admin', '', 'invalid', '']], True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['errores'][0]['fila'], 3)
        self.assertEqual(self.db.query(Cuenta).count(), 1)

    def test_contabilidad_cannot_import_administrator(self):
        self.actual.rol = 'contabilidad'
        self.db.commit()
        result = self.upload([['newadmin', '', 'administrador', 'secret']], True)
        self.assertFalse(result['ok'])
        self.assertEqual(self.db.query(Cuenta).count(), 1)

    def test_duplicate_file_users_are_rejected(self):
        result = self.upload([['ana', '', 'cajero', 'secret'], ['ana', '', 'cajero', 'secret']], True)
        self.assertFalse(result['ok'])
        self.assertEqual(self.db.query(Cuenta).count(), 1)
