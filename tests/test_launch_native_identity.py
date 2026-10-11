"""Launch-only Windows absence/identity proof; fake kernel, no OS process calls."""
import ctypes
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock
from microstructure_probe import control as pc

class NativeLaunchIdentityTest(unittest.TestCase):
    def kernel(self, exit_code=259, error=5, open_ok=True, time_ok=True, exit_ok=True):
        stamp=datetime(2026,10,11,tzinfo=timezone.utc)
        ticks=(int(stamp.timestamp()*1000000)+11644473600000000)*10
        def exit_query(handle,pointer):
            ctypes.cast(pointer,ctypes.POINTER(pc._WIN_DWORD)).contents.value=exit_code
            return int(exit_ok)
        def times(handle,created,*others):
            ft=ctypes.cast(created,ctypes.POINTER(pc._FILETIME)).contents
            ft.dwHighDateTime=ticks>>32
            ft.dwLowDateTime=ticks & 0xffffffff
            return int(time_ok)
        return SimpleNamespace(OpenProcess=mock.Mock(return_value=0x100000123 if open_ok else 0),
            GetProcessTimes=mock.Mock(side_effect=times),GetExitCodeProcess=mock.Mock(side_effect=exit_query),
            GetLastError=mock.Mock(return_value=error),TerminateProcess=mock.Mock(),CloseHandle=mock.Mock(return_value=1))

    def run_state(self,kernel,ctime="2026-10-11T00:00:00+00:00"):
        with mock.patch.object(pc.os,"name","nt"),mock.patch.object(pc.ctypes.windll,"kernel32",kernel):
            return pc._default_process_state(12345,ctime)

    def test_known_live_identity(self):
        k=self.kernel()
        self.assertEqual(self.run_state(k),"owned")
        k.CloseHandle.assert_called_once_with(0x100000123)
        self.assertIs(k.GetExitCodeProcess.restype,pc._WIN_BOOL)

    def test_replaced_identity(self):
        k=self.kernel()
        self.assertEqual(self.run_state(k,"other"),"replaced")
        k.TerminateProcess.assert_not_called()
        k.CloseHandle.assert_called_once()

    def test_missing_expected_ctime_unknown(self):
        k=self.kernel()
        self.assertEqual(self.run_state(k,None),"unknown")
        k.CloseHandle.assert_called_once()

    def test_absent_pid_error_87(self):
        k=self.kernel(open_ok=False,error=87)
        self.assertEqual(self.run_state(k),"gone")
        k.CloseHandle.assert_not_called()

    def test_access_denied_unknown(self):
        k=self.kernel(open_ok=False,error=5)
        self.assertEqual(self.run_state(k),"unknown")

    def test_exited_handle_proves_gone(self):
        k=self.kernel(exit_code=0)
        self.assertEqual(self.run_state(k),"gone")
        k.CloseHandle.assert_called_once()

    def test_failed_exit_query_unknown(self):
        k=self.kernel(exit_ok=False)
        self.assertEqual(self.run_state(k),"unknown")
        k.CloseHandle.assert_called_once()

    def test_failed_ctime_query_unknown(self):
        k=self.kernel(time_ok=False)
        self.assertEqual(self.run_state(k),"unknown")
        k.CloseHandle.assert_called_once()
