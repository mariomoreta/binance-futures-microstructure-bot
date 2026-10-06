import os
import unittest
from unittest import mock

from microstructure_probe.config import load_config


class ConfigTest(unittest.TestCase):
    def test_default_configuration_loads_three_symbols(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config("config/probe.json")
        self.assertEqual(config.symbols, ("BTCUSDT", "ETHUSDT", "SOLUSDT"))
        self.assertEqual(config.clock_sync.interval_seconds, 600)
        self.assertEqual(config.clock_sync.samples, 5)

    def test_non_observe_mode_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, {"BOT_MODE": "live"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "no esta permitido"):
                load_config("config/probe.json")


if __name__ == "__main__":
    unittest.main()
