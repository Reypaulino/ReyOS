"""Plain-words reason for a failed system update (pacman via reyos-channel).

Control Center used to end a failed update with a bare "Update failed.": the
real cause (2026-11-23: archive.archlinux.org timing out) was only in the
scrolling log. explain() reads the update's output and names the cause.
"""
import re

ARCHIVE = "archive.archlinux.org"
REYOS_REPO = "reypaulino.github.io"

_NETWORK = re.compile(
    r"timed out|too slow|could not resolve|resolving timed out|failed to connect|"
    r"connection (?:refused|reset)|couldn't connect|network is unreachable|"
    r"ssl connect error|the requested url returned error: 5\d\d|too many errors from|"
    r"download library error|failed retrieving file|failed to synchronize",
    re.I)
_SPACE = re.compile(r"no space left on device|not enough free disk space|partition .* too full", re.I)
_LOCK = re.compile(r"unable to lock database|could not lock database", re.I)
_SIGNATURE = re.compile(
    r"signature .* (?:is (?:invalid|unknown trust|marginal trust)|could not be verified)|"
    r"invalid or corrupted (?:package|database) \(pgp signature\)|"
    r"key .* could not be (?:looked up|imported)|required key missing", re.I)
_CORRUPT = re.compile(r"invalid or corrupted package|checksum|is corrupted", re.I)
_DEPENDS = re.compile(r"unable to satisfy dependency|could not satisfy dependencies|"
                      r"unresolvable package conflicts", re.I)
_FILES = re.compile(r"conflicting files|exists in filesystem", re.I)
_SUDO = re.compile(r"sudo: (?:a password is required|a terminal is required|.*not allowed)", re.I)
_NOTHING_CHANGED = re.compile(r"no packages were upgraded|failed to synchronize|"
                              r"failed to update \S+ \(|failed to commit transaction \(download", re.I)


def _server(text):
    if ARCHIVE in text:
        return f"Arch's package archive ({ARCHIVE})"
    if REYOS_REPO in text or "reyos-local" in text:
        return "the ReyOS package server"
    m = re.search(r"from (\S+?) ?:", text)
    if m:
        return m.group(1)
    return "the package server"


def _last_error(lines):
    for line in reversed(lines):
        m = re.match(r"\s*error:\s*(.+)", line, re.I)
        if m:
            return m.group(1).strip()
    return ""


def explain(lines, what="Update"):
    """One or two sentences: why the update failed and what to do.

    `lines` is the update's output (newest last); `what` starts the sentence
    ("Update", "Switching to the Stable channel", ...)."""
    errors = [l for l in lines if re.search(r"error|warning|sudo:|failed", l, re.I)]
    text = "\n".join(errors)
    unchanged = " Nothing was changed." if _NOTHING_CHANGED.search(text) else ""

    if _SUDO.search(text):
        return (f"{what} failed: Control Center isn't allowed to run the updater "
                "(sudo refused). Reinstall reyos-control-center-gui, or run "
                "'sudo reyos-channel upgrade' in a terminal.")
    if _LOCK.search(text):
        return (f"{what} failed: another update is still running (the package database is locked). "
                "Wait for it to finish, then try again." + unchanged)
    if _SPACE.search(text):
        return f"{what} failed: not enough disk space. Free some space and try again." + unchanged
    if _SIGNATURE.search(text):
        return (f"{what} failed: a package's signature couldn't be checked, so it wasn't installed. "
                "Try again later; if it keeps happening, report it." + unchanged)
    if _CORRUPT.search(text):
        return (f"{what} failed: a download arrived damaged. Try again; the damaged file is "
                "downloaded again." + unchanged)
    if _DEPENDS.search(text):
        return (f"{what} failed: the updates don't fit together right now (a dependency problem: "
                f"{_last_error(errors) or 'see the log'}). Try again later." + unchanged)
    if _FILES.search(text):
        return (f"{what} failed: a file the update wants to install already exists "
                f"({_last_error(errors) or 'see the log'})." + unchanged)
    if _NETWORK.search(text):
        return (f"{what} failed: couldn't download from {_server(text)}: it isn't answering or is "
                "too slow. Check your internet connection, or try again later." + unchanged)
    last = _last_error(errors)
    if last:
        return f"{what} failed: {last}" + unchanged
    return f"{what} failed. See the log above for details."
