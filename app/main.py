import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  — registra las tablas en Base.metadata
from app import permissions as perms
from app.config import SECRET_KEY, settings
from app.database import Base, SessionLocal, engine
from app.routers import auth, caja, config, cuentas, reportes, servicios, usuarios, ventas
from app.seed import run_seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="SanitaPoint Web")

# Cookie de sesión firmada (autenticación). https_only=False porque en la LAN
# el acceso es por http; same_site="lax" es suficiente para este uso.
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY,
                   same_site="lax", https_only=False)

class StaticNoCache(StaticFiles):
    """Sirve estáticos con revalidación: evita que los navegadores de las cajas
    queden con versiones viejas de JS/CSS tras actualizar la app."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", StaticNoCache(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(auth.router)
app.include_router(cuentas.router)
app.include_router(servicios.router)
app.include_router(caja.router)
app.include_router(ventas.router)
app.include_router(usuarios.router)
app.include_router(config.router)
app.include_router(reportes.router)


def _asegurar_columnas():
    """Agrega columnas nuevas a tablas ya existentes (SQLite ADD COLUMN).

    `create_all` crea tablas que faltan pero no altera las que ya existen. Esto
    permite que una base de datos anterior reciba las columnas nuevas sin un
    paso de migración manual.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    nuevas = {"cajas": {"nro_apertura": "INTEGER", "nro_cierre": "INTEGER"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for tabla, columnas in nuevas.items():
            existentes = {c["name"] for c in insp.get_columns(tabla)}
            for col, tipo in columnas.items():
                if col not in existentes:
                    conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}"))


def _migrar_roles():
    """Renombra roles antiguos al nuevo esquema (operador → cajero)."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE cuentas SET rol='cajero' WHERE rol='operador'"))


@app.on_event("startup")
def on_startup():
    # Crea las tablas si no existen (reemplaza a las migraciones Alembic: con
    # SQLite en un solo archivo no hace falta un paso de migración manual).
    Base.metadata.create_all(bind=engine)
    _asegurar_columnas()
    _migrar_roles()
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()


def _cuenta_actual(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None
    db = SessionLocal()
    try:
        return db.get(models.Cuenta, uid)
    finally:
        db.close()


# path -> (template, capacidades que dan acceso a la página)
# Se puede entrar si el rol tiene AL MENOS UNA de esas capacidades.
PAGES = {
    "/": ("venta.html", {perms.EMITIR_BOLETAS}),
    "/caja": ("caja.html", {perms.CAJA_APERTURA, perms.CAJA_CIERRE, perms.CAJA_RETIRO}),
    "/historial": ("historial.html", {perms.VER_HISTORIAL}),
    "/cierres": ("cierres.html", {perms.VER_CIERRES}),
    "/usuarios": ("usuarios.html", {perms.GESTION_CLIENTES}),
    "/reportes": ("reportes.html", {perms.VER_REPORTES}),
    "/config": ("config.html", {perms.CONFIGURACION}),
    "/cuentas": ("cuentas.html", {perms.GESTION_CUENTAS}),
}

# Página de inicio según lo que puede hacer el rol (a dónde llega tras el login).
_HOME_PRIORIDAD = [
    (perms.EMITIR_BOLETAS, "/"),
    (perms.CAJA_RETIRO, "/caja"),
    (perms.VER_REPORTES, "/reportes"),
    (perms.VER_CIERRES, "/cierres"),
    (perms.GESTION_CUENTAS, "/cuentas"),
    (perms.CONFIGURACION, "/config"),
    (perms.VER_HISTORIAL, "/historial"),
]


def _home_path(cuenta) -> str:
    caps = perms.caps_de(cuenta.rol)
    for cap, path in _HOME_PRIORIDAD:
        if cap in caps:
            return path
    return "/login"


def _make_page(path: str, template: str, caps_permitidas: set):
    async def handler(request: Request):
        cuenta = _cuenta_actual(request)
        if not cuenta or not cuenta.activo:
            return RedirectResponse("/login", status_code=302)
        if not (perms.caps_de(cuenta.rol) & caps_permitidas):
            # No puede ver esta página → a su inicio según rol.
            return RedirectResponse(_home_path(cuenta), status_code=302)
        return templates.TemplateResponse(request, template, {})
    app.get(path, include_in_schema=False)(handler)


for path, (template, caps_permitidas) in PAGES.items():
    _make_page(path, template, caps_permitidas)


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    # Si ya hay sesión válida, ir directo al inicio del rol.
    cuenta = _cuenta_actual(request)
    if cuenta and cuenta.activo:
        return RedirectResponse(_home_path(cuenta), status_code=302)
    return templates.TemplateResponse(request, "login.html", {})
