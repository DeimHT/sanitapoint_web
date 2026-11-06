import io
import queue
import unittest
from unittest.mock import Mock, patch

from scripts import servidor_consola as servidor


class FinPrueba(Exception):
    pass


class ServidorConsolaTests(unittest.TestCase):
    def test_desactiva_quick_edit_sin_alterar_otros_modos(self):
        kernel = Mock()
        kernel.GetStdHandle.return_value = 123
        def leer(handle, salida):
            salida._obj.value = 0x0040 | 0x0007
            return True
        kernel.GetConsoleMode.side_effect = leer
        kernel.SetConsoleMode.return_value = True
        with patch.object(servidor.os, 'name', 'nt'), \
             patch.object(servidor.ctypes, 'WinDLL', return_value=kernel, create=True):
            self.assertTrue(servidor.desactivar_seleccion_rapida())
        kernel.SetConsoleMode.assert_called_once_with(123, 0x0080 | 0x0007)

    def test_consola_no_disponible_no_intenta_cambiar_modo(self):
        kernel = Mock()
        kernel.GetConsoleMode.return_value = False
        with patch.object(servidor.os, 'name', 'nt'), \
             patch.object(servidor.ctypes, 'WinDLL', return_value=kernel, create=True):
            self.assertFalse(servidor.desactivar_seleccion_rapida())
        kernel.SetConsoleMode.assert_not_called()

    def test_salida_independiente_de_consola_y_reinicio_del_proceso(self):
        log = io.StringIO()
        proceso = Mock()
        proceso.stdout = ['INFO: GET /api/ventas 200 OK\n', '[KAME] Folio 456\n']
        proceso.wait.return_value = 1
        administrador = Mock()
        administrador.__enter__ = Mock(return_value=proceso)
        administrador.__exit__ = Mock(return_value=False)
        with patch.object(servidor.subprocess, 'Popen', return_value=administrador) as iniciar, \
             patch.object(servidor.time, 'sleep', side_effect=[None, FinPrueba]):
            with self.assertRaises(FinPrueba):
                servidor.supervisar(log)
        self.assertEqual(iniciar.call_count, 2)
        opciones = iniciar.call_args.kwargs
        self.assertEqual(opciones['stdout'], servidor.subprocess.PIPE)
        self.assertEqual(opciones['stderr'], servidor.subprocess.STDOUT)
        self.assertEqual(opciones['stdin'], servidor.subprocess.DEVNULL)
        if servidor.os.name == 'nt':
            self.assertEqual(opciones['creationflags'], servidor.subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertIn('--reload', iniciar.call_args.args[0])
        self.assertIn('codigo 1', log.getvalue())
        self.assertRegex(log.getvalue(), r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\] INFO: GET')
        self.assertIn('[KAME] Folio 456', log.getvalue())

    def test_error_de_arranque_se_registra_y_reintenta(self):
        log = io.StringIO()
        with patch.object(servidor.subprocess, 'Popen', side_effect=OSError('fallo de prueba')), \
             patch.object(servidor.time, 'sleep', side_effect=FinPrueba):
            with self.assertRaises(FinPrueba):
                servidor.supervisar(log)
        self.assertIn('fallo de prueba', log.getvalue())

    def test_consola_bloqueada_no_bloquea_registro(self):
        pantalla = queue.Queue(maxsize=1)
        log = io.StringIO()
        servidor.registrar(log, 'Primera accion', pantalla)
        servidor.registrar(log, 'Segunda accion\nTercera accion', pantalla)
        self.assertEqual(pantalla.qsize(), 1)
        self.assertIn('Segunda accion', log.getvalue())
        self.assertIn('Tercera accion', log.getvalue())
        self.assertEqual(len(log.getvalue().splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
