# SanitaPoint Web

SanitaPoint ayuda a llevar el cobro de **baños y duchas**: registra las ventas, entrega tickets y permite revisar el dinero y los accesos de cada turno. También se conecta con KAME para emitir boletas electrónicas.

Se usa desde el navegador. Un computador principal mantiene el sistema funcionando y los equipos de caja se conectan a él por la misma red del local.

## Cómo entrar

1. En el computador principal, abre la carpeta de SanitaPoint y haz doble clic en **`iniciar_servidor.bat`**.
2. Espera a que termine de iniciar. **Deja esa ventana abierta mientras se esté usando el sistema.**
3. En ese computador, abre [SanitaPoint](http://localhost:8000). Si la página todavía no carga, espera unos segundos y vuelve a intentarlo.
4. En los otros equipos, abre en el navegador la dirección que aparece en la ventana de inicio. Será parecida a `http://192.168.1.10:8000`; usa la que muestre tu equipo.
5. Ingresa con tu usuario y contraseña.

Puedes guardar la dirección en los favoritos del navegador para encontrarla más rápido.

### Si es la primera vez

La persona encargada de instalar el sistema debe tener **Python 3.11 o superior** en el computador principal, con la opción **“Add Python to PATH”** marcada durante su instalación. Al abrir SanitaPoint por primera vez, se descargan los componentes necesarios; hace falta internet y puede tardar unos minutos.

En una instalación nueva, la cuenta inicial es:

| Usuario | Contraseña |
|---|---|
| `admin` | `admin123` |

**Cambia esa contraseña al entrar:** ve a **Cuentas**, edita la cuenta `admin` y escribe una nueva contraseña. Crea una cuenta para cada persona que vaya a trabajar con el sistema.

Antes de comenzar a vender, pide al administrador que revise los precios, los datos del negocio, la impresora y la conexión con KAME. Para emitir boletas reales, el acceso a KAME debe estar configurado y el computador principal debe tener internet.

En Mac, el archivo de inicio es **`iniciar_servidor.command`**. Si no abre, solicita ayuda a quien instaló el sistema.

## El trabajo de cada día

### 1. Abrir tu caja

Entra con tu propia cuenta y ve a **Caja → Abrir caja**. Completa:

- **Caja Inicial:** el dinero en efectivo con el que comienzas.
- **Torniquete Baño Inicial:** el número que marca el contador del torniquete de baño.
- **Torniquete Ducha Inicial:** el número que marca el contador del torniquete de ducha.

Pulsa **Abrir**. Cada cajero trabaja con su propio turno; necesitas tener la caja abierta para registrar ventas.

### 2. Registrar una venta

1. Entra a **Venta**.
2. Elige la forma de pago: **Efectivo** o **Tarjetas**.
3. Revisa el precio y pulsa el servicio: **Uso de Baño** o **Ducha**. **Al pulsarlo se registra la venta.**
4. Revisa el resultado en pantalla: allí se indica el ticket, el estado de la boleta y si se envió a la impresora.

Puedes abrir el comprobante con **Ver PDF**. En **Historial** puedes consultar las ventas y volver a obtener sus tickets.

Si aparece un error de KAME, **la venta puede haber quedado registrada aunque la boleta no se haya emitido**. Revisa el Historial y avisa al encargado para que compruebe el estado en KAME antes de repetir la operación.

Si el resultado dice **“modo prueba”**, corresponde a una boleta de prueba. Pide al administrador que revise la configuración antes de usar el sistema para ventas reales.

### 3. Registrar un pase libre

Los pases libres permiten registrar un acceso gratuito al **baño** para una persona registrada en **Clientes**.

1. En **Venta**, pulsa **Registrar PASE LIBRE**.
2. Busca a la persona por su nombre o RUT y pulsa **Elegir**.
3. Si se ofrecen varios servicios de baño, selecciona el que corresponda.
4. Comprueba que aparezca el aviso de pase registrado.

El sistema controla el máximo de pases diarios por persona y avisa cuando se alcanza el límite. El administrador puede ajustar ese límite en **Config**.

### 4. Registrar un retiro de dinero

Cuando se saca dinero de una caja durante el turno, el **supervisor o administrador** debe registrarlo en **Caja → Retiro**: selecciona la caja del usuario, indica el monto y el motivo, y pulsa **Retirar**.

Así, ese dinero se tiene en cuenta al revisar el cierre.

### 5. Cerrar tu turno

1. Cuenta el efectivo que queda en tu caja.
2. Ve a **Caja → Cerrar caja**.
3. En **Caja Final**, escribe el efectivo contado.
4. Ingresa las lecturas finales de los torniquetes de baño y ducha.
5. Pulsa **Cerrar** y revisa el resumen.

El sistema compara el efectivo contado con lo que debería haber: dinero inicial, más ventas en efectivo, menos retiros. Las transferencias no se suman al efectivo de la caja.

También compara los accesos registrados con el avance de los torniquetes. Si hay un faltante, sobrante o diferencia de accesos, revísalo con el encargado; la diferencia queda registrada.

Al terminar, pulsa **Salir** para cerrar tu sesión. Salir de la cuenta no reemplaza el cierre de caja.

## Qué puede hacer cada persona

El menú muestra las opciones disponibles para tu cuenta.

| Tipo de cuenta | Funciones principales |
|---|---|
| **Cajero** | Abrir y cerrar su caja, registrar ventas y pases libres, consultar el historial y gestionar clientes. |
| **Supervisor** | Registrar retiros de dinero de las cajas. |
| **Contabilidad** | Consultar historial, reportes y cierres; administrar cuentas y contraseñas. |
| **Administrador** | Acceder a todas las funciones y ajustar precios, impresora y configuración. |

**Clientes** contiene las personas que usan los servicios y sus pases. **Cuentas** contiene las personas que ingresan a trabajar al sistema. Solo un administrador puede crear o modificar cuentas administradoras.

Si olvidaste tu contraseña, pide a Contabilidad o al administrador que la cambie desde **Cuentas**. Para una cuenta administradora, debe hacerlo otro administrador.

## Consultar ventas y cierres

- **Historial:** busca ventas anteriores y consulta sus tickets.
- **Cierres:** revisa los turnos y pulsa **Ver cuadre** para ver el detalle del dinero y los accesos.
- **Reportes:** elige un día, un rango de fechas o un servicio y descarga el informe en **PDF** o **Excel**. También puedes obtener un reporte anual.

## Guardar una copia de los datos

Los datos se guardan en el computador principal, dentro de la carpeta **`data`** de SanitaPoint. Guarda una copia al finalizar la jornada:

1. Comprueba que todas las cajas hayan terminado y que nadie esté usando el sistema.
2. Detén SanitaPoint cerrando la ventana de inicio del computador principal.
3. Copia la carpeta completa **`data`** a un pendrive o a otro lugar de respaldo. Ponle la fecha para identificarla.
4. Vuelve a iniciar SanitaPoint si necesitas seguir trabajando.

Esta copia incluye los registros, los tickets guardados y otros archivos necesarios para el funcionamiento. **No borres ni cambies los archivos de la carpeta original.** Si necesitas recuperar una copia, pide ayuda al encargado antes de reemplazar los datos actuales.

## Si algo no funciona

| Problema | Qué hacer |
|---|---|
| No abre la página | Comprueba que el computador principal esté encendido, que la ventana de SanitaPoint siga abierta y que ambos equipos estén conectados a la misma red. Usa la dirección indicada al iniciar. |
| Aparece “No se encontró Python” | Pide al encargado que revise la instalación de Python en el computador principal. |
| No puedes registrar una venta | Revisa que hayas abierto tu caja con la cuenta que estás usando. |
| El ticket no sale en papel | Revisa que la impresora esté encendida, conectada y con papel. Abre el PDF de la venta y pide al administrador que revise la impresora en **Config**. No registres otra venta solo para imprimir. |
| Aparece un error de KAME | Revisa el Historial y avisa al encargado. Antes de repetir la venta, hay que comprobar si KAME recibió la boleta. |
| No aparece una opción del menú | Puede que tu cuenta no tenga permiso para usarla. Consulta al administrador. |

Para instalación manual y detalles técnicos, la persona encargada puede consultar la [guía técnica](GUIA.md).


## Configurar la impresora ONE R200

En Windows, **Config → Actualizar lista** detecta impresoras instaladas y dispositivos USB del computador principal. Selecciona la R200 y pulsa **Imprimir prueba**: los datos se completan y guardan automáticamente. Si aparece con su nombre en Windows, usa esa opción para imprimir mediante su controlador. Si solo aparece como «Compatibilidad con impresoras USB», la conexión está detectada pero puede faltar el controlador necesario. La detección no instala ni cambia controladores.

### Importar cuentas de acceso desde Excel

En **Cuentas → Importar Excel**, descarga la plantilla y completa la hoja **Cuentas** con las columnas `usuario`, `nombre`, `rol`, `contrasena`. Los roles permitidos son `cajero`, `supervisor`, `contabilidad` y `administrador`; solo un administrador puede crear cuentas administradoras. Se admiten hasta 500 cuentas y archivos de hasta 1 MB.

Pulsa **Revisar archivo** para ver las cuentas antes de crearlas. Las contraseñas no se muestran. Si hay errores, corrige las filas indicadas y vuelve a cargar el archivo; no se crea ninguna cuenta hasta que todas sean válidas. Luego pulsa **Crear cuentas**. Las cuentas existentes no se modifican y las nuevas contraseñas se almacenan mediante hash.

### Personas con pase libre y lector USB

En **Pases libres** puedes **Ingresar datos** manualmente o **Escanear cédula**. Usa una pistola que lea QR en modo USB teclado (HID), con Enter al terminar. La lectura se recibe en el campo enfocado del equipo donde está abierto el navegador. Puedes pegar el contenido para probar sin hardware. Se reconocen RUN/RUT y nombre cuando vienen como parámetros de la URL o campos JSON; si no vienen, completa los datos manualmente. No se abre el enlace ni se consulta Registro Civil.

En **Configuración → Lector de cédulas**, activa/desactiva la lectura, consulta dispositivos candidatos del computador principal, guarda el dispositivo de referencia y prueba el QR sin crear una persona. Windows puede mostrar lectores como teclados genéricos: esta lista también incluye teclados y no vincula las pulsaciones exclusivamente a un dispositivo. Revisa los datos antes de guardar; una lectura no otorga un pase automáticamente.

Después de actualizar el sistema, cierra la ventana del servidor y abre de nuevo **iniciar_servidor.bat**. El inicio instala el soporte Windows si falta. Recarga la página: un aviso «Not Found» en impresión o detección indica que debes comprobar que el servidor esté ejecutando esta versión.

1. Conecta la R200 por Ethernet a la red del computador principal y averigua su IP con la utilidad o documentación de la impresora. Mantén esa dirección fija o reservada en el router.
2. En **Config → Ticket e impresora térmica**, selecciona **Red (ESC/POS)**, ingresa la IP y el puerto configurado en la impresora (habitualmente **9100**).
3. Elige **Solo con botón Imprimir boleta** si quieres imprimir después de registrar cada venta. La opción **Automática** envía una copia al registrar la venta; pulsar el botón después envía otra copia.
4. Pulsa **Imprimir prueba**: guarda los ajustes de impresora y envía un ticket de prueba sin registrar una venta ni emitir en KAME.
5. Registra una venta y pulsa **Imprimir boleta**. El botón imprime la venta existente, sin volver a cobrar ni emitir una boleta en KAME. Si falla, puedes volver a intentarlo.

Para USB, la impresora debe estar conectada al computador principal que ejecuta Python. Ingresa sus identificadores **VID** y **PID** reales en hexadecimal (en Windows, Administrador de dispositivos → Propiedades → Detalles → Id. de hardware). El envío USB usa libusb y puede necesitar un controlador compatible; Ethernet suele ser más sencillo.

El envío se realiza desde el servidor: si está alojado fuera del local necesita acceso a la red de la impresora. Conectar la impresora al equipo del navegador no le da acceso al servidor. El mensaje «enviado» confirma el envío de datos; comprueba físicamente el papel. El contenido conserva el estado de KAME y señala si es una prueba o un comprobante pendiente de emisión.

Al ingresar con Baño 2, los turnos nuevos no solicitan lecturas de ducha ni permiten vender ese servicio. Baño 1 mantiene las lecturas de baño y ducha. El servicio queda guardado en la caja durante todo el turno.
