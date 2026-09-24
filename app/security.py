"""Hash y verificación de contraseñas con la biblioteca estándar (pbkdf2).

No se usan dependencias externas (bcrypt/passlib) para mantener la instalación
simple en Windows. pbkdf2_hmac con SHA-256 y muchas iteraciones es un método
de hashing de contraseñas aceptado y robusto.
"""
import hashlib
import secrets

_ALGO = "pbkdf2_sha256"
_ITERACIONES = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERACIONES)
    return f"{_ALGO}${_ITERACIONES}${salt}${dk.hex()}"


def verify_password(password: str, almacenado: str) -> bool:
    try:
        _algo, iteraciones, salt, hexhash = almacenado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iteraciones))
        return secrets.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False
