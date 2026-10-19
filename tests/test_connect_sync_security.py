import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-connect/files/usr/share/reyos/connect/providers/sync_provider.py"
spec = importlib.util.spec_from_file_location("sync_provider", SOURCE)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

class SyncSecurityTests(unittest.TestCase):
    def test_loopback(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "127.0.0.1:8384", False)):
            self.assertEqual(sync._base_url(), "http://127.0.0.1:8384")
    def test_reject_remote(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "example.com:8384", False)):
            with self.assertRaises(sync.SyncApiError): sync._base_url()
    def test_reject_malformed(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "localhost:bad", False)):
            with self.assertRaises(sync.SyncApiError): sync._base_url()
    def test_ipv6_loopback(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "[::1]:8384", False)):
            self.assertEqual(sync._base_url(), "http://[::1]:8384")
    def test_wildcard_maps_to_ipv4_loopback(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "0.0.0.0:8384", True)):
            self.assertEqual(sync._base_url(), "https://127.0.0.1:8384")
    def test_reject_lan_address(self):
        with patch.object(sync, "_read_config_xml", return_value=("key", "192.168.1.5:8384", False)):
            with self.assertRaises(sync.SyncApiError): sync._base_url()
    def test_refuse_home_and_root(self):
        with patch.object(sync, "_put") as put:
            for path in ("~", "/"):
                with self.assertRaises(ValueError): sync.add_folder("f", "F", path, [], "sendreceive")
            put.assert_not_called()
    def test_escape_path(self):
        self.assertEqual(sync._resource_id("folder/one"), "folder%2Fone")
        with self.assertRaises(ValueError): sync._resource_id("bad\nname")

if __name__ == "__main__": unittest.main()
