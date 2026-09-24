from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite necesita check_same_thread=False porque FastAPI atiende las rutas
# síncronas en un pool de hilos y SQLAlchemy puede reutilizar conexiones.
connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # WAL permite que varias cajas lean/escriban a la vez sobre el mismo
        # archivo; busy_timeout evita errores "database is locked" bajo carga.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
