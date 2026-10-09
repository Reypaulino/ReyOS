"""Add GameMode (and the MangoHud overlay) to every installed Steam game's
launch options. Qt-free so it can be tested on its own.

Steam starts its games itself, so the only per-game hook is the launch
options it keeps in userdata/<id>/config/localconfig.vdf. Steam rewrites
that file when it exits, so it has to be closed while we edit it."""
import os
import re
import subprocess
from pathlib import Path

WRAPPERS = ("gamemoderun", "mangohud")
# Steam lists these as installed apps, but they're runtimes, not games.
_NOT_GAMES = re.compile(r"proton|steam linux runtime|steamworks common|steamvr", re.I)
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*|\s+')


def steam_roots():
    home = Path.home()
    seen, roots = set(), []
    for path in (home / ".local/share/Steam", home / ".steam/steam",
                 home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        try:
            real = path.resolve(strict=True)
        except OSError:
            continue
        if real not in seen and (real / "steamapps").is_dir():
            seen.add(real)
            roots.append(real)
    return roots


def steam_running():
    return subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "steam"],
                          stdout=subprocess.DEVNULL).returncode == 0


# ---- VDF (Valve's KeyValues text format) ------------------------------------
# A node is a list of [key, value] pairs, value being a string (kept escaped,
# exactly as in the file) or another node, so a file round-trips unchanged
# apart from whitespace.

def parse_vdf(text):
    stack, node, key = [], [], None
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            child = []
            node.append([key, child])
            stack.append(node)
            node, key = child, None
        elif brace == "}":
            node = stack.pop()
        elif s is not None:
            if key is None:
                key = s
            else:
                node.append([key, s])
                key = None
    if stack:
        raise ValueError("unbalanced braces")
    return node


def dump_vdf(node, depth=0):
    out, tab = [], "\t" * depth
    for key, value in node:
        if isinstance(value, list):
            out.append(f'{tab}"{key}"\n{tab}{{\n{dump_vdf(value, depth + 1)}{tab}}}\n')
        else:
            out.append(f'{tab}"{key}"\t\t"{value}"\n')
    return "".join(out)


def _get(node, key, create=False):
    for k, v in node:
        if k.lower() == key.lower() and isinstance(v, list):
            return v
    if not create:
        return None
    child = []
    node.append([key, child])
    return child


def _get_str(node, key):
    for k, v in node:
        if k.lower() == key.lower() and isinstance(v, str):
            return v
    return None


def _set_str(node, key, value):
    for pair in node:
        if pair[0].lower() == key.lower() and isinstance(pair[1], str):
            pair[1] = value
            return
    node.append([key, value])


# ---- Installed games and launch options -------------------------------------

def installed_games(root):
    """{appid: name} for the games installed in every library of one Steam."""
    libraries = [root]
    try:
        folders = _get(parse_vdf((root / "steamapps/libraryfolders.vdf").read_text(errors="replace")), "libraryfolders")
        for _, lib in folders or []:
            if isinstance(lib, list) and _get_str(lib, "path"):
                libraries.append(Path(_get_str(lib, "path").replace("\\\\", "\\")))
    except (OSError, ValueError):
        pass
    games, seen = {}, set()
    for lib in libraries:
        apps = lib / "steamapps"
        try:
            if apps.resolve() in seen:
                continue
            seen.add(apps.resolve())
            manifests = list(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            try:
                state = _get(parse_vdf(manifest.read_text(errors="replace")), "AppState")
            except (OSError, ValueError):
                continue
            appid, name = _get_str(state or [], "appid"), _get_str(state or [], "name") or ""
            if appid and not _NOT_GAMES.search(name):
                games[appid] = name
    return games


def compose(existing, wanted):
    """Launch options with `wanted` wrappers in front of %command%, keeping
    everything else the user had (environment variables, game arguments)."""
    existing = existing.strip()
    if "%command%" in existing:
        before, after = existing.split("%command%", 1)
    else:  # plain arguments go after the game
        before, after = "", (" " + existing if existing else "")
    kept = [t for t in before.split() if t not in WRAPPERS]
    prefix = " ".join(kept + list(wanted))
    result = (prefix + " " if prefix else "") + "%command%" + after
    return "" if result == "%command%" else result


def apply(wanted):
    """Set the launch options of every installed game for every Steam user.
    Returns (ok, message)."""
    if steam_running():
        return False, "Close Steam first (Steam menu > Exit), then press this again."
    roots = steam_roots()
    if not roots:
        return False, "Steam hasn't been set up yet -- start it once and sign in."
    changed, total, users = 0, 0, 0
    for root in roots:
        games = installed_games(root)
        for config in (root / "userdata").glob("*/config/localconfig.vdf"):
            try:
                tree = parse_vdf(config.read_text(errors="replace"))
            except (OSError, ValueError) as e:
                return False, f"Couldn't read Steam's settings ({config}): {e}"
            store = _get(tree, "UserLocalConfigStore", create=True)
            steam = _get(_get(_get(store, "Software", True), "Valve", True), "Steam", True)
            apps = _get(steam, "apps", create=True)
            users += 1
            dirty = False
            for appid in games:
                app = _get(apps, appid, create=True)
                old = _get_str(app, "LaunchOptions") or ""
                new = compose(old, wanted)
                total += 1
                if new != old:
                    _set_str(app, "LaunchOptions", new)
                    changed += 1
                    dirty = True
            if dirty:
                backup = config.with_name("localconfig.vdf.reyos-backup")
                backup.write_bytes(config.read_bytes())
                tmp = config.with_name("localconfig.vdf.reyos-tmp")
                tmp.write_text(dump_vdf(tree))
                tmp.replace(config)
    if total == 0:
        return False, "No installed Steam games found -- install a game, then press this again."
    what = " and ".join({"gamemoderun": "GameMode", "mangohud": "the performance overlay"}[w] for w in wanted) or "nothing extra"
    if changed == 0:
        return True, f"All {total} Steam game(s) already use {what}."
    return True, f"Steam games now start with {what} ({changed} of {total} updated). Start Steam again."
