"""Is the running Linux kernel still the installed one?

Arch replaces a kernel in place: updating `linux` (or `linux-lts`) removes
/usr/lib/modules/<running version>, so until a restart nothing new can be
loaded (a Bluetooth controller's hid-playstation, a USB stick's filesystem).
reyos-base ships kernel-modules-hook, which puts the running kernel's modules
back after the update, but the new kernel still only starts on a restart.
"""
import os
import subprocess
from pathlib import Path

MODULES = Path("/usr/lib/modules")


def status():
    """{"needed": restart needed to start the installed kernel,
    "modulesMissing": the running kernel's modules are gone (devices that
    need a driver not loaded yet won't work until the restart),
    "running": `uname -r`}."""
    running = os.uname().release
    result = {"needed": False, "modulesMissing": False, "running": running}
    # WSL and containers run a kernel ReyOS doesn't install.
    if "microsoft" in running.lower() or not MODULES.is_dir():
        return result
    mod_dir = MODULES / running
    if not (mod_dir / "modules.dep").is_file():
        result["needed"] = result["modulesMissing"] = True
        return result
    # kernel-modules-hook's restored copy belongs to no package.
    try:
        owned = subprocess.run(["pacman", "-Qqo", str(mod_dir / "vmlinuz")],
                               capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return result
    result["needed"] = not owned
    return result
