"""reyos-scan: command line for ReyOS Scan.

  reyos-scan status                      scanner, definitions, last scan
  reyos-scan scan --quick | --home | PATH...
  reyos-scan check FILE                  pre-run check of an installer/.exe
  reyos-scan run-checked FILE -- CMD...  check, then run CMD only if clean
  reyos-scan quarantine [list | add PATH [SIGNATURE] | restore ID | delete ID]
  reyos-scan history

Exit codes for scan/check/run-checked: 0 no known threats, 1 threat found,
2 not verified (scanner missing, no definitions, unreadable/too-big files),
3 cancelled. --json prints the report instead of text.

run-checked is meant as a launcher wrapper, for example Lutris's
per-game "Command prefix": `reyos-scan run-checked /path/to/game.exe --`.
ReyOS Scan never changes Lutris settings by itself."""
import argparse
import json
import os
import signal
import sys
import time

from . import core

EXIT = {"clean": 0, "found": 1, "not_verified": 2, "cancelled": 3}


def _print_report(report, as_json):
    if as_json:
        print(json.dumps(report, indent=1))
        return
    print(report["summary"])
    for f in report.get("findings", []):
        print(f"  THREAT  {f['path']}  ({f['signature']}, sha256 {f['sha256'][:16]}…)")
    for s in report.get("skipped", []):
        print(f"  NOT CHECKED  {s['path']}  ({s['reason']})")
    for e in report.get("errors", [])[:20]:
        print(f"  ERROR  {e}")
    if report.get("definitions"):
        print(f"Definitions: {report['definitions']} ({report.get('definitions_date', '')}), ClamAV {report.get('engine', '')}")


def _progress(n, path):
    print(f"\r{n} files…", end="", file=sys.stderr, flush=True)


def cmd_status(args):
    defs = core.definitions()
    last = core.last_report()
    info = {"version": core.VERSION, "installed": core.installed(), "engine": defs["engine"],
            "definitions": defs["version"], "definitions_date": defs["date"], "age_days": defs["age_days"],
            "updater": core.updater() if core.installed() else "", "last": last,
            "quarantined": len(core.quarantined())}
    if args.json:
        print(json.dumps(info, indent=1))
        return 0
    print(f"ReyOS Scan {core.VERSION}")
    if not info["installed"]:
        print("ClamAV isn't installed.")
        return 2
    print(f"ClamAV {defs['engine']}, definitions {defs['version'] or 'none'} {defs['date']}"
          + (f" ({defs['age_days']} days old)" if defs["age_days"] >= 0 else ""))
    print({"service": "Definitions update automatically (clamav-freshclam service).",
           "timer": "Definitions update automatically every day (clamav-freshclam-once timer).",
           "manual": "Definitions don't update by themselves: run `sudo freshclam`."}[info["updater"]])
    if last:
        print(f"Last scan ({last['kind']}, {time.strftime('%Y-%m-%d %H:%M', time.localtime(last['finished']))}): {last['summary']}")
    print(f"In quarantine: {info['quarantined']}")
    return 0


def _run_scan(scan, args):
    # Ctrl+C stops the scan cleanly (reported as cancelled, not clean).
    signal.signal(signal.SIGINT, lambda *_: scan.cancel())
    report = scan.run()
    if not args.json:
        print("\r", end="", file=sys.stderr)
    _print_report(report, args.json)
    return EXIT[report["status"]]


def cmd_scan(args):
    if args.quick:
        paths, kind = core.quick_scope(), "quick"
    elif args.home:
        paths, kind = [os.path.expanduser("~")], "home"
    elif args.paths:
        paths, kind = [os.path.abspath(p) for p in args.paths], "folder"
    else:
        print("Say what to scan: --quick, --home or one or more paths.", file=sys.stderr)
        return 2
    return _run_scan(core.Scan(paths, kind, progress=None if args.json else _progress), args)


def cmd_check(args):
    report = core.check_program(os.path.abspath(args.file), progress=None if args.json else _progress)
    if not args.json:
        print("\r", end="", file=sys.stderr)
    _print_report(report, args.json)
    return EXIT[report["status"]]


def cmd_run_checked(args):
    if not args.command:
        print("Give the command to run after --.", file=sys.stderr)
        return 2
    report = core.check_program(os.path.abspath(args.file))
    if report["status"] == "clean":
        os.execvp(args.command[0], args.command)
    _print_report(report, False)
    print("Not started: " + ("a threat was found." if report["status"] == "found"
                             else "the files couldn't be verified (run it yourself if you trust it)."), file=sys.stderr)
    return EXIT[report["status"]]


def cmd_quarantine(args):
    action = args.action or "list"
    if action == "list":
        items = core.quarantined()
        if args.json:
            print(json.dumps(items, indent=1))
        for q in items if not args.json else []:
            print(f"{q['id']}  {q['original_path']}  ({q['signature']}, "
                  f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(q['quarantined_at']))})")
        if not items and not args.json:
            print("Nothing in quarantine.")
        return 0
    if action == "add" and args.args:
        ok, msg = core.quarantine(os.path.abspath(args.args[0]), args.args[1] if len(args.args) > 1 else "")
    elif action in ("restore", "delete") and len(args.args) == 1:
        if action == "delete" and not args.yes:
            print("Deleting can't be undone: add --yes to confirm.", file=sys.stderr)
            return 2
        ok, msg = (core.restore if action == "restore" else core.delete)(args.args[0])
    else:
        print("usage: reyos-scan quarantine [list | add PATH [SIGNATURE] | restore ID | delete --yes ID]", file=sys.stderr)
        return 2
    print(msg)
    return 0 if ok else 1


def cmd_history(args):
    items = core.history()
    if args.json:
        print(json.dumps(items, indent=1))
        return 0
    for r in items:
        print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['finished']))}  {r['kind']:8}  {r['status']:12}  {r['summary']}")
    if not items:
        print("No scans yet.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="reyos-scan", description="Malware scan with ClamAV (ReyOS Scan).")
    p.add_argument("--version", action="version", version=f"reyos-scan {core.VERSION}")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("scan"); s.add_argument("--json", action="store_true")
    s.add_argument("--quick", action="store_true"); s.add_argument("--home", action="store_true")
    s.add_argument("paths", nargs="*")
    s = sub.add_parser("check"); s.add_argument("--json", action="store_true"); s.add_argument("file")
    s = sub.add_parser("run-checked"); s.add_argument("file"); s.add_argument("command", nargs=argparse.REMAINDER)
    s = sub.add_parser("quarantine"); s.add_argument("--json", action="store_true"); s.add_argument("--yes", action="store_true")
    s.add_argument("action", nargs="?", choices=["list", "add", "restore", "delete"]); s.add_argument("args", nargs="*")
    s = sub.add_parser("history"); s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "run-checked" and args.command[:1] == ["--"]:
        args.command = args.command[1:]
    handlers = {"status": cmd_status, "scan": cmd_scan, "check": cmd_check, "run-checked": cmd_run_checked,
                "quarantine": cmd_quarantine, "history": cmd_history}
    if args.cmd not in handlers:
        p.print_help()
        return 2
    return handlers[args.cmd](args)
