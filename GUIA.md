# Guía de SanitaPoint Web — cómo funciona y cómo instalarlo

Documento único con: qué hace la app por dentro, cómo están conectadas sus
piezas, y el paso a paso para instalarla y operarla. **Versión sin Docker, con
base de datos SQLite y ejecutable de arranque.**

---

## 1. ¿Qué es esta app?

Un punto de venta (POS) web para servicios sanitarios ("Uso de Baño" y "Ducha").
Al vender un servicio, la app:

1. Cobra según la tarifa configurada.
2. Emite una boleta electrónica vía KAME; el modo simulado requiere
   configurar explícitamente `KAME_MODO=mock` para pruebas.
3. Permite consultar el PDF e imprimir desde el navegador del puesto;
   los pases libres no generan boleta ni impresión.
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

### 3.3 KAME: emision y documentos con timbre

La emision real usa las credenciales de `.env`. El modo `KAME_MODO=mock` se habilita explicitamente para pruebas. Tras la emision se recupera el XML firmado documentado por KAME y su TED original se imprime como PDF417 en el ticket termico. **Ver PDF** descarga el PDF oficial de KAME.

Configura `KAME_RUT` con el RUT emisor. Si el XML no trae su resolucion, completa `KAME_RESOLUCION_NUMERO` y `KAME_RESOLUCION_FECHA` con los datos reales de la empresa. Si el documento aun no esta disponible, **Imprimir boleta** reintenta descargarlo sin volver a cobrar ni emitir. La impresion automatica abre el dialogo del navegador solo cuando el timbre esta listo.

Consulta [la integracion KAME](docs/KAME.md) para contratos oficiales, configuracion, cache y pruebas pendientes con hardware real.

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

## 5. Instalación del servidor local del terminal (Windows)

Estas instrucciones son para un servidor dedicado con Windows 11 Pro o Windows Server, SQLite local y dos computadores de caja. Las tareas se ejecutan al encender Windows, sin que una persona tenga que iniciar sesión. Ejecuta los comandos de administración en **Windows PowerShell como administrador**, en el servidor; no en las cajas.

### 5.1 Preparar el equipo y la red

Ejemplo que debes adaptar con el encargado de la red:

| Dato | Ejemplo |
|---|---|
| Carpeta del sistema | `C:\SanitaPoint` |
| IPv4 fija/reservada del servidor | `192.168.10.10` |
| Subred interna autorizada | `192.168.10.0/24` (máscara `255.255.255.0`) |
| Puerto de la aplicación | TCP `8000` |
| Carpeta de respaldos, idealmente otro disco | `D:\Respaldos\SanitaPoint` |
| Hora diaria del respaldo | `00:00`, zona horaria de Santiago |

- Conecta el servidor por cable a la red interna del terminal. Reserva su IP en DHCP o configura una IP fija fuera del rango dinámico para evitar conflictos. Comprueba adaptador, IP y máscara con `Get-NetIPConfiguration`.
- La base SQLite debe estar en un **disco local** del servidor; no en una carpeta compartida, OneDrive ni una unidad de red.
- Instala Python 3.11 o superior **para todos los usuarios**, con su ejecutable accesible a la cuenta `SYSTEM`. Un Python instalado solo dentro de un perfil personal puede no funcionar en el inicio desatendido.
- En la configuración de energía, desactiva la suspensión e hibernación automáticas del servidor. Apagar la pantalla no afecta al sistema.
- En BIOS/UEFI, activa **Restore on AC Power Loss / Power On after Power Failure** para que el equipo vuelva a encenderse cuando regrese la electricidad. Windows no puede arrancar un equipo apagado sin esta función. Si el arranque pide PIN de BitLocker, requiere intervención; coordina la política de arranque con el responsable del equipo. Se recomienda UPS.
- Comprueba fecha, hora y sincronización. En Windows, para Santiago:

```powershell
Set-TimeZone -Id "Pacific SA Standard Time"
Get-Date
Get-TimeZone
```

### 5.2 Instalar la aplicación y comprobarla

Copia el proyecto completo a `C:\SanitaPoint`, incluidos `app`, `scripts` y `requirements.txt`. **No copies el entorno `.venv` de otro computador**: créalo en el servidor. Conserva `data` y `.env` si estás actualizando una instalación existente; antes cierra los turnos y respalda.

```powershell
Set-Location C:\SanitaPoint
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

La primera instalación necesita internet. Una vez preparada, el inicio automático no instala dependencias. KAME necesita conexión saliente a internet para emitir boletas reales.

Si no existe `.env`, copia `.env.example` a `.env` y completa las credenciales KAME. No sobrescribas uno existente. Usa `KAME_MODO=mock` solo durante pruebas; cambia a `real`, completa sus credenciales y reinicia antes de operar. No se simulan boletas por faltar credenciales en modo real.

Comprueba el sistema **primero en el servidor**:

```powershell
& C:\SanitaPoint\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre `http://127.0.0.1:8000/login`. Cambia inmediatamente la clave inicial `admin123` de `admin`, crea las cuentas y configura tarifas y KAME. Comprueba la venta en modo de prueba, los dos servicios y el cierre. Detén esta ejecución con **Ctrl+C** antes de instalar el arranque automático.

Los comandos siguientes usan SQLite en `C:\SanitaPoint\data\sanitapoint.db`. Si configuraste otra ruta mediante `DATABASE_URL`, ajusta también `--origen` en el respaldo. No sirven para respaldar PostgreSQL.

### 5.3 Acceso exclusivamente desde la red interna

**Abrir un puerto no autentica a los usuarios**: cualquier equipo autorizado de la subred podrá llegar al login; cada trabajador sigue necesitando su cuenta. Si la red de pasajeros comparte esa subred, también alcanzará el login. Separa invitados y operación en redes/VLAN distintas y autoriza solo la subred de trabajo.

Revisa el perfil del adaptador con `Get-NetConnectionProfile`. En un equipo sin dominio, cambia **solo el adaptador interno de confianza** a Privado, reemplazando el índice por el real:

```powershell
Get-NetConnectionProfile
# Ejemplo: 12 debe ser el InterfaceIndex del adaptador interno.
Set-NetConnectionProfile -InterfaceIndex 12 -NetworkCategory Private
```

En equipos unidos a dominio, conserva `DomainAuthenticated`; usa `Domain` en la regla siguiente y coordina los cambios con quien administra las políticas del dominio.

Crea una única regla de acceso a la app, limitada a IP del servidor, subred y puerto. Las siguientes variables se usan también en los pasos posteriores; vuelve a definirlas si abres otra consola:

```powershell
$RutaApp = 'C:\SanitaPoint'
$PythonApp = Join-Path $RutaApp '.venv\Scripts\python.exe'
$IpInterna = '192.168.10.10'
$SubredInterna = '192.168.10.0/24'
$RutaRespaldos = 'D:\Respaldos\SanitaPoint'

# Mantener el firewall activo y el bloqueo predeterminado de entradas.
# En servidores con otras funciones, revisar el impacto con su administrador.
Set-NetFirewallProfile -Profile Private,Public,Domain -Enabled True -DefaultInboundAction Block

New-NetFirewallRule -Name 'SanitaPoint-LAN-8000' -DisplayName 'SanitaPoint - red interna TCP 8000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -LocalAddress $IpInterna -RemoteAddress $SubredInterna -Profile Private -EdgeTraversalPolicy Block
```

No agregues una regla global de bloqueo del puerto 8000: en Windows un bloqueo explícito puede imponerse al permiso de la LAN. Usa el bloqueo predeterminado y el permiso limitado anterior. Si la regla ya existe, revísala con `Get-NetFirewallRule -Name 'SanitaPoint-LAN-8000'` en lugar de crearla nuevamente.

**Revisa reglas de permiso anteriores** en `wf.msc` → Reglas de entrada. Deshabilita las reglas antiguas de Python/Uvicorn o del puerto 8000 que autoricen cualquier origen y amplíen el acceso. Mantener una regla amplia junto a la restringida puede dejar el sistema accesible desde otras redes. Si Windows pregunta si deseas permitir Python en todas las redes, cancela ese permiso amplio y conserva esta regla. No deshabilites reglas de otros servicios sin revisar su uso.

En el router/firewall del terminal:

- No configures **port forwarding**, NAT entrante ni DMZ hacia el servidor o su puerto 8000.
- Desactiva UPnP si permite crear aperturas automáticas. Revisa que no existan túneles públicos, proxys publicados ni VPN que den acceso a esta subred desde afuera.
- Bloquea el tráfico hacia el servidor desde la red de invitados y desde las demás VLAN no autorizadas.
- No publiques puertos de SQLite, impresoras ni administración para usar esta app. Los clientes solo necesitan **TCP 8000**. Mantén la salida necesaria a KAME, DNS y sincronización de hora; no bloquees toda la salida del servidor.

El arranque del siguiente paso escucha **solo en la IPv4 interna indicada**, en vez de `0.0.0.0`. Esto limita interfaces; el firewall y el router son los que limitan quién puede conectarse. HTTP se reserva para la red interna de confianza; para una red no confiable, configura HTTPS antes de usar credenciales.

Referencia: [reglas de Firewall de Windows y filtros de dirección](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule).

### 5.4 Iniciar automáticamente al encender Windows

Se usa el **Programador de tareas** con desencadenador **Al iniciar el sistema**, sin depender de una sesión de escritorio. No uses la carpeta `shell:startup` ni el `.bat` interactivo para este despliegue: requieren sesión, abren navegador o dejan ventanas de pausa.

El archivo incluido [`scripts/servidor_local.py`](scripts/servidor_local.py) inicia Uvicorn sin navegador y con recarga automática del código Python en `app/`. Al guardar cambios, espera las solicitudes en curso y recarga el proceso; puede haber una pausa breve. Usa `--no-reload` para desactivar esta función y ejecutar un solo proceso sin supervisor de recarga. Escribe la salida en `C:\SanitaPoint\logs\servidor-AAAA-MM-DD.log` (el nombre corresponde al día de inicio del lanzador; no rota hasta reiniciarlo). Devuelve el código de salida a Windows para que pueda reintentar ante un fallo.

La receta utiliza la cuenta local de servicio `SYSTEM`, que no requiere almacenar una contraseña. **Protege `C:\SanitaPoint` con permisos NTFS**: modificación solo para Administradores y SYSTEM; las cuentas comunes no necesitan acceso a esa carpeta. La tarea ejecuta ese código con privilegios del sistema. En una instalación administrada puede usarse una cuenta de servicio dedicada con los permisos de lectura/escritura necesarios.

```powershell
$PrincipalApp = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$AccionApp = New-ScheduledTaskAction -Execute $PythonApp -Argument ('"{0}\scripts\servidor_local.py" --host {1} --port 8000' -f $RutaApp, $IpInterna) -WorkingDirectory $RutaApp
$InicioApp = New-ScheduledTaskTrigger -AtStartup
$OpcionesApp = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'SanitaPoint-Servidor' -Action $AccionApp -Trigger $InicioApp -Principal $PrincipalApp -Settings $OpcionesApp -Description 'Servidor web local del terminal; arranca sin iniciar sesion.'
Start-ScheduledTask -TaskName 'SanitaPoint-Servidor'
```

Comprueba que aparece **En ejecución** en `taskschd.msc`, revisa el log y entra a `http://192.168.10.10:8000/login` desde una caja. Si la interfaz de red aún no está lista al encender, el fallo permite reintentar cada minuto. No inicies a la vez el `.bat`, otra copia de Uvicorn o una segunda tarea.

El reinicio por fallo tiene un límite de 999 intentos; **no supervisa bloqueos en los que el proceso siga vivo**. Si se detuvo intencionalmente o agotó intentos, corrige el problema y usa `Start-ScheduledTask`. Revisa tareas y logs durante la operación.

Referencia: [opciones de ejecución y reinicio del Programador de tareas](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

### 5.5 Respaldo diario a las 00:00, sin detener las cajas

El script incluido [`scripts/respaldar_bd.py`](scripts/respaldar_bd.py) usa la API de respaldo de SQLite, valida la integridad y solo entonces publica el archivo `.db` definitivo. Funciona con el sistema encendido y con WAL activo. **No copies a mano el `.db`, `-wal` y `-shm` mientras hay ventas**, porque copiarlos por separado no garantiza una copia consistente.

Crea una carpeta de destino **local**, preferentemente en otro disco físico. SYSTEM debe tener permiso de escritura. Una unidad `D:` no existe en todos los equipos: reemplaza la ruta por una real. Una partición en el mismo disco no protege frente a la falla de ese disco. Mantén además una copia periódica en otro equipo o soporte desconectado. Esta receta con SYSTEM no presupone acceso a carpetas de red.

```powershell
New-Item -ItemType Directory -Path $RutaRespaldos -Force
# Prueba manual: debe imprimir "Respaldo verificado" y una ruta nueva.
& $PythonApp "$RutaApp\scripts\respaldar_bd.py" --destino $RutaRespaldos

$AccionRespaldo = New-ScheduledTaskAction -Execute $PythonApp -Argument ('"{0}\scripts\respaldar_bd.py" --destino "{1}"' -f $RutaApp, $RutaRespaldos) -WorkingDirectory $RutaApp
$HoraRespaldo = New-ScheduledTaskTrigger -Daily -At '00:00'
$OpcionesRespaldo = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'SanitaPoint-Respaldo-Diario' -Action $AccionRespaldo -Trigger $HoraRespaldo -Principal $PrincipalApp -Settings $OpcionesRespaldo -Description 'Respaldo SQLite consistente diario a las 00:00, hora local de Windows.'

# Probar tambien bajo SYSTEM, no solo bajo tu usuario.
Start-ScheduledTask -TaskName 'SanitaPoint-Respaldo-Diario'
```

Espera a que termine y comprueba:

```powershell
Get-ScheduledTaskInfo -TaskName 'SanitaPoint-Respaldo-Diario'
Get-ChildItem -LiteralPath $RutaRespaldos -Filter 'sanitapoint-*.db' | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name,Length,LastWriteTime
```

`LastTaskResult = 0` indica ejecución correcta. Confirma también la fecha y que exista un `.db` reciente. Una copia `.parcial` no es un respaldo terminado. El historial de la tarea permite revisar fallos; habilítalo en el Programador de tareas.

Si el servidor estaba apagado a medianoche, `StartWhenAvailable` permite ejecutar el respaldo al volver a estar disponible; **no puede respaldar mientras no tenga electricidad ni reconstruir una copia de cada medianoche perdida**. La hora se toma de Windows y sigue su zona horaria. La tarea conserva todos los respaldos: revisa espacio libre y define retención según las necesidades del terminal, sin borrar el último respaldo verificado.

Respalda por separado y con acceso restringido `.env` y `data\secret_key.txt`. El `.db` contiene las ventas y cuentas, pero no las credenciales del archivo `.env` ni los ajustes locales de los navegadores. El código y dependencias también deben poder reinstalarse.

Referencia: [API de respaldo SQLite de Python](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup).

### 5.6 Configurar las dos cajas y aceptar la instalación

En cada puesto abre siempre `http://192.168.10.10:8000` con el mismo navegador. Inicia sesión con una cuenta individual y el servicio correcto. Instala la impresora en ese computador y configura **Este computador**; conecta también ahí su lector USB. Las tarifas y ajustes generales se administran una sola vez en el servidor.

Antes de entregar el sistema:

1. Desde ambas cajas, comprueba login, precios y una prueba de impresión/escaneo locales. No generes boletas reales solo para probar infraestructura.
2. Abre con Pepe en Baño 1: Juan no debe poder abrir allí hasta el cierre de Pepe. Baño 2 debe operar de manera independiente. Comprueba historiales propios y el historial completo con un rol superior.
3. Reinicia Windows y **no inicies sesión en el servidor**: el login debe quedar disponible desde las cajas después del arranque y los reintentos de red.
4. Ejecuta y verifica el respaldo bajo SYSTEM y prueba su restauración en una copia de ensayo.
5. En una caja interna, `Test-NetConnection 192.168.10.10 -Port 8000` debe indicar `TcpTestSucceeded: True`. Desde una red de invitados no autorizada debe fallar. Desde internet, prueba la IP pública del terminal y el puerto 8000 usando un equipo fuera de su red, por ejemplo con datos móviles: no debe abrir. Revisa también publicaciones de otros puertos que redirijan al servidor; una sola prueba al 8000 no demuestra que no existan otros accesos.

---

### 5.7 Actualizar desde un repositorio privado de GitHub, sin cuenta personal en el servidor

Se usa una **deploy key SSH de solo lectura**, exclusiva del repositorio. El servidor conserva esa credencial técnica, no una sesión de tu cuenta. Desde tu propio computador autorizas la clave pública una vez en GitHub. La clave privada queda protegida en el servidor; no se copia a GitHub ni se sube al repositorio.

El actualizador consulta `main` **cada cinco minutos mediante una conexión saliente**; no usa webhooks ni necesita abrir un puerto entrante. Si hay cajas abiertas, espera a una ejecución posterior. Con las cajas cerradas, prepara un entorno Python independiente, activa mantenimiento, espera las solicitudes en curso, vuelve a comprobar las cajas, detiene el servicio, respalda SQLite, actualiza y verifica el arranque. Solo entonces vuelve a aceptar usuarios. Durante esa pausa breve, la web responde que hay una actualización en curso.

Si falla el arranque, intenta recuperar código, entorno y base anteriores **antes de permitir nuevas operaciones**. Si la recuperación también falla, conserva mantenimiento y requiere revisión manual. No cambia `.env`, los datos de negocio ni la configuración local de los navegadores. Las actualizaciones de esquema solo se consideran correctas si la aplicación arranca; la comprobación no sustituye las pruebas funcionales de cada versión.

#### A. Preparar Git y la clave del terminal

Instala **Git para Windows para todos los usuarios** y el cliente **OpenSSH de Windows**. Comprueba que existan `C:\Program Files\Git\cmd\git.exe` y `C:\Windows\System32\OpenSSH\ssh.exe`. La instalación inicial de esta receta debe incluir los scripts y `/api/salud` de esta versión; una instalación antigua necesita actualizarse manualmente primero.

En PowerShell como administrador del servidor:

```powershell
$RutaApp = 'C:\SanitaPoint'
$RutaOps = 'C:\SanitaPoint-Operaciones'
$RutaRespaldos = 'D:\Respaldos\SanitaPoint'
$GitTerminal = 'C:\Program Files\Git\cmd\git.exe'
$SshTerminal = 'C:\Windows\System32\OpenSSH\ssh.exe'
$PythonApp = Join-Path $RutaApp '.venv\Scripts\python.exe'
$IpInterna = '192.168.10.10'

New-Item -ItemType Directory -Path $RutaOps -Force
# Solo SYSTEM y Administradores: los usuarios del POS no necesitan esta carpeta.
icacls $RutaOps /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
& C:\Windows\System32\OpenSSH\ssh-keygen.exe -t ed25519 -f "$RutaOps\github_ed25519" -C 'SanitaPoint-Terminal'
```

Cuando solicite una frase de contraseña, deja ambas respuestas vacías para que la tarea desatendida pueda leer la clave. No reutilices una clave personal. Muestra **solo la clave pública**:

```powershell
Get-Content -LiteralPath "$RutaOps\github_ed25519.pub"
```

En GitHub, **desde tu propio computador**: repositorio → **Settings → Deploy keys → Add deploy key**. Nombre: `Servidor terminal SanitaPoint`. Pega el contenido del archivo `.pub` y **deja desmarcado Allow write access**. El terminal no necesita cuenta de GitHub ni poder hacer `push`.

Referencia: [claves de despliegue por repositorio y permisos de lectura](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys).

#### B. Verificar la identidad de GitHub y fijar la conexión SSH

```powershell
& C:\Windows\System32\OpenSSH\ssh-keyscan.exe -t ed25519 github.com | Set-Content -LiteralPath "$RutaOps\known_hosts" -Encoding ascii
& C:\Windows\System32\OpenSSH\ssh-keygen.exe -lf "$RutaOps\known_hosts"
```

**Antes de continuar**, compara la huella mostrada con la huella Ed25519 publicada en [la documentación oficial de GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints). `ssh-keyscan` por sí solo no autentica el servidor. Si no coincide, detén la configuración y revisa la red; no desactives la verificación.

Crea un archivo SSH exclusivo para esta tarea, sin usar el perfil de tu cuenta:

```powershell
@(
  'Host github.com',
  '  HostName github.com',
  '  User git',
  '  IdentityFile C:/SanitaPoint-Operaciones/github_ed25519',
  '  IdentitiesOnly yes',
  '  IdentityAgent none',
  '  BatchMode yes',
  '  StrictHostKeyChecking yes',
  '  HostKeyAlgorithms ssh-ed25519',
  '  UserKnownHostsFile C:/SanitaPoint-Operaciones/known_hosts'
) | Set-Content -LiteralPath "$RutaOps\ssh_config" -Encoding ascii

$ComandoSsh = '"C:/Windows/System32/OpenSSH/ssh.exe" -F "C:/SanitaPoint-Operaciones/ssh_config"'
$RemotoGitHub = 'git@github.com:PROPIETARIO/REPOSITORIO.git'
& $GitTerminal -c "core.sshCommand=$ComandoSsh" ls-remote $RemotoGitHub refs/heads/main
```

Reemplaza `PROPIETARIO/REPOSITORIO` por los datos reales. La última orden debe mostrar el commit de `main` sin pedir usuario, contraseña ni confirmación. Solo necesita salida a GitHub por SSH (TCP 22) y a los repositorios de paquetes por HTTPS; esto no abre acceso al terminal desde internet.

#### C. Tener una copia Git limpia en el servidor

Para una **instalación nueva**, clona en lugar de copiar el código del paso 5.2 y luego crea `.venv` e instala las dependencias como allí se indica:

```powershell
& $GitTerminal -c "core.sshCommand=$ComandoSsh" clone --branch main $RemotoGitHub $RutaApp
& $GitTerminal -C $RutaApp config core.sshCommand $ComandoSsh
```

Si la carpeta ya existe sin `.git`, no clones encima ni borres `data`: detén las tareas, conserva la instalación completa en un resguardo, clona una carpeta nueva en la ruta esperada y recupera **solo `data` y `.env`**. Recrea `.venv`, revisa permisos y prueba el sistema antes de reactivar las tareas. Si ya tiene `.git`, comprueba `git status`, rama `main` y `origin` SSH; no uses un reset para borrar cambios locales.

La instalación debe tener `main` sin cambios locales. `.env`, `data`, `.venv` y logs permanecen fuera de Git. El actualizador rechaza divergencias, cambios sin guardar y commits que intenten versionar esos datos; no fuerza `push`, no limpia archivos locales ni elimina ramas.

#### D. Crear configuración y habilitar el entorno activo

Con las variables anteriores definidas:

```powershell
$RevisionInicial = (& $GitTerminal -C $RutaApp rev-parse HEAD).Trim()
@{ python = $PythonApp; revision = $RevisionInicial } | ConvertTo-Json | Set-Content -LiteralPath "$RutaOps\runtime.json" -Encoding UTF8
@{
  repositorio = $RutaApp
  operaciones = $RutaOps
  respaldos = $RutaRespaldos
  git = $GitTerminal
  ssh = $SshTerminal
  ssh_config = "$RutaOps\ssh_config"
  salud = "http://${IpInterna}:8000/api/salud"
  tarea = 'SanitaPoint-Servidor'
} | ConvertTo-Json | Set-Content -LiteralPath "$RutaOps\actualizacion.json" -Encoding UTF8
```

El actualizador soporta la **base SQLite predeterminada** `data\sanitapoint.db` y un solo proceso Uvicorn. No lo habilites con `DATABASE_URL` apuntando a otra base. `runtime.json` elige el Python de la versión activa; el `.venv` inicial se conserva para arrancar los scripts de control y respaldo. Las dependencias de versiones nuevas se instalan bajo `C:\SanitaPoint-Operaciones\entornos\COMMIT`.

Modifica la acción de la tarea del servidor para usar `runtime.json`. Haz este cambio inicial con ambas cajas cerradas:

```powershell
Stop-ScheduledTask -TaskName 'SanitaPoint-Servidor'
$AccionConRuntime = New-ScheduledTaskAction -Execute $PythonApp -Argument ('"{0}\scripts\servidor_local.py" --host {1} --port 8000 --runtime "{2}\runtime.json"' -f $RutaApp, $IpInterna, $RutaOps) -WorkingDirectory $RutaApp
Set-ScheduledTask -TaskName 'SanitaPoint-Servidor' -Action $AccionConRuntime
Start-ScheduledTask -TaskName 'SanitaPoint-Servidor'
Invoke-RestMethod -Uri "http://${IpInterna}:8000/api/salud"
```

Espera al arranque antes de la última orden. Debe devolver `ok: True`, `sqlite_predeterminada: True`, `mantenimiento: False` y `revision` igual a `$RevisionInicial`. No continúes si no coincide. `/api/salud` solo informa estado; no permite actualizar remotamente ni revela ventas o credenciales.

#### E. Programar la consulta automática de main

```powershell
$PrincipalActualizacion = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$AccionActualizacion = New-ScheduledTaskAction -Execute $PythonApp -Argument ('"{0}\scripts\actualizar_servidor.py" --config "{1}\actualizacion.json"' -f $RutaApp, $RutaOps) -WorkingDirectory $RutaApp
$CadaCincoMinutos = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$OpcionesActualizacion = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'SanitaPoint-Actualizar-main' -Action $AccionActualizacion -Trigger $CadaCincoMinutos -Settings $OpcionesActualizacion -Principal $PrincipalActualizacion -Description 'Consulta main con deploy key de lectura y actualiza solo sin cajas abiertas.'
Start-ScheduledTask -TaskName 'SanitaPoint-Actualizar-main'
```

La repetición no tiene fecha de fin; se ejecuta cada cinco minutos, también después de un reinicio. Prueba la tarea bajo SYSTEM: sus permisos SSH pueden ser distintos a los de tu sesión. Revisa `Get-ScheduledTaskInfo -TaskName 'SanitaPoint-Actualizar-main'` y `C:\SanitaPoint-Operaciones\actualizaciones.log`. Un resultado 0 puede significar que no hay cambios o que la actualización está pendiente por una caja abierta; confirma el commit en salud para saber qué versión está sirviendo.

Para comprobar la instalación: sube un cambio de prueba sin efectos en datos a `main`, confirma que queda pendiente si hay una caja abierta y que se aplica al cerrar ambas. Después verifica la nueva `revision` en `/api/salud`, la venta, impresión y el respaldo previo. No uses una venta real como prueba de despliegue.

No edites el código directamente en el servidor ni ejecutes `git pull` mientras la tarea esté activa. La tarea aplica todo lo que llegue a `main`: publica allí solamente versiones probadas. Cambios que eliminen el control de mantenimiento, el endpoint de salud o el contrato de los scripts necesitan un despliegue manual coordinado.

#### F. Fallos, recuperación y revocación

- Sin internet o sin acceso a GitHub, la descarga falla y la versión instalada sigue funcionando. Se vuelve a consultar más tarde.
- Si falla una versión durante el cambio y se recupera la anterior, se registra `version-fallida.json`. No vuelve a intentar ese mismo commit cada cinco minutos: espera un commit nuevo o una revisión manual antes de retirar ese registro.
- Si un corte de energía o el límite de 30 minutos interrumpe la tarea, puede quedar `actualizador.lock` en la carpeta de operaciones o `data\actualizacion.lock`. **No borres estos archivos a ciegas**: detén la tarea de actualización, revisa logs, `runtime.json`, HEAD y `ultimo-despliegue.json`. Este último conserva commit anterior, entorno anterior y ruta del respaldo cuando ya se inició el cambio. Comprueba que los commits coincidan con el marcador del mantenimiento actual; `respaldo: null` significa que todavía no se publicó una copia para ese intento. No uses el registro de un despliegue anterior como si fuera el actual.
- Para recuperar manualmente, mantén el servidor detenido, comprueba que no escuche en 8000, restaura la base según la sección 7 y vuelve al commit anterior con `git reset --keep COMMIT_ANTERIOR`, solo después de resguardar cualquier cambio local. Recupera también el `runtime_anterior` guardado en `ultimo-despliegue.json`. Antes de retirar el mantenimiento y reactivar actualizaciones, inicia la tarea del servidor y comprueba el commit correcto en `/api/salud`. Si no hubo cambio de versión, no restaures una copia innecesariamente.
- La restauración de la sección 7 debe conservar o volver a crear `data\actualizacion.lock` hasta completar esa verificación. Las tareas de actualización y respaldo deben permanecer deshabilitadas durante una recuperación manual.
- Los entornos anteriores y respaldos no se borran automáticamente. Revisa espacio disponible; conserva el entorno activo, el anterior y los respaldos verificados.
- Para desactivar la automatización, deshabilita `SanitaPoint-Actualizar-main`. Para retirar el acceso del terminal al repositorio, elimina su deploy key desde Settings del repositorio en GitHub. La versión ya instalada seguirá funcionando.

---

## 6. ¿Qué cambió respecto a la versión con Docker?

| Antes (Docker + PostgreSQL) | Ahora (sin Docker + SQLite) |
|---|---|
| Requería Docker Desktop abierto | No requiere Docker |
| PostgreSQL como servicio aparte | SQLite = un archivo `data/sanitapoint.db` |
| `alembic upgrade head` para crear tablas | Se crean solas al arrancar |
| Arranque por comandos en terminal | Doble clic en `iniciar_servidor.bat` |
| Backup con `pg_dump` | Backup consistente con `scripts/respaldar_bd.py` |

`psycopg` y `alembic` se quitaron de `requirements.txt`; la carpeta `alembic/`
se eliminó.

---

## 7. Operación diaria, actualizaciones y restauración

- **Arranque normal:** automático al encender Windows; no abrir el `.bat`.
- **Estado del servidor:** `Get-ScheduledTask -TaskName 'SanitaPoint-Servidor'` y los archivos de `C:\SanitaPoint\logs`.
- **Revisar respaldos diariamente:** último `.db` generado y resultado de `SanitaPoint-Respaldo-Diario`. Verifica espacio libre también en el disco de logs.
- **Reiniciar tras cambiar `.env`:** `Stop-ScheduledTask -TaskName 'SanitaPoint-Servidor'` y luego `Start-ScheduledTask -TaskName 'SanitaPoint-Servidor'`. Comprueba que el proceso anterior liberó el puerto antes de volver a iniciarlo.
- **Actualizar:** cerrar turnos, generar respaldo, detener la tarea, sustituir el código preservando `data` y `.env`, instalar las dependencias nuevas y volver a iniciar. Si se detectan cajas abiertas duplicadas en un servicio, concílialas antes de migrar; no se cierran automáticamente.

### Restaurar un respaldo

Una restauración reemplaza todas las ventas y cambios posteriores a la fecha de la copia. Coordina una ventana sin operación y conserva la base actual antes de reemplazarla.

1. Deshabilita temporalmente las tareas del servidor, respaldo y actualización (si está instalada) en `taskschd.msc` y detén `SanitaPoint-Servidor`. Confirma que no sigue Uvicorn ni hay conexiones en el puerto 8000; compruébalo con `Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue`. No cierres procesos ajenos al sistema.
2. Con la aplicación detenida, mueve la carpeta `C:\SanitaPoint\data` completa a una ubicación de resguardo fechada. Así conservas también los archivos WAL anteriores. **No mezcles un respaldo con los `-wal` o `-shm` de la base reemplazada.**
3. Crea una carpeta `data` nueva y copia el `.db` verificado elegido como `C:\SanitaPoint\data\sanitapoint.db`. Recupera también `secret_key.txt` de la carpeta anterior o de su respaldo protegido. Conserva `.env` y verifica que `DATABASE_URL` siga apuntando a la base restaurada.
4. Restablece permisos para SYSTEM y Administradores. Habilita la tarea del servidor, iníciala y comprueba usuarios, ventas y cierres antes de permitir nuevas ventas.
5. Habilita nuevamente el respaldo diario y genera una copia manual verificada. Conserva el resguardo anterior hasta confirmar la recuperación.

Prueba este procedimiento primero en un entorno separado, sin credenciales KAME reales ni operaciones contra la base del terminal.

---

## 8. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| El `.bat` dice "No se encontro Python" | Python no instalado o sin PATH | Reinstalar Python marcando "Add Python to PATH" |
| Una caja no abre el sistema | URL/IP incorrecta, o servidor apagado, o firewall | Verificar que el `.bat` esté corriendo; usar la IP que muestra; revisar la regla limitada a la subred interna (sección 5.3) |
| "database is locked" ocasional bajo mucha carga | Muchas escrituras simultáneas | Ya mitigado con WAL + busy_timeout; si persistiera, evaluar MariaDB |
| El ticket no sale por impresora física | Sin impresora ESC/POS configurada | Instalar en el puesto y seleccionar su impresora en el dialogo del navegador |
| La boleta dice "(modo prueba)" | `KAME_MODO=mock` en `.env` | Cambiar a `KAME_MODO=real`, reiniciar y usar **Probar conexión a KAME** en Config |

## 9. Seguridad: usuarios, contraseñas y roles

El sistema exige **ingresar con usuario y contraseña**. Al abrir cualquier
página sin sesión, redirige a `/login`.

### Roles (grupos)
- **Cajero**: emite boletas, abre caja (ingresa el Nro de torniquete/aperturas) y
  cierra su turno. Ve: Venta, Caja (solo Abrir/Cerrar), Historial, Clientes.
- **Supervisor**: retiros de caja e historial completo con cajero y servicio.
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
- Aplicar y verificar la regla del puerto 8000 limitada a la red interna
  descrita en la sección 5.3; no aceptar permisos amplios de Python.


## Servidor local con dos puestos (actualizacion)

Cada servicio admite un solo turno abierto mediante un indice unico parcial en la base de datos. Las ventas y los movimientos pertenecen a la cuenta de su caja. El historial de cajero se filtra en la API; PDF y vistas de impresion comprueban el mismo propietario. Supervisor, Contabilidad y Administrador consultan todas las ventas con cajero y servicio de la caja.

La web imprime desde el navegador cliente. Los antiguos endpoints de deteccion del hardware del servidor y prueba ESC/POS devuelven 410; las rutas de ventas no invocan la impresion ESC/POS. Las claves impresora_* y lector_* ya no se exponen ni se guardan en configuracion compartida. Los ajustes del puesto viven en localStorage (sanitapoint.equipo); no se migran valores globales antiguos para evitar asignar una impresora ajena. El controlador y la seleccion fisica de impresora pertenecen al sistema operativo/navegador local. El modo automatico abre el dialogo del navegador y requiere confirmacion.

Cierra turnos y respalda antes de actualizar. El inicio instala el indice en tablas existentes; si detecta aperturas duplicadas exige conciliar los turnos sin modificarlos automaticamente. Los torniquetes sugeridos para abrir son los del ultimo cierre del mismo servicio, aunque cambie el cajero.
