# SanitaPoint Web 🚿🚽

Sistema POS web para servicios sanitarios (Uso de Baño / Ducha) con boleta
electrónica vía KAME, apertura/cierre/retiro de caja, y reportes de ventas en
PDF y Excel.

**Sin Docker. Base de datos SQLite (un solo archivo).** El servidor se levanta
con un doble clic en el equipo central; cada caja se conecta abriendo el
navegador en `http://<ip-servidor>:8000`. No se instala nada en las cajas
aparte de un navegador.

---

## Instalación rápida (Windows — equipo servidor)

1. Instala **Python 3.11 o superior** desde <https://www.python.org/downloads/>.
   ⚠️ Marca la casilla **"Add Python to PATH"** durante la instalación.
2. Copia la carpeta `sanitapoint_web` al equipo que será el servidor.
3. Haz **doble clic en `iniciar_servidor.bat`**.
   - La **primera vez** instala todo automáticamente (tarda unos minutos).
   - Las siguientes veces solo arranca el servidor.
4. La ventana te mostrará la dirección que deben usar las cajas, por ejemplo
   `http://192.168.1.10:8000`. Anótala.

En cada **caja**: abre el navegador en esa dirección (puedes crear un acceso
directo). Listo.

Para **apagar** el servidor: cierra la ventana negra del `.bat`.

> En macOS/Linux usa `iniciar_servidor.command` (doble clic) en vez del `.bat`.

---

## Acceso y seguridad

El sistema pide **usuario y contraseña**. Hay cuatro grupos (roles):

| Rol | Puede |
|---|---|
| **Cajero** | Emitir boletas, abrir caja (Nro de torniquete/aperturas) y cerrar su turno |
| **Supervisor** | Retiros de caja |
| **Contabilidad** | Ver informes de ventas y cierres; administrar cuentas/claves |
| **Administrador** | Acceso completo a tarifas, impresora y prueba de conexión KAME |

Cada usuario ve en el menú solo lo que su rol permite. Solo un administrador puede
crear o modificar cuentas administradoras.

**Cuenta inicial** (creada automáticamente la primera vez):

| Usuario | Contraseña |
|---|---|
| `admin` | `admin123` |

⚠️ **Cambia esta contraseña tras el primer ingreso**: entra como `admin` →
pestaña **Cuentas** → Editar → escribe una nueva contraseña. Desde ahí también
creas las cuentas de los operadores.

Las sesiones se mantienen con una cookie firmada; la clave de firma se guarda en
`data/secret_key.txt` (no la borres: si se pierde, todos deben volver a ingresar).

---

## ¿Dónde quedan los datos?

Todo vive en la carpeta `data/`:
- `data/sanitapoint.db` → la base de datos completa (ventas, caja, usuarios…).
- `data/tickets/` → los PDF de los tickets emitidos.

**Backup = copiar el archivo `data/sanitapoint.db`.** Nada más. (Ver `GUIA.md`
para el detalle de respaldos con el servidor apagado.)

---

## Integración KAME

La integración sigue `sanitapoint/modules/kame_api.py`: obtiene un token en
`POST /oauth/token` y emite en `POST /api/Documento/addVenta`.

La integración se configura exclusivamente con variables `KAME_*` en `.env`
(consulta `.env.example`). Para validar la autenticación sin emitir una boleta,
entra a Configuración y pulsa **Probar conexión a KAME**. La prueba requiere
`KAME_CLIENT_ID` y `KAME_CLIENT_SECRET`; un token Bearer fijo no se marca como
válido sin hacer una operación real contra la API.
El modo **mock** genera folios de prueba sin conexión. En modo real, las
credenciales ausentes o los rechazos generan un error, nunca una simulación.
La venta queda registrada aunque KAME falle y caja recibe el aviso. Ante una
respuesta incierta, verifica en KAME antes de repetir la venta para evitar duplicados.

Como en la integración de escritorio, las líneas usan precios brutos, IVA
con redondeo decimal y `FormaPago = "1"`. El medio de pago del POS se conserva
localmente. El token OAuth se reutiliza dentro de cada operación; no se
comparte entre solicitudes web. No hay reintentos automáticos salvo un 401
con credenciales OAuth. La conexión real debe validarse con la cuenta KAME.

---

## Impresora térmica ESC/POS

En ⚙️ Config → "Ticket e impresora térmica":
- **Ninguna**: el ticket solo se genera como PDF descargable.
- **Red**: IP y puerto (normalmente `9100`) de la impresora térmica de red.
- **USB**: vendor/product ID.

En todos los casos se genera además un PDF de respaldo en `data/tickets/`.

---

## Reportes

Pestaña **📊 Reportes**: por día, por rango de fechas, por servicio y anual.
Cada uno se descarga en **PDF** o **Excel**.

---

## Estructura del proyecto

```
sanitapoint_web/
├── iniciar_servidor.bat       ← ▶ EJECUTABLE (Windows): doble clic para arrancar
├── iniciar_servidor.command   ← equivalente para macOS/Linux
├── app/
│   ├── main.py                 ← app FastAPI; crea las tablas al iniciar
│   ├── config.py                ← ruta de la base SQLite, puerto y clave de sesión
│   ├── database.py               ← conexión SQLite (WAL para multi-caja)
│   ├── models.py                  ← esquema (cuentas, servicios, cajas, ventas, usuarios…)
│   ├── security.py                 ← hash de contraseñas (pbkdf2)
│   ├── deps.py                      ← control de acceso (login / rol admin)
│   ├── seed.py                       ← datos por defecto + admin inicial
│   ├── routers/                       ← endpoints REST (incluye auth y cuentas)
│   ├── services/                       ← KAME, impresión, reportes
│   ├── templates/                       ← páginas web (incluye login y cuentas)
│   └── static/                           ← CSS/JS
├── data/
│   ├── sanitapoint.db          ← la base de datos (se crea sola)
│   └── tickets/                 ← PDFs de tickets
└── requirements.txt
```

Para instalación manual (sin el `.bat`) y detalles de operación, ver
[`GUIA.md`](GUIA.md).
