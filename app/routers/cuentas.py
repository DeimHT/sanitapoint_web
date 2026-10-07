"""Gestión de cuentas de acceso (login). Contabilidad y Administrador.

Salvaguarda contra escalada de privilegios: solo un administrador puede crear o
modificar cuentas con rol administrador. Contabilidad puede administrar las
demás cuentas y restablecer contraseñas, pero no otorgarse el rol admin.
"""
import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_cuenta, require_cap
from app.models import Cuenta
from app.permissions import GESTION_CUENTAS, ROLES
from app.schemas import CuentaCrearIn, CuentaEditarIn, CuentaOut
from app.security import hash_password

router = APIRouter(prefix="/api/cuentas", tags=["cuentas"],
                   dependencies=[Depends(require_cap(GESTION_CUENTAS))])


def _admins_activos(db: Session, excluir_id: int | None = None) -> int:
    q = db.query(Cuenta).filter(Cuenta.rol == "administrador", Cuenta.activo.is_(True))
    if excluir_id is not None:
        q = q.filter(Cuenta.id != excluir_id)
    return q.count()


@router.get("", response_model=list[CuentaOut])
def listar_cuentas(db: Session = Depends(get_db)):
    return db.query(Cuenta).order_by(Cuenta.username).all()


@router.get("/plantilla")
def plantilla_cuentas():
    wb = Workbook()
    ws = wb.active
    ws.title = "Cuentas"
    ws.append(["usuario", "nombre", "rol", "contrasena"])
    for col, width in (("A", 24), ("B", 32), ("C", 24), ("D", 28)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ayuda = wb.create_sheet("Instrucciones")
    for text in ("Completa la hoja Cuentas. Máximo 500 cuentas por archivo.",
                 "Roles: cajero, supervisor, contabilidad, administrador.",
                 "Usuario y contraseña son obligatorios. No se modifican cuentas existentes.",
                 "Solo un administrador puede importar cuentas administradoras.",
                 "Escribe las contraseñas como texto; el sistema no las mostrará en la vista previa."):
        ayuda.append([text])
    ayuda.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla_cuentas.xlsx"'})


def validar_importacion(contenido, db, actual):
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 10 * 1024 * 1024:
                raise ValueError("Archivo demasiado grande")
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=False)
    except Exception:
        raise HTTPException(400, "No se pudo leer el Excel. Usa la plantilla .xlsx del sistema.")
    try:
        ws = wb["Cuentas"] if "Cuentas" in wb.sheetnames else wb.active
        rows = ws.iter_rows()
        headers = [str(c.value or "").strip().lower() for c in next(rows, [])]
        if headers[:4] != ["usuario", "nombre", "rol", "contrasena"]:
            raise HTTPException(400, "Las columnas deben ser: usuario, nombre, rol, contrasena.")
        existentes = {c[0] for c in db.query(Cuenta.username).all()}
        seen, records, errors = set(), [], []
        for number, cells in enumerate(rows, 2):
            if number > 1001:
                raise HTTPException(400, "La hoja contiene demasiadas filas. Máximo 500 cuentas.")
            if all(c.value is None for c in cells):
                continue
            if len(records) >= 500:
                raise HTTPException(400, "Máximo 500 cuentas por importación.")
            values = [c.value for c in cells[:4]]
            values += [None] * (4 - len(values))
            username, nombre, rol, password = [str(v or "").strip() for v in values]
            rol = rol.lower()
            problem = []
            if any(c.data_type == "f" for c in cells[:4]):
                problem.append("Usa valores de texto, sin fórmulas")
            if not username or not password:
                problem.append("Usuario y contraseña son obligatorios")
            if len(username) > 100 or len(nombre) > 200 or len(password) > 256:
                problem.append("Usuario, nombre o contraseña demasiado largos")
            if username in existentes or username in seen:
                problem.append("El usuario ya existe o está repetido en el archivo")
            if rol not in ROLES:
                problem.append("Rol inválido")
            elif rol == "administrador" and actual.rol != "administrador":
                problem.append("Solo un administrador puede crear cuentas administradoras")
            seen.add(username)
            if problem:
                errors.append({"fila": number, "usuario": username, "mensaje": ". ".join(problem)})
            records.append(dict(username=username, nombre=nombre, rol=rol, password=password))
        if not records:
            raise HTTPException(400, "El archivo no contiene cuentas.")
        return records, errors
    finally:
        wb.close()


@router.post("/importar")
async def importar_cuentas(archivo: UploadFile = File(...), confirmar: bool = False,
                          db: Session = Depends(get_db), actual: Cuenta = Depends(get_current_cuenta)):
    contenido = await archivo.read(1024 * 1024 + 1)
    if len(contenido) > 1024 * 1024:
        raise HTTPException(400, "El Excel no debe superar 1 MB.")
    records, errors = validar_importacion(contenido, db, actual)
    preview = [{"usuario": r["username"], "nombre": r["nombre"], "rol": r["rol"]} for r in records]
    if errors or not confirmar:
        return {"ok": not errors, "cuentas": preview, "errores": errors, "creadas": 0}
    try:
        for record in records:
            db.add(Cuenta(username=record["username"], nombre=record["nombre"], rol=record["rol"],
                          password_hash=hash_password(record["password"]), activo=True))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Un usuario ya fue creado por otra operación. Vuelve a validar el archivo.")
    except Exception:
        db.rollback()
        raise
    return {"ok": True, "creadas": len(records), "errores": [], "cuentas": preview}


@router.post("", response_model=CuentaOut)
def crear_cuenta(body: CuentaCrearIn, db: Session = Depends(get_db),
                 actual: Cuenta = Depends(get_current_cuenta)):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(400, "Usuario y contraseña son obligatorios")
    if body.rol not in ROLES:
        raise HTTPException(400, "Rol inválido")
    if body.rol == "administrador" and actual.rol != "administrador":
        raise HTTPException(403, "Solo un administrador puede crear cuentas administradoras")
    if db.query(Cuenta).filter(Cuenta.username == username).first():
        raise HTTPException(400, "Ya existe una cuenta con ese usuario")
    cuenta = Cuenta(
        username=username,
        password_hash=hash_password(body.password),
        nombre=body.nombre.strip(),
        rol=body.rol,
        activo=True,
    )
    db.add(cuenta)
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.put("/{cuenta_id}", response_model=CuentaOut)
def editar_cuenta(cuenta_id: int, body: CuentaEditarIn, db: Session = Depends(get_db),
                  actual: Cuenta = Depends(get_current_cuenta)):
    cuenta = db.get(Cuenta, cuenta_id)
    if not cuenta:
        raise HTTPException(404, "Cuenta no encontrada")
    if body.rol not in ROLES:
        raise HTTPException(400, "Rol inválido")

    # Solo un administrador puede tocar cuentas admin o asignar el rol admin.
    if actual.rol != "administrador" and (cuenta.rol == "administrador" or body.rol == "administrador"):
        raise HTTPException(403, "Solo un administrador puede gestionar cuentas administradoras")

    # No dejar el sistema sin ningún administrador activo.
    quita_admin = cuenta.rol == "administrador" and (body.rol != "administrador" or not body.activo)
    if quita_admin and _admins_activos(db, excluir_id=cuenta.id) == 0:
        raise HTTPException(400, "Debe quedar al menos un administrador activo")

    cuenta.nombre = body.nombre.strip()
    cuenta.rol = body.rol
    cuenta.activo = body.activo
    if body.password:
        cuenta.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.post("/{cuenta_id}/desactivar")
def desactivar_cuenta(cuenta_id: int, db: Session = Depends(get_db),
                      actual: Cuenta = Depends(get_current_cuenta)):
    cuenta = db.get(Cuenta, cuenta_id)
    if not cuenta:
        raise HTTPException(404, "Cuenta no encontrada")
    if cuenta.id == actual.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta")
    if actual.rol != "administrador" and cuenta.rol == "administrador":
        raise HTTPException(403, "Solo un administrador puede desactivar cuentas administradoras")
    if cuenta.rol == "administrador" and _admins_activos(db, excluir_id=cuenta.id) == 0:
        raise HTTPException(400, "Debe quedar al menos un administrador activo")
    cuenta.activo = False
    db.commit()
    return {"ok": True}
