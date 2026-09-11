# ReyOS Reader

A native reading application for EPUB books, PDF documents, and CBZ/CBR manga/comics. One application, two reading modes (book / manga), sharing a single library, theme, and persistence layer.

## Naming — deliberate deviation from the original spec

The build brief suggested `org.reyos.Reader` / `org.reyos.reader.desktop`. The Phase 0 audit found that **no existing ReyOS app uses reverse-DNS naming** — `reyos-browser`, `reyos-control-center`, and `reyos-welcome` all use plain `reyos-<name>` for the package, binary, `.desktop` file, and icon. Reader follows the real repo convention instead of the suggested one, to stay visually/mechanically consistent with the other three apps:

- Package: `reyos-reader`
- Executable: `/usr/bin/reyos-reader`
- Desktop file: `reyos-reader.desktop`
- Icon: `reyos-reader.svg`
- Python app id / `QGuiApplication.setDesktopFileName`: `reyos-reader`

## Architecture

**Rewritten 2026-09-10 to drop Kirigami entirely** — see "Kirigami removal" below for why. Reader is now plain `QtQuick.Controls`, the same shape as `reyos-browser`, not the Kirigami-drawer shape originally described here:

- A `qml/kirishim/` compat layer (Units, Theme, Heading, Icon, Separator, PlaceholderMessage, SearchField, AbstractCard, Page/ScrollablePage, OverlaySheet, Action, GlobalDrawer, ApplicationWindow) reimplements just the subset of Kirigami's QML API this app actually used, on top of plain `QtQuick.Controls`. Every page file's only change was its import line (`import "kirishim" as Kirigami` instead of `import org.kde.kirigami as Kirigami`) — the `Kirigami.X` names in the QML below are these shim types, not real Kirigami.
- `qml/kirishim/ApplicationWindow.qml` provides the app shell: a docked sidebar (`globalDrawer`, laid out via `RowLayout`) next to a `Controls.StackView` (`pageStack`), plus a simple top `ToolBar` showing the current page's `title` and `actions` (Kirigami normally renders these via `pageStack.globalToolBar`, which has no QtQuick Controls equivalent).
- `main.py` bootstraps `QApplication` + `QQmlApplicationEngine`, registers a `Backend(QObject)` context property. Long-running work (library scan, thumbnailing, archive opening, PDF merge/split) runs on `QThread` workers that emit signals back to QML.
- Reading views are separate QML pages pushed onto `pageStack`: `LibraryPage.qml`, `BookReaderPage.qml` (EPUB), `PdfReaderPage.qml`, `ComicReaderPage.qml` (CBZ/CBR/loose images), `PdfToolsPage.qml` (merge/split).

```
reyos-packages/reyos-reader/
├── PKGBUILD
└── files/
    ├── usr/bin/reyos-reader                                  # launcher (VM GPU workaround, same idiom as reyos-browser)
    ├── usr/share/applications/reyos-reader.desktop
    ├── usr/share/icons/hicolor/scalable/apps/reyos-reader.svg
    └── usr/share/reyos/reader/
        ├── main.py
        ├── library.py          # SQLite access layer
        ├── scanner.py          # library-folder scanning + metadata extraction (QThread worker)
        ├── imagecache.py       # QQuickImageProvider: comic pages + icon-theme lookups
        ├── highlighter.js      # EPUB text-highlighting selection UI, injected into the WebEngineView
        ├── formats/
        │   ├── __init__.py     # Format enum + sniffing by extension
        │   ├── epub.py         # ebooklib wrapper, TOC, safe EpubSchemeHandler
        │   ├── comic.py        # CbzArchive / CbrArchive, shared ComicArchive interface
        │   ├── pdf.py          # thin QPdfDocument metadata/cover helper
        │   └── pdf_tools.py    # pypdf-backed merge/split
        └── qml/
            ├── qmldir
            ├── ReyOSStyle.qml
            ├── Main.qml
            ├── LibraryPage.qml
            ├── BookReaderPage.qml
            ├── PdfReaderPage.qml
            ├── ComicReaderPage.qml
            ├── PdfToolsPage.qml
            ├── kirishim/        # QtQuick-Controls compat layer, see above
            └── components/
                ├── LibraryCard.qml
                ├── ContinueReadingCard.qml
                └── BookmarkRibbon.qml
```

### Kirigami removal (2026-09-10)

Ubuntu port work (below) found two real, confirmed-live problems with the original Kirigami-based build, not theoretical ones:

1. Ubuntu 24.04 has no Qt6/KF6 Kirigami at all — the only Kirigami package in its repos, `qml-module-org-kde-kirigami2`, is Kirigami **2** built against **Qt5**, incompatible with PySide6's Qt6.
2. A Flatpak build against `org.kde.Platform//6.9` (which does bundle a real Qt6 Kirigami) built fine but crashed at runtime: pip's PySide6 wheel bundles its own private Qt 6.9.2 build, which is not ABI-compatible with the KDE runtime's separately-built Qt 6.9 that Kirigami's plugins link against — `undefined symbol: _ZNK11QQmlPrivate18AOTCompiledContext9setLocalsE...`, confirmed by actually loading it, not guessed. A real fix would mean compiling PySide6 from source against the runtime's own Qt (multi-hour build, not attempted).

Decision: drop Kirigami, rewrite onto `QtQuick.Controls` via the `kirishim/` shim described above. Three real bugs surfaced during the rewrite (all found via live `QQmlProperty` inspection of a running instance, not by code review): `Controls.ApplicationWindow` defaults to `visible: false` unlike Kirigami's (window never showed at all); the sidebar's width was bound to `globalDrawer.width` while `globalDrawer`'s own width was *also* re-bound (via `anchors.fill`) back onto that same sidebar slot — a direct circular binding that collapsed both to 0; `StackView.initialItem` set as a dotted assignment from the outer document ran too late to trigger its auto-push, replaced with an explicit `pageStack.push()` in `Component.onCompleted`.

## Dependencies

| Need | Arch package (`extra`) | Ubuntu/Debian equivalent |
|---|---|---|
| App framework | `pyside6` | bundled venv (pip `PySide6==6.9.2`), no Kirigami/KDE Frameworks dependency at all since the removal above |
| PDF | *(bundled in `pyside6`/`qt6-declarative`)* | same, bundled in the venv's PySide6 |
| EPUB | `python-ebooklib` | pip `ebooklib` in the bundled venv |
| CBZ | *(none — stdlib `zipfile`)* | same |
| CBR | `python-rarfile` + `unrar` | pip `rarfile` in the venv + apt `unrar` (real system dependency, not bundled — a Python wheel can't bundle a GPL/proprietary CLI tool) |
| PDF merge/split | `python-pypdf` | pip `pypdf` in the venv |

`reyos-reader`'s Arch `PKGBUILD` `depends=()` (as of pkgrel 19, kirigami removed):
```
depends=('pyside6' 'qt6-webengine' 'qt6-webchannel' 'python-ebooklib' 'python-rarfile' 'unrar' 'python-pypdf')
```

### Ubuntu/Debian packaging (added 2026-09-10)

Same self-contained-venv `.deb` shape as `reyos-browser`'s: a bundled Python venv under `/opt/reyos-reader/.venv` (built by copying the browser's already-working PySide6+QtWebEngine venv, then `pip install ebooklib rarfile pypdf` into the copy — avoids a from-scratch PySide6 download), `/usr/bin/reyos-reader` launcher pointing at it, `/usr/share/applications/reyos-reader.desktop`. `apt` `Depends:` covers `unrar` plus the same Chromium/QtWebEngine runtime library set the browser's `.deb` needed (`libnspr4`, `libnss3`, `libxcb-cursor0`, etc. — Reader also embeds a `WebEngineView` for EPUB).

**Real gap, same class already flagged for the browser**: the staging directory (`~/reyos-reader-deb`) lives entirely outside git, same as `~/reyos-browser-deb` — not version-controlled, so a future rebuild has no reviewable source of truth for `DEBIAN/control`/`postinst`. Not brought into the repo yet (explicitly deferred for the browser's version 2026-09-10; the same call applies here).

Published as GitHub Releases on `Reypaulino/ReyOS`: `reyos-reader-v1.0.0-1ubuntu1` (initial port) → `-2ubuntu1` (EPUB cover-image zoom fix, PDF Tools preview button) → `-3ubuntu1` (highlighting) → `-4ubuntu1` (bookmark corner-tap fix).

## Supported file formats

| Format | Library used | Status |
|---|---|---|
| `.epub` | `ebooklib` + Qt `QWebEngineView` (sandboxed, see Rendering strategy) | v1 |
| `.pdf` | Qt `QtPdf` / `QtQuick.Pdf` | v1 (unencrypted; encrypted PDFs surface a clear error, see Known limitations) |
| `.cbz` | stdlib `zipfile` | v1 |
| `.cbr` | `rarfile` + `unrar` | v1 — implemented, see Testing plan for real pass/fail, not assumed |
| loose image folder as a "chapter" | stdlib `pathlib`/`Pillow`-free (Qt `QImage` reads the common formats directly) | v1, reuses the comic page-list code path |

## Library model

SQLite database at `~/.local/share/reyos-reader/library.db` (see Persistence model for schema). A **library folder** is a user-chosen directory (`~/Books`, `~/Manga`, ...) stored in `library_folders`; scanning only walks *inside* configured folders — Reader never scans the filesystem outside what the user explicitly added, and "Refresh Library" is a manual, on-demand action (a `QThread` `ScanWorker`), not a background poller or filesystem watcher in v1 (the spec allows watching later "only if it can be done efficiently" — deferred, see Future roadmap in the build brief).

Each discovered file becomes one `items` row. Metadata extraction is per-format (`ebooklib`'s OPF metadata for EPUB, `QPdfDocument.metaData()` for PDF, first-image-as-cover + filename-as-title for CBZ/CBR/image folders). Missing metadata never fails the scan — the filename (minus extension) becomes the title, per the spec.

Filters (All / Books / Manga / Comics / PDFs) are a `format` column query, not separate tables — "Manga" vs "Comics" is a user-set `reading_direction`/category hint on CBZ/CBR items (right-to-left defaults to "Manga" filter bucket, left-to-right to "Comics"), not a distinct file type.

## Rendering strategy

**EPUB** — a `QWebEngineView` (same Qt module `reyos-browser` already depends on), but locked down, not a general web view:
- A custom `QWebEngineUrlSchemeHandler` registered for a private `reyos-epub:` scheme serves each chapter/resource (HTML, CSS, images, fonts) by reading it straight out of the open `ebooklib` book object — **no permanent extraction to disk**, each resource is read into memory only when the page actually requests it.
- **Revised from the original plan**: JavaScript is left *enabled* (`runJavaScript()` — used for progress-restore scrolling, in-page find, and appearance CSS injection — turned out not to run at all with `JavascriptEnabled` off, a real Qt behavior confirmed live, not assumed). The actual containment boundary is a `QWebEngineUrlRequestInterceptor` (`EpubNavigationInterceptor`) that blocks every request whose scheme isn't `reyos-epub`, plus `LocalContentCanAccessRemoteUrls`/`LocalContentCanAccessFileUrls` left off — so a book's markup or script has no route to the network or any other local file, regardless of what it asks for. This still satisfies "do not permit arbitrary EPUB content unrestricted access to the local machine," just via network/origin isolation rather than disabling script execution outright.
- Reading-appearance controls (font size, line spacing, letter/word spacing, margins, alignment, Dark/Light/Sepia) are injected as a small stylesheet override, not by editing the book's own CSS files. Default body font is a serif stack (Georgia/Liberation Serif/DejaVu Serif) and the Light reading theme uses a warm cream background rather than stark white — both requested by the user (2026-08-26) to feel closer to Kindle's desktop reading pane.
- **Kindle-style reading chrome** (also user-requested 2026-08-26): the toolbar and a bottom status bar (chapter/page position + percent) auto-hide after 3 seconds idle, reappearing on hover near either edge or via a small always-present reveal handle centered at the top. `BookReaderPage.qml` additionally turns chapters by clicking the left/right ~7% page edges. User confirmed liking the result the same day; the same idle-hide + reveal-handle treatment was then also applied to `ComicReaderPage.qml` (which already had its own 25%-wide edge-click prev/next zones from v1, now paired with the same auto-hiding header/footer).

**PDF** — `QtQuick.Pdf`'s `PdfDocument` + `PdfMultiPageView` QML components. Qt renders and caches pages on demand internally; Reader does not rasterize the whole document up front and does not implement its own PDF page cache — this is exactly the "prefer Qt PDF, avoid converting the whole file to images" guidance from the brief, achieved by using the Qt-maintained component rather than hand-rolling one.

**CBZ/CBR/image-folder ("comic") pages** — a `QQuickImageProvider` (`image://reyospage/<item-id>/<page-index>`) backed by the `ComicArchive` abstraction (`CbzArchive`/`CbrArchive`, same interface: `list_pages()`, `read_page_bytes(index)`). QML's `Image` with `asynchronous: true` inside a `ListView`/`PathView` requests pages by URL; Qt Quick's own view virtualization (only visible delegates + a small `cacheBuffer` are instantiated) combined with an explicit bounded LRU in the image provider (see Memory-management strategy) means only a handful of decoded pages ever exist in memory at once, regardless of archive size.

## Persistence model

SQLite (`~/.local/share/reyos-reader/library.db`), per the spec's explicit direction. Schema:

```sql
CREATE TABLE library_folders (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    library_folder_id INTEGER REFERENCES library_folders(id),
    title TEXT NOT NULL,
    author TEXT,
    format TEXT NOT NULL,              -- epub | pdf | cbz | cbr | images
    cover_cache_path TEXT,
    added_at TEXT NOT NULL,
    last_opened_at TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    reading_direction TEXT NOT NULL DEFAULT 'ltr',  -- ltr | rtl
    view_mode TEXT NOT NULL DEFAULT 'single',        -- single | double | continuous | webtoon
    zoom REAL NOT NULL DEFAULT 1.0,
    progress_json TEXT,                -- format-specific location, e.g. {"page": 42} or {"chapter": 3, "scroll_frac": 0.6}
    progress_percent REAL NOT NULL DEFAULT 0.0,
    missing INTEGER NOT NULL DEFAULT 0  -- set when the source file is gone, item stays visible, never auto-deleted
);

CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    location_json TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL
);
```

Writes go through the same atomic pattern already established by `reyos-browser` (`write to a temp file, os.replace`) where flat files are used (none needed here beyond SQLite itself, which is durable by construction); SQLite access is wrapped in a single `Library` class opening one connection with `PRAGMA journal_mode=WAL` so a crash mid-write can't corrupt the whole database.

A missing/moved source file is detected on scan or on open, flips `missing=1`, and the item stays in the library (greyed out, "File not found") rather than being silently dropped — satisfies "handle moved/deleted files gracefully... do not crash."

## Memory-management strategy

Two independent mechanisms, one per content type:

1. **PDF** — delegated entirely to `QtQuick.Pdf`'s own internal page cache. Not reimplemented.
2. **Comics (CBZ/CBR/images)** — a small in-process LRU in `imagecache.py`'s `QQuickImageProvider`, holding at most **5 decoded `QImage`s**: the current page, the previous page, and the next 2–3 pages, matching the brief's stated target exactly. Anything evicted from the LRU is simply dropped (Python/Qt reference-counted, no manual `del` bookkeeping needed beyond removing the dict entry) and re-decoded on demand if revisited. Full-resolution source images are downscaled to the view's actual pixel size before being handed to QML (`QImage.scaled()` against the current viewport size, not the raw archive resolution) so a 4000px-wide scan doesn't sit in memory at full size when displayed at 1080p.

Measured, not assumed (see Testing plan for the exact numbers once run): a small (~20-page) and a large (~150+ page, full-resolution) generated CBZ are both opened and scrolled through on the Dev VM, RSS sampled before opening, after opening, and after scrolling to the end, to confirm memory stays bounded rather than growing per page viewed.

## Packaging

Standard ReyOS `PKGBUILD` shape (`cp -a files/... $pkgdir/`, `chmod` executables to 755, everything else 644) — no tarball `source=()`, matching every other `reyos-*` package. **`reyos-reader` is deliberately not in `reyos-iso/packages.x86_64`** (removed 2026-09-10, see Roadmap) — like `reyos-browser`, it ships as an opt-in package on `reyos-local` (`reyos-reader 1.0.0-19` published there this session) rather than being baked into the base image, so a Reader-only fix never needs a full ISO rebuild.

No Control Center page (Reader owns its own in-app preferences, per the brief). No Welcome integration in v1 (optional future work, not mandatory in the base ISO). No AppStream `metainfo.xml` in v1 — the audit found that's a Flatpak-only, still-WIP convention unique to `reyos-browser`, not a repo-wide requirement.

## Known limitations (v1)

- CBR support depends on the external `unrar` binary; if it's ever missing at runtime, Reader surfaces a clear "CBR support unavailable" error for that file rather than crashing, but does not remove CBR files from the library.
- Encrypted/password-protected PDFs are detected and surface a clear error; a password-prompt UI is not implemented in v1.
- No full-text search across book contents in v1 (library search is title/author only, per the brief's explicit scope limit). "Find in page" (2026-08-18) only searches the *current chapter/page*, not the whole book — a real, user-noticed gap for anything longer than a few pages, see Roadmap.
- Highlighting (2026-09-10) works only for EPUB — PDF and comic pages render through `QtQuick.Pdf`/an image provider, not a DOM the same `<mark>`-wrapping approach can target, so there's no highlighting there yet. See Roadmap.
- No filesystem watcher — library refresh is manual.
- No online metadata, covers, or scraping of any kind (offline-only, by design).
- Double-page spread heuristics (detecting genuinely wide images vs. two single pages) are basic in v1: the reading-direction/view-mode combination is user-selected per item, not auto-detected per page.
- **No PDF form-field support.** Checked directly against the installed `pyside6` 6.11.2 on the Dev VM: `PySide6.QtPdf` exposes only `QPdfDocument`, `QPdfBookmarkModel`, `QPdfLink(Model)`, `QPdfPageNavigator`, `QPdfPageRenderer`, `QPdfSearchModel`, `QPdfSelection` -- no AcroForm/form-field class of any kind, and the `QtQuick.Pdf` QML module has no "form" references either. Qt's PDF stack here is render/search/link-navigation only. Filling PDF forms would need a second, unrelated PDF library (e.g. PyMuPDF or pypdf) purely for field detection + value read/write, plus custom QML input overlays positioned over Qt's rendered page images -- a real subsystem, not a small addition, and it pushes Reader toward "PDF editor" territory the original brief explicitly avoided (Okular stays the general-purpose PDF tool). User asked for this 2026-08-26; deliberately deferred to a later version rather than built ad hoc -- see Future roadmap below.

## PDF Tools: merge/split (added 2026-09-08)

User asked for a way to merge/split PDFs locally instead of using a web tool, and whether it belonged in `reyos-reader` given it already owns PDFs in the app ecosystem. Answer: yes, but it's a genuine (small) scope note worth recording here rather than silently absorbing — `formats/pdf.py`'s existing PDF support is `QtPdf`'s `QPdfDocument`, which is read-only (render/search/link-navigation only, confirmed in the "No PDF form-field support" entry above); it has no write/save API at all, so merge/split needed a second library regardless. Added `python-pypdf` as a new `depends=` (pkgrel 18) — same dependency this doc's own Future roadmap section already flagged as the likely candidate for form-filling, so this isn't a surprise addition.

New `formats/pdf_tools.py`: `merge_pdfs(paths, output)` (concatenates in list order), `split_pdf(path, output, ranges_str)` (1-indexed page ranges like `1-3,5,8-10`, parsed and validated — out-of-range or malformed input raises a clear error rather than silently clamping), `page_count(path)`. Both merge and split only ever read the inputs and write a brand-new output file — never modify or delete the source PDFs, matching this doc's own "originals are never touched" pattern used elsewhere in Reader. Encrypted/password-protected inputs are detected and rejected with a clear message rather than crashing (same posture as `pdf.py`'s existing `PdfEncryptedError` handling).

New `Backend` slots in `main.py` (`pickPdfsToMerge`, `pickPdfToSplit`, `pickPdfSaveAs`, `pdfPageCount`, `mergePdfs`, `splitPdf`) run the actual merge/split on a background `QThread` (`PdfToolWorker`, mirrors `reyos-connect`'s `ActionWorker` convention) so a large merge doesn't freeze the UI. New `PdfToolsPage.qml` (reachable via a new "PDF Tools" entry in the nav drawer, below a separator) — two `Kirigami.AbstractCard` sections (Merge: add/reorder/remove files, then "Merge Into..."; Split: pick one file + a page-range field, then "Split Into...") with a shared `Kirigami.InlineMessage` result banner.

**Live-tested on `ReyOS-Test` (2026-09-08)**: since the Dev VM's SSH access was broken all session (see [[project_reyos]]), the updated files were pushed directly onto the running live-ISO test VM instead — packaged as a tarball, served over a throwaway `python3 -m http.server`, pulled with `curl` and extracted with `sudo tar` over the installed `/usr/share/reyos/reader/` (not a real `makepkg`/`pacman -U` package flow, a real gap to close before this ships). `python-pypdf` had to be installed manually too (`sudo pacman -S python-pypdf`, pulled cleanly from `extra`), since this ISO predates the `PKGBUILD` dependency bump. With that in place, `reyos-reader` launched cleanly (module import succeeded, no `ModuleNotFoundError`), and clicking through to the new **PDF Tools** nav entry rendered both cards correctly — Merge's "Merge Into..." button correctly stayed disabled with fewer than 2 files queued, Split showed "No file selected" and the page-range field as designed. (Real environment gotcha unrelated to this feature: this VM's Wayland compositor didn't register simultaneous mouse-down+up as a click — separating them with a ~300ms delay fixed it; worth remembering for any future GUI automation against this same VM.)

**Not yet tested**: actually running a merge or split through the file-picker dialogs end-to-end (adding real PDFs, picking an output path, confirming the result opens correctly and originals are untouched) — the page renders and its enable/disable logic is confirmed correct, but no file was actually merged or split this session. Also not yet done: a real `makepkg`/`pacman -U` install (this was a direct file overlay onto an already-installed package, not the packaging flow itself).

This intentionally stays scoped to whole-page merge/split, not a PDF editor — no form-filling, no page rotation/deletion-in-place, no annotation. If form-field filling (already on the Future roadmap below) gets built later, it can share the `python-pypdf` dependency this feature just added.

## Highlighting (added 2026-09-10)

User asked for EPUB text highlighting + notes, similar to Kindle. Selecting text in `BookReaderPage.qml` shows a small floating color picker (yellow/green/blue/pink, defined in `highlighter.js`); picking a color wraps the selection in a `<mark>` and persists it to a new `highlights` SQLite table (`item_id`, `chapter`, `range_json`, `color`, `snippet`, `note`). A "Highlights" toolbar button lists every highlight across the whole book with its snippet, chapter, an editable note field, jump-to-chapter, and delete; clicking a highlight in the text removes it directly.

No `QWebChannel` — that's the browser's mechanism for its password bridge, and would mean bundling `qwebchannel.js` and registering a channel object here too. Reused the simpler `console.log`-prefix trick instead (`"REYOS_HIGHLIGHT_NEW:"`/`"REYOS_HIGHLIGHT_CLICK:"`, picked up by `WebEngineView.onJavaScriptConsoleMessage`), acceptable here since EPUB content is always our own sandboxed `reyos-epub://` scheme, never an arbitrary page.

Range persistence uses character offsets into `document.body`'s flattened text content (computed via `TreeWalker`), not DOM node references, since those don't survive a fresh chapter load. Re-applying a highlight walks the same `TreeWalker` and wraps each intersecting text node's overlapping span separately, so a highlight crossing an inline tag boundary (e.g. selecting across a `<b>`) still renders as multiple `<mark>` fragments sharing one id, instead of failing outright.

**Verified independently**, not just by inspection: the library round-trip (add/list/update-note/remove) against a throwaway DB, and the JS wrap/apply logic in a real `WebEngineView` against known text offsets (confirmed the resulting `<mark>` wrapped exactly the intended substring, byte-for-byte). One real bug caught by a live end-to-end test rather than review: a bare `ToolTip.visible` in a file that imports `QtQuick.Controls` under the `Controls` alias needs `Controls.ToolTip.visible` — without it, `StackView.push` failed outright with "Non-existent attached object."

## Roadmap

Ranked by what's most likely to matter next, not strictly by effort. None of this is started unless a dated section above says otherwise.

1. **Book-wide search.** "Find in page" only searches the current chapter — for anything longer than a few pages this is a real, already-noticed gap (see Known limitations). Needs a per-book search index: either scan all chapters' extracted text on demand when the search box is used (simplest, slower for very long books) or build a lightweight index at library-scan time (faster, more moving parts — extra schema, invalidation when a file changes). Start with the on-demand version; only build an index if it's actually too slow in practice.
2. **Export highlights and notes.** Kindle's "My Clippings.txt" is the model: a "Copy as text" or "Export" action from the Highlights sheet that dumps snippet + note + chapter per highlight, so notes taken in Reader are usable outside it (a paper, a summary, anywhere else). Low effort — the data's already there in `list_highlights()`, this is purely a formatting + file-save/clipboard action.
3. **PDF form-field filling.** Requested 2026-08-26, deferred since. Needs a new `formats/pdf_forms.py` module for field detection and value read/write (candidate library: `python-pymupdf`, since `pypdf` — already a dependency for merge/split — has weaker form support) and QML input widgets overlaid on `PdfMultiPageView` at each field's page-space rect. Scope dependency choice, save-in-place vs. save-as, and encrypted-PDF interaction before starting; this is a real subsystem, not a small addition.
4. **PDF and comic highlighting/annotation.** Today's highlighting is EPUB-only because it's built on wrapping DOM text nodes in a `WebEngineView` — PDF pages render via `QtQuick.Pdf`'s `PdfMultiPageView` and comic pages via a plain `Image` bound to an image provider, neither of which has a DOM to mark up. Would need a parallel, genuinely different mechanism: an overlay `Canvas`/`Shape` drawing highlight rects in page-space coordinates, persisted as `(page, rect, color)` rather than a text-offset range. Real scope, don't bolt it onto the EPUB `highlighter.js` mechanism.
5. **Keyboard-only highlighting.** Select text, press a shortcut, done — highlights with the last-used (or a fixed default) color without touching the mouse for the floating picker. Small addition on top of the existing `highlighter.js`/backend plumbing once someone actually asks for it.
6. **Filesystem watcher for library folders** (currently manual "Refresh Library" only) — explicitly deferred in v1's own scope ("only if it can be done efficiently"), still not started.
7. **Bring both `.deb` staging directories under version control** (`~/reyos-browser-deb` and `~/reyos-reader-deb`) — currently untracked host-only folders, the same real gap flagged for the browser 2026-08-24 (a missing-libraries bug shipped once already because of it) and now true for Reader's `.deb` too. Deferred by explicit user decision for the browser 2026-09-10; revisit for both together rather than fixing one and not the other.
8. ~~Add `reyos-reader` to `reyos-iso/packages.x86_64`~~ — **reversed 2026-09-10**: explicitly pulled *out* of the base ISO instead (it had been added at some point without a recorded decision). Reader now ships the same way `reyos-browser` does: an opt-in package on `reyos-local`, installed post-boot, so a Reader fix never needs a full ISO rebuild. `reyos-reader 1.0.0-19` (Kirigami removed, highlighting, bookmark corner-tap fix) published to `reyos-local` this same session.
9. **CBR end-to-end test** — `unrar` is wired as a dependency on both Arch and Ubuntu builds, but no `.cbr` file has actually been opened and paged through this session or before; still genuinely untested, not just "probably fine."

## Testing plan

Tested against the actual installed Arch package on the Dev VM (`ReyOS`) and, where a fresh-user flow matters, `ReyOS-Test`/`reytest` — not just `python3 main.py` from source. Fixtures are generated locally (public-domain/synthetic), never real copyrighted books — see `reyos-packages/reyos-reader/testdata/` (generated at test time, not committed if large). Results are recorded as **PASS / FAIL / NOT TESTED** below once each run actually happens — this document is updated with real outcomes, not marked complete until the runs are done.
