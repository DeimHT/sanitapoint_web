"""Read-only discovery on the computer running the server."""
import json
import re
import subprocess
import sys


def detectar_impresoras():
    if sys.platform != "win32":
        return {"impresoras": [], "mensaje": "La detección automática está disponible en Windows. Puedes configurar la conexión manualmente."}
    script = r"""
    $ErrorActionPreference = 'Stop'
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $installed = @(Get-CimInstance Win32_Printer | Select-Object Name, PortName)
    $usb = @(Get-PnpDevice -PresentOnly | Where-Object {
        $_.InstanceId -match '^USB\\VID_' -and
        ($_.FriendlyName -match 'print|impres|R200' -or $_.Class -eq 'Printer')
    } | Select-Object FriendlyName, InstanceId)
    @{installed=$installed; usb=$usb} | ConvertTo-Json -Depth 4 -Compress
    """
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, encoding="utf-8", errors="replace", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            return {"impresoras": [], "mensaje": "Windows no permitió consultar las impresoras. Revisa los permisos del servidor."}
        return {"impresoras": _normalizar(json.loads(result.stdout)), "mensaje": ""}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"impresoras": [], "mensaje": "No se pudieron consultar las impresoras. Intenta actualizar la lista."}


def _normalizar(data):
    printers = []
    for row in data.get("installed", []):
        name = row["Name"]
        if any(word in name.lower() for word in ("onenote", "print to pdf", "xps", "fax")):
            continue
        printers.append({"id": "windows:" + name, "nombre": name + " (Windows)",
                         "tipo": "windows", "nombre_windows": name})
    seen = set()
    for row in data.get("usb", []):
        match = re.search(r"VID_([0-9a-f]{4})&PID_([0-9a-f]{4})", row["InstanceId"], re.I)
        if not match or match.group(0).lower() in seen:
            continue
        seen.add(match.group(0).lower())
        vid, pid = ("0x" + value.lower() for value in match.groups())
        printers.append({"id": f"usb:{vid}:{pid}", "nombre": f"{row['FriendlyName']} ({vid}:{pid}, USB directo)",
                         "tipo": "usb", "vendor": vid, "product": pid})
    return printers
