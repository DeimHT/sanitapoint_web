"""Actualizacion de main por consulta saliente, con mantenimiento y recuperacion.

Ejecutar solo desde la tarea SYSTEM documentada en GUIA.md. No configura GitHub,
firewall ni tareas por su cuenta. La configuracion vive fuera del repositorio.
"""
import argparse
from contextlib import closing
import ipaddress
import json
import logging
import os
from pathlib import Path
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlparse
from urllib.request import urlopen

if __package__:
    from .respaldar_bd import respaldar
else:
    from respaldar_bd import respaldar

LOG = logging.getLogger("actualizacion")


def guardar_json(ruta, valor):
    temporal = ruta.with_suffix(ruta.suffix + ".nuevo")
    temporal.write_text(json.dumps(valor, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


def cajas_abiertas(ruta):
    with closing(sqlite3.connect(ruta.resolve(strict=True).as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute("SELECT COUNT(*) FROM cajas WHERE estado = 'abierta'").fetchone()[0]


def restaurar_bd(copia, destino):
    # La API de SQLite reemplaza el contenido y maneja sus propios WAL/SHM.
    # Solo se llama con mantenimiento activo y el servidor detenido.
    with closing(sqlite3.connect(copia.as_uri() + "?mode=ro", uri=True)) as origen:
        with closing(sqlite3.connect(destino, timeout=30)) as db:
            origen.backup(db)
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("No se pudo verificar la base restaurada")


class Actualizador:
    def __init__(self, config):
        self.config = config
        self.repo = Path(config["repositorio"]).resolve()
        self.ops = Path(config["operaciones"]).resolve()
        self.runtime = self.ops / "runtime.json"
        self.marcador = self.repo / "data" / "actualizacion.lock"
        self.base = self.repo / "data" / "sanitapoint.db"
        self.backups = Path(config["respaldos"]).resolve()
        self.git_exe = config["git"]
        self.url = config["salud"].rstrip("/")
        url = urlparse(self.url)
        if url.scheme != "http" or url.path != "/api/salud" or not ipaddress.ip_address(url.hostname).is_private:
            raise ValueError("La URL de salud debe ser http://IPv4-interna:8000/api/salud")
        self.host, self.port = url.hostname, url.port or 80
        self.ops.mkdir(parents=True, exist_ok=True)
        # Ignora perfiles SSH personales y exige la clave/known_hosts indicados.
        self.ssh = shlex.join([str(Path(config["ssh"]).as_posix()), "-F",
                               str(Path(config["ssh_config"]).as_posix())])
        self.env = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
                    "GIT_SSH_COMMAND": self.ssh, "GIT_SSH_VARIANT": "ssh"}

    def ejecutar(self, argumentos, timeout=600, **kwargs):
        resultado = subprocess.run(argumentos, cwd=self.repo, env=self.env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=timeout, **kwargs)
        if resultado.returncode:
            raise RuntimeError(f"Fallo {Path(argumentos[0]).name}: {resultado.stderr[-4000:]}")
        return resultado.stdout.strip()

    def git(self, *args):
        return self.ejecutar([self.git_exe, "-c", f"core.sshCommand={self.ssh}", *args])

    def tarea(self, operacion):
        # El nombre llega como variable de entorno, nunca como codigo PowerShell.
        codigo = {"detener": "Disable-ScheduledTask -TaskName $env:SANITA_TAREA | Out-Null; if ((Get-ScheduledTask -TaskName $env:SANITA_TAREA).State -eq 'Running') { Stop-ScheduledTask -TaskName $env:SANITA_TAREA }",
                  "iniciar": "Enable-ScheduledTask -TaskName $env:SANITA_TAREA | Out-Null; Start-ScheduledTask -TaskName $env:SANITA_TAREA"}[operacion]
        entorno = {**self.env, "SANITA_TAREA": self.config.get("tarea", "SanitaPoint-Servidor")}
        proceso = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                  "$ErrorActionPreference = 'Stop'; " + codigo], env=entorno,
                                 capture_output=True, text=True, timeout=60)
        if proceso.returncode:
            raise RuntimeError("No se pudo " + operacion + " la tarea: " + proceso.stderr)

    def salud(self):
        try:
            with urlopen(self.url, timeout=3) as respuesta:
                return json.load(respuesta)
        except (OSError, ValueError):
            return None

    def esperar(self, condicion, mensaje, segundos=90):
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if condicion():
                return
            time.sleep(1)
        raise RuntimeError(mensaje)

    def sin_puerto(self):
        try:
            with socket.create_connection((self.host, self.port), timeout=1):
                return False
        except OSError:
            return True

    def detener(self):
        self.tarea("detener")
        self.esperar(self.sin_puerto, "El proceso sigue escuchando. No se modifico el codigo.")

    def iniciar(self, revision):
        self.tarea("iniciar")
        def lista():
            estado = self.salud() or {}
            return (estado.get("ok") and estado.get("revision") == revision and
                    estado.get("mantenimiento") and estado.get("sqlite_predeterminada"))
        self.esperar(lista, "La version no supero la comprobacion de arranque", segundos=120)

    def preparar_entorno(self, revision):
        carpeta = self.ops / "entornos" / revision
        python = carpeta / "Scripts" / "python.exe"
        self.ejecutar([getattr(sys, "_base_executable", sys.executable), "-m", "venv", str(carpeta)])
        requisitos = carpeta / "requirements-version.txt"
        requisitos.write_text(self.git("show", f"{revision}:requirements.txt") + "\n", encoding="utf-8")
        self.ejecutar([str(python), "-m", "pip", "install", "-r", str(requisitos)])
        self.ejecutar([str(python), "-m", "pip", "check"])
        return str(python)

    def comprobar_checkout(self):
        if self.git("branch", "--show-current") != "main":
            raise RuntimeError("La instalacion debe estar en la rama main")
        if self.git("status", "--porcelain", "--untracked-files=normal"):
            raise RuntimeError("Hay cambios locales. Se conservan y se cancela la actualizacion.")
        remoto = self.git("remote", "get-url", "origin")
        if not remoto.startswith("git@github.com:") or any(c.isspace() for c in remoto):
            raise RuntimeError("origin debe usar git@github.com:PROPIETARIO/REPOSITORIO.git")

    def validar_archivos(self, revision):
        for archivo in self.git("ls-tree", "-r", "--name-only", revision).splitlines():
            nombre = archivo.lower().split("/")[0]
            if (nombre in {"data", "logs", "respaldos", "backups", ".env", ".venv"} or
                    nombre.startswith(".venv-") or (nombre.startswith(".env.") and nombre != ".env.example")):
                raise RuntimeError(f"La version intenta versionar datos locales protegidos: {archivo}")

    def actualizar(self):
        if self.marcador.exists():
            raise RuntimeError("Hay un mantenimiento pendiente; requiere revision manual")
        self.comprobar_checkout()
        anterior = self.git("rev-parse", "HEAD")
        self.git("fetch", "--no-tags", "origin", "main")
        nueva = self.git("rev-parse", "FETCH_HEAD")
        if anterior == nueva:
            LOG.info("main sin cambios")
            return "sin cambios"
        self.git("merge-base", "--is-ancestor", anterior, nueva)
        fallida = self.ops / "version-fallida.json"
        if fallida.exists() and json.loads(fallida.read_text(encoding="utf-8"))["revision"] == nueva:
            LOG.warning("La version %s fallo antes; no se reintenta automaticamente", nueva)
            return "version fallida"
        self.validar_archivos(nueva)
        if cajas_abiertas(self.base):
            LOG.info("Version %s pendiente: hay cajas abiertas", nueva)
            return "pendiente"
        previo = json.loads(self.runtime.read_text(encoding="utf-8-sig"))
        if previo.get("revision") != anterior:
            raise RuntimeError("runtime.json no coincide con HEAD; revisar instalacion")
        entorno = self.preparar_entorno(nueva)
        if self.git("rev-parse", "HEAD") != anterior:
            raise RuntimeError("HEAD cambio durante la preparacion; se cancela")
        self.comprobar_checkout()
        self.marcador.parent.mkdir(exist_ok=True)
        with self.marcador.open("x", encoding="utf-8") as archivo:
            json.dump({"anterior": anterior, "nueva": nueva}, archivo)
        conservar = False
        detenido = False
        copia = None
        try:
            guardar_json(self.ops / "ultimo-despliegue.json", {
                "anterior": anterior, "nueva": nueva, "respaldo": None,
                "runtime_anterior": previo, "fase": "mantenimiento"})
            def drenada():
                estado = self.salud() or {}
                return (estado.get("ok") and estado.get("mantenimiento") and
                        estado.get("sqlite_predeterminada") and estado.get("solicitudes_en_curso") == 0 and
                        estado.get("revision") == anterior)
            self.esperar(drenada, "No se pudo drenar el servidor sin interrumpir solicitudes")
            if cajas_abiertas(self.base):
                LOG.info("Se abrio una caja durante la preparacion. Se pospone la actualizacion.")
                return "pendiente"
            detenido = True
            self.detener()
            if cajas_abiertas(self.base):
                self.iniciar(anterior)
                return "pendiente"
            copia = respaldar(self.base, self.backups)
            guardar_json(self.ops / "ultimo-despliegue.json", {
                "anterior": anterior, "nueva": nueva, "respaldo": str(copia), "runtime_anterior": previo, "fase": "respaldo listo"})
            self.git("merge", "--ff-only", "--no-edit", nueva)
            guardar_json(self.runtime, {"python": entorno, "revision": nueva})
            self.iniciar(nueva)
            LOG.info("Version %s aplicada. Respaldo previo: %s", nueva, copia)
            return "actualizado"
        except Exception:
            if detenido:
                try:
                    guardar_json(fallida, {"revision": nueva, "anterior": anterior})
                except OSError:
                    LOG.exception("No se pudo registrar la version fallida")

                try:
                    self.detener()
                    # --keep conserva cambios locales si alguien intervino y aborta ante conflictos.
                    self.git("reset", "--keep", anterior)
                    if copia:
                        restaurar_bd(copia, self.base)
                    guardar_json(self.runtime, previo)
                    self.iniciar(anterior)
                    LOG.exception("Actualizacion fallida; se recupero la version anterior")
                except Exception:
                    conservar = True
                    LOG.exception("RECUPERACION MANUAL NECESARIA. Se conserva el mantenimiento.")
            raise
        finally:
            if not conservar:
                self.marcador.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    ops = Path(config["operaciones"])
    ops.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=ops / "actualizaciones.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    cerrojo = ops / "actualizador.lock"
    try:
        descriptor = os.open(cerrojo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        LOG.error("Ya hay una actualizacion o un bloqueo pendiente de revisar")
        return 1
    try:
        os.close(descriptor)
        Actualizador(config).actualizar()
        return 0
    except Exception:
        LOG.exception("No se aplico la nueva version")
        return 1
    finally:
        cerrojo.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
