# Guía de SanitaPoint Web — cómo funciona y cómo instalarlo

Documento único con: qué hace la app por dentro, cómo están conectadas sus
piezas, y el paso a paso para instalarla y operarla. **Versión sin Docker, con
base de datos SQLite y ejecutable de arranque.**

---

## 1. ¿Qué es esta app?

Un punto de venta (POS) web para servicios sanitarios ("Uso de Baño" y "Ducha").
Al vender un servicio, la app:

1. Cobra según la tarifa configurada.
2. Emite una boleta electrónica vía KAME (o una simulada si aún no hay
   credenciales — "modo mock").
3. Genera un ticket (PDF siempre; opcionalmente lo imprime en térmica ESC/POS).
4. Registra el movimiento en la caja abierta.

Además: apertura/cierre/retiro de caja, usuarios con "pases libres", y reportes
de ventas (día, rango, servicio, anual) exportables a PDF y Excel.

## 2. Arquitectura: cliente-servidor, sin Docker

```
┌────────────────────────┐        HTTP (red local)        ┌───────────────────────┐
│  Navegador (Caja 1)     │ ─────────────────────────────▶ │   EQUIPO SERVIDOR      │
├────────────────────────┤                                 │   (Windows)            │
│  Navegador (Caja 2)     │ ─────────────────────────────▶ │                        │
├────────────────────────┤                                 │  iniciar_servidor.bat  │
│  Navegador (Caja N)     │ ─────────────────────────────▶ │        │               │
└────────────────────────┘                                 │        ▼               │
                                                            │   uvicorn :8000        │
                                                            │        │               │
                                                            │        ▼               │
                                                            │  data/sanitapoint.db   │
                                                            │  (archivo SQLite)      │
                                                            └───────────────────────┘
```

- **Servidor**: un equipo central (Windows). Ahí se hace doble clic en
  `iniciar_servidor.bat`, que arranca el proceso web (`uvicorn`) en el puerto
  8000. Ese proceso contiene toda la lógica y sirve las páginas web.
- **Base de datos**: **SQLite** = un solo archivo (`data/sanitapoint.db`). No hay
  un "servidor de base de datos" aparte, ni Docker, ni servicio que administrar.
  El archivo lo lee y escribe directamente el proceso del servidor.
- **Clientes (cajas)**: solo un navegador apuntando a
  `http://<ip-del-servidor>:8000`. No se instala nada en las cajas.

### ¿Aguanta varias cajas a la vez?
Sí. SQLite se abre en modo **WAL** (`PRAGMA journal_mode=WAL`) con un
`busy_timeout`, lo que permite que varias cajas lean y escriban sobre el mismo
archivo simultáneamente. Para el volumen de este negocio (2 servicios, unas
pocas cajas) es más que suficiente — es el mismo enfoque que usaba la versión de
escritorio original.

## 3. Cómo funciona por dentro (los flujos clave)

### 3.1 Venta
`app/templates/venta.html` → `POST /api/ventas`
([ventas.py](app/routers/ventas.py)): verifica caja abierta → emite boleta con
[`kame_client`](app/services/kame_client.py) → guarda la venta y el movimiento
de caja → genera el ticket con
[`ticket_printer`](app/services/ticket_printer.py).

### 3.2 Caja
[caja.py](app/routers/caja.py): abrir / cerrar / retiro / resumen del día. Toda
venta queda asociada a la caja abierta del usuario autenticado. Dos usuarios
pueden mantener turnos abiertos a la vez; cada uno ve sus propios contadores.

- **Apertura:** Caja Inicial (dinero), Torniquete Baño Inicial y Torniquete Ducha
  Inicial (lecturas físicas). El operador se toma de la cuenta conectada.
- **Contadores internos:** empiezan en cero en cada turno. Una venta de baño o
  un pase gratuito suma un acceso de baño; una venta de ducha suma uno de ducha.
  Los pases gratuitos corresponden al baño. Los contadores se obtienen de las
  ventas confirmadas de esa caja, por lo que no se pierden al recargar o salir.
- **Retiros:** el supervisor selecciona explícitamente la caja del usuario.
- **Cierre:** Caja Final, Torniquete Baño Final y Torniquete Ducha Final. Las
  lecturas finales no pueden ser menores que las iniciales.
- **Cuadre de efectivo:** esperado = inicial + ventas en efectivo − retiros;
  diferencia = final − esperado. Un valor negativo es faltante, positivo es
  sobrante. También se muestra el cambio final − inicial y el ingreso ajustado
  final − inicial + retiros. Los pagos electrónicos no aumentan el efectivo.
- **Cuadre de personas:** pasos = lectura final − inicial; diferencia = pasos
  − contador interno. Baño contrasta ventas + pases; ducha contrasta ventas.
  Las diferencias se registran y muestran sin impedir el cierre.

El último cierre se muestra en Caja; Contabilidad puede consultar todos los
turnos en Cierres y abrir **Ver cuadre** para revisar el detalle.

Al reiniciar, SQLite agrega las columnas nuevas sin borrar registros. Los
turnos anteriores se vinculan a una cuenta solo cuando el nombre del operador
identifica una única cuenta; los nombres ambiguos requieren revisión manual.
Las lecturas antiguas que no existen se muestran como “—”, sin inventar ceros.

### 3.3 KAME (real / mock)
[kame_client.py](app/services/kame_client.py). Controlado por `kame_modo` en
⚙️ Config. En `mock` genera folios ficticios sin llamar a nadie; en `real` hace
`POST {kame_url}/api/Documento/addVenta`, autenticando mediante OAuth o token Bearer.
Configura correo KAME, credenciales y unidad de negocio. Consulta README.md.

### 3.4 Reportes
[reportes.py](app/services/reportes.py): reportlab → PDF, openpyxl → Excel.

### 3.5 Creación de la base de datos
No hay migraciones que correr. Al arrancar, `app/main.py` ejecuta
`Base.metadata.create_all(...)`: si el archivo SQLite no existe o le faltan
tablas, las crea; luego siembra los servicios y la configuración por defecto.
Por eso el `.bat` solo necesita "arrancar" — la base se prepara sola.

## 4. Estructura de carpetas

```
sanitapoint_web/
├── iniciar_servidor.bat       ← ejecutable de arranque (Windows)
├── iniciar_servidor.command   ← equivalente macOS/Linux
├── app/
│   ├── main.py                 ← arranque; crea tablas + seed
│   ├── config.py                ← ruta del archivo SQLite y puerto
│   ├── database.py               ← conexión SQLite + WAL
│   ├── models.py                  ← tablas
│   ├── routers/ services/ templates/ static/
├── data/
│   ├── sanitapoint.db          ← LA BASE DE DATOS (se crea sola)
│   └── tickets/                 ← PDFs de tickets
└── requirements.txt
```

---

## 5. Instalación paso a paso (Windows)

### Requisitos
- **Python 3.11+** con "Add Python to PATH" marcado al instalar
  (<https://www.python.org/downloads/>).
- **No** se necesita Docker, ni PostgreSQL, ni instalar ninguna base de datos.

### Opción A — con el ejecutable (recomendada)

1. Copia la carpeta `sanitapoint_web` al equipo servidor.
2. Doble clic en **`iniciar_servidor.bat`**.
   - 1ª vez: crea el entorno e instala dependencias automáticamente (unos
     minutos). Luego arranca.
   - Siguientes veces: arranca de inmediato.
3. La ventana muestra la(s) URL para las cajas, p. ej. `http://192.168.1.10:8000`.
4. En cada caja, abre esa URL en el navegador.

### Opción B — instalación manual (por si el `.bat` falla o para depurar)

```bat
cd sanitapoint_web
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En macOS/Linux es igual pero con `python3`, `source .venv/bin/activate` y las
mismas líneas de `pip` / `uvicorn`.

### Verificar
Abre `http://localhost:8000` en el servidor. Debe verse la pantalla de Venta con
"Uso de Baño" y "Ducha". Prueba: Caja → Abrir caja → Venta → elegir servicio →
aparece el ticket con folio `MOCK-000001`.

---

## 6. ¿Qué cambió respecto a la versión con Docker?

| Antes (Docker + PostgreSQL) | Ahora (sin Docker + SQLite) |
|---|---|
| Requería Docker Desktop abierto | No requiere Docker |
| PostgreSQL como servicio aparte | SQLite = un archivo `data/sanitapoint.db` |
| `alembic upgrade head` para crear tablas | Se crean solas al arrancar |
| Arranque por comandos en terminal | Doble clic en `iniciar_servidor.bat` |
| Backup con `pg_dump` | Backup = copiar `sanitapoint.db` |

`psycopg` y `alembic` se quitaron de `requirements.txt`; la carpeta `alembic/`
se eliminó.

---

## 7. Operación diaria

**Encender:** doble clic en `iniciar_servidor.bat` (deja la ventana abierta).
**Apagar:** cierra esa ventana.

**Dejarlo siempre encendido** (opcional): pon un acceso directo a
`iniciar_servidor.bat` en la carpeta de Inicio de Windows
(`Win+R` → `shell:startup`) para que el servidor arranque solo al prender el PC.

### Backup de la base de datos
Con el servidor **apagado** (ventana cerrada), copia el archivo
`data\sanitapoint.db` a un pendrive o carpeta de respaldo. Eso es todo el
sistema. (Si copias con el servidor encendido, copia también
`sanitapoint.db-wal` y `sanitapoint.db-shm` para no perder lo más reciente; por
eso es más seguro apagarlo antes.)

### Restaurar
Reemplaza `data\sanitapoint.db` por tu copia (servidor apagado) y vuelve a
arrancar.

---

## 8. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| El `.bat` dice "No se encontro Python" | Python no instalado o sin PATH | Reinstalar Python marcando "Add Python to PATH" |
| Una caja no abre el sistema | URL/IP incorrecta, o servidor apagado, o firewall | Verificar que el `.bat` esté corriendo; usar la IP que muestra; permitir Python en el Firewall de Windows |
| "database is locked" ocasional bajo mucha carga | Muchas escrituras simultáneas | Ya mitigado con WAL + busy_timeout; si persistiera, evaluar MariaDB |
| El ticket no sale por impresora física | Sin impresora ESC/POS configurada | Configurar IP/puerto (red) o USB en ⚙️ Config |
| La boleta dice "(modo prueba)" | `KAME_MODO=mock` en `.env` | Cambiar a `KAME_MODO=real`, reiniciar y usar **Probar conexión a KAME** en Config |

## 9. Seguridad: usuarios, contraseñas y roles

El sistema exige **ingresar con usuario y contraseña**. Al abrir cualquier
página sin sesión, redirige a `/login`.

### Roles (grupos)
- **Cajero**: emite boletas, abre caja (ingresa el Nro de torniquete/aperturas) y
  cierra su turno. Ve: Venta, Caja (solo Abrir/Cerrar), Historial, Clientes.
- **Supervisor**: retiros de caja. Ve: Caja (solo el botón Retiro).
- **Contabilidad**: informes de ventas (Reportes), cierres de caja (Cierres),
  historial, y administración de cuentas/claves (Cuentas). No opera caja ni vende.
- **Administrador**: acceso completo a tarifas, impresora, prueba de conexión
  KAME y gestión de cuentas. Las credenciales KAME solo se editan en `.env`.

Cada usuario ve en el menú solo lo que su rol permite; si intenta entrar por URL a
una sección sin permiso, es redirigido a su pantalla de inicio, y la API responde
403. La segregación de funciones es intencional: el cajero no puede hacer sus
propios retiros (los hace el supervisor) y contabilidad no toca la caja pero
revisa la información y administra los accesos.

Salvaguarda de privilegios: contabilidad puede administrar cuentas y restablecer
claves, pero **solo un administrador** puede crear/editar cuentas administradoras
o asignar el rol administrador.

### Cuenta inicial
La primera vez se crea automáticamente:

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `admin123` | administrador |

**Cámbiala apenas ingreses**: pestaña **Cuentas** → Editar `admin` → nueva
contraseña. Desde ahí creas las cuentas de los operadores (botón "Nueva cuenta").

### Cómo está implementado (resumen técnico)
- Contraseñas: nunca se guardan en texto plano; se almacena un hash
  `pbkdf2_sha256` con salt ([app/security.py](app/security.py)).
- Sesión: cookie firmada (SessionMiddleware). La clave de firma se guarda en
  `data/secret_key.txt` y se genera sola la primera vez. **No la borres**: si
  cambia, todas las sesiones activas se invalidan (los usuarios vuelven a entrar).
- Control de acceso por **capacidades**: el mapa rol→permisos está en
  [app/permissions.py](app/permissions.py); las rutas piden una capacidad concreta
  con `require_cap(...)` ([app/deps.py](app/deps.py)), no un rol fijo, así ajustar
  quién puede hacer qué es cambiar una línea en un solo lugar.
- Salvaguardas: no se puede desactivar la propia cuenta ni dejar el sistema sin
  ningún administrador activo.

### Reglas prácticas
- Cada cajero con su propia cuenta de operador (no compartir el admin).
- Deja siempre al menos una cuenta administradora activa y con contraseña conocida.
- Si un operador olvida su contraseña, un administrador se la restablece desde
  **Cuentas → Editar** (escribe una nueva; el campo en blanco no la cambia).

## 10. Pendientes (fuera del alcance de la app)

- Solicitar a KAME el acceso a su API (no tienen documentación pública).
- Fijar la IP del equipo servidor (IP fija o reserva DHCP en el router) para que
  la dirección de las cajas no cambie.
- Abrir el puerto 8000 en el Firewall de Windows la primera vez (Windows suele
  preguntarlo al arrancar el servidor; permitir "Redes privadas").
