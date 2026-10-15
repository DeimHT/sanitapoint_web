"""Barrera local de mantenimiento; no expone controles remotos de despliegue."""
import os
from pathlib import Path

from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]


def archivo_mantenimiento():
    return Path(os.environ.get("SANITAPOINT_MANTENIMIENTO", str(ROOT / "data" / "actualizacion.lock")))


class MantenimientoMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/api/salud":
            return await self.app(scope, receive, send)
        if archivo_mantenimiento().exists():
            respuesta = JSONResponse(
                {"detail": "Actualizacion en curso. Espera un momento y recarga la pagina."},
                status_code=503, headers={"Retry-After": "30", "Cache-Control": "no-store"})
            return await respuesta(scope, receive, send)
        estado = scope["app"].state
        estado.solicitudes_en_curso = getattr(estado, "solicitudes_en_curso", 0) + 1
        try:
            await self.app(scope, receive, send)
        finally:
            estado.solicitudes_en_curso -= 1
