import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts.respaldar_bd import respaldar
from scripts import servidor_local


class RespaldoServidorTests(unittest.TestCase):
    def test_respaldo_en_caliente_incluye_wal_y_es_restaurable(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            origen = raiz / "original.db"
            with closing(sqlite3.connect(origen)) as activa:
                activa.execute("PRAGMA journal_mode=WAL")
                activa.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, monto INTEGER)")
                activa.execute("INSERT INTO ventas (monto) VALUES (500)")
                activa.commit()
                self.assertTrue(Path(str(origen) + "-wal").exists())
                copia = respaldar(origen, raiz / "copias")
                with closing(sqlite3.connect(copia)) as restaurada:
                    self.assertEqual(restaurada.execute("SELECT monto FROM ventas").fetchall(), [(500,)])
                    self.assertEqual(restaurada.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                activa.execute("INSERT INTO ventas (monto) VALUES (700)")
                activa.commit()
                segunda = respaldar(origen, raiz / "copias")
                self.assertNotEqual(copia, segunda)
                with closing(sqlite3.connect(segunda)) as restaurada:
                    self.assertEqual(restaurada.execute("SELECT COUNT(*) FROM ventas").fetchone(), (2,))
                self.assertFalse(list((raiz / "copias").glob("*.parcial")))

    def test_origen_inexistente_no_crea_base_vacia(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            with self.assertRaises(FileNotFoundError):
                respaldar(raiz / "ausente.db", raiz / "copias")
            self.assertFalse((raiz / "ausente.db").exists())

    def test_base_invalida_no_publica_respaldo(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            origen = raiz / "rota.db"
            origen.write_text("no es una base SQLite")
            with self.assertRaises(sqlite3.DatabaseError):
                respaldar(origen, raiz / "copias")
            self.assertEqual(list((raiz / "copias").iterdir()), [])

    def test_comando_respaldo_devuelve_estado_de_exito_y_archivo(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            origen = raiz / "original.db"
            with closing(sqlite3.connect(origen)) as db:
                db.execute("CREATE TABLE prueba (id INTEGER)")
            resultado = subprocess.run([sys.executable, "scripts/respaldar_bd.py", "--origen", str(origen),
                                       "--destino", str(raiz / "copias")], capture_output=True, text=True)
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            self.assertIn("Respaldo verificado", resultado.stdout)
            self.assertEqual(len(list((raiz / "copias").glob("*.db"))), 1)

    def test_arranque_usa_ip_interna_y_propaga_fallo_a_windows(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            with patch.object(servidor_local, "ROOT", raiz), \
                 patch.object(sys, "argv", ["servidor_local.py", "--host", "192.168.10.10"]), \
                 patch.object(servidor_local.subprocess, "call", return_value=1) as iniciar:
                self.assertEqual(servidor_local.main(), 1)
                args = iniciar.call_args.args[0]
                self.assertEqual(args, [sys.executable, "-m", "uvicorn", "app.main:app", "--host",
                                        "192.168.10.10", "--port", "8000", "--reload", "--reload-dir", str(raiz / "app")])
                self.assertEqual(iniciar.call_args.kwargs["cwd"], raiz)
                self.assertEqual(len(list((raiz / "logs").glob("servidor-*.log"))), 1)

    def test_recarga_se_puede_desactivar(self):
        with tempfile.TemporaryDirectory() as directorio:
            with patch.object(servidor_local, "ROOT", Path(directorio)), \
                 patch.object(sys, "argv", ["servidor_local.py", "--host", "127.0.0.1", "--no-reload"]), \
                 patch.object(servidor_local.subprocess, "call", return_value=0) as iniciar:
                self.assertEqual(servidor_local.main(), 0)
                comando = iniciar.call_args.args[0]
                self.assertNotIn("--reload", comando)
                self.assertEqual(comando[-2:], ["--workers", "1"])
