import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/control-center/remote_play.py"
spec = importlib.util.spec_from_file_location("remote_play", SOURCE)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)

ADMIN = ROOT / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/bin/reyos-admin"
admin_spec = importlib.util.spec_from_loader("reyos_admin", loader=None)
admin = importlib.util.module_from_spec(admin_spec)
exec(compile(ADMIN.read_text(), str(ADMIN), "exec"), admin.__dict__)

VAINFO_INTEL = """vainfo: Driver version: Intel iHD driver for Intel(R) Gen Graphics - 25.3.4
      VAProfileH264Main               : VAEntrypointVLD
      VAProfileH264Main               : VAEntrypointEncSlice
      VAProfileH264High               : VAEntrypointVLD
      VAProfileH264High               : VAEntrypointEncSlice
      VAProfileHEVCMain               : VAEntrypointVLD
      VAProfileHEVCMain               : VAEntrypointEncSlice
      VAProfileHEVCMain10             : VAEntrypointVLD
"""
VAINFO_DECODE_ONLY = """vainfo: Driver version: Mesa Gallium driver
      VAProfileH264High               : VAEntrypointVLD
      VAProfileHEVCMain               : VAEntrypointVLD
"""


class ConfTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.conf = Path(self.dir.name) / "sunshine.conf"

    def tearDown(self):
        self.dir.cleanup()

    def test_new_file(self):
        self.assertTrue(rp.write_conf(rp.FORCED, {"max_bitrate": "15000"}, self.conf))
        conf = rp.read_conf(self.conf)
        self.assertEqual(conf["origin_web_ui_allowed"], "pc")
        self.assertEqual(conf["upnp"], "disabled")
        self.assertEqual(conf["max_bitrate"], "15000")

    def test_forced_overrides_user_but_defaults_dont(self):
        self.conf.write_text("# mine\norigin_web_ui_allowed = wan\nmax_bitrate = 30000\nfps = [60]\nupnp=enabled\n")
        rp.write_conf(rp.FORCED, {"max_bitrate": "15000", "capture": "kwin"}, self.conf)
        conf = rp.read_conf(self.conf)
        self.assertEqual(conf["origin_web_ui_allowed"], "pc")
        self.assertEqual(conf["upnp"], "disabled")
        self.assertEqual(conf["max_bitrate"], "30000")
        self.assertEqual(conf["capture"], "kwin")
        self.assertEqual(conf["fps"], "[60]")
        self.assertIn("# mine", self.conf.read_text())

    def test_unchanged_is_not_rewritten(self):
        rp.write_conf(rp.FORCED, {}, self.conf)
        self.assertFalse(rp.write_conf(rp.FORCED, {}, self.conf))

    def test_commented_key_is_not_a_setting(self):
        self.conf.write_text("# upnp = enabled\n")
        self.assertNotIn("upnp", rp.read_conf(self.conf))


class AppsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.apps = Path(self.dir.name) / "apps.json"
        self.patches = [patch.object(rp, "APPS", self.apps), patch.object(rp, "_games_cover", return_value="")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def test_adds_games_after_desktop_and_drops_xrandr_sample(self):
        self.apps.write_text(json.dumps({"apps": [
            {"name": "Desktop"},
            {"name": "Low Res Desktop", "prep-cmd": [{"do": "xrandr --output HDMI-1 --mode 1920x1080", "undo": ""}]},
            {"name": "Steam Big Picture", "detached": ["setsid steam steam://open/bigpicture"]}]}))
        self.assertTrue(rp.ensure_games_app())
        names = [a["name"] for a in json.loads(self.apps.read_text())["apps"]]
        self.assertEqual(names, ["Desktop", "ReyOS Games", "Steam Big Picture"])
        self.assertEqual(json.loads(self.apps.read_text())["apps"][1]["detached"], [rp.GAMES_CMD])
        self.assertFalse(rp.ensure_games_app())

    def test_keeps_users_own_entries(self):
        self.apps.write_text(json.dumps({"apps": [{"name": "Low Res Desktop", "cmd": "my-script"}]}))
        rp.ensure_games_app()
        names = [a["name"] for a in json.loads(self.apps.read_text())["apps"]]
        self.assertIn("Low Res Desktop", names)

    def test_no_file(self):
        rp.ensure_games_app()
        names = [a["name"] for a in json.loads(self.apps.read_text())["apps"]]
        self.assertEqual(names, ["Desktop", "ReyOS Games"])


class EncoderTests(unittest.TestCase):
    def run_vainfo(self, out):
        with patch.object(rp.shutil, "which", return_value="/usr/bin/vainfo"), \
             patch.object(rp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, out, "")):
            return rp.vaapi_encoders("/dev/dri/renderD128")

    def test_intel_encodes(self):
        self.assertEqual(self.run_vainfo(VAINFO_INTEL), ["H.264", "HEVC"])

    def test_decode_only(self):
        self.assertEqual(self.run_vainfo(VAINFO_DECODE_ONLY), [])

    def test_encode_node_skips_nvidia(self):
        nodes = [{"path": "/dev/dri/renderD128", "vendor": "nvidia", "driver": "nvidia", "name": ""},
                 {"path": "/dev/dri/renderD129", "vendor": "intel", "driver": "i915", "name": ""}]
        with patch.object(rp, "render_nodes", return_value=nodes), \
             patch.object(rp, "vaapi_encoders", side_effect=lambda n: ["H.264"]):
            self.assertEqual(rp.encode_node()["path"], "/dev/dri/renderD129")

    def test_report_from_log(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "sunshine.log"
            log.write_text("Info: Encoder [nvenc] failed\nInfo: Encoder [vulkan] failed\n"
                           "Info: Found H.264 encoder: h264_vaapi [vaapi]\nInfo: Found HEVC encoder: hevc_vaapi [vaapi]\n")
            with patch.object(rp, "LOG", log), patch.object(rp, "render_nodes", return_value=[]):
                report = rp.encoder_report()
        self.assertEqual(report["inUse"], "H.264 with h264_vaapi")
        self.assertEqual(report["failed"], ["nvenc", "vulkan"])
        self.assertFalse(report["software"])

    def test_software_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "sunshine.log"
            log.write_text("Info: Found H.264 encoder: libx264 [software]\n")
            with patch.object(rp, "LOG", log), patch.object(rp, "render_nodes", return_value=[]):
                self.assertTrue(rp.encoder_report()["software"])


class NetworkTests(unittest.TestCase):
    def test_local_addresses_skip_vpn_and_bridges(self):
        out = ("2: wlp4s0    inet 192.168.68.52/22 brd 192.168.71.255 scope global dynamic wlp4s0\n"
               "3: tailscale0    inet 100.101.102.103/32 scope global tailscale0\n"
               "4: virbr0    inet 192.168.122.1/24 scope global virbr0\n")
        with patch.object(rp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, out, "")):
            self.assertEqual(rp.local_addresses(), [{"interface": "wlp4s0", "address": "192.168.68.52"}])

    def test_tailscale_direct_and_relayed(self):
        data = {"BackendState": "Running", "Self": {"TailscaleIPs": ["100.64.0.5", "fd7a::5"]},
                "Peer": {"a": {"HostName": "iPhone", "Online": True, "CurAddr": "1.2.3.4:41641", "Relay": "nyc"},
                         "b": {"HostName": "raspi5", "Online": True, "CurAddr": "", "Relay": "dfw"},
                         "c": {"HostName": "old", "Online": False}}}
        with patch.object(rp.shutil, "which", return_value="/usr/bin/tailscale"), \
             patch.object(rp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(data), "")):
            st = rp.tailscale_status()
        self.assertEqual(st["address"], "100.64.0.5")
        self.assertEqual({p["name"]: p["path"] for p in st["peers"]}, {"iPhone": "direct", "raspi5": "relayed"})

    def test_tailscale_signed_out(self):
        with patch.object(rp.shutil, "which", return_value="/usr/bin/tailscale"), \
             patch.object(rp.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, '{"BackendState": "NeedsLogin"}', "")):
            self.assertEqual(rp.tailscale_status(), {"state": "NeedsLogin"})

    def test_no_tailscale(self):
        with patch.object(rp.shutil, "which", return_value=None):
            self.assertEqual(rp.tailscale_status(), {})


class PairingInputTests(unittest.TestCase):
    def test_rejects_bad_input_without_calling_sunshine(self):
        with patch.object(rp, "api") as api:
            self.assertFalse(rp.pair("x" * 32, "1234", "TV")[0])
            self.assertFalse(rp.pair("a" * 32, "12a4", "TV")[0])
            self.assertFalse(rp.unpair("../etc")[0])
            self.assertFalse(rp.decline("nothex"))
            api.assert_not_called()

    def test_pair_sends_request(self):
        with patch.object(rp, "api", return_value={"status": True}) as api:
            ok, _ = rp.pair("a" * 32, "1234", "Apple TV")
        self.assertTrue(ok)
        self.assertEqual(api.call_args[0][2], {"pairing_id": "a" * 32, "pin": "1234", "name": "Apple TV"})


class FirewallRuleTests(unittest.TestCase):
    def test_rules_are_private_networks_and_tailscale_only(self):
        rules = admin.remote_play_rules()
        sources = {r[1] for r in rules if r[0] == "from"}
        self.assertEqual(sources, {"192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"})
        self.assertTrue(all(r[0] == "from" or r[:3] == ["in", "on", "tailscale0"] for r in rules))
        self.assertFalse(any("47990" in " ".join(r) for r in rules))

    def test_on_needs_password(self):
        self.assertTrue(admin.needs_password("remote-play-firewall", ["on"]))
        self.assertFalse(admin.needs_password("remote-play-firewall", ["off"]))

    def test_bad_args_refused(self):
        with self.assertRaises(admin.Refused):
            admin.remote_play_firewall(["open"])

    def test_status_text(self):
        self.assertTrue(rp.firewall_open("47984,47989,48010/tcp ALLOW 192.168.0.0/16  # ReyOS Remote Play"))
        self.assertFalse(rp.firewall_open("22/tcp ALLOW Anywhere"))


if __name__ == "__main__":
    unittest.main()
