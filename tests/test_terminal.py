import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.database import get_db
from app.main import app
from app.models import Caja, Cuenta
from app.routers.caja import abrir_caja
from app.security import hash_password
import test_turnos


class TerminalTests(unittest.TestCase):
    def setUp(self):
        test_turnos.TurnosTests.setUp(self)
        for caja in self.db.query(Caja).all():
            caja.estado = "cerrada"
        password = hash_password("secreto")
        for cuenta in (self.a, self.b, self.supervisor):
            cuenta.password_hash = password
        self.admin = Cuenta(username="admin", nombre="Admin", password_hash=password, rol="administrador")
        self.contable = Cuenta(username="contable", nombre="Contable", password_hash=password, rol="contabilidad")
        self.db.add_all([self.admin, self.contable])
        self.db.commit()
        def test_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.addCleanup(app.dependency_overrides.pop, get_db)

    def call(self, method, path, body=None, cookie=""):
        async def run():
            messages = []
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                     "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1234),
                     "headers": [(b"content-type", b"application/json"), (b"cookie", cookie.encode())]}
            async def receive():
                return {"type": "http.request", "body": json.dumps(body or {}).encode(), "more_body": False}
            async def send(message):
                messages.append(message)
            await app(scope, receive, send)
            start = next(m for m in messages if m["type"] == "http.response.start")
            raw = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            try:
                data = json.loads(raw)
            except ValueError:
                data = raw.decode()
            cookies = [v.decode().split(";")[0] for k, v in start["headers"] if k == b"set-cookie"]
            return start["status"], data, cookies[0] if cookies else cookie
        return asyncio.run(run())

    def login(self, username, servicio="Ba\u00f1o 1"):
        status, data, cookie = self.call("POST", "/api/auth/login", {
            "username": username, "password": "secreto", "servicio": servicio})
        self.assertEqual(status, 200, data)
        return cookie

    def abrir(self, cookie):
        return self.call("POST", "/api/caja/abrir", self.inicio.model_dump(), cookie)

    def test_relevo_y_dos_banos_independientes(self):
        pepe = self.login("a")
        juan = self.login("b")
        self.assertEqual(self.abrir(pepe)[0], 200)
        status, error, _ = self.abrir(juan)
        self.assertEqual(status, 409)
        self.assertIn("Ana", error["detail"])
        otro_bano = self.login("b", "Ba\u00f1o 2")
        self.assertEqual(self.abrir(otro_bano)[0], 200)
        self.assertEqual(self.call("POST", "/api/auth/login", {
            "username": "a", "password": "secreto", "servicio": "Ba\u00f1o 2"})[0], 409)
        cierre = {"saldo_final": 10000, "torniquete_bano_final": 100, "torniquete_ducha_final": 200}
        self.assertEqual(self.call("POST", "/api/caja/cerrar", cierre, pepe)[0], 200)
        self.assertEqual(self.call("POST", "/api/caja/cerrar", cierre, otro_bano)[0], 200)
        self.assertEqual(self.abrir(juan)[0], 200)

    def test_historial_y_tickets_aislados_con_sesiones_reales(self):
        a = self.login("a")
        b = self.login("b", "Ba\u00f1o 2")
        self.assertEqual(self.abrir(a)[0], 200)
        self.assertEqual(self.abrir(b)[0], 200)
        tickets = []
        with patch("app.routers.ventas.ticket_printer.imprimir_escpos") as printer:
            for cookie in (a, b):
                status, venta, _ = self.call("POST", "/api/ventas", {
                    "servicio_id": self.bano.id, "forma_pago": "efectivo"}, cookie)
                self.assertEqual(status, 200)
                tickets.append(venta["ticket"])
            printer.assert_not_called()
        for cookie, propio, ajeno in ((a, tickets[0], tickets[1]), (b, tickets[1], tickets[0])):
            status, ventas, _ = self.call("GET", "/api/ventas", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual([v["ticket"] for v in ventas], [propio])
            for metodo, sufijo in (("GET", "pdf"), ("POST", "imprimir"), ("GET", "imprimir")):
                self.assertEqual(self.call(metodo, f"/api/ventas/{ajeno}/{sufijo}", cookie=cookie)[0], 404)
            self.assertEqual(self.call("POST", f"/api/ventas/{propio}/imprimir", cookie=cookie)[0], 200)
            status, html, _ = self.call("GET", f"/api/ventas/{propio}/imprimir", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertIn("window.print()", html)
            self.assertIn("data:image/png;base64,", html)
        for username in ("super", "contable", "admin"):
            cookie = self.login(username)
            status, ventas, _ = self.call("GET", "/api/ventas", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual({v["ticket"] for v in ventas}, set(tickets))
            self.assertEqual({v["cajero"] for v in ventas}, {"Ana", "Beto"})
            self.assertEqual({v["servicio_caja"] for v in ventas}, {"Ba\u00f1o 1", "Ba\u00f1o 2"})

    def test_apertura_concurrente_distintos_cajeros_mismo_bano(self):
        ids = (self.a.id, self.b.id)
        self.db.rollback()
        barrera = Barrier(2)
        def abrir(cuenta_id):
            with Session(self.engine) as db:
                cuenta = db.get(Cuenta, cuenta_id)
                request = Request({"type": "http", "session": {"servicio": "Ba\u00f1o 1"}})
                barrera.wait(timeout=10)
                try:
                    abrir_caja(self.inicio, db, cuenta, request)
                    return True
                except HTTPException:
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(abrir, ids)), [False, True])
        self.assertEqual(self.db.query(Caja).filter(Caja.estado == "abierta").count(), 1)

    def test_migracion_indice_existente_y_conflictos_sin_perder_turnos(self):
        from app.main import _asegurar_caja_por_servicio
        indice = next(iter(Caja.__table__.indexes))
        indice.drop(self.engine)
        with patch("app.main.engine", self.engine):
            _asegurar_caja_por_servicio()
            _asegurar_caja_por_servicio()
            indice.drop(self.engine)
            self.db.add_all([Caja(operador="Uno", servicio="Ba\u00f1o 1", estado="abierta"),
                             Caja(operador="Dos", servicio="Ba\u00f1o 1", estado="abierta")])
            self.db.commit()
            with self.assertRaisesRegex(RuntimeError, "Concilia"):
                _asegurar_caja_por_servicio()
            self.assertEqual(self.db.query(Caja).filter(Caja.estado == "abierta").count(), 2)

    def test_tarifas_compartidas_y_referencia_de_torniquete_por_servicio(self):
        admin = self.login("admin")
        precio = self.call("PUT", f"/api/servicios/{self.bano.id}/precio", {"precio": 700}, admin)
        self.assertEqual(precio[0], 200)
        a, b = self.login("a"), self.login("b")
        for cookie in (a, b):
            servicios = self.call("GET", "/api/servicios", cookie=cookie)[1]
            self.assertEqual(next(s["precio"] for s in servicios if s["id"] == self.bano.id), 700)
        self.assertEqual(self.abrir(a)[0], 200)
        cierre = {"saldo_final": 10000, "torniquete_bano_final": 123, "torniquete_ducha_final": 234}
        self.assertEqual(self.call("POST", "/api/caja/cerrar", cierre, a)[0], 200)
        status, sugerencia, _ = self.call("GET", "/api/caja/sugerencia-apertura", cookie=b)
        self.assertEqual(status, 200)
        self.assertEqual(sugerencia["torniquete_bano_inicial"], 123)
        self.assertEqual(sugerencia["torniquete_ducha_inicial"], 234)

    def test_restriccion_base_de_datos_y_configuracion_compartida(self):
        cookie = self.login("admin")
        valores = {"impresora_tipo": "windows", "impresora_nombre": "AJENA", "lector_modo": "ninguno",
                   "empresa_nombre": "Terminal", "ticket_pie": "Gracias"}
        self.assertEqual(self.call("PUT", "/api/config", {"valores": valores}, cookie)[0], 200)
        status, cfg, _ = self.call("GET", "/api/config", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(cfg["empresa_nombre"], "Terminal")
        self.assertFalse(any(k.startswith(("impresora_", "lector_")) for k in cfg))
        for method, path in (("GET", "/api/config/impresoras"), ("GET", "/api/config/lectores"), ("POST", "/api/config/impresora/test")):
            self.assertEqual(self.call(method, path, cookie=cookie)[0], 410)
        self.db.add(Caja(operador="Uno", servicio="Ba\u00f1o 1", estado="abierta"))
        self.db.commit()
        self.db.add(Caja(operador="Dos", servicio="Ba\u00f1o 1", estado="abierta"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
