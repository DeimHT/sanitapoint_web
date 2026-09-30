import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.main import _asignar_cajas_anteriores, app
from app.models import Caja, Cuenta, Servicio, Usuario, Venta
from app.routers.caja import (abrir_caja, cerrar_caja, listar_movimientos,
                              obtener_caja_abierta, registrar_movimiento, ultimo_cierre)
from app.routers.ventas import registrar_venta
from app.schemas import AbrirCajaIn, CerrarCajaIn, MovimientoIn, VentaIn
from app.services.cuadre import resumen_caja
from app.security import hash_password


class TurnosTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(temporal.name) / 'test.db'}",
                                    connect_args={"check_same_thread": False, "timeout": 15})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.a = Cuenta(username="a", nombre="Ana", password_hash="test", rol="cajero")
        self.b = Cuenta(username="b", nombre="Beto", password_hash="test", rol="cajero")
        self.supervisor = Cuenta(username="super", nombre="Supervisor", password_hash="test", rol="supervisor")
        self.bano = Servicio(nombre="Uso de Baño", precio=500)
        self.ducha = Servicio(nombre="Ducha", precio=2000)
        self.cliente = Usuario(nombre="Cliente")
        self.db.add_all([self.a, self.b, self.supervisor, self.bano, self.ducha, self.cliente])
        self.db.commit()
        self.inicio = AbrirCajaIn(saldo_inicial=10000, torniquete_bano_inicial=100,
                                  torniquete_ducha_inicial=200)
        self.ca = abrir_caja(self.inicio, self.db, self.a)
        self.cb = abrir_caja(self.inicio, self.db, self.b)
        for target, result in (
            ("app.routers.ventas.emitir_boleta", (None, "omitido")),
            ("app.routers.ventas.ticket_printer.emitir_ticket",
             {"impreso_termica": False, "detalle_impresion": "Prueba"}),
        ):
            mock = patch(target, return_value=result)
            mock.start()
            self.addCleanup(mock.stop)

    def vender(self, cuenta, servicio, pago="efectivo", pase=False):
        return registrar_venta(VentaIn(servicio_id=servicio.id, forma_pago=pago,
                                       es_pase_libre=pase,
                                       usuario_id=self.cliente.id if pase else None), self.db, cuenta)

    def cerrar(self, cuenta, dinero=10000, bano=100, ducha=200):
        return cerrar_caja(CerrarCajaIn(saldo_final=dinero, torniquete_bano_final=bano,
                                        torniquete_ducha_final=ducha), self.db, cuenta)

    def test_contadores_por_usuario_y_reinicio_por_turno(self):
        self.assertEqual((self.ca.contador_bano, self.ca.contador_ducha), (0, 0))
        self.assertEqual(self.ca.saldo_esperado, 10000)
        self.vender(self.a, self.bano)
        self.vender(self.a, self.bano, pase=True)
        self.vender(self.a, self.ducha, "transferencia")
        self.vender(self.b, self.ducha)
        a = obtener_caja_abierta(self.db, self.a)
        b = obtener_caja_abierta(self.db, self.b)
        self.assertEqual((a.contador_bano, a.contador_ducha, a.pases_bano), (2, 1, 1))
        self.assertEqual((b.contador_bano, b.contador_ducha), (0, 1))
        self.cerrar(self.a, 10500, 102, 201)
        nueva = abrir_caja(self.inicio, self.db, self.a)
        self.assertNotEqual(nueva.id, self.ca.id)
        self.assertEqual((nueva.contador_bano, nueva.contador_ducha), (0, 0))
        self.assertEqual(obtener_caja_abierta(self.db, self.b).contador_ducha, 1)

    def test_cuadre_con_efectivo_transferencia_pases_y_retiros(self):
        self.vender(self.a, self.bano)
        self.vender(self.a, self.ducha)
        self.vender(self.a, self.bano, "transferencia")
        self.vender(self.a, self.ducha, "transferencia")
        self.vender(self.a, self.ducha, "transferencia")
        self.vender(self.a, self.bano, pase=True)
        registrar_movimiento(MovimientoIn(tipo="retiro", monto=1000, caja_id=self.ca.id),
                             self.db, self.supervisor)
        cierre = self.cerrar(self.a, 11400, 104, 202)
        self.assertEqual(cierre.ventas_efectivo, 2500)
        self.assertEqual(cierre.total_retiros, 1000)
        self.assertEqual(cierre.saldo_esperado, 11500)
        self.assertEqual(cierre.cambio_dinero, 1400)
        self.assertEqual(cierre.ingreso_ajustado_retiros, 2400)
        self.assertEqual(cierre.diferencia_dinero, -100)
        self.assertEqual((cierre.personas_bano, cierre.contador_bano, cierre.diferencia_bano), (4, 3, 1))
        self.assertEqual((cierre.personas_ducha, cierre.contador_ducha, cierre.diferencia_ducha), (2, 3, -1))
        self.assertEqual(ultimo_cierre(self.db, self.a).model_dump(), cierre.model_dump())
        self.assertEqual(obtener_caja_abierta(self.db, self.b).total_retiros, 0)

    def test_no_usa_caja_ajena_ni_permite_mutar_turno_cerrado(self):
        self.cerrar(self.a)
        with self.assertRaises(HTTPException):
            self.vender(self.a, self.bano)
        with self.assertRaises(HTTPException):
            self.cerrar(self.a)
        with self.assertRaises(HTTPException):
            listar_movimientos(self.cb.id, self.db, self.a)
        with self.assertRaises(HTTPException):
            registrar_movimiento(MovimientoIn(tipo="retiro", monto=100, caja_id=self.ca.id),
                                 self.db, self.supervisor)
        self.assertEqual(obtener_caja_abierta(self.db, self.b).id, self.cb.id)

    def test_lecturas_finales_no_pueden_retroceder(self):
        for bano, ducha in ((99, 200), (100, 199)):
            with self.assertRaises(HTTPException):
                self.cerrar(self.a, bano=bano, ducha=ducha)
            caja = self.db.get(Caja, self.ca.id)
            self.assertEqual(caja.estado, "abierta")
            self.assertIsNone(caja.torniquete_bano_final)

    def test_validacion_de_cierre_y_retiro(self):
        base = dict(saldo_final=0, torniquete_bano_final=0, torniquete_ducha_final=0)
        for campo in base:
            for valor in (-1, 0.5, None):
                with self.assertRaises(ValidationError):
                    CerrarCajaIn(**{**base, campo: valor})
            with self.assertRaises(ValidationError):
                CerrarCajaIn(**{k: v for k, v in base.items() if k != campo})
        for monto in (-1, 0):
            with self.assertRaises(ValidationError):
                MovimientoIn(tipo="retiro", monto=monto)

    def test_pase_solo_bano_y_rechazado_no_incrementa(self):
        with self.assertRaises(HTTPException):
            self.vender(self.a, self.ducha, pase=True)
        self.vender(self.a, self.bano, pase=True)
        with self.assertRaises(HTTPException):
            self.vender(self.b, self.bano, pase=True)
        self.db.rollback()
        self.assertEqual(obtener_caja_abierta(self.db, self.a).contador_bano, 1)
        self.assertEqual(obtener_caja_abierta(self.db, self.b).contador_bano, 0)

    def test_migracion_de_propietario_no_adivina_nombres_ambiguos(self):
        historica = Caja(operador="Ana", estado="cerrada", saldo_inicial=0)
        ambigua = Caja(operador="Desconocido", estado="cerrada", saldo_inicial=0)
        self.db.add_all([historica, ambigua])
        self.db.commit()
        _asignar_cajas_anteriores(self.db)
        _asignar_cajas_anteriores(self.db)
        self.assertEqual(historica.cuenta_id, self.a.id)
        self.assertIsNone(ambigua.cuenta_id)
        self.assertIsNone(resumen_caja(self.db, historica).personas_bano)

    def test_ventas_simultaneas_dos_usuarios_tickets_y_contadores(self):
        cuentas = [self.a.id, self.b.id]
        servicio_id = self.bano.id
        self.db.rollback()
        barrera = Barrier(2)

        def vender_en_hilo(cuenta_id):
            with Session(self.engine) as db:
                cuenta = db.get(Cuenta, cuenta_id)
                barrera.wait(timeout=10)
                return registrar_venta(VentaIn(servicio_id=servicio_id, forma_pago="efectivo"),
                                       db, cuenta).ticket

        with ThreadPoolExecutor(max_workers=2) as pool:
            tickets = list(pool.map(vender_en_hilo, cuentas))
        self.assertEqual(len(set(tickets)), 2)
        self.assertEqual(obtener_caja_abierta(self.db, self.a).contador_bano, 1)
        self.assertEqual(obtener_caja_abierta(self.db, self.b).contador_bano, 1)

    def test_aperturas_simultaneas_mismo_usuario_solo_una(self):
        self.cerrar(self.a)
        cuenta_id = self.a.id
        self.db.rollback()
        barrera = Barrier(2)

        def abrir_en_hilo(_):
            with Session(self.engine) as db:
                cuenta = db.get(Cuenta, cuenta_id)
                barrera.wait(timeout=10)
                try:
                    abrir_caja(self.inicio, db, cuenta)
                    return True
                except HTTPException:
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(abrir_en_hilo, range(2)))
        self.assertEqual(sorted(resultados), [False, True])

    def test_api_con_sesiones_reales_y_permisos(self):
        self.a.password_hash = hash_password("secreto")
        self.b.password_hash = self.a.password_hash
        self.supervisor.password_hash = self.a.password_hash
        self.db.commit()

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.addCleanup(app.dependency_overrides.pop, get_db)

        async def request(method, path, body=None, cookie=""):
            messages = []
            raw = json.dumps(body or {}).encode()
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": method, "scheme": "http", "path": path,
                     "raw_path": path.encode(), "query_string": b"", "root_path": "",
                     "server": ("test", 80), "client": ("test", 1234),
                     "headers": [(b"content-type", b"application/json"), (b"cookie", cookie.encode())]}

            async def receive():
                return {"type": "http.request", "body": raw, "more_body": False}

            async def send(message):
                messages.append(message)

            await app(scope, receive, send)
            start = next(m for m in messages if m["type"] == "http.response.start")
            data = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            cookies = [v.decode().split(";")[0] for k, v in start["headers"] if k == b"set-cookie"]
            return start["status"], json.loads(data), cookies[0] if cookies else cookie

        def call(method, path, body=None, cookie=""):
            return asyncio.run(request(method, path, body, cookie))

        self.assertEqual(call("GET", "/api/caja")[0], 401)
        cookies = {}
        for username in ("a", "b", "super"):
            status, _, cookie = call("POST", "/api/auth/login", {
                "username": username, "password": "secreto", "servicio": "Baño 1"})
            self.assertEqual(status, 200)
            cookies[username] = cookie
        for username, caja in (("a", self.ca), ("b", self.cb)):
            status, data, _ = call("GET", "/api/caja", cookie=cookies[username])
            self.assertEqual(status, 200)
            self.assertEqual(data["id"], caja.id)
        self.assertEqual(call("GET", f"/api/caja/{self.cb.id}/movimientos", cookie=cookies["a"])[0], 404)
        self.assertEqual(call("POST", "/api/caja/movimiento", {
            "tipo": "retiro", "monto": 100, "caja_id": self.cb.id}, cookies["a"])[0], 403)
        self.assertEqual(call("POST", "/api/caja/movimiento", {
            "tipo": "retiro", "monto": 100, "caja_id": self.ca.id}, cookies["super"])[0], 200)
        self.assertEqual(call("POST", "/api/ventas", {
            "servicio_id": self.bano.id, "forma_pago": "efectivo"}, cookies["a"])[0], 200)
        status, cierre, _ = call("POST", "/api/caja/cerrar", {
            "saldo_final": 10400, "torniquete_bano_final": 101,
            "torniquete_ducha_final": 200}, cookies["a"])
        self.assertEqual(status, 200)
        self.assertEqual(cierre["diferencia_dinero"], 0)
        self.assertEqual(cierre["diferencia_bano"], 0)
        self.assertEqual(call("GET", "/api/caja", cookie=cookies["b"])[1]["contador_bano"], 0)
