"""ReyOS Scan: on-demand malware scans with ClamAV (Control Center →
Security, ReyOS Games). Qt-free so it can be tested on its own.

clamscan runs as the user, on demand only (no clamd daemon: it keeps about
1 GB of signatures in memory all the time). Its definitions are updated as
root by reyos-admin malware-setup / clamav-freshclam-once.timer.

What this can and can't say: a signature scan finds *known* malware. A clean
result is "No known threats found" for the files scanned at that time, never
"safe"; a scan with errors or without definitions is "Not verified".

Quarantine moves a file into a private folder (0700), stored without any
execute permission, with its SHA-256, and only on the user's say-so. Restore
puts it back after checking the hash; nothing is ever deleted unasked."""
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import time
from pathlib import Path

import emulation

SCHEMA = 1
PACKAGES = ["clamav"]
DATA = Path.home() / ".local" / "share" / "reyos" / "security"
REPORTS = DATA / "scans"
QUARANTINE = DATA / "quarantine"
# Programs, scripts and archives: what Add PC game checks before anything
# runs (a whole game's data files would take minutes and aren't executed).
PROGRAM_RE = r"\.([eE][xX][eE]|[dD][lL][lL]|[mM][sS][iI]|[bB][aA][tT]|[cC][mM][dD]|[pP][sS]1|[vV][bB][sS]|[sS][cC][rR]|[cC][oO][mM]|[rR][eE][gG]|[zZ][iI][pP]|7[zZ]|[rR][aA][rR]|[cC][aA][bB])$"
_FOUND_RE = re.compile(r"^(.*): (.+) FOUND$")
_ERROR_RE = re.compile(r"^(.*): (.+) ERROR$")


def installed():
    return bool(shutil.which("clamscan"))


def definitions():
    """{"engine", "version", "date", "age_days"}: from `clamscan --version`,
    which reads the definitions' header only (instant). version "" = none."""
    try:
        out = subprocess.run(["clamscan", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return {"engine": "", "version": "", "date": "", "age_days": -1}
    parts = out.split("/")
    info = {"engine": parts[0].replace("ClamAV ", ""), "version": "", "date": "", "age_days": -1}
    if len(parts) >= 3:
        info["version"], info["date"] = parts[1], parts[2]
        try:
            info["age_days"] = int((time.time() - time.mktime(time.strptime(parts[2], "%a %b %d %H:%M:%S %Y"))) // 86400)
        except ValueError:
            pass
    return info


def quick_scope():
    """Where downloaded files and games land."""
    home = Path.home()
    paths = [home / "Downloads", home / "Desktop", emulation.GAMES_DIR]
    storage = emulation.load_settings()["game_storage"]
    if storage:
        paths.append(Path(storage))
    return [str(p) for p in paths if p.is_dir()]


def program_scope(exe):
    """What Add PC game checks: the chosen file, and the programs, scripts
    and archives in its folder (unless that folder is Downloads, Desktop or
    home itself, full of unrelated files). (paths, include_regex or None)"""
    exe = Path(exe)
    folder = exe.parent
    home = Path.home()
    if folder in (home, home / "Downloads", home / "Desktop"):
        return [str(exe)], None
    return [str(folder)], PROGRAM_RE


def sha256(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Scan:
    """One clamscan run. run() blocks; cancel() may be called from another
    thread. progress(files_checked, current_path) is called as it goes."""

    def __init__(self, paths, kind, include=None, progress=None):
        self.paths, self.kind, self.include = [str(p) for p in paths], kind, include
        self.progress = progress or (lambda n, path: None)
        self.proc = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

    def run(self):
        defs = definitions()
        report = {"schema": SCHEMA, "kind": self.kind, "scope": self.paths, "started": time.time(),
                  "engine": defs["engine"], "definitions": defs["version"], "definitions_date": defs["date"],
                  "files": 0, "findings": [], "errors": []}
        if not installed():
            return self._finish(report, "not_verified", "The scanner (ClamAV) isn't installed.")
        if not defs["version"]:
            return self._finish(report, "not_verified", "The scanner has no virus definitions yet: update them first.")
        # Not into other filesystems or along symlinks (Wine prefixes link to
        # / and to other drives), and never the quarantine itself.
        cmd = ["clamscan", "--recursive", "--verbose", "--stdout", "--no-summary", "--cross-fs=no",
               "--follow-dir-symlinks=0", "--follow-file-symlinks=0",
               f"--exclude-dir=^{re.escape(str(QUARANTINE))}"]
        if self.include:
            cmd.append(f"--include={self.include}")
        try:
            self.proc = subprocess.Popen(cmd + ["--"] + self.paths, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, errors="replace")
        except OSError as e:
            return self._finish(report, "not_verified", f"The scanner couldn't start: {e}")
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("Scanning "):
                report["files"] += 1
                if report["files"] % 25 == 1:
                    self.progress(report["files"], line[9:])
            elif (m := _FOUND_RE.match(line)):
                path = m.group(1)
                try:
                    digest, size = sha256(path), os.lstat(path).st_size
                except OSError:
                    digest, size = "", 0
                report["findings"].append({"path": path, "signature": m.group(2), "sha256": digest, "size": size})
            elif (m := _ERROR_RE.match(line)):
                report["errors"].append(f"{m.group(1)}: {m.group(2)}")
            elif line.startswith(("WARNING:", "ERROR:", "LibClamAV Error")):
                report["errors"].append(line)
        rc = self.proc.wait()
        if self.cancelled:
            return self._finish(report, "cancelled", "Scan stopped before the end: not everything was checked.")
        if report["findings"]:
            n = len(report["findings"])
            return self._finish(report, "found", f"{n} threat{'s' if n > 1 else ''} found.")
        if rc == 0 and not report["errors"]:
            return self._finish(report, "clean", f"No known threats found in {report['files']} files.")
        return self._finish(report, "not_verified",
                            f"Checked {report['files']} files, but {len(report['errors']) or 'some'} could not be "
                            "read, so this scan is not complete.")

    def _finish(self, report, status, summary):
        report.update(status=status, summary=summary, finished=time.time())
        REPORTS.mkdir(parents=True, exist_ok=True)
        os.chmod(DATA, 0o700)
        name = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["started"])) + f"-{report['kind']}.json"
        (REPORTS / name).write_text(json.dumps(report, indent=1))
        return report


def last_report():
    try:
        latest = max(REPORTS.glob("*.json"))
        return json.loads(latest.read_text())
    except (ValueError, OSError):
        return None


# ---- Quarantine --------------------------------------------------------------

def _private_dir():
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    os.chmod(QUARANTINE, 0o700)
    return QUARANTINE


def _copy_verified(src_fd, dst, mode, digest):
    """Copy an open file to dst (which must not exist), then check its hash."""
    out = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(out, "wb") as o, os.fdopen(os.dup(src_fd), "rb") as i:
        i.seek(0)
        shutil.copyfileobj(i, o, 1 << 20)
        o.flush()
        os.fsync(o.fileno())
    if sha256(dst) != digest:
        os.unlink(dst)
        raise OSError("the copy didn't match the original")


def quarantine(path, signature=""):
    """Moves one file into the quarantine. (ok, message)"""
    path = Path(path)
    try:
        st = os.lstat(path)
    except OSError as e:
        return False, f"{path.name} can't be found any more ({e.strerror})."
    if not stat.S_ISREG(st.st_mode):
        return False, f"{path.name} isn't a regular file (link or folder): not moved."
    qdir = _private_dir()
    qid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    data = qdir / f"{qid}.quarantined"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as e:
        return False, f"Couldn't open {path.name}: {e.strerror}."
    try:
        fst = os.fstat(fd)
        if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            return False, f"{path.name} changed while it was being moved: not moved."
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        digest = digest.hexdigest()
        _copy_verified(fd, data, 0o400, digest)
    except OSError as e:
        return False, f"Couldn't move {path.name}: {e}."
    finally:
        os.close(fd)
    meta = {"schema": SCHEMA, "id": qid, "original_path": str(path), "sha256": digest, "size": st.st_size,
            "mode": stat.S_IMODE(st.st_mode), "mtime": st.st_mtime, "signature": signature,
            "quarantined_at": time.time()}
    (qdir / f"{qid}.json").write_text(json.dumps(meta, indent=1))
    try:
        # Only the file that was copied: not one put in its place meanwhile.
        now = os.lstat(path)
        if (now.st_dev, now.st_ino) == (st.st_dev, st.st_ino):
            os.unlink(path)
        else:
            return True, f"{path.name} was copied to quarantine, but the file there changed, so it wasn't removed."
    except OSError as e:
        return False, f"{path.name} is in quarantine, but the original couldn't be removed ({e.strerror})."
    return True, f"{path.name} is in quarantine. It can't run from there; you can restore or delete it later."


def quarantined():
    items = []
    for meta in sorted(QUARANTINE.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(meta.read_text()))
        except (OSError, ValueError):
            pass
    return items


def restore(qid):
    """Back to where it came from (or next to it, if that name is taken)."""
    meta_path = QUARANTINE / f"{qid}.json"
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return False, "That item isn't in quarantine any more."
    data = QUARANTINE / f"{qid}.quarantined"
    dst = Path(meta["original_path"])
    if not dst.parent.is_dir():
        return False, f"Its folder ({dst.parent}) doesn't exist any more."
    n = 1
    while os.path.lexists(dst):
        dst = dst.with_name(f"{Path(meta['original_path']).stem} (restored {n}){dst.suffix}")
        n += 1
    try:
        fd = os.open(data, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            _copy_verified(fd, dst, meta["mode"] & 0o777, meta["sha256"])
        finally:
            os.close(fd)
        os.utime(dst, (meta["mtime"], meta["mtime"]))
    except OSError as e:
        return False, f"Couldn't restore it: {e}."
    os.unlink(data)
    meta_path.unlink()
    return True, f"Restored to {dst}."


def delete(qid):
    for suffix in (".quarantined", ".json"):
        try:
            (QUARANTINE / f"{qid}{suffix}").unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            return False, f"Couldn't delete it: {e.strerror}."
    return True, "Deleted for good."
