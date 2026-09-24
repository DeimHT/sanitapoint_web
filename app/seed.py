"""Carga configuración y servicios por defecto si las tablas están vacías."""
from sqlalchemy.orm import Session

from app.models import Configuracion, Cuenta, Servicio
from app.security import hash_password

DEFAULTS_CONFIG = {
    "empresa_nombre": "Servicios Sanitarios",
    "empresa_rut": "00.000.000-0",
    "empresa_direccion": "Dirección no configurada",
    "empresa_telefono": "",
    "ticket_pie": "¡Gracias por su visita!",
    "impresora_tipo": "ninguna",  # ninguna | red | usb
    "impresora_ip": "",
    "impresora_puerto": "9100",
    "pases_por_dia": "1",
}

DEFAULTS_SERVICIOS = [
    ("Uso de Baño", 500),
    ("Ducha", 2000),
]


def run_seed(db: Session) -> None:
    for clave, valor in DEFAULTS_CONFIG.items():
        if not db.get(Configuracion, clave):
            db.add(Configuracion(clave=clave, valor=valor))

    if db.query(Servicio).count() == 0:
        for nombre, precio in DEFAULTS_SERVICIOS:
            db.add(Servicio(nombre=nombre, precio=precio))

    # Cuenta administradora inicial (cambiar la contraseña tras el primer ingreso).
    if db.query(Cuenta).count() == 0:
        db.add(Cuenta(
            username="admin",
            password_hash=hash_password("admin123"),
            nombre="Administrador",
            rol="administrador",
            activo=True,
        ))

    db.commit()
