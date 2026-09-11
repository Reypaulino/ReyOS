// Text highlighting for EPUB chapters. Selecting text shows a small color
// picker; picking a color wraps the selection in a <mark> and reports it to
// Python via console.log with a REYOS_HIGHLIGHT_* prefix -- BookReaderPage.qml's
// WebEngineView.onJavaScriptConsoleMessage picks these up. No QWebChannel
// here (unlike the browser's password bridge): this is a much smaller
// surface and a plain string prefix is simplest given content is always our
// own reyos-epub:// scheme, never arbitrary web pages.
(function () {
    if (window.__reyosHighlighterInstalled) {
        return;
    }
    window.__reyosHighlighterInstalled = true;

    var TOOLBAR_ID = "__reyos-hl-toolbar";
    var COLORS = ["#FFEB3B", "#A5D6A7", "#90CAF9", "#F48FB1"];

    function textOffset(root, node, offset) {
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        var total = 0;
        var cur;
        while ((cur = walker.nextNode())) {
            if (cur === node) {
                return total + offset;
            }
            total += cur.textContent.length;
        }
        return total;
    }

    function removeToolbar() {
        var el = document.getElementById(TOOLBAR_ID);
        if (el) {
            el.remove();
        }
    }

    function showToolbar(rect, onPick) {
        removeToolbar();
        var bar = document.createElement("div");
        bar.id = TOOLBAR_ID;
        bar.style.cssText =
            "position:absolute;z-index:999999;background:#302217;" +
            "border:1px solid #8E5A2E;border-radius:8px;padding:6px;" +
            "display:flex;gap:6px;box-shadow:0 2px 8px rgba(0,0,0,0.5);";
        bar.style.left = Math.max(4, rect.left + window.scrollX) + "px";
        bar.style.top = Math.max(4, rect.top + window.scrollY - 42) + "px";
        COLORS.forEach(function (color) {
            var sw = document.createElement("div");
            sw.style.cssText =
                "width:22px;height:22px;border-radius:50%;cursor:pointer;" +
                "background:" + color + ";border:2px solid rgba(255,255,255,0.4);";
            sw.addEventListener("mousedown", function (e) {
                e.preventDefault();
                onPick(color);
                removeToolbar();
            });
            bar.appendChild(sw);
        });
        document.body.appendChild(bar);
    }

    document.addEventListener("selectionchange", function () {
        clearTimeout(window.__reyosSelTimer);
        window.__reyosSelTimer = setTimeout(function () {
            var sel = window.getSelection();
            if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
                removeToolbar();
                return;
            }
            var text = sel.toString().trim();
            if (!text.length) {
                removeToolbar();
                return;
            }
            var range = sel.getRangeAt(0);
            var rect = range.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) {
                removeToolbar();
                return;
            }
            showToolbar(rect, function (color) {
                var start = textOffset(document.body, range.startContainer, range.startOffset);
                var end = textOffset(document.body, range.endContainer, range.endOffset);
                var payload = { start: start, end: end, color: color, snippet: text.slice(0, 200) };
                sel.removeAllRanges();
                console.log("REYOS_HIGHLIGHT_NEW:" + JSON.stringify(payload));
            });
        }, 150);
    });

    // Clicking elsewhere should dismiss the color picker without leaving it
    // stuck onscreen once the selection is gone.
    document.addEventListener("mousedown", function (e) {
        if (e.target && e.target.closest && e.target.closest("#" + TOOLBAR_ID)) {
            return;
        }
        removeToolbar();
    });

    function wrapRange(startOffset, endOffset, color, hlId) {
        var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        var total = 0;
        var node;
        var spans = [];
        while ((node = walker.nextNode())) {
            var nodeStart = total;
            var nodeEnd = total + node.textContent.length;
            if (nodeEnd > startOffset && nodeStart < endOffset && node.textContent.length > 0) {
                spans.push({
                    node: node,
                    from: Math.max(0, startOffset - nodeStart),
                    to: Math.min(node.textContent.length, endOffset - nodeStart),
                });
            }
            total = nodeEnd;
            if (total >= endOffset) {
                break;
            }
        }
        spans.forEach(function (s) {
            if (s.from >= s.to) {
                return;
            }
            try {
                var r = document.createRange();
                r.setStart(s.node, s.from);
                r.setEnd(s.node, s.to);
                var mark = document.createElement("mark");
                mark.className = "reyos-highlight";
                mark.dataset.reyosHl = hlId;
                mark.style.backgroundColor = color;
                mark.style.color = "inherit";
                mark.style.cursor = "pointer";
                mark.title = "Click to remove this highlight";
                mark.addEventListener("click", function (e) {
                    e.stopPropagation();
                    console.log("REYOS_HIGHLIGHT_CLICK:" + hlId);
                });
                r.surroundContents(mark);
            } catch (e) {
                // A range crossing an element boundary in a way
                // surroundContents can't wrap -- skip that fragment rather
                // than fail the whole highlight.
            }
        });
    }

    window.__reyosApplyHighlights = function (jsonList) {
        document.querySelectorAll("mark.reyos-highlight").forEach(function (m) {
            var parent = m.parentNode;
            while (m.firstChild) {
                parent.insertBefore(m.firstChild, m);
            }
            parent.removeChild(m);
            parent.normalize();
        });
        var list = JSON.parse(jsonList);
        list.forEach(function (h) {
            wrapRange(h.range.start, h.range.end, h.color, h.id);
        });
    };
})();
