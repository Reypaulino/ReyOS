#!/usr/bin/env bash
# Rebuilds the Reyva Flatpak when Flathub updates the KDE runtime or the PySide
# BaseApp it is built on, tests that the rebuild starts, and publishes it to
# the Reyva Flatpak repo (github.com/Reypaulino/reyva-flatpak).
#
# Why: Reyva's PySide6 (from io.qt.PySide.BaseApp) uses Qt's private API,
# which only works with the exact Qt version it was built against. When
# Flathub moves org.kde.Platform//6.11 to a new Qt point release, the
# published Reyva stops starting until it is rebuilt (2026-10-31: Qt 6.11.3).
# Flathub updates the BaseApp a few days after the runtime (6.11.3: runtime
# 10-31, BaseApp 11-02); until then a rebuild fails the test too, so a failed
# combination is retried only when one of the two changes again.
#
# It rebuilds exactly what is published (the /app/manifest.json recorded in
# the published commit, same source commit), only against Flathub's current
# runtime and BaseApp; the app version stays the same. Builds in RAM
# (/dev/shm), in a separate Flatpak installation, because the host disk is
# nearly full; only the signed export touches the disk.
#
# Meant to run daily from a systemd user timer on the machine with the ReyOS
# signing key and the reyva-flatpak working copy (install-timer.sh).
#
#   rebuild.sh            normal run
#   rebuild.sh --dry-run  build and test, never publish
#   rebuild.sh --force    rebuild even if nothing changed on Flathub
set -euo pipefail

SITE=${REYVA_SITE:-$HOME/reyva-flatpak-work/site}
SRC_GIT=${REYVA_SRC_GIT:-$HOME/reyva-flatpak-work/reyos-main.git}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/reyva-rebuild
SHM=/dev/shm/reyva-rebuild
KEY=9A17D49EE3929AC6402337FA66E4085621026272
APP=com.reyapps.Reyva
BRANCH=stable
RUNTIME=org.kde.Platform//6.11
BASE=io.qt.PySide.BaseApp//6.11
PAGES_URL=${REYVA_PAGES_URL:-https://reypaulino.github.io/reyva-flatpak/repo}

DRY_RUN=0 FORCE=0 ARGS="$*"
while [ $# -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --force) FORCE=1 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || { echo "another rebuild.sh is running"; exit 0; }
exec > >(tee -a "$STATE/rebuild.log") 2>&1
echo "=== $(date -Is) rebuild.sh $ARGS"

notify() { notify-send -a Reyva -i com.reyapps.Reyva "$1" "$2" 2>/dev/null || true; }
fail() { echo "ERROR: $1"; notify "Reyva Flatpak rebuild failed" "$1"; exit 1; }
# Must return 0: under set -e a failing trap would replace the exit status.
cleanup() { if [ -d "$SHM" ]; then rm -rf --one-file-system "$SHM"; fi; }
trap cleanup EXIT

flathub_commit() {
    flatpak remote-info --user flathub "$1" 2>/dev/null | sed -n 's/^ *Commit: *//p' | head -1
}

# What the published Reyva was built against.
published=$(ostree --repo="$SITE/repo" cat "app/$APP/x86_64/$BRANCH" /files/manifest.json) \
    || fail "can't read the published Reyva from $SITE/repo"
pub() { python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get(sys.argv[1], ""))' "$1" <<<"$published"; }
pub_runtime=$(pub runtime-commit)
pub_base=$(pub base-commit)

cur_runtime=$(flathub_commit "$RUNTIME")
cur_base=$(flathub_commit "$BASE")
[ -n "$cur_runtime" ] && [ -n "$cur_base" ] || { echo "Flathub not reachable; will retry next run"; exit 0; }
base_version=$(flatpak remote-info --user flathub "$BASE" 2>/dev/null | sed -n 's/^ *Version: *//p' | head -1)

echo "published: runtime ${pub_runtime:0:12} base ${pub_base:0:12}"
echo "flathub:   runtime ${cur_runtime:0:12} base ${cur_base:0:12} (PySide $base_version)"
key="$cur_runtime $cur_base"
if [ "$FORCE" = 0 ]; then
    if [ "$cur_runtime" = "$pub_runtime" ] && [ "$cur_base" = "$pub_base" ]; then
        echo "up to date"
        exit 0
    fi
    if [ "$(cat "$STATE/failed-for" 2>/dev/null)" = "$key" ]; then
        echo "this runtime + BaseApp already failed; waiting for Flathub to update one of them"
        exit 0
    fi
fi

if [ "$DRY_RUN" = 0 ]; then
    if ! gh auth token >/dev/null 2>&1; then
        echo "GitHub login isn't available (keyring locked: nobody logged in?); will retry next run"
        exit 0
    fi
    echo probe > "$STATE/sigprobe"
    gpg --batch --yes --pinentry-mode error --local-user "$KEY" --detach-sign "$STATE/sigprobe" 2>/dev/null \
        || fail "can't sign with the ReyOS key $KEY without a passphrase prompt"
    [ -z "$(git -C "$SITE" status --porcelain)" ] || fail "$SITE has uncommitted changes; commit or clean them first"
    git -C "$SITE" pull -q --ff-only || fail "git pull in $SITE failed"
    # Each publish adds ~200 MB of objects before pruning; ostree keeps 3% free.
    [ "$(df --output=avail -k "$SITE" | tail -1)" -gt $((1500 * 1024)) ] \
        || fail "less than 1.5 GB free on the disk holding $SITE"
fi
[ "$(df --output=avail -k /dev/shm | tail -1)" -gt $((10 * 1024 * 1024)) ] \
    || fail "less than 10 GB free in /dev/shm for the build"

echo "--- build"
rm -rf --one-file-system "$SHM"
mkdir -p "$SHM"
export FLATPAK_USER_DIR=$SHM/flatpak
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# The published manifest minus its runtime/SDK/BaseApp pins, with the ReyOS
# source fetched from the local mirror (GitHub's full clone crawls).
printf '%s\n' "$published" > "$SHM/published.json"
python3 - "$SHM/published.json" "$SHM/manifest.json" "$SRC_GIT" <<'PY'
import json, re, sys
src, out, src_git = sys.argv[1:4]
m = json.load(open(src))
for k in ("runtime-commit", "sdk-commit", "base-commit"):
    m.pop(k, None)
for mod in m["modules"]:
    for s in mod.get("sources", []):
        if s.get("type") == "git" and re.search(r"(github\.com/Reypaulino/ReyOS|reyos-main\.git)", s.get("url", "")):
            s["url"] = "file://" + src_git
            print("source commit", s["commit"])
json.dump(m, open(out, "w"), indent=2)
PY
src_commit=$(python3 -c 'import json,sys; print(next(s["commit"] for mod in json.load(open(sys.argv[1]))["modules"] for s in mod.get("sources", []) if s.get("type") == "git"))' "$SHM/manifest.json")
git -C "$SRC_GIT" cat-file -e "$src_commit^{commit}" 2>/dev/null || git -C "$SRC_GIT" fetch -q origin main
git -C "$SRC_GIT" cat-file -e "$src_commit^{commit}" || fail "source commit $src_commit not in $SRC_GIT"

flatpak-builder --user --force-clean --disable-rofiles-fuse --install-deps-from=flathub \
    --default-branch="$BRANCH" --state-dir="$SHM/state" --repo="$SHM/testrepo" \
    "$SHM/build" "$SHM/manifest.json" > "$SHM/build.log" 2>&1 \
    || { tail -30 "$SHM/build.log"; fail "flatpak-builder failed (log above)"; }
new_runtime=$(flatpak info --user -c "$RUNTIME" 2>/dev/null || true)
echo "built against runtime ${new_runtime:0:12}"

echo "--- test"
# Installed the way users get it, on the runtime users have now.
flatpak remote-add --user --no-gpg-verify reyva-test "$SHM/testrepo"
flatpak install --user -y --noninteractive reyva-test "$APP//$BRANCH" > "$SHM/install.log" 2>&1 \
    || { tail -20 "$SHM/install.log"; fail "test install failed"; }
test_failed() {
    echo "TEST FAILED: $1"
    echo "$key" > "$STATE/failed-for"
    notify "Reyva Flatpak: rebuild doesn't start" \
        "$1. Flathub's runtime ${cur_runtime:0:12} and PySide $base_version don't work together yet; it retries when Flathub updates one of them."
    exit 1
}
flatpak run --user --command=python3 "$APP" -c \
    'import PySide6.QtCore, PySide6.QtGui, PySide6.QtQml, PySide6.QtQuick, PySide6.QtWebEngineCore, PySide6.QtWebEngineQuick; print("imports ok, Qt", PySide6.QtCore.qVersion())' \
    > "$SHM/imports.log" 2>&1 || { cat "$SHM/imports.log"; test_failed "PySide6 can't be imported"; }
cat "$SHM/imports.log"
# The real app for 30 s without a screen: still running = it started.
rc=0
timeout 30 flatpak run --user --env=QT_QPA_PLATFORM=offscreen "$APP" about:blank > "$SHM/run.log" 2>&1 || rc=$?
if [ "$rc" != 124 ] || grep -qE "Traceback|ImportError|undefined symbol" "$SHM/run.log"; then
    tail -20 "$SHM/run.log"
    test_failed "Reyva exited during the start test (exit $rc)"
fi
echo "Reyva ran 30 s offscreen"
rm -f "$STATE/failed-for"

new_commit=$(ostree --repo="$SHM/testrepo" rev-parse "app/$APP/x86_64/$BRANCH")
if [ "$DRY_RUN" = 1 ]; then
    echo "dry run: built and tested (commit ${new_commit:0:12}), nothing published"
    exit 0
fi

echo "--- publish"
subject="Rebuild for Flathub runtime ${cur_runtime:0:12} and PySide $base_version"
refs=("app/$APP/x86_64/$BRANCH")
ostree --repo="$SHM/testrepo" rev-parse "runtime/$APP.Locale/x86_64/$BRANCH" >/dev/null 2>&1 \
    && refs+=("runtime/$APP.Locale/x86_64/$BRANCH")
flatpak build-commit-from --src-repo="$SHM/testrepo" --gpg-sign="$KEY" --subject="$subject" \
    --no-update-summary "$SITE/repo" "${refs[@]}" || fail "signing the rebuild into $SITE/repo failed"
# Git doesn't keep empty folders, and ostree's prune needs these.
mkdir -p "$SITE/repo/refs/remotes" "$SITE/repo/refs/mirrors" "$SITE/repo/tmp"
# Keeps the Pages site (1 GB limit) from growing with every rebuild.
flatpak build-update-repo --title=Reyva --default-branch="$BRANCH" --gpg-sign="$KEY" \
    --prune --prune-depth=3 "$SITE/repo" || fail "updating the repo summary failed"
published_commit=$(ostree --repo="$SITE/repo" rev-parse "app/$APP/x86_64/$BRANCH")

git -C "$SITE" add -A
git -C "$SITE" commit -q -m "Reyva: $subject

Built and tested by tools/reyva-flatpak/rebuild.sh (ReyOS repo); same source commit ${src_commit:0:12}."
git -C "$SITE" push -q origin HEAD || fail "push to reyva-flatpak failed; push $SITE by hand"

for _ in $(seq 1 40); do
    url="$PAGES_URL/refs/heads/app/$APP/x86_64/$BRANCH"
    case $url in http*) url="$url?x=$RANDOM" ;; esac
    if [ "$(curl -fs "$url")" = "$published_commit" ]; then
        echo "live: $published_commit"
        notify "Reyva Flatpak rebuilt" "Built for Flathub's new runtime (PySide $base_version) and published. Users get it with their next update."
        exit 0
    fi
    sleep 15
done
echo "pushed, but GitHub Pages isn't serving it after 10 minutes; check the Pages deploy"
notify "Reyva Flatpak pushed" "The rebuild was pushed, but GitHub Pages hasn't picked it up yet."
