from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_cap
from app.permissions import CONFIGURACION
from app.schemas import ConfigIn
from app.services.config_store import get_all_config, set_config
from app.services.kame_client import KameAPI

router = APIRouter(prefix="/api/config", tags=["config"],
                   dependencies=[Depends(require_cap(CONFIGURACION))])


@router.get("")
def leer_config(db: Session = Depends(get_db)):
    # Valores KAME antiguos pueden permanecer en bases existentes, pero no se
    # usan ni se exponen: la única fuente válida es .env/el entorno.
    return {k: v for k, v in get_all_config(db).items() if not k.startswith("kame_")}


@router.put("")
def guardar_config(body: ConfigIn, db: Session = Depends(get_db)):
    for clave, valor in body.valores.items():
        if clave.startswith("kame_"):
            continue  # KAME se administra exclusivamente mediante .env
        set_config(db, clave, valor)
    return {"ok": True}


@router.post("/kame/test")
def probar_kame(db: Session = Depends(get_db)):
    """Valida la autenticación configurada en .env sin emitir documentos."""
    return KameAPI(db).ping()


@router.post("/impresora/test")
def probar_impresora(db: Session = Depends(get_db)):
    from app.services.ticket_printer import imprimir_escpos
    ok, mensaje = imprimir_escpos(
        db, ticket_num="PRUEBA", servicio_nombre="PRUEBA DE IMPRESION - SIN VENTA",
        monto=0, forma_pago="efectivo", folio_kame=None, estado_kame="mock",
        rut_cliente=None, es_pase_libre=False,
    )
    return {"ok": ok, "mensaje": "Prueba enviada a la impresora." if ok else mensaje}


@router.get("/impresoras")
def listar_impresoras():
    from app.services.printer_discovery import detectar_impresoras
    return detectar_impresoras()


@router.get("/lectores")
def listar_lectores():
    from app.services.scanner_discovery import detectar_lectores
    return detectar_lectores()
