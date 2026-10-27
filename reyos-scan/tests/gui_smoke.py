"""GUI smoke test: drives the real window offscreen (QT_QPA_PLATFORM=offscreen)
against real ClamAV in a temporary HOME: Quick scan finds EICAR and lists a
disc image apart, quarantine + restore from the window, History, a second
scan refused while one runs. Saves screenshots to $SHOTS (default /tmp).
Run: QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="reyos-scan-gui-"))
os.environ["HOME"] = str(tmp)
sys.path.insert(0, os.environ.get("REYOS_SCAN_LIB", str(Path(__file__).resolve().parent.parent)))
from reyos_scan import core, gui  # noqa: E402
from reyos_scan.qt import QtWidgets as W  # noqa: E402

core.DATA = tmp / ".local/share/reyos/security"
core.REPORTS, core.QUARANTINE, core.CACHE = core.DATA / "scans", core.DATA / "quarantine", core.DATA / "cache.json"
SHOTS = Path(os.environ.get("SHOTS", "/tmp"))
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
(tmp / "Downloads").mkdir()
(tmp / "Desktop").mkdir()
(tmp / "Downloads/eicar.com").write_bytes(EICAR)
(tmp / "Downloads/readme.txt").write_text("hello\n")
(tmp / "Desktop/Game (USA).iso").write_bytes(b"\0" * 4096)

app = W.QApplication(sys.argv)
win = gui.Window()
win.resize(900, 640)
win.show()
answers = []
W.QMessageBox.question = staticmethod(lambda *a, **k: W.QMessageBox.StandardButton.Yes)
W.QMessageBox.warning = staticmethod(lambda *a, **k: W.QMessageBox.StandardButton.Yes)
W.QMessageBox.information = staticmethod(lambda *a, **k: answers.append(a[2]))


def wait_job(limit=180):
    end = time.time() + limit
    while win.job is not None and time.time() < end:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    assert win.job is None, "scan didn't finish"


fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


win.grab().save(str(SHOTS / "reyos-scan-1-start.png"))
win.quick()
for _ in range(40):
    app.processEvents(); time.sleep(0.05)
check(win.job is not None and win.cancel_button.isVisible(), "quick scan running, Cancel shown")
other = core.Scan([str(tmp / "Downloads")], "folder").run(save=False)
check(other["status"] == "not_verified" and "Another" in other["summary"], "second scan refused meanwhile")
wait_job()
r = win.report
check(r["status"] == "found", f"EICAR found (status {r['status']}: {r['summary']})")
check([Path(p).name for p in r["left_out"]] == ["Game (USA).iso"], f"disc image listed apart {r['left_out']}")
check(win.findings.rowCount() == 1 and win.quarantine_button.isVisible(), "finding row + quarantine button")
win.grab().save(str(SHOTS / "reyos-scan-2-found.png"))
win.findings.selectRow(0)
win.quarantine_selected()
check(not (tmp / "Downloads/eicar.com").exists() and len(core.quarantined()) == 1, "moved to quarantine")
win.load_quarantine()
win.qtable.selectRow(0)
win.restore()
check((tmp / "Downloads/eicar.com").read_bytes() == EICAR and not core.quarantined(), "restored, same bytes")
win.load_history()
check(win.htable.rowCount() >= 1 and win.htable.item(0, 2).text() == "Threat found", "history row")
win.start("folder", [str(tmp / "Downloads/readme.txt")], what="readme.txt")
wait_job()
check(win.report["status"] == "clean", f"clean file: {win.report['summary']}")
win.start("home", [str(tmp)], what="home")
for _ in range(20):
    app.processEvents(); time.sleep(0.05)
win.cancel()
wait_job()
check(win.report["status"] in ("cancelled", "found"), f"cancel: {win.report['status']}")
win.grab().save(str(SHOTS / "reyos-scan-3-after.png"))
print(f"{len(fails)} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
