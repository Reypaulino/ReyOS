#!/usr/bin/env python3
"""Markdown table of two bench.py results: median (min–max) before and after.

    python3 compare.py baseline.json after.json
"""
import json
import sys

METRICS = [
    ("ready_seconds", "Ready (s)", 2),
    ("pss_mb", "PSS (MB)", 1),
    ("rss_mb", "RSS (MB)", 1),
    ("webengine_processes", "Web processes", 0),
    ("idle_cpu_seconds", "Idle CPU (s/30 s)", 2),
    ("delta_pss_mb", "PSS growth (MB)", 1),
]


def cell(summary: dict, key: str, digits: int) -> str:
    entry = summary.get(key)
    if not entry:
        return "–"
    fmt = f"{{:.{digits}f}}"
    if entry["min"] == entry["max"]:
        return fmt.format(entry["median"])
    return f"{fmt.format(entry['median'])} ({fmt.format(entry['min'])}–{fmt.format(entry['max'])})"


def change(before: dict, after: dict, key: str) -> str:
    if not before.get(key) or not after.get(key):
        return ""
    b, a = before[key]["median"], after[key]["median"]
    if not b:
        return ""
    return f"{(a - b) / b * 100:+.0f}%"


def main() -> int:
    before = json.load(open(sys.argv[1]))
    after = json.load(open(sys.argv[2]))
    print(f"Before: {before['label']} · After: {after['label']}  ")
    print(f"Machine: {before['machine']}  \n")
    print("| Scenario | Metric | Before | After | Change |")
    print("|---|---|---|---|---|")
    for name, data in before["scenarios"].items():
        if name not in after["scenarios"]:
            continue
        b, a = data["summary"], after["scenarios"][name]["summary"]
        for key, label, digits in METRICS:
            if key in b or key in a:
                print(f"| {name} | {label} | {cell(b, key, digits)} | {cell(a, key, digits)} | {change(b, a, key)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
