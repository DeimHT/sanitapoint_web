import unittest
from unittest.mock import MagicMock, patch

from app.services import ticket_printer
from app.services.printer_discovery import _normalizar, detectar_impresoras


class PrinterTests(unittest.TestCase):
    def test_free_pass_never_reaches_pdf_or_printer(self):
        with patch.object(ticket_printer, "generar_ticket_pdf") as pdf, \
                patch.object(ticket_printer, "imprimir_escpos") as send:
            result = ticket_printer.emitir_ticket(MagicMock(), "T1", "Baño", 0,
                                                  "efectivo", None, "omitido", None, True)
            self.assertFalse(result["impreso_termica"])
            self.assertIsNone(result["pdf_path"])
            pdf.assert_not_called()
            send.assert_not_called()
        with patch.object(ticket_printer, "get_config") as config:
            ok, _ = ticket_printer.imprimir_escpos(MagicMock(), es_pase_libre=True)
            self.assertFalse(ok)
            config.assert_not_called()
        with self.assertRaises(ValueError):
            ticket_printer.generar_ticket_pdf(MagicMock(), "T1", "Baño", 0,
                                              "efectivo", None, "omitido", None, True)

    def test_usb_passes_windows_backend_and_timeout(self):
        values = {"impresora_tipo": "usb", "impresora_usb_vendor": "0x0483",
                  "impresora_usb_product": "0x5720"}
        backend = object()
        with patch.object(ticket_printer, "get_config", side_effect=lambda db, k, d="": values.get(k, d)), \
                patch("app.services.ticket_printer.sys.platform", "win32"), \
                patch("libusb_package.get_libusb1_backend", return_value=backend), \
                patch("escpos.printer.Usb") as usb:
            ok, _ = ticket_printer.imprimir_escpos(
                MagicMock(), ticket_num="T1", servicio_nombre="Ducha", monto=2000,
                forma_pago="efectivo", folio_kame=None, estado_kame="mock",
                rut_cliente=None, es_pase_libre=False)
            self.assertTrue(ok)
            usb.assert_called_once_with(0x0483, 0x5720, usb_args={"backend": backend}, timeout=5000)

    def test_discovery_filters_virtual_and_extracts_usb_ids(self):
        printers = _normalizar({"installed": [{"Name": "Microsoft Print to PDF"},
                                              {"Name": "ONE R200"}],
                               "usb": [{"FriendlyName": "USB Printing Support",
                                        "InstanceId": r"USB\VID_0483&PID_5720\123"}]})
        self.assertEqual(len(printers), 2)
        self.assertEqual(printers[0]["nombre_windows"], "ONE R200")
        self.assertEqual(printers[1]["vendor"], "0x0483")
        self.assertEqual(printers[1]["product"], "0x5720")

    def test_discovery_timeout_returns_actionable_message(self):
        import subprocess
        with patch("app.services.printer_discovery.sys.platform", "win32"), \
                patch("app.services.printer_discovery.subprocess.run", side_effect=subprocess.TimeoutExpired("powershell", 20)):
            result = detectar_impresoras()
        self.assertEqual(result["impresoras"], [])
        self.assertTrue(result["mensaje"])

    def test_windows_selection_uses_saved_name(self):
        values = {"impresora_tipo": "windows", "impresora_nombre": "ONE R200"}
        with patch.object(ticket_printer, "get_config", side_effect=lambda db, k, d="": values.get(k, d)), \
                patch("escpos.printer.Win32Raw") as windows:
            ok, _ = ticket_printer.imprimir_escpos(
                MagicMock(), ticket_num="T1", servicio_nombre="Ducha", monto=2000,
                forma_pago="efectivo", folio_kame=None, estado_kame="mock",
                rut_cliente=None, es_pase_libre=False)
            self.assertTrue(ok)
            windows.assert_called_once_with("ONE R200")
            windows.return_value.close.assert_called_once()

    def test_network_send_and_close_on_failure(self):
        values = {"impresora_tipo": "red", "impresora_ip": "192.168.1.50"}
        args = dict(ticket_num="T000001", servicio_nombre="Ducha", monto=2000,
                    forma_pago="efectivo", folio_kame=None, estado_kame="mock",
                    rut_cliente=None, es_pase_libre=False)
        with patch.object(ticket_printer, "get_config", side_effect=lambda db, k, d="": values.get(k, d)), \
                patch("escpos.printer.Network") as network:
            printer = network.return_value
            ok, _ = ticket_printer.imprimir_escpos(MagicMock(), **args)
            self.assertTrue(ok)
            network.assert_called_once_with("192.168.1.50", port=9100, timeout=5)
            printer.cut.assert_called_once()
            printer.close.assert_called_once()
            printer.reset_mock()
            printer.image.side_effect = OSError("offline")
            ok, message = ticket_printer.imprimir_escpos(MagicMock(), **args)
            self.assertFalse(ok)
            self.assertIn("offline", message)
            printer.close.assert_called_once()

    def test_manual_mode_does_not_print_on_sale(self):
        with patch.object(ticket_printer, "generar_ticket_pdf", return_value="ticket.pdf"), \
                patch.object(ticket_printer, "get_config", return_value="0"), \
                patch.object(ticket_printer, "imprimir_escpos") as send:
            result = ticket_printer.emitir_ticket(MagicMock(), "T1", "Ducha", 2000,
                                                  "efectivo", None, "mock", None, False)
            self.assertFalse(result["impreso_termica"])
            send.assert_not_called()
