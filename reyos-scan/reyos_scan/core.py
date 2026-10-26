"""ReyOS Scan core: on-demand malware scans with ClamAV, scan reports,
user-approved quarantine and a pre-run check for Windows game files.

Distro-neutral and Qt-free: the same file is used by the standalone app
(Ubuntu .deb, `reyos-scan`) and by ReyOS Control Center / ReyOS Games
(a copy kept identical by tests/test_core.py).

clamscan runs as the user, on demand (no clamd daemon: about 1 GB of
signatures kept in memory all the time). Definitions are updated by the
system: clamav-freshclam.service on Ubuntu, clamav-freshclam-once.timer on
ReyOS.

What it can say: a signature scan finds *known* malware. "clean" means no
known threats in the files that were checked, never "safe"; errors, files
too big to check or missing definitions make a scan "not_verified".

Quarantine only on request, per file: copied into a private folder (0700),
stored read-only and not executable, SHA-256 checked, the original removed
only if it's still the same file. Restore checks the hash again. Nothing is
deleted unasked."""
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

VERSION = "0.1.0"
SCHEMA = 1
DATA = Path(os.environ.get("REYOS_SCAN_DATA", Path.home() / ".local" / "share" / "reyos" / "security"))
REPORTS = DATA / "scans"
QUARANTINE = DATA / "quarantine"
CACHE = DATA / "cache.json"
# Windows programs, scripts, libraries and installer archives: what the
# pre-run check looks at (a game's data files aren't executed).
PROGRAM_EXTS = {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".com", ".reg", ".sys",
                ".zip", ".7z", ".rar", ".cab"}
# Bounds for archives and huge files (ClamAV's own options). Anything over
# them is reported as "not checked", never as clean.
LIMITS = ["--max-filesize=500M", "--max-scansize=1000M", "--max-recursion=16", "--max-files=20000",
          "--alert-exceeds-max=yes"]
LIMIT_SIGNATURE = "Heuristics.Limits.Exceeded"
_FOUND_RE = re.compile(r"^(.*): (.+) FOUND$")
_ERROR_RE = re.compile(r"^(.*): (.+) ERROR$")


def installed():
    return bool(shutil.which("clamscan"))


def definitions():
    """{"engine", "version", "date", "age_days"} from `clamscan --version`
    (reads the definitions' header only). version "" = no definitions."""
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


def updater():
    """How definitions are kept fresh here: "service" (freshclam daemon,
    Ubuntu's default), "timer" (ReyOS) or "manual"."""
    def active(unit):
        try:
            return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    if active("clamav-freshclam.service"):
        return "service"
    if active("clamav-freshclam-once.timer"):
        return "timer"
    return "manual"


def quick_scope(extra=()):
    """Where downloaded files land, plus extra folders (games...)."""
    home = Path.home()
    paths = [home / "Downloads", home / "Desktop", *map(Path, extra)]
    seen, out = set(), []
    for p in paths:
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            out.append(str(p))
    return out


def removable_drives():
    """Mounted external drives: /media/$USER/* (Ubuntu), /run/media/$USER/* (ReyOS)."""
    user = os.environ.get("USER", "")
    out = []
    for base in (Path("/media") / user, Path("/run/media") / user):
        try:
            out += [str(p) for p in sorted(base.iterdir()) if p.is_dir() and os.path.ismount(p)]
        except OSError:
            pass
    return out


def sha256(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def program_files(target):
    """The files the pre-run check looks at for a chosen .exe/installer:
    the file itself, plus programs/libraries/archives in its folder (all of
    its subfolders) unless that folder is home, Downloads or Desktop,
    full of unrelated files. Regular files only, no symlinks."""
    target = Path(target)
    files = [target]
    folder = target.parent
    home = Path.home()
    if folder not in (home, home / "Downloads", home / "Desktop"):
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() in PROGRAM_EXTS and p != target and not p.is_symlink() and p.is_file():
                    files.append(p)
    return files


class Scan:
    """One clamscan run over paths (folders, files) or, with files=, an
    exact list of files. run() blocks; cancel() may be called from another
    thread; progress(files_checked, current_path) is called as it goes."""

    def __init__(self, paths, kind, progress=None, files=None):
        self.paths, self.kind = [str(p) for p in paths], kind
        self.files = [str(f) for f in files] if files is not None else None
        self.progress = progress or (lambda n, path: None)
        self.proc = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

    def run(self, save=True):
        defs = definitions()
        report = {"schema": SCHEMA, "app": f"reyos-scan {VERSION}", "kind": self.kind, "scope": self.paths,
                  "started": time.time(), "engine": defs["engine"], "definitions": defs["version"],
                  "definitions_date": defs["date"], "files": 0, "findings": [], "skipped": [], "errors": []}
        if not installed():
            return self._finish(report, "not_verified", "The scanner (ClamAV) isn't installed.", save)
        if not defs["version"]:
            return self._finish(report, "not_verified", "There are no virus definitions yet: update them first.", save)
        # Not into other filesystems or along symlinks (Wine prefixes link to
        # / and to other drives), never into the quarantine.
        cmd = ["clamscan", "--recursive", "--verbose", "--stdout", "--no-summary", "--cross-fs=no",
               "--follow-dir-symlinks=0", "--follow-file-symlinks=0",
               f"--exclude-dir=^{re.escape(str(QUARANTINE))}", *LIMITS]
        listfile = None
        if self.files is not None:
            if not self.files:
                return self._finish(report, "clean", "Nothing new to check.", save)
            listfile = tempfile.NamedTemporaryFile("w", prefix="reyos-scan-", suffix=".txt", delete=False)
            listfile.write("\n".join(self.files) + "\n")
            listfile.close()
            cmd.append(f"--file-list={listfile.name}")
        else:
            cmd += ["--"] + self.paths
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, errors="replace")
        except OSError as e:
            return self._finish(report, "not_verified", f"The scanner couldn't start: {e}", save)
        try:
            for line in self.proc.stdout:
                self._line(report, line.rstrip("\n"))
            rc = self.proc.wait()
        finally:
            if listfile is not None:
                os.unlink(listfile.name)
        if self.cancelled:
            return self._finish(report, "cancelled", "Scan stopped before the end: not everything was checked.", save)
        if report["findings"]:
            n = len(report["findings"])
            return self._finish(report, "found", f"{n} threat{'s' if n > 1 else ''} found.", save)
        if rc == 0 and not report["errors"] and not report["skipped"]:
            return self._finish(report, "clean", f"No known threats found in {report['files']} files.", save)
        problems = []
        if report["skipped"]:
            problems.append(f"{len(report['skipped'])} too big or too deeply packed to check")
        if report["errors"] or not report["skipped"]:
            problems.append(f"{len(report['errors']) or 'some'} couldn't be read")
        return self._finish(report, "not_verified", f"Checked {report['files']} files, but "
                            + " and ".join(problems) + ", so this scan isn't complete.", save)

    def _line(self, report, line):
        if line.startswith("Scanning "):
            report["files"] += 1
            if report["files"] % 25 == 1:
                self.progress(report["files"], line[9:])
        elif (m := _FOUND_RE.match(line)):
            path, signature = m.group(1), m.group(2)
            if signature.startswith(LIMIT_SIGNATURE):
                report["skipped"].append({"path": path, "reason": signature})
                return
            try:
                digest, size = sha256(path), os.lstat(path).st_size
            except OSError:
                digest, size = "", 0
            report["findings"].append({"path": path, "signature": signature, "sha256": digest, "size": size})
        elif (m := _ERROR_RE.match(line)):
            report["errors"].append(f"{m.group(1)}: {m.group(2)}")
        elif line.startswith(("WARNING:", "ERROR:", "LibClamAV Error")):
            report["errors"].append(line)

    def _finish(self, report, status, summary, save):
        report.update(status=status, summary=summary, finished=time.time())
        if save:
            REPORTS.mkdir(parents=True, exist_ok=True)
            os.chmod(DATA, 0o700)
            name = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["started"])) + f"-{report['kind']}.json"
            path = REPORTS / name
            n = 1
            while path.exists():
                path, n = REPORTS / name.replace(".json", f"-{n}.json"), n + 1
            path.write_text(json.dumps(report, indent=1))
        return report


# ---- Pre-run check (Windows games): only files not already checked ----------

def _load_cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def check_program(target, progress=None):
    """Checks an installer/.exe and the programs next to it before anything
    runs. A file already found clean with the same definitions (same
    SHA-256) isn't scanned again; any changed file is. Returns a report
    (status clean / found / not_verified / cancelled)."""
    files = program_files(target)
    defs = definitions()
    cache = _load_cache()
    todo, hashes = [], {}
    for f in files:
        try:
            hashes[str(f)] = h = sha256(f)
        except OSError:
            todo.append(f)
            continue
        if cache.get(h) != defs["version"] or not defs["version"]:
            todo.append(f)
    scan = Scan([str(Path(target).parent)], "addgame", progress=progress, files=todo)
    report = scan.run()
    report["checked_before"] = len(files) - len(todo)
    if report["status"] == "clean" and defs["version"]:
        bad = {f["path"] for f in report["findings"]}
        for path, h in hashes.items():
            if path not in bad:
                cache[h] = defs["version"]
        DATA.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache))
        if report["checked_before"]:
            report["summary"] = (f"No known threats found ({len(todo)} files checked now, "
                                 f"{report['checked_before']} unchanged since an earlier check).")
    return report


def last_report():
    try:
        return json.loads(max(REPORTS.glob("*.json")).read_text())
    except (ValueError, OSError):
        return None


def history(limit=50):
    out = []
    for path in sorted(REPORTS.glob("*.json"), reverse=True)[:limit]:
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
    return out


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
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", qid or ""):
        return False, "That isn't a quarantine item."
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
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", qid or ""):
        return False, "That isn't a quarantine item."
    for suffix in (".quarantined", ".json"):
        try:
            (QUARANTINE / f"{qid}{suffix}").unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            return False, f"Couldn't delete it: {e.strerror}."
    return True, "Deleted for good."
