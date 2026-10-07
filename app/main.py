import os
from typing import get_args

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  — registra las tablas en Base.metadata
from app import permissions as perms
from app.config import SECRET_KEY, settings
from app.database import Base, SessionLocal, engine, get_db
from app.schemas import ServicioLogin
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
    nuevas = {"cajas": {
        "servicio": "VARCHAR",
        "nro_apertura": "INTEGER", "nro_cierre": "INTEGER",
        "torniquete_bano_inicial": "INTEGER", "torniquete_ducha_inicial": "INTEGER",
        "cuenta_id": "INTEGER REFERENCES cuentas(id)",
        "torniquete_bano_final": "INTEGER", "torniquete_ducha_final": "INTEGER",
    }, "ventas": {"tipo_acceso": "VARCHAR", "kame_documento_id": "VARCHAR"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for tabla, columnas in nuevas.items():
            if not insp.has_table(tabla):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla)}
            for col, tipo in columnas.items():
                if col not in existentes:
                    conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}"))


def _asignar_cajas_anteriores(db: Session):
    """Asigna turnos antiguos solo cuando el operador identifica una única cuenta."""
    cuentas = db.query(models.Cuenta).all()
    for caja_anterior in db.query(models.Caja).filter(models.Caja.cuenta_id.is_(None)).all():
        coincidencias = [c for c in cuentas if caja_anterior.operador in
                         (c.username, c.nombre.strip() if c.nombre else "")]
        if len(coincidencias) == 1:
            cuenta_id = coincidencias[0].id
            if caja_anterior.estado == "abierta" and db.query(models.Caja).filter(
                models.Caja.cuenta_id == cuenta_id, models.Caja.estado == "abierta"
            ).first():
                continue
            caja_anterior.cuenta_id = cuenta_id
    db.commit()


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
        _asignar_cajas_anteriores(db)
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
async def login_page(request: Request, db: Session = Depends(get_db)):
    # Si ya hay sesión válida, ir directo al inicio del rol.
    cuenta = _cuenta_actual(request)
    if cuenta and cuenta.activo:
        return RedirectResponse(_home_path(cuenta), status_code=302)
    cuentas = db.query(models.Cuenta).order_by(models.Cuenta.username).all()
    return templates.TemplateResponse(request, "login.html", {
        "cuentas": cuentas, "servicios": get_args(ServicioLogin),
    })
