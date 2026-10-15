import asyncio
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.mantenimiento import MantenimientoMiddleware
from scripts.actualizar_servidor import Actualizador, guardar_json


class ActualizacionTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.fuente = self.raiz / "fuente"
        self.repo = self.raiz / "instalado"
        self.ops = self.raiz / "operaciones"
        self.ops.mkdir()
        self.git_exe = shutil.which("git")
        self.assertIsNotNone(self.git_exe)
        self.fuente.mkdir()
        self.cmd(self.fuente, "init", "--initial-branch=main")
        (self.fuente / ".gitignore").write_text("data/\n.env\n", encoding="utf-8")
        (self.fuente / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (self.fuente / "version.txt").write_text("anterior", encoding="utf-8")
        self.commit()
        self.cmd(self.raiz, "clone", str(self.fuente), str(self.repo))
        self.anterior = self.cmd(self.repo, "rev-parse", "HEAD")
        (self.fuente / "version.txt").write_text("nueva", encoding="utf-8")
        self.commit()
        self.nueva = self.cmd(self.fuente, "rev-parse", "HEAD")
        config = {"repositorio": str(self.repo), "operaciones": str(self.ops),
                  "respaldos": str(self.raiz / "copias"), "git": self.git_exe,
                  "ssh": "C:/Windows/System32/OpenSSH/ssh.exe", "ssh_config": str(self.ops / "ssh_config"),
                  "salud": "http://192.168.10.10:8000/api/salud"}
        self.u = Actualizador(config)
        self.u.base.parent.mkdir()
        with closing(sqlite3.connect(self.u.base)) as db:
            db.execute("CREATE TABLE cajas (estado TEXT)")
            db.execute("INSERT INTO cajas VALUES ('cerrada')")
            db.commit()
        (self.repo / ".env").write_text("SECRETO=se-conserva", encoding="utf-8")
        guardar_json(self.u.runtime, {"python": "python-anterior", "revision": self.anterior})
        # Solo el transporte de Git usa un repositorio local en lugar de GitHub.
        git_real = self.u.git
        def git(*args):
            if args == ("remote", "get-url", "origin"):
                return "git@github.com:prueba/privado.git"
            return git_real(*args)
        self.u.git = git
        self.u.preparar_entorno = lambda revision: "python-nuevo"
        self.encendido = True
        self.falla_nueva = False
        self.operaciones = []
        def tarea(operacion):
            self.operaciones.append(operacion)
            self.encendido = operacion == "iniciar"
            runtime = json.loads(self.u.runtime.read_text())
            if self.encendido and runtime["revision"] == self.nueva and self.falla_nueva:
                with closing(sqlite3.connect(self.u.base)) as db:
                    db.execute("ALTER TABLE cajas ADD COLUMN cambio INTEGER")
        self.u.tarea = tarea
        self.u.sin_puerto = lambda: not self.encendido
        def salud():
            runtime = json.loads(self.u.runtime.read_text())
            return {"ok": self.encendido and not (self.falla_nueva and runtime["revision"] == self.nueva),
                    "revision": runtime["revision"], "mantenimiento": self.u.marcador.exists(),
                    "solicitudes_en_curso": 0, "sqlite_predeterminada": True}
        self.u.salud = salud
        def esperar(condicion, mensaje, segundos=90):
            if not condicion():
                raise RuntimeError(mensaje)
        self.u.esperar = esperar

    def cmd(self, carpeta, *args):
        resultado = subprocess.run([self.git_exe, *args], cwd=carpeta, capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        return resultado.stdout.strip()

    def commit(self):
        self.cmd(self.fuente, "add", ".")
        self.cmd(self.fuente, "-c", "user.name=Prueba", "-c", "user.email=prueba@example.test", "commit", "-m", "version")

    def test_actualiza_main_preserva_datos_y_respalda(self):
        self.assertEqual(self.u.actualizar(), "actualizado")
        self.assertEqual(self.cmd(self.repo, "rev-parse", "HEAD"), self.nueva)
        self.assertEqual((self.repo / ".env").read_text(), "SECRETO=se-conserva")
        self.assertTrue(self.encendido)
        self.assertFalse(self.u.marcador.exists())
        self.assertEqual(len(list(self.u.backups.glob("*.db"))), 1)
        self.assertEqual(self.u.actualizar(), "sin cambios")

    def test_pospone_con_caja_abierta_sin_detener_servidor(self):
        with closing(sqlite3.connect(self.u.base)) as db:
            db.execute("UPDATE cajas SET estado='abierta'")
            db.commit()
        self.assertEqual(self.u.actualizar(), "pendiente")
        self.assertEqual(self.operaciones, [])
        self.assertEqual(self.cmd(self.repo, "rev-parse", "HEAD"), self.anterior)

    def test_revisa_de_nuevo_si_abrieron_durante_preparacion(self):
        def preparar(revision):
            with closing(sqlite3.connect(self.u.base)) as db:
                db.execute("UPDATE cajas SET estado='abierta'")
                db.commit()
            return "python-nuevo"
        self.u.preparar_entorno = preparar
        self.assertEqual(self.u.actualizar(), "pendiente")
        self.assertEqual(self.operaciones, [])
        self.assertFalse(self.u.marcador.exists())

    def test_fallo_arranque_recupera_codigo_entorno_y_base(self):
        self.falla_nueva = True
        with self.assertRaisesRegex(RuntimeError, "arranque"):
            self.u.actualizar()
        self.assertEqual(self.cmd(self.repo, "rev-parse", "HEAD"), self.anterior)
        self.assertEqual(json.loads(self.u.runtime.read_text())["python"], "python-anterior")
        with closing(sqlite3.connect(self.u.base)) as db:
            self.assertEqual([r[1] for r in db.execute("PRAGMA table_info(cajas)")], ["estado"])
        self.assertTrue(self.encendido)
        self.assertFalse(self.u.marcador.exists())
        self.assertEqual(self.u.actualizar(), "version fallida")

    def test_conserva_mantenimiento_si_recuperacion_falla(self):
        self.falla_nueva = True
        tarea = self.u.tarea
        def fallar(operacion):
            runtime = json.loads(self.u.runtime.read_text())
            if operacion == "iniciar" and runtime["revision"] == self.anterior:
                raise RuntimeError("fallo de tarea")
            tarea(operacion)
        self.u.tarea = fallar
        with self.assertRaises(RuntimeError):
            self.u.actualizar()
        self.assertTrue(self.u.marcador.exists())
        self.assertFalse(self.encendido)

    def test_no_sobrescribe_ediciones_locales(self):
        (self.repo / "version.txt").write_text("cambio local")
        with self.assertRaisesRegex(RuntimeError, "cambios locales"):
            self.u.actualizar()
        self.assertEqual((self.repo / "version.txt").read_text(), "cambio local")
        self.assertEqual(self.operaciones, [])

    def test_rechaza_commits_que_versionan_datos_privados(self):
        (self.fuente / "data").mkdir()
        (self.fuente / "data" / "ventas.txt").write_text("privado")
        self.cmd(self.fuente, "add", "-f", "data/ventas.txt")
        self.cmd(self.fuente, "-c", "user.name=Prueba", "-c", "user.email=prueba@example.test", "commit", "-m", "datos")
        with self.assertRaisesRegex(RuntimeError, "protegidos"):
            self.u.actualizar()
        self.assertEqual(self.operaciones, [])

    def test_no_despliega_si_no_puede_drenar_solicitudes(self):
        salud = self.u.salud
        self.u.salud = lambda: {**salud(), "solicitudes_en_curso": 1}
        with self.assertRaisesRegex(RuntimeError, "drenar"):
            self.u.actualizar()
        self.assertEqual(self.operaciones, [])
        self.assertFalse(self.u.marcador.exists())


class MantenimientoTests(unittest.TestCase):
    def test_barrera_bloquea_nuevas_solicitudes_y_espera_respuestas_activas(self):
        async def escenario(marcador):
            iniciada, terminar = asyncio.Event(), asyncio.Event()
            app = SimpleNamespace(state=SimpleNamespace())
            async def interna(scope, receive, send):
                if scope["path"] == "/lenta":
                    iniciada.set()
                    await terminar.wait()
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"OK"})
            middleware = MantenimientoMiddleware(interna)
            async def llamada(path):
                mensajes = []
                async def receive():
                    return {"type": "http.request", "body": b""}
                async def send(message):
                    mensajes.append(message)
                await middleware({"type": "http", "path": path, "app": app}, receive, send)
                return mensajes[0]["status"]
            with patch("app.services.mantenimiento.archivo_mantenimiento", return_value=marcador):
                activa = asyncio.create_task(llamada("/lenta"))
                await iniciada.wait()
                marcador.touch()
                self.assertEqual(app.state.solicitudes_en_curso, 1)
                self.assertEqual(await llamada("/api/caja/abrir"), 503)
                self.assertEqual(await llamada("/api/salud"), 200)
                self.assertEqual(app.state.solicitudes_en_curso, 1)
                terminar.set()
                self.assertEqual(await activa, 200)
                self.assertEqual(app.state.solicitudes_en_curso, 0)
        with tempfile.TemporaryDirectory() as directorio:
            asyncio.run(escenario(Path(directorio) / "mantenimiento"))
