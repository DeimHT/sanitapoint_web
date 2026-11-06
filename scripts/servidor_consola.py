"""Servidor asociado a la ventana del BAT, sin depender de su salida de texto."""
import ctypes
from ctypes import wintypes
from datetime import datetime
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[1]


def desactivar_seleccion_rapida():
    if os.name != 'nt':
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.SetConsoleMode.restype = wintypes.BOOL
    entrada = kernel.GetStdHandle(-10 & 0xffffffff)
    modo = wintypes.DWORD()
    if not kernel.GetConsoleMode(entrada, ctypes.byref(modo)):
        return False
    # ENABLE_EXTENDED_FLAGS permite desactivar ENABLE_QUICK_EDIT_MODE.
    return bool(kernel.SetConsoleMode(entrada, (modo.value | 0x0080) & ~0x0040))


def registrar(log, mensaje, pantalla=None):
    for linea in mensaje.splitlines():
        registro = f'[{datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")}] {linea}'
        log.write(registro + '\n')
        log.flush()
        if pantalla is not None:
            try:
                pantalla.put_nowait(registro)
            except queue.Full:
                pass  # El archivo conserva todo aunque la consola quede detenida.


def mostrar_consola(pantalla):
    while True:
        try:
            print(pantalla.get(), flush=True)
        except OSError:
            return


def supervisar(log, pantalla=None):
    comando = [sys.executable, '-u', '-m', 'uvicorn', 'app.main:app',
               '--host', '0.0.0.0', '--port', '8000', '--reload',
               '--reload-dir', str(ROOT / 'app'), '--no-use-colors']
    # Sigue asociado a esta consola: cerrar su ventana termina los procesos.
    # Un grupo nuevo evita que Ctrl+C accidental alcance al servidor.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    while True:
        registrar(log, 'Inicio servidor', pantalla)
        try:
            entorno = os.environ.copy()
            entorno['PYTHONIOENCODING'] = 'utf-8'
            with subprocess.Popen(comando, cwd=ROOT, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding='utf-8', errors='replace',
                                  env=entorno, creationflags=flags) as proceso:
                for linea in proceso.stdout:
                    registrar(log, linea.rstrip('\r\n'), pantalla)
                codigo = proceso.wait()
            registrar(log, f'Servidor termino con codigo {codigo}. Reintento en 3 segundos.', pantalla)
        except OSError as error:
            registrar(log, f'No se pudo iniciar: {error}. Reintento en 3 segundos.', pantalla)
        time.sleep(3)


def main():
    desactivar_seleccion_rapida()
    if os.name == 'nt':
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    carpeta = ROOT / 'logs'
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f'servidor-consola-{datetime.now():%Y-%m-%d}.log'
    print('Servidor protegido contra pausas por seleccion de texto.', flush=True)
    print(f'Registro de actividad y errores: {ruta}', flush=True)
    print('Puedes minimizar esta ventana. Para apagar, cierrala completamente.', flush=True)
    # La pantalla tiene su propio hilo y cola limitada: nunca frena el registro
    # a disco ni el drenaje de la salida del servidor si Windows pausa la consola.
    pantalla = queue.Queue(maxsize=1000)
    threading.Thread(target=mostrar_consola, args=(pantalla,), daemon=True).start()
    with ruta.open('a', encoding='utf-8') as log:
        supervisar(log, pantalla)


if __name__ == '__main__':
    main()
