#!/usr/bin/env python3
"""Run every import statement and load every QML module the ReyOS apps use.

An Arch rebuild that leaves Qt libraries out of step with PySide6 or with
QML plugins (Kirigami, ...) shows up here as an ImportError or a QML
"module ... is not installed / plugin cannot be loaded" error.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/reyos")
QML_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)(?:\s+[\d.]+)?(?:\s+as\s+\w+)?\s*$")


def local_modules(py_files):
    names = set()
    for f in py_files:
        names.add(f.stem)
        names.add(f.parent.name)
    return names


def optional_import_nodes(tree):
    """Imports inside `try: ... except (ImportError|Exception)` are optional."""
    optional = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        caught = set()
        for h in node.handlers:
            types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
            caught |= {getattr(t, "id", None) for t in types} if h.type else {"Exception"}
        if caught & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
            for stmt in node.body:
                optional |= {id(n) for n in ast.walk(stmt)}
    return optional


def python_statements(py_files, local):
    stmts, optional = set(), set()
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(errors="replace"), str(f))
        except SyntaxError as e:
            stmts.add(f"raise SyntaxError({str(e)!r})")
            continue
        opt = optional_import_nodes(tree)
        for node in ast.walk(tree):
            found = []
            if isinstance(node, ast.Import):
                found = [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in local]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module.split(".")[0] not in local:
                    names = ", ".join(sorted(a.name for a in node.names if a.name != "*"))
                    found = [f"from {node.module} import {names}" if names else f"import {node.module}"]
            (optional if id(node) in opt else stmts).update(found)
    return sorted(stmts), sorted(optional - stmts)


def qml_modules(qml_files):
    mods = set()
    for f in qml_files:
        for line in f.read_text(errors="replace").splitlines():
            m = QML_IMPORT_RE.match(line)
            if m:
                mods.add(m.group(1))
    return sorted(mods)


def check_python(stmts):
    failures = []
    for stmt in stmts:
        r = subprocess.run([sys.executable, "-c", stmt], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or ["(no output)"])[-1]
            failures.append(f"{stmt}\n    {last}")
    return failures


QML_PROBE = r"""
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
app = QGuiApplication(sys.argv)
engine = QQmlEngine()
bad = []
for mod in sys.argv[1:]:
    c = QQmlComponent(engine)
    c.setData(f"import QtQuick\nimport {mod}\nItem {{}}\n".encode(), "probe.qml")
    if c.isError():
        bad.append(mod + ": " + "; ".join(e.toString() for e in c.errors()))
print("\n".join(bad))
sys.exit(1 if bad else 0)
"""


def check_qml(mods):
    if not mods:
        return []
    r = subprocess.run([sys.executable, "-c", QML_PROBE, *mods], capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        return []
    out = r.stdout.strip() or r.stderr.strip() or "QML probe crashed"
    return out.splitlines()


LIB_DIRS = ["/usr/lib/qt6/qml", "/usr/lib/qt6/plugins"]


def check_library_symbols():
    """`ldd -r` on PySide6's modules and Qt's QML/plugin libraries.

    Catches a library built against a newer Qt than the one installed
    (undefined symbol) even in modules no ReyOS app uses yet. Modules whose
    Qt library isn't installed at all ("not found") are skipped, and Python
    C-API symbols are expected to be undefined in extension modules.
    """
    dirs = [str(p) for p in Path("/usr/lib").glob("python3*/site-packages/PySide6")] + LIB_DIRS
    failures = []
    for d in dirs:
        for so in sorted(Path(d).rglob("*.so")):
            r = subprocess.run(["ldd", "-r", str(so)], capture_output=True, text=True, timeout=60)
            out = r.stdout + r.stderr
            if "=> not found" in out:
                continue
            bad = [line.split("undefined symbol: ", 1)[1].split()[0].rstrip(",")
                   for line in out.splitlines() if "undefined symbol: " in line]
            bad = [b for b in bad if not b.startswith(("Py", "_Py"))]
            if bad:
                failures.append(f"{so}: {len(bad)} undefined, e.g. {bad[0]}")
    return failures


def main():
    py_files = [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts]
    qml_files = list(ROOT.rglob("*.qml"))
    local = local_modules(py_files)
    stmts, optional = python_statements(py_files, local)
    mods = qml_modules(qml_files)
    print(f"{len(py_files)} Python files, {len(stmts)} required + {len(optional)} optional imports; "
          f"{len(qml_files)} QML files, {len(mods)} QML modules")

    py_fail = check_python(stmts)
    opt_fail = check_python(optional)
    qml_fail = check_qml(mods)
    lib_fail = check_library_symbols()
    if opt_fail:
        print(f"\nOptional imports (warnings only): {len(opt_fail)} unavailable")
        for f in opt_fail:
            print("  " + f)
    for title, fails in (("Python imports", py_fail), ("QML modules", qml_fail), ("Library symbols", lib_fail)):
        print(f"\n{title}: {'OK' if not fails else f'{len(fails)} FAILED'}")
        for f in fails:
            print("  " + f)
    sys.exit(1 if (py_fail or qml_fail or lib_fail) else 0)


if __name__ == "__main__":
    main()
