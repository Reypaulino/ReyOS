"""ReyOS Scan's window (Qt Widgets): Quick scan, a file or folder, an
external drive, the whole home folder, a game installer before it runs,
quarantine and history. Everything goes through core.py; scans run in a
thread so the window stays responsive and Cancel works."""
import os
import sys
import time
from pathlib import Path

from . import core
from .qt import BINDING, QIcon, QObject, Qt, QThread, QtWidgets, Signal  # noqa: F401

W = QtWidgets
ACCENT = "#C97932"
STATUS = {
    "clean": ("No known threats found", "#2e9d57"),
    "found": ("Threat found", "#d9443a"),
    "not_verified": ("Not verified", "#c98a1e"),
    "cancelled": ("Stopped", "#888888"),
}
INSTALLER_FILTER = "Programs and installers (*.exe *.EXE *.msi *.MSI *.zip *.ZIP *.7z *.rar *.RAR *.bat *.cmd);;All files (*)"


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("bytes", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def count_files(paths, leave_out=()):
    """Files and bytes about to be scanned, the way clamscan walks them (no
    symlinks, not into other drives), so the window can say up front how
    big the job is."""
    files = size = 0
    skip = tuple("." + e for e in leave_out)
    for top in paths:
        top = Path(top)
        if top.is_file():
            files, size = files + 1, size + top.stat().st_size
            continue
        try:
            dev = top.stat().st_dev
        except OSError:
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))
                           and _same_dev(os.path.join(dirpath, d), dev)
                           and os.path.join(dirpath, d) != str(core.QUARANTINE)]
            for name in filenames:
                if skip and name.lower().endswith(skip):
                    continue
                try:
                    st = os.lstat(os.path.join(dirpath, name))
                except OSError:
                    continue
                if not os.path.islink(os.path.join(dirpath, name)):
                    files, size = files + 1, size + st.st_size
    return files, size


def _same_dev(path, dev):
    try:
        return os.stat(path).st_dev == dev
    except OSError:
        return False


class Job(QThread):
    """A scan (or check) off the window's thread."""
    counted = Signal(int, object)
    progress = Signal(int, str)
    done = Signal(object)

    def __init__(self, kind, paths=(), target=None, leave_out=()):
        super().__init__()
        self.kind, self.paths, self.target, self.leave_out = kind, list(paths), target, tuple(leave_out)
        self.scan = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.scan is not None:
            self.scan.cancel()

    def run(self):
        try:
            if self.target is not None:
                self.done.emit(core.check_program(self.target, progress=self.progress.emit))
                return
            files, size = count_files(self.paths, self.leave_out)
            self.counted.emit(files, size)
            if self.cancelled:
                return
            self.scan = core.Scan(self.paths, self.kind, progress=self.progress.emit, leave_out=self.leave_out)
            self.done.emit(self.scan.run())
        except Exception as e:  # shown in the window, never a crash
            self.done.emit({"status": "not_verified", "summary": f"The scan failed: {e}", "findings": [],
                            "skipped": [], "errors": [str(e)], "left_out": []})


class Window(W.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReyOS Scan")
        self.setWindowIcon(QIcon.fromTheme("reyos-scan", QIcon.fromTheme("security-high")))
        self.resize(900, 640)
        self.job = None
        self.report = None
        self.total = 0

        central = W.QWidget()
        self.setCentralWidget(central)
        root = W.QVBoxLayout(central)
        title = W.QLabel("ReyOS Scan")
        title.setStyleSheet(f"font-size: 20pt; font-weight: 600; color: {ACCENT};")
        root.addWidget(title)
        self.status_line = W.QLabel()
        self.status_line.setWordWrap(True)
        root.addWidget(self.status_line)

        tabs = W.QTabWidget()
        root.addWidget(tabs, 1)
        tabs.addTab(self._scan_tab(), "Scan")
        tabs.addTab(self._quarantine_tab(), "Quarantine")
        tabs.addTab(self._history_tab(), "History")
        tabs.currentChanged.connect(lambda i: (self.load_quarantine(), self.load_history()))

        note = W.QLabel("A scan finds known malware only. \"No known threats\" isn't a promise that a program is "
                        "safe, and Wine/Proton don't sandbox Windows programs: get games from trustworthy stores.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(placeholder-text); font-size: 9pt;")
        root.addWidget(note)
        self.refresh_status()

    # ---- Scan tab -------------------------------------------------------------
    def _scan_tab(self):
        tab = W.QWidget()
        lay = W.QVBoxLayout(tab)
        grid = W.QGridLayout()
        lay.addLayout(grid)
        self.buttons = []

        def button(text, tip, slot, row, col, main=False):
            b = W.QPushButton(text)
            b.setToolTip(tip)
            b.setMinimumHeight(40)
            if main:
                b.setStyleSheet(f"QPushButton {{ background: {ACCENT}; color: white; font-weight: 600; }}")
            b.clicked.connect(slot)
            grid.addWidget(b, row, col)
            self.buttons.append(b)
            return b

        button("Quick scan", "Downloads and Desktop, where downloaded files land. Disc images are left out "
               "(listed apart).", self.quick, 0, 0, True)
        button("Scan a folder…", "Pick a folder to scan.", self.pick_folder, 0, 1)
        button("Scan a file…", "Pick one file to scan.", self.pick_file, 0, 2)
        self.drive_button = button("External drive…", "USB sticks and drives plugged in to this PC.",
                                   self.pick_drive, 1, 0)
        button("Full home scan", "Your whole home folder: can take hours.", self.home_scan, 1, 1)
        button("Check a game installer…", "Before running a Windows installer or game: the .exe and the "
               "programs, DLLs and archives next to it. Files checked before and unchanged are skipped.",
               self.pick_installer, 1, 2)

        self.progress_label = W.QLabel("Pick what to scan.")
        self.progress_label.setWordWrap(True)
        lay.addWidget(self.progress_label)
        row = W.QHBoxLayout()
        self.bar = W.QProgressBar()
        self.bar.setVisible(False)
        row.addWidget(self.bar, 1)
        self.cancel_button = W.QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.cancel_button)
        lay.addLayout(row)

        self.result = W.QLabel()
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.result)
        self.findings = W.QTableWidget(0, 3)
        self.findings.setHorizontalHeaderLabels(["File", "Threat", "Size"])
        self.findings.horizontalHeader().setSectionResizeMode(0, W.QHeaderView.ResizeMode.Stretch)
        self.findings.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.ResizeToContents)
        self.findings.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.findings.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.findings.setVisible(False)
        lay.addWidget(self.findings, 1)
        self.quarantine_button = W.QPushButton("Move selected to quarantine…")
        self.quarantine_button.setVisible(False)
        self.quarantine_button.clicked.connect(self.quarantine_selected)
        lay.addWidget(self.quarantine_button)
        self.details = W.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setVisible(False)
        lay.addWidget(self.details, 1)
        lay.addStretch(0)
        return tab

    def refresh_status(self):
        if not core.installed():
            self.status_line.setText("<b>ClamAV isn't installed.</b> Install it with: "
                                     "<code>sudo apt install clamav clamav-freshclam</code>")
            return
        d = core.definitions()
        upd = core.updater()
        how = {"service": "updated automatically (clamav-freshclam)",
               "timer": "updated automatically every day",
               "manual": "<b>not updated automatically</b>: turn the updater on with "
                         "<code>sudo systemctl enable --now clamav-freshclam</code>"}[upd]
        if not d["version"]:
            text = ("<b style='color:#d9443a'>No virus definitions yet.</b> "
                    + ("They're downloading (clamav-freshclam): wait a few minutes." if upd == "service"
                       else "Run <code>sudo freshclam</code>."))
        else:
            age = d["age_days"]
            stale = age > 7
            text = (f"ClamAV {d['engine']} · definitions {d['version']} "
                    f"(<span style='color:{'#d9443a' if stale else 'inherit'}'>"
                    f"{'today' if age == 0 else f'{age} day' + ('s' if age != 1 else '') + ' old'}</span>), {how}.")
            if stale:
                text += " <b>Old definitions miss new threats:</b> check the network, or run <code>sudo freshclam</code>."
        self.status_line.setText(text)

    def start(self, kind, paths=(), target=None, leave_out=(), what=""):
        if self.job is not None and self.job.isRunning():
            return
        self.report = None
        self.findings.setVisible(False)
        self.quarantine_button.setVisible(False)
        self.details.setVisible(False)
        self.result.setText("")
        for b in self.buttons:
            b.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.progress_label.setText(f"Getting ready to scan {what}…" if target is None
                                    else f"Checking {Path(target).name} and the programs next to it…")
        self.started = time.time()
        self.job = Job(kind, paths, target, leave_out)
        self.job.counted.connect(self.on_counted)
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.on_done)
        self.job.start()

    def on_counted(self, files, size):
        self.total = files
        self.bar.setRange(0, max(files, 1))
        self.progress_label.setText(f"About to check {files:,} files ({human_size(size)}). "
                                    "Loading the virus definitions takes about 15 seconds.")

    def on_progress(self, n, path):
        if self.total:
            self.bar.setValue(min(n, self.total))
        elapsed = int(time.time() - self.started)
        self.progress_label.setText(f"{n:,}{f' of {self.total:,}' if self.total else ''} files checked "
                                    f"({elapsed // 60}:{elapsed % 60:02d})\n{path}")

    def on_done(self, report):
        self.job = None
        self.total = 0
        self.report = report
        for b in self.buttons:
            b.setEnabled(True)
        self.bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.progress_label.setText("")
        label, color = STATUS.get(report.get("status"), ("Not verified", "#c98a1e"))
        self.result.setText(f"<span style='font-size:14pt; font-weight:600; color:{color}'>{label}</span><br>"
                            f"{report.get('summary', '')}")
        findings = report.get("findings", [])
        self.findings.setRowCount(len(findings))
        for i, f in enumerate(findings):
            for col, text in enumerate((f["path"], f["signature"], human_size(f.get("size", 0)))):
                self.findings.setItem(i, col, W.QTableWidgetItem(text))
        self.findings.setVisible(bool(findings))
        self.quarantine_button.setVisible(bool(findings))
        lines = []
        for s in report.get("skipped", []):
            lines.append(f"Not checked (too big or packed too deep): {s['path']}  [{s['reason']}]")
        for e in report.get("errors", []):
            lines.append(f"Couldn't read: {e}")
        for p in report.get("left_out", []):
            lines.append(f"Left out (disc image): {p}")
        if report.get("definitions"):
            lines.append(f"Definitions {report['definitions']} ({report.get('definitions_date', '')}), "
                         f"ClamAV {report.get('engine', '')}")
        self.details.setPlainText("\n".join(lines))
        self.details.setVisible(bool(lines))
        self.refresh_status()
        self.load_history()

    def cancel(self):
        if self.job is not None:
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("Stopping…")
            self.job.cancel()

    def quick(self):
        paths = core.quick_scope()
        if not paths:
            W.QMessageBox.information(self, "ReyOS Scan", "There's no Downloads or Desktop folder to scan.")
            return
        self.start("quick", paths, leave_out=core.DISC_IMAGE_EXTS, what="Downloads and Desktop")

    def pick_folder(self):
        path = W.QFileDialog.getExistingDirectory(self, "Folder to scan", str(Path.home()))
        if path:
            self.start("folder", [path], what=path)

    def pick_file(self):
        path, _ = W.QFileDialog.getOpenFileName(self, "File to scan", str(Path.home() / "Downloads"))
        if path:
            self.start("folder", [path], what=Path(path).name)

    def pick_drive(self):
        drives = core.removable_drives()
        if not drives:
            W.QMessageBox.information(self, "ReyOS Scan", "No external drive is plugged in (or it isn't open "
                                      "yet: open it in Files once).")
            return
        menu = W.QMenu(self)
        for d in drives:
            menu.addAction(Path(d).name, lambda d=d: self.start("drive", [d], what=Path(d).name))
        menu.exec(self.drive_button.mapToGlobal(self.drive_button.rect().bottomLeft()))

    def home_scan(self):
        if W.QMessageBox.question(self, "Full home scan", "Scan your whole home folder? With games and videos "
                                  "this can take hours; you can keep using the PC meanwhile.") \
                == W.QMessageBox.StandardButton.Yes:
            self.start("home", [str(Path.home())], what="your home folder")

    def pick_installer(self):
        path, _ = W.QFileDialog.getOpenFileName(self, "Game installer or .exe to check",
                                                str(Path.home() / "Downloads"), INSTALLER_FILTER)
        if path:
            self.start("addgame", target=path)

    def quarantine_selected(self):
        rows = sorted({i.row() for i in self.findings.selectedIndexes()}) or list(range(self.findings.rowCount()))
        items = [self.report["findings"][r] for r in rows]
        names = "\n".join(f"{Path(f['path']).name}  ({f['signature']})" for f in items)
        if W.QMessageBox.question(self, "Move to quarantine",
                                  f"Move these files to quarantine? They can't run from there, and you can "
                                  f"restore them later.\n\n{names}") != W.QMessageBox.StandardButton.Yes:
            return
        messages = [core.quarantine(f["path"], f["signature"])[1] for f in items]
        W.QMessageBox.information(self, "Quarantine", "\n".join(messages))
        self.load_quarantine()

    # ---- Quarantine tab -----------------------------------------------------------
    def _quarantine_tab(self):
        tab = W.QWidget()
        lay = W.QVBoxLayout(tab)
        lay.addWidget(W.QLabel("Files moved here can't run. Restore puts one back where it was, after checking "
                               "it's unchanged (SHA-256)."))
        self.qtable = W.QTableWidget(0, 4)
        self.qtable.setHorizontalHeaderLabels(["Moved", "Where it was", "Threat", "SHA-256"])
        self.qtable.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.Stretch)
        self.qtable.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.qtable.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.qtable.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.qtable, 1)
        row = W.QHBoxLayout()
        for text, slot in (("Restore…", self.restore), ("Delete for good…", self.delete), ("Refresh", self.load_quarantine)):
            b = W.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.load_quarantine()
        return tab

    def load_quarantine(self):
        self.qitems = core.quarantined()
        self.qtable.setRowCount(len(self.qitems))
        for i, q in enumerate(self.qitems):
            for col, text in enumerate((when(q.get("quarantined_at")), q.get("original_path", ""),
                                        q.get("signature", ""), q.get("sha256", "")[:16] + "…")):
                self.qtable.setItem(i, col, W.QTableWidgetItem(text))

    def _selected_q(self):
        rows = {i.row() for i in self.qtable.selectedIndexes()}
        return self.qitems[rows.pop()] if rows else None

    def restore(self):
        q = self._selected_q()
        if q is None:
            return
        if W.QMessageBox.warning(self, "Restore", f"Put {Path(q['original_path']).name} back in "
                                 f"{Path(q['original_path']).parent}?\n\nIt was flagged as {q.get('signature') or 'a threat'}. "
                                 "Only restore it if you're sure it's a false alarm.",
                                 W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No) \
                != W.QMessageBox.StandardButton.Yes:
            return
        ok, msg = core.restore(q["id"])
        (W.QMessageBox.information if ok else W.QMessageBox.warning)(self, "Restore", msg)
        self.load_quarantine()

    def delete(self):
        q = self._selected_q()
        if q is None:
            return
        if W.QMessageBox.warning(self, "Delete for good", f"Delete {Path(q['original_path']).name} for good? "
                                 "This can't be undone.",
                                 W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No) \
                != W.QMessageBox.StandardButton.Yes:
            return
        ok, msg = core.delete(q["id"])
        (W.QMessageBox.information if ok else W.QMessageBox.warning)(self, "Delete", msg)
        self.load_quarantine()

    # ---- History tab --------------------------------------------------------------
    def _history_tab(self):
        tab = W.QWidget()
        lay = W.QVBoxLayout(tab)
        self.htable = W.QTableWidget(0, 4)
        self.htable.setHorizontalHeaderLabels(["When", "What", "Result", "Summary"])
        self.htable.horizontalHeader().setSectionResizeMode(3, W.QHeaderView.ResizeMode.Stretch)
        self.htable.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.htable.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.htable.cellDoubleClicked.connect(self.show_report)
        lay.addWidget(self.htable, 1)
        lay.addWidget(W.QLabel("Double-click a scan for its details."))
        self.load_history()
        return tab

    def load_history(self):
        self.hitems = core.history()
        kinds = {"quick": "Quick scan", "folder": "File/folder", "drive": "External drive", "home": "Home folder",
                 "addgame": "Game check", "game": "Game"}
        self.htable.setRowCount(len(self.hitems))
        for i, r in enumerate(self.hitems):
            for col, text in enumerate((when(r.get("finished")), kinds.get(r.get("kind"), r.get("kind", "")),
                                        STATUS.get(r.get("status"), ("?", ""))[0], r.get("summary", ""))):
                self.htable.setItem(i, col, W.QTableWidgetItem(text))

    def show_report(self, row, _col):
        r = self.hitems[row]
        lines = [r.get("summary", ""), "", "Scanned: " + ", ".join(r.get("scope", []))]
        lines += [f"THREAT {f['path']} ({f['signature']}, sha256 {f.get('sha256', '')})" for f in r.get("findings", [])]
        lines += [f"Not checked: {s['path']} ({s['reason']})" for s in r.get("skipped", [])]
        lines += [f"Couldn't read: {e}" for e in r.get("errors", [])[:50]]
        lines += [f"Left out (disc image): {p}" for p in r.get("left_out", [])]
        lines.append(f"Definitions {r.get('definitions', '?')}, ClamAV {r.get('engine', '?')}")
        box = W.QMessageBox(self)
        box.setWindowTitle("Scan details")
        box.setText(STATUS.get(r.get("status"), ("?", ""))[0])
        box.setDetailedText("\n".join(lines))
        box.setInformativeText(r.get("summary", ""))
        box.exec()

    def closeEvent(self, event):
        if self.job is not None and self.job.isRunning():
            if W.QMessageBox.question(self, "ReyOS Scan", "A scan is running. Stop it and close?") \
                    != W.QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.job.cancel()
            self.job.wait(10000)
        event.accept()


def main():
    app = W.QApplication(sys.argv)
    app.setApplicationName("ReyOS Scan")
    app.setDesktopFileName("reyos-scan")
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
