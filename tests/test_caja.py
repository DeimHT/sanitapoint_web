import unittest
from unittest.mock import patch, Mock

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database import Base
from app.main import _asegurar_columnas
from app.models import Caja, Cuenta
from app.routers.caja import abrir_caja
from app.schemas import AbrirCajaIn, CajaOut


class AperturaCajaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.cuenta = Cuenta(username="cajero", nombre="Ana Pérez", password_hash="test", rol="cajero")
        self.db.add(self.cuenta)
        self.db.commit()
        self.datos = dict(saldo_inicial=25000, torniquete_bano_inicial=1234,
                          torniquete_ducha_inicial=567)

    def test_guarda_lecturas_y_usa_usuario_autenticado(self):
        body = AbrirCajaIn(**self.datos, operador="Otro operador")
        caja = abrir_caja(body, self.db, self.cuenta)
        self.db.expire_all()
        guardada = self.db.get(Caja, caja.id)
        self.assertEqual(guardada.operador, "Ana Pérez")
        salida = CajaOut.model_validate(guardada)
        for campo, valor in self.datos.items():
            self.assertEqual(getattr(salida, campo), valor)
        with self.assertRaises(HTTPException):
            abrir_caja(body, self.db, self.cuenta)

    def test_sin_nombre_usa_username_y_acepta_ceros(self):
        self.cuenta.nombre = " "
        caja = abrir_caja(AbrirCajaIn(**dict.fromkeys(self.datos, 0)), self.db, self.cuenta)
        self.assertEqual(caja.operador, "cajero")

    def test_campos_obligatorios_enteros_no_negativos(self):
        for campo in self.datos:
            datos = self.datos.copy()
            del datos[campo]
            if campo != "torniquete_ducha_inicial":
                with self.assertRaises(ValidationError):
                    AbrirCajaIn(**datos)
            for invalido in (-1, 1.5, "") + (() if campo == "torniquete_ducha_inicial" else (None,)):
                with self.assertRaises(ValidationError):
                    AbrirCajaIn(**{**self.datos, campo: invalido})

    def test_bano_2_opens_and_closes_without_shower_readings(self):
        from app.routers.caja import cerrar_caja
        from app.schemas import CerrarCajaIn
        request = Mock(session={"servicio": "Ba\u00f1o 2"})
        caja = abrir_caja(AbrirCajaIn(saldo_inicial=0, torniquete_bano_inicial=10),
                          self.db, self.cuenta, request)
        self.assertEqual(caja.servicio, "Ba\u00f1o 2")
        self.assertIsNone(caja.torniquete_ducha_inicial)
        cierre = cerrar_caja(CerrarCajaIn(saldo_final=0, torniquete_bano_final=10),
                             self.db, self.cuenta)
        self.assertIsNone(cierre.torniquete_ducha_final)

    def test_bano_1_requires_shower_reading(self):
        request = Mock(session={"servicio": "Ba\u00f1o 1"})
        with self.assertRaises(HTTPException):
            abrir_caja(AbrirCajaIn(saldo_inicial=0, torniquete_bano_inicial=10),
                       self.db, self.cuenta, request)

    def test_migracion_conserva_datos_y_es_repetible(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE cajas (id INTEGER PRIMARY KEY, saldo_inicial INTEGER)"))
            conn.execute(text("INSERT INTO cajas VALUES (1, 5000)"))
        with patch("app.main.engine", engine), patch("app.main.settings") as settings:
            settings.database_url = "sqlite://"
            _asegurar_columnas()
            _asegurar_columnas()
        columnas = {c["name"] for c in inspect(engine).get_columns("cajas")}
        self.assertTrue({"torniquete_bano_inicial", "torniquete_ducha_inicial"} <= columnas)
        with engine.connect() as conn:
            fila = conn.execute(text("SELECT saldo_inicial, torniquete_bano_inicial, torniquete_ducha_inicial FROM cajas")).one()
        self.assertEqual(tuple(fila), (5000, None, None))
