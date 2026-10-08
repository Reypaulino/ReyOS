#!/usr/bin/env bash
# Moves the stable update channel to a newer Arch Linux Archive snapshot once
# GitHub's "Stable snapshot check" workflow has passed it, then builds, signs
# and publishes reyos-update-channel. Meant to run daily from a systemd user
# timer; it only acts when a promotion is due (stable date older than the most
# recent Saturday), so promotions land on Sunday. If no newer snapshot has
# passed, it asks the workflow to test yesterday's and waits for the result,
# so a failed week is retried with each following day.
#
#   promote.sh                 normal run
#   promote.sh --dry-run       build, sign and update a local copy of the repo
#                              database; don't start workflows, commit or push
#   promote.sh --date D        promote snapshot D (YYYY/MM/DD), which must have passed
#   promote.sh --force         skip the "is a promotion due" check
set -euo pipefail

REPO=${REYOS_REPO:-$HOME/Developer/ReyOS}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/reyos-promote
KEY=9A17D49EE3929AC6402337FA66E4085621026272
PKGDIR=reyos-packages/reyos-update-channel
SNAPFILE=$PKGDIR/files/usr/share/reyos/stable-snapshot
PAGES_URL=https://reypaulino.github.io/ReyOS
IMAGE=archlinux:latest
GH_REPO=Reypaulino/ReyOS
WORKFLOW=stable-snapshot-check.yml

DRY_RUN=0 FORCE=0 CANDIDATE=""
while [ $# -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --force) FORCE=1 ;;
        --date) CANDIDATE=${2:?--date needs YYYY/MM/DD}; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || { echo "another promote.sh is running"; exit 0; }
exec > >(tee -a "$STATE/promote.log") 2>&1
echo "=== $(date '+%F %T') promote.sh${*:+ $*}"

notify() { notify-send -a ReyOS -i system-software-update "$1" "$2" 2>/dev/null || true; }
fail() { echo "ERROR: $1"; notify "Stable channel promotion failed" "$1"; exit 1; }
to_epoch() { date -u -d "${1//\//-}" +%s; }

git -C "$REPO" fetch -q origin main reyos-pages

# The published package is the source of truth: a run that pushed reyos-pages
# but not main must not look like "nothing to do" next time.
published=$(git -C "$REPO" show origin/reyos-pages:reyos-local.db.tar.gz \
    | tar -xzO --wildcards '*/desc' | awk '/^%NAME%$/{getline; n=$0} /^%VERSION%$/{getline; if (n=="reyos-update-channel") print}')
[ -n "$published" ] || fail "reyos-update-channel not found in the published repo database"
current=$(echo "$published" | sed -E 's/-[0-9]+$//; s#\.#/#g')
source_date=$(git -C "$REPO" show "origin/main:$SNAPFILE")
echo "published stable snapshot: $current (package $published); origin/main says $source_date"

[ -z "$CANDIDATE" ] || [[ $CANDIDATE =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ ]] || fail "bad date: $CANDIDATE"
last_sat=$(date -u -d "$(( ($(date -u +%u) + 1) % 7 )) days ago" +%Y/%m/%d)
if [ "$FORCE" = 0 ] && [ "$(to_epoch "$current")" -ge "$(to_epoch "$last_sat")" ]; then
    echo "not due: stable is $current, most recent Saturday is $last_sat"
    exit 0
fi

if ! gh auth token >/dev/null 2>&1; then
    echo "GitHub login isn't available (keyring locked: nobody logged in?); will retry next run"
    exit 0
fi
echo probe > "$STATE/sigprobe"
gpg --batch --yes --pinentry-mode error --local-user "$KEY" --detach-sign "$STATE/sigprobe" 2>/dev/null \
    || fail "can't sign with the ReyOS key $KEY without a passphrase prompt"

results() {  # "<date> <passed|FAILED> <issue number>", newest date first
    gh issue list --repo "$GH_REPO" --state all --limit 100 --search "Stable snapshot in:title" \
        --json number,title -q '.[] | "\(.title) #\(.number)"' \
    | sed -nE 's#^Stable snapshot ([0-9]{4}/[0-9]{2}/[0-9]{2}) (passed|FAILED).* \#([0-9]+)$#\1 \2 \3#p' | sort -r
}
newest_pass() {
    results | while read -r d r n; do
        [ "$r" = passed ] || continue
        if [ -n "$CANDIDATE" ]; then [ "$d" = "$CANDIDATE" ] && { echo "$d $n"; break; }
        elif [ "$(to_epoch "$d")" -gt "$(to_epoch "$current")" ]; then echo "$d $n"; break; fi
    done
}

pick=$(newest_pass)
if [ -z "$pick" ]; then
    test_date=${CANDIDATE:-$(date -u -d yesterday +%Y/%m/%d)}
    if results | grep -q "^$test_date FAILED "; then
        echo "snapshot $test_date already FAILED the check; stable stays on $current, next run tries the next day's"
        exit 0
    fi
    if [ "$DRY_RUN" = 1 ]; then
        echo "dry run: no passed snapshot newer than $current; a real run would start the check for $test_date"
        exit 0
    fi
    echo "--- no newer snapshot has passed yet; starting the check for $test_date"
    before=$(gh run list --repo "$GH_REPO" --workflow "$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId // 0')
    gh workflow run "$WORKFLOW" --repo "$GH_REPO" --ref main -f date="$test_date"
    run=""
    for _ in $(seq 1 20); do
        sleep 6
        run=$(gh run list --repo "$GH_REPO" --workflow "$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId // 0')
        [ "$run" != "$before" ] && break
    done
    [ -n "$run" ] && [ "$run" != "$before" ] || fail "the snapshot check for $test_date didn't start"
    echo "waiting for https://github.com/$GH_REPO/actions/runs/$run"
    gh run watch "$run" --repo "$GH_REPO" --exit-status --interval 30 >/dev/null 2>&1 || true
    sleep 20  # the report job opens the issue after the test job
    CANDIDATE=$test_date
    pick=$(newest_pass)
    if [ -z "$pick" ]; then
        echo "snapshot $test_date FAILED the check; stable stays on $current, next run tries the next day's"
        notify "Arch snapshot $test_date failed the ReyOS check" "Stable stays on $current. It will try again tomorrow."
        exit 0
    fi
fi
read -r CANDIDATE ISSUE <<<"$pick"
echo "snapshot $CANDIDATE passed the check (issue #$ISSUE)"

WORK=$STATE/work
cleanup() {
    git -C "$REPO" worktree remove --force "$WORK/main" 2>/dev/null || true
    git -C "$REPO" worktree remove --force "$WORK/pages" 2>/dev/null || true
    git -C "$REPO" worktree prune
}
cleanup
rm -rf "$WORK"
mkdir -p "$WORK/out"
[ "$DRY_RUN" = 1 ] || trap cleanup EXIT
git -C "$REPO" worktree add -q --detach "$WORK/main" origin/main
git -C "$REPO" worktree add -q --detach "$WORK/pages" origin/reyos-pages
docker pull -q "$IMAGE" >/dev/null

pkgver=${CANDIDATE//\//.}
echo "$CANDIDATE" > "$WORK/main/$SNAPFILE"
sed -i "s/^pkgver=.*/pkgver=$pkgver/; s/^pkgrel=.*/pkgrel=1/" "$WORK/main/$PKGDIR/PKGBUILD"
pkg=reyos-update-channel-$pkgver-1-any.pkg.tar.zst

echo "--- build $pkg"
docker run --rm \
    -v "$WORK/main/$PKGDIR:/src:ro" -v "$WORK/out:/out" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    "$IMAGE" bash -euc '
        pacman -Sy --noconfirm --needed fakeroot binutils >/dev/null
        echo "OPTIONS=(!strip !debug emptydirs purge)" >> /etc/makepkg.conf
        useradd -m -u "$HOST_UID" builder
        cp -r /src /home/builder/pkg && chown -R builder /home/builder/pkg
        su builder -c "cd /home/builder/pkg && PACKAGER=\"ReyOS <packages@reyapps.com>\" makepkg -f --noconfirm --nodeps" >/dev/null
        cp /home/builder/pkg/*.pkg.tar.zst /out/
        chown "$HOST_UID:$HOST_GID" /out/*' || fail "building $pkg failed"
[ -f "$WORK/out/$pkg" ] || fail "build produced no $pkg"
[ "$(tar -xOf "$WORK/out/$pkg" usr/share/reyos/stable-snapshot)" = "$CANDIDATE" ] \
    || fail "built package carries the wrong snapshot date"

sign() {
    gpg --batch --yes --local-user "$KEY" --detach-sign "$1"
    gpg --verify "$1.sig" "$1" 2>&1 | grep -q 'Good signature' || fail "bad signature on $(basename "$1")"
}

echo "--- sign and add to the repo database"
cp "$WORK/out/$pkg" "$WORK/pages/"
sign "$WORK/pages/$pkg"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$WORK/pages:/repo" -w /repo \
    "$IMAGE" repo-add -q reyos-local.db.tar.gz "$pkg" || fail "repo-add failed"
sign "$WORK/pages/reyos-local.db.tar.gz"
sign "$WORK/pages/reyos-local.files.tar.gz"
tar -tzf "$WORK/pages/reyos-local.db.tar.gz" | grep -q "^reyos-update-channel-$pkgver-1/" \
    || fail "repo database doesn't list the new package"

if [ "$DRY_RUN" = 1 ]; then
    echo "dry run: built, signed and added to a local copy of the database, nothing pushed. Files in $WORK"
    exit 0
fi

echo "--- publish"
files=(reyos-local.db.tar.gz reyos-local.db.tar.gz.sig reyos-local.files.tar.gz reyos-local.files.tar.gz.sig "$pkg" "$pkg.sig")
git -C "$WORK/pages" add -- "${files[@]}"
git -C "$WORK/pages" commit -q -m "reyos-update-channel $pkgver-1: stable channel moves to Arch snapshot $CANDIDATE" -- "${files[@]}"
git -C "$WORK/pages" push -q origin HEAD:reyos-pages || fail "push to reyos-pages failed"

git -C "$WORK/main" commit -q -m "Stable channel: Arch snapshot $CANDIDATE

Passed the Stable snapshot check (#$ISSUE); promoted by tools/stable-snapshot/promote.sh." -- "$SNAPFILE" "$PKGDIR/PKGBUILD"
git -C "$WORK/main" push -q origin HEAD:main || fail "reyos-pages has $pkgver but the push to main failed; push it by hand"

for _ in $(seq 1 40); do
    if curl -fs "$PAGES_URL/reyos-local.db?x=$RANDOM" | tar -tz 2>/dev/null | grep -q "^reyos-update-channel-$pkgver-1/"; then
        echo "live on $PAGES_URL"
        gh issue comment "$ISSUE" --repo "$GH_REPO" --body "Promoted: reyos-update-channel $pkgver-1 is published; the stable channel is on $CANDIDATE." >/dev/null || true
        gh issue close "$ISSUE" --repo "$GH_REPO" >/dev/null || true
        notify "ReyOS stable channel updated" "Now on Arch snapshot $CANDIDATE (was $current)."
        exit 0
    fi
    sleep 15
done
echo "pushed, but GitHub Pages isn't serving it after 10 minutes; check the Pages deploy"
notify "ReyOS stable channel pushed" "Snapshot $CANDIDATE was pushed, but GitHub Pages hasn't picked it up yet."
