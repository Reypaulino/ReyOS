# Claude Code — Reyva Implementation Instructions

## Start here
Read **[the full Reyva development handoff](./REYVA_CLAUDE_IMPLEMENTATION_TEST_BUGFIX_HANDOFF.md)** completely before changing anything. This is the authoritative implementation and testing checklist.

Repository: `Reypaulino/ReyOS`. Work from the latest `origin/main` on a dedicated implementation branch. Check the actual code and release docs before implementing; do not assume that any proposed feature is missing.

## Mission
Implement and verify the seven approved improvements: (1) RAM optimization and leak prevention, (2) startup/idle efficiency, (3) refinements to existing smart tab sleeping, (4) privacy-aware crash recovery, (5) a guided first-launch welcome with bookmarks import, (6) lightweight optional vertical tabs and tab search, and (7) usability improvements to Shields and permissions. Add a **Smart Dashboard** on the existing New Tab view that searches or switches existing open tabs, finds bookmarks, searches the web, and launches installed web apps **in their dedicated app windows**, not duplicated private tabs.

**Do not implement cross-device sync or iOS/macOS App Store releases.** Those are postponed.

## Mandatory checks
1. Inventory existing behavior first: Low Memory Mode already freezes and may discard inactive tabs; browser bookmarks import HTML; password import supports CSV; web apps use a separate launch path. Reuse these implementations instead of creating parallel ones.
2. Capture reproducible baseline measurements before changes: aggregate process-tree PSS/RSS on Linux, CPU, startup latency, and 1/5/10/20 tab workloads; compare the same workloads after changes.
3. Avoid extra WebEngine views, always-running search indexers, polling, telemetry, new server dependencies, and account sign-ins.
4. Audit current bugs, including `docs/bugs.md`, `docs/bugs-old.md`, and `docs/fixes.md`. Reproduce suspected issues before calling them bugs; document each fix and retest it.
5. Verify first-run, bookmarks, passwords, tabs, closed-tab reopening, audio/video, web-app launch and persistent login separation, downloads including portal paths, printing/PDF, Shields, offline behavior, Qt runtime compatibility, and application shutdown.
6. Test fresh and upgraded installs in ReyOS's Flatpak/Arch launcher path and Ubuntu/Debian .deb path. Validate the download website in a **local preview** only. Preserve Windows compatibility even if its build is not a release target.
7. Produce test logs, before/after performance table, known issues with severity, build instructions, release notes draft, checksums for any local candidate artifacts, and a clear GO / NO-GO assessment. Do not state tests passed without executing them.

## Release boundary — mandatory
**No public release without owner approval.** Do not push binaries or OSTree repository updates, sign or upload release packages, create tags/GitHub Releases, deploy the website, or modify public download links. Do not merge into `main` without approval. A reviewable branch/PR, local test builds, and reports are the handoff deliverables.

## Prompt to begin
> Read `docs/handoffs/REYVA_CLAUDE_IMPLEMENTATION_TEST_BUGFIX_HANDOFF.md` and follow it as the implementation specification. First audit and baseline Reyva from current origin/main. Then implement the approved low-memory enhancements, Smart Dashboard and other scoped changes in small commits. Reproduce and fix bugs, execute all required tests, prepare local ReyOS and Ubuntu candidate builds and website preview, and write a release readiness report. Stop before merge or public release for my approval.
