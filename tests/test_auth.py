import asyncio
import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.database import Base
from app.main import login_page
from app.models import Cuenta
from app.routers.auth import login, logout, me
from app.schemas import LoginIn
from app.security import hash_password


class LoginTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.cuenta = Cuenta(username="cajero", nombre="Caja", rol="cajero",
                             password_hash=hash_password("secreto"), activo=True)
        self.db.add(self.cuenta)
        self.db.commit()
        self.request = Request({"type": "http", "session": {}, "headers": []})

    def test_servicio_persiste_y_logout_limpia_sesion(self):
        for servicio in ("Baño 1", "Baño 2"):
            result = login(LoginIn(username="cajero", password="secreto", servicio=servicio),
                           self.request, self.db)
            self.assertEqual(result.servicio, servicio)
            self.assertEqual(self.request.session["uid"], self.cuenta.id)
            self.assertEqual(me(self.request, self.cuenta).servicio, servicio)
        logout(self.request)
        self.assertEqual(self.request.session, {})

    def test_servicio_obligatorio_y_limitado(self):
        for extra in ({}, {"servicio": ""}, {"servicio": "Baño 3"}):
            with self.assertRaises(ValidationError):
                LoginIn(username="cajero", password="secreto", **extra)

    def test_rechaza_credenciales_y_cuentas_inactivas(self):
        for username, password, activo in (("cajero", "mal", True),
                                            ("inexistente", "secreto", True),
                                            ("cajero", "secreto", False)):
            self.cuenta.activo = activo
            self.db.commit()
            with self.assertRaises(HTTPException) as error:
                login(LoginIn(username=username, password=password, servicio="Baño 1"),
                      self.request, self.db)
            self.assertEqual(error.exception.status_code, 401)
            self.assertEqual(self.request.session, {})

    def test_pagina_carga_selectores_y_escapa_nombres(self):
        self.db.add(Cuenta(username="otro", nombre="<script>alert(1)</script>",
                           password_hash="oculto", activo=False))
        self.db.commit()
        response = asyncio.run(login_page(self.request, self.db))
        html = response.body.decode()
        self.assertIn('<select id="servicio"', html)
        self.assertIn('<select id="username"', html)
        self.assertIn('value="Baño 1"', html)
        self.assertIn('value="Baño 2"', html)
        self.assertIn('value="cajero"', html)
        self.assertIn('value="otro" disabled', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn(self.cuenta.password_hash, html)


if __name__ == "__main__":
    unittest.main()
