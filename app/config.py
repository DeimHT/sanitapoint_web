"""Configuración de entorno (no confundir con la tabla `configuracion` de negocio).

Por defecto usa SQLite: un único archivo local en `data/sanitapoint.db`, sin
necesidad de un servidor de base de datos aparte ni Docker. Se puede sobrescribir
con la variable DATABASE_URL en `.env` si en el futuro se quisiera otro motor.
"""
import os
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (carpeta que contiene `app/`)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "sanitapoint.db")

_SECRET_FILE = os.path.join(DATA_DIR, "secret_key.txt")


def _cargar_o_crear_secret() -> str:
    """Clave para firmar las cookies de sesión. Se genera una vez y se guarda,
    para que las sesiones sobrevivan reinicios del servidor."""
    if os.path.exists(_SECRET_FILE):
        with open(_SECRET_FILE, "r", encoding="utf-8") as f:
            valor = f.read().strip()
            if valor:
                return valor
    valor = secrets.token_hex(32)
    with open(_SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(valor)
    return valor


SECRET_KEY = _cargar_o_crear_secret()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite por defecto (archivo local). Ruta absoluta para que funcione sin
    # importar desde qué carpeta se ejecute el servidor.
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    sanitapoint_host: str = "0.0.0.0"
    sanitapoint_port: int = 8000


settings = Settings()
