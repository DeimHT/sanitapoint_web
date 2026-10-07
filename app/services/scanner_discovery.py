"""Keyboard/HID candidates, not a claim that every device is a scanner."""
import json
import subprocess
import sys


def detectar_lectores():
    if sys.platform != "win32":
        return {"lectores": [], "mensaje": "Usa el modo USB teclado. La lista de dispositivos está disponible en Windows."}
    script = r"""
    $ErrorActionPreference = 'Stop'
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $devices = @(Get-PnpDevice -PresentOnly | Where-Object {
      $_.InstanceId -match '^(USB|HID)\\VID_' -and
      ($_.Class -eq 'Keyboard' -or $_.FriendlyName -match 'scanner|barcode|lector|scan')
    } | Select-Object FriendlyName, InstanceId)
    ConvertTo-Json -InputObject $devices -Compress
    """
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, encoding="utf-8", errors="replace", timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError()
        rows = json.loads(result.stdout)
        return {"lectores": [{"id": r["InstanceId"], "nombre": r["FriendlyName"] + " — " + r["InstanceId"].split("\\")[1]} for r in rows],
                "mensaje": "Incluye teclados USB: selecciona el lector y comprueba una lectura en el campo de prueba."}
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyError):
        return {"lectores": [], "mensaje": "No se pudieron consultar los dispositivos. Puedes usar el modo USB teclado sin seleccionar un modelo."}
