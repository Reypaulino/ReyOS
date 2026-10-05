import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebChannel
import QtWebEngine
import "components"

ApplicationWindow {
    id: window
    width: 1200
    height: 760
    minimumWidth: 760
    minimumHeight: 520
    visible: true
    title: currentView && currentView.title ? currentView.title + " — Reyva" : "Reyva"
    color: accentSurfaceWindow

    // pages.count is read so this re-evaluates once the first tab's view exists.
    property var currentView: pages.count > tabBar.currentIndex ? pages.itemAt(tabBar.currentIndex) : null
    property var downloadRequests: ({})
    property var closedTabsStack: []
    property int findMatchCount: 0
    readonly property string downloadsPath: StandardPaths.writableLocation(StandardPaths.DownloadLocation).toString().replace(/^file:\/\//, "")
    readonly property url homeUrl: Qt.resolvedUrl("../home.html")

    // The active Look's accent, and every shade derived from it, centralized
    // here instead of scattered as literal hex through ~180 places in this
    // file. applyLook() (reyos-control-center-gui) patches these 9
    // declarations directly by name on a Look switch -- a flat per-channel
    // RGB patch of scattered literals was tried first and needed four
    // separate bug fixes in one session (wrong derivation source when the
    // literals drifted out of sync with each other, hue collapsing toward
    // blue for any accent Copper-shaped math didn't fit, over-broad matching
    // corrupting an unrelated field, and floating-point rounding silently
    // breaking the match). A single named property per role has none of
    // those failure modes: QML's own binding system propagates one change
    // to every usage, so there's nothing left to scan for or get out of sync.
    readonly property color accentColor: "#C97932"          // the raw accent
    readonly property color accentBorder: "#8E5B2E"          // every popup/dialog border + hairline divider
    readonly property color accentSurfaceHover: "#3B2B1C"    // hover/highlighted/checked-alt chip background
    readonly property color accentSurfaceRaised: "#302317"   // popup/dialog/menu-item default background
    readonly property color accentSurfaceBase: "#211911"     // deepest background (tab strip, article view, root window)
    readonly property color accentSurfaceToolbar: "#241B13"  // toolbar background
    readonly property color accentSurfaceWindow: "#15110E"   // root window background
    readonly property color accentHoverStrong: "#4A3420"     // pinned ("keep alive") tab's own hover shade
    readonly property color accentGlow: "#F0A96A"             // non-https padlock / accent label text
    readonly property string iconLinkFinderScript: "(function() { function abs(href) { try { return new URL(href, document.baseURI).href } catch (e) { return '' } } var links = document.querySelectorAll('link[rel~=\"icon\"], link[rel=\"apple-touch-icon\"], link[rel=\"apple-touch-icon-precomposed\"]'); var best = ''; var bestSize = 0; for (var i = 0; i < links.length; i++) { var link = links[i]; var href = link.getAttribute('href'); if (!href) continue; var size = 32; var sizesAttr = link.getAttribute('sizes') || ''; var match = sizesAttr.match(/(\\d+)x\\d+/); if (match) { size = parseInt(match[1], 10) } else if ((link.getAttribute('rel') || '').indexOf('apple-touch-icon') !== -1) { size = 180 } if (size > bestSize) { bestSize = size; best = href } } return best ? abs(best) : '' })()"

    // Fusion draws every stock control from the palette, so this one block
    // keeps dialogs, fields, menus and buttons dark and on the active Look.
    palette.window: accentSurfaceRaised
    palette.windowText: "#FFF3E6"
    palette.base: accentSurfaceWindow
    palette.alternateBase: accentSurfaceBase
    palette.text: "#FFF3E6"
    palette.button: accentSurfaceHover
    palette.buttonText: "#FFF3E6"
    palette.highlight: accentColor
    palette.highlightedText: "#FFFFFF"
    palette.placeholderText: "#9F8873"
    palette.toolTipBase: accentSurfaceRaised
    palette.toolTipText: "#FFF3E6"
    palette.light: accentHoverStrong
    palette.midlight: accentSurfaceHover
    palette.mid: accentBorder
    palette.dark: accentSurfaceBase
    palette.shadow: "#000000"
    palette.link: accentGlow
    palette.brightText: accentGlow
    palette.disabled.buttonText: "#8C7867"
    palette.disabled.windowText: "#8C7867"
    palette.disabled.text: "#8C7867"

    QtObject {
        id: theme
        readonly property color accent: window.accentColor
        readonly property color border: window.accentBorder
        readonly property color hover: window.accentSurfaceHover
        readonly property color hoverStrong: window.accentHoverStrong
        readonly property color raised: window.accentSurfaceRaised
        readonly property color base: window.accentSurfaceBase
        readonly property color toolbar: window.accentSurfaceToolbar
        readonly property color windowBg: window.accentSurfaceWindow
        readonly property color glow: window.accentGlow
    }

    readonly property bool currentIsHome: currentView ? isHomeUrl(currentView.url.toString()) : true
    readonly property bool currentIsHttps: currentView ? String(currentView.url).indexOf("https:") === 0 : false
    readonly property real tabWidth: Math.max(112, Math.min(224, (tabStrip.width - brandRow.width - newTabButton.width - 48) / Math.max(1, tabs.count)))
    readonly property bool compactToolbar: width < 900
    property int activeDownloadCount: 0

    ListModel { id: tabs }
    ListModel { id: downloads }
    ListModel { id: sessionHistory }

    WebEngineProfile {
        id: privateProfile
        objectName: "privateProfile"
        offTheRecord: true
        httpCacheType: WebEngineProfile.MemoryHttpCache
        persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies
        downloadPath: window.downloadsPath
        onDownloadRequested: function(download) {
            window.startDownload(download)
        }
    }

    function isHomeUrl(value) {
        var candidate = String(value || "")
        return candidate === homeUrl.toString()
    }

    function isReaderUrl(value) {
        var candidate = String(value || "")
        return candidate.indexOf("data:text/html") === 0 && candidate.indexOf("reyos-reader-view") > 0
    }

    function addressLabel() {
        if (!currentView || isHomeUrl(currentView.url.toString())) {
            return ""
        }
        return currentView.url.toString()
    }

    function recordHistory(pageUrl, pageTitle) {
        if (!pageUrl || isHomeUrl(pageUrl) || isReaderUrl(pageUrl)) {
            return
        }
        if (sessionHistory.count > 0 && sessionHistory.get(sessionHistory.count - 1).pageUrl === pageUrl) {
            sessionHistory.setProperty(sessionHistory.count - 1, "pageTitle", pageTitle || pageUrl)
            return
        }
        sessionHistory.append({ pageUrl: pageUrl, pageTitle: pageTitle || pageUrl })
        if (sessionHistory.count > 50) {
            sessionHistory.remove(0)
        }
    }

    function updateHistoryTitle(pageUrl, pageTitle) {
        for (var i = sessionHistory.count - 1; i >= 0; --i) {
            if (sessionHistory.get(i).pageUrl === pageUrl) {
                sessionHistory.setProperty(i, "pageTitle", pageTitle || pageUrl)
                return
            }
        }
    }

    function openHistoryPage(pageUrl) {
        if (currentView) {
            currentView.url = pageUrl
        }
        historyDialog.close()
    }

    function syncCurrentSite() {
        if (currentView) {
            browserBackend.setCurrentSite(currentView.url.toString())
        }
        if (!address.activeFocus) {
            address.text = window.addressLabel()
        }
    }

    function updateDownload(download) {
        for (var i = 0; i < downloads.count; ++i) {
            if (downloads.get(i).downloadId === download.id) {
                downloads.setProperty(i, "receivedBytes", download.receivedBytes)
                downloads.setProperty(i, "totalBytes", download.totalBytes)
                break
            }
        }
    }

    function finishDownload(download) {
        for (var i = 0; i < downloads.count; ++i) {
            if (downloads.get(i).downloadId === download.id) {
                var completed = download.state === WebEngineDownloadRequest.DownloadCompleted
                var cancelled = download.state === WebEngineDownloadRequest.DownloadCancelled
                if (!downloads.get(i).finished) {
                    activeDownloadCount = Math.max(0, activeDownloadCount - 1)
                }
                downloads.setProperty(i, "finished", true)
                downloads.setProperty(i, "completed", completed)
                downloads.setProperty(i, "status", completed ? "Completed" : (cancelled ? "Cancelled" : "Failed: " + download.interruptReasonString))
                if (completed) {
                    browserBackend.notify("Download finished", download.downloadFileName + " is ready in Downloads")
                } else if (!cancelled) {
                    browserBackend.notify("Download failed", download.downloadFileName + " could not be saved")
                }
                break
            }
        }
    }

    function startDownload(download) {
        download.downloadDirectory = downloadsPath
        downloads.append({
            downloadId: download.id,
            name: download.downloadFileName,
            status: "Starting",
            receivedBytes: download.receivedBytes,
            totalBytes: download.totalBytes,
            finished: false,
            completed: false
        })
        downloadRequests[download.id] = download
        activeDownloadCount += 1
        download.receivedBytesChanged.connect(function() { window.updateDownload(download) })
        download.totalBytesChanged.connect(function() { window.updateDownload(download) })
        download.isFinishedChanged.connect(function() {
            if (download.isFinished) {
                window.finishDownload(download)
            }
        })
        browserBackend.notify("Download started", download.downloadFileName + " is saving to Downloads")
        download.accept()
    }

    function cancelDownload(downloadId) {
        var request = downloadRequests[downloadId]
        if (request && !request.isFinished) {
            request.cancel()
        }
    }

    function openDownload(name) {
        Qt.openUrlExternally("file://" + downloadsPath + "/" + encodeURIComponent(name))
    }

    function requestPermission(request) {
        permissionDialog.permissionRequest = request
        permissionDialog.answered = false
        permissionDialog.site = currentView ? currentView.url.host : "this website"
        permissionDialog.open()
    }

    function openAddress(value) {
        var text = value.trim()
        if (!text.length || !currentView) {
            return
        }
        if (!text.match(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//)) {
            if (text.indexOf(".") >= 0 && text.indexOf(" ") < 0) {
                text = "https://" + text
            } else {
                text = browserBackend.searchBase + encodeURIComponent(text)
            }
        }
        currentView.url = text
        address.focus = false
        Qt.callLater(window.syncCurrentSite)
    }

    function toggleBookmark() {
        if (!currentView || isHomeUrl(currentView.url.toString())) {
            return
        }
        var url = currentView.url.toString()
        if (browserBackend.isBookmarked(url)) {
            browserBackend.removeBookmark(url)
        } else {
            browserBackend.addBookmark(url, currentView.title || currentView.url.host)
        }
    }

    function openManageApps() {
        manageAppsDialog.open()
    }

    function confirmInstallApp(url, title) {
        var view = currentView
        if (!view) {
            return
        }
        view.runJavaScript(iconLinkFinderScript, function(result) {
            if (result && result.length > 0) {
                browserBackend.installAsApp(url, title, "", result)
            } else {
                appIconGrabber.pageUrl = url
                appIconGrabber.pageTitle = title
                appIconGrabber.source = view.icon
            }
        })
    }

    function installCurrentAsApp() {
        if (!currentView || isHomeUrl(currentView.url.toString())) {
            return
        }
        installAppNameDialog.pendingUrl = currentView.url.toString()
        installAppNameField.text = currentView.title || currentView.url.host
        installAppNameDialog.open()
        installAppNameField.selectAll()
        installAppNameField.forceActiveFocus()
    }

    function openBookmarkUrl(pageUrl) {
        if (!pageUrl) {
            return
        }
        if (!currentView) {
            window.initializeFirstTab()
        }
        if (currentView) {
            currentView.url = pageUrl
        }
    }

    function escapeReaderHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;")
    }

    function readerIsActive() {
        return tabs.count > tabBar.currentIndex && tabs.get(tabBar.currentIndex).readerOriginalUrl.length > 0
    }

    function buildReaderHtml(title, sourceUrl, text) {
        var t = window.escapeReaderHtml(title)
        var u = window.escapeReaderHtml(sourceUrl)
        var body = window.escapeReaderHtml(text)
        return "<!--reyos-reader-view--><!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Reader: " + t + "</title><style>:root{color-scheme:dark}body{margin:0;background:linear-gradient(145deg,#15110E,#241B13);color:#FFF3E6;font:19px/1.8 Georgia,serif}.shell{max-width:900px;margin:42px auto;padding:0 24px 72px}.mast{border:1px solid #8E5B2E;border-bottom:0;border-radius:18px 18px 0 0;padding:24px 34px 20px;background:linear-gradient(135deg,#3B2B1C,#302317)}.brand{font:700 13px system-ui,sans-serif;letter-spacing:1.2px;color:#F0A96A;text-transform:uppercase}.source{margin-top:9px;color:#F4D5A8;font:13px system-ui,sans-serif;word-break:break-all}article{background:#211911;border:1px solid #8E5B2E;border-radius:0 0 18px 18px;padding:34px;box-shadow:0 18px 52px #0008;white-space:pre-wrap}h1{font:700 37px/1.18 system-ui,sans-serif;letter-spacing:-.7px;color:#fff;margin:0}</style></head><body><main class=\"shell\"><header class=\"mast\"><div class=\"brand\">ReyOS Reader</div><h1>" + t + "</h1><div class=\"source\">" + u + "</div></header><article>" + body + "</article></main></body></html>"
    }

    function openReaderMode() {
        if (!currentView) {
            return
        }
        if (readerIsActive()) {
            var originalUrl = tabs.get(tabBar.currentIndex).readerOriginalUrl
            tabs.setProperty(tabBar.currentIndex, "readerOriginalUrl", "")
            currentView.url = originalUrl
            return
        }
        var sourceUrl = currentView.url.toString()
        if (isReaderUrl(sourceUrl)) {
            return
        }
        var tabIndex = tabBar.currentIndex
        var extractScript = "(function(){var root=document.querySelector('article, main, [role=main]')||document.body;return JSON.stringify({title:document.title||'Reader view',text:root?root.innerText:''})})()"
        currentView.runJavaScript(extractScript, function(result) {
            var data = null
            try {
                data = JSON.parse(result)
            } catch (e) {
                data = null
            }
            if (!data || !data.text) {
                browserBackend.notify("Reader Mode", "This page could not be converted to a reading view")
                return
            }
            tabs.setProperty(tabIndex, "readerOriginalUrl", sourceUrl)
            currentView.url = "data:text/html;charset=utf-8," + encodeURIComponent(window.buildReaderHtml(data.title, sourceUrl, data.text))
        })
    }

    function findInPage(query, backwards) {
        if (!currentView) {
            return
        }
        currentView.findText(query, backwards ? WebEngineView.FindBackward : 0, function(count) {
            window.findMatchCount = count
        })
    }

    function openFind() {
        findDialog.open()
        Qt.callLater(function() {
            findField.forceActiveFocus()
            findField.selectAll()
        })
    }

    function initializeFirstTab(startUrls) {
        if (startUrls && startUrls.length > 0) {
            for (var i = 0; i < startUrls.length; ++i) {
                openInNewTab(startUrls[i])
            }
            tabBar.currentIndex = tabs.count - 1
        } else if (tabs.count === 0) {
            addTab()
        }
    }

    function addTab() {
        tabs.append({ pageUrl: homeUrl.toString(), pageTitle: "New Tab", readerOriginalUrl: "", keepAlive: false })
        tabBar.currentIndex = tabs.count - 1
        Qt.callLater(newTabPage.focusSearch)
    }

    function openInNewTab(pageUrl) {
        if (!pageUrl) {
            return
        }
        tabs.append({ pageUrl: String(pageUrl), pageTitle: "Loading…", readerOriginalUrl: "", keepAlive: false })
    }

    function openShortcutDialog(index) {
        shortcutDialog.editIndex = index
        shortcutDialog.errorText = ""
        var entry = index >= 0 ? browserBackend.shortcuts[index] : null
        shortcutNameField.text = entry ? entry.title : ""
        shortcutUrlField.text = entry ? entry.url : ""
        shortcutDialog.open()
        Qt.callLater(function() { (entry ? shortcutNameField : shortcutUrlField).forceActiveFocus() })
    }

    function stashClosedTab(index) {
        var tab = tabs.get(index)
        if (tab.pageUrl && !isHomeUrl(tab.pageUrl)) {
            closedTabsStack.push({ pageUrl: tab.pageUrl, pageTitle: tab.pageTitle })
            if (closedTabsStack.length > 10) {
                closedTabsStack.shift()
            }
        }
    }

    function closeCurrentTab() {
        stashClosedTab(tabBar.currentIndex)
        if (tabs.count === 1) {
            currentView.url = homeUrl
            return
        }
        tabs.remove(tabBar.currentIndex)
        tabBar.currentIndex = Math.max(0, tabBar.currentIndex - 1)
    }

    function closeTab(index) {
        stashClosedTab(index)
        if (tabs.count === 1) {
            currentView.url = homeUrl
            return
        }
        tabs.remove(index)
        tabBar.currentIndex = Math.max(0, Math.min(index, tabs.count - 1))
    }

    function reopenClosedTab() {
        if (closedTabsStack.length === 0) {
            return
        }
        var tab = closedTabsStack.pop()
        tabs.append({ pageUrl: tab.pageUrl, pageTitle: tab.pageTitle, readerOriginalUrl: "", keepAlive: false })
        tabBar.currentIndex = tabs.count - 1
    }

    Shortcut { sequence: "Ctrl+T"; onActivated: window.addTab() }
    Shortcut { sequence: "Ctrl+W"; onActivated: window.closeCurrentTab() }
    Shortcut { sequence: "Ctrl+Shift+T"; onActivated: window.reopenClosedTab() }
    Shortcut { sequence: "Ctrl+L"; onActivated: { address.forceActiveFocus(); address.selectAll() } }
    Shortcut { sequence: "Ctrl+R"; onActivated: { if (currentView) currentView.reload() } }
    Shortcut { sequence: "Ctrl+F"; onActivated: window.openFind() }
    Shortcut { sequence: "Ctrl+Shift+R"; onActivated: window.openReaderMode() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }

    Connections {
        target: passwordBridge
        function onSavePromptRequested(origin, username, password) {
            passwordPrompt.origin = origin
            passwordPrompt.username = username
            passwordPrompt.password = password
            passwordPrompt.open()
        }
    }

    header: ColumnLayout {
        id: headerLayout
        spacing: 0

        Rectangle {
            id: tabStrip
            Layout.fillWidth: true
            implicitHeight: 46
            color: accentSurfaceWindow

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 8
                spacing: 6

                RowLayout {
                    id: brandRow
                    spacing: 8
                    Layout.rightMargin: 6
                    Image {
                        source: Qt.resolvedUrl("../assets/reyos-browser-logo.png")
                        sourceSize.width: 24
                        sourceSize.height: 24
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 24
                        mipmap: true
                    }
                    Label {
                        visible: window.width >= 1000
                        text: "Reyva"
                        color: "#FFF3E6"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                }

                TabBar {
                    id: tabBar
                    currentIndex: 0
                    spacing: 4
                    Layout.preferredHeight: 38
                    Layout.alignment: Qt.AlignBottom
                    Layout.preferredWidth: tabs.count * (window.tabWidth + spacing)
                    Layout.maximumWidth: tabStrip.width - brandRow.width - newTabButton.width - 48
                    onCurrentIndexChanged: {
                        address.focus = false
                        Qt.callLater(window.syncCurrentSite)
                    }
                    background: Item {}

                    Repeater {
                        model: tabs
                        delegate: TabButton {
                            id: tabButton
                            required property int index
                            required property string pageTitle
                            required property bool keepAlive
                            readonly property bool isCurrent: index === tabBar.currentIndex
                            readonly property var view: pages.itemAt(index)
                            readonly property int lifecycle: view ? view.lifecycleState : WebEngineView.LifecycleState.Active
                            width: window.tabWidth
                            height: 38
                            text: pageTitle
                            focusPolicy: Qt.NoFocus
                            onClicked: tabBar.currentIndex = index
                            ToolTip.visible: hovered && pageTitle.length > 18
                            ToolTip.delay: 700
                            ToolTip.text: pageTitle

                            background: Rectangle {
                                radius: 9
                                color: tabButton.isCurrent ? accentSurfaceToolbar : (tabButton.hovered ? accentSurfaceBase : "transparent")
                                border.width: tabButton.isCurrent ? 1 : 0
                                border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.5)
                                Rectangle {
                                    visible: tabButton.isCurrent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    height: 2
                                    radius: 1
                                    color: accentColor
                                }
                            }
                            contentItem: RowLayout {
                                spacing: 6
                                Item {
                                    Layout.leftMargin: 4
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    Image {
                                        id: tabFavicon
                                        anchors.fill: parent
                                        source: tabButton.view && !window.isHomeUrl(tabButton.view.url.toString()) ? tabButton.view.icon : ""
                                        sourceSize.width: 16
                                        sourceSize.height: 16
                                        visible: status === Image.Ready
                                    }
                                    Image {
                                        anchors.fill: parent
                                        visible: tabFavicon.status !== Image.Ready
                                        source: tabButton.view && window.isHomeUrl(tabButton.view.url.toString()) ? Qt.resolvedUrl("../assets/reyos-browser-logo.png") : Qt.resolvedUrl("../icons/reyos-globe.svg")
                                        sourceSize.width: 16
                                        sourceSize.height: 16
                                        mipmap: true
                                        opacity: 0.85
                                    }
                                }
                                Label {
                                    text: tabButton.pageTitle
                                    color: tabButton.isCurrent ? "#FFF3E6" : "#C9B6A3"
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    visible: text.length > 0
                                    text: tabButton.lifecycle === WebEngineView.LifecycleState.Discarded ? "◌" : (tabButton.lifecycle === WebEngineView.LifecycleState.Frozen ? "❄" : "")
                                    color: "#F4D5A8"
                                    font.pixelSize: 15
                                    ToolTip.visible: tabStateHover.hovered
                                    ToolTip.text: tabButton.lifecycle === WebEngineView.LifecycleState.Discarded ? "Unloaded to save memory — reloads when selected" : "Paused to save memory"
                                    HoverHandler { id: tabStateHover }
                                }
                                ToolButton {
                                    id: keepAliveButton
                                    visible: tabButton.keepAlive || tabButton.hovered || hovered
                                    focusPolicy: Qt.NoFocus
                                    icon.source: Qt.resolvedUrl("../icons/reyos-pin.svg")
                                    icon.width: 14
                                    icon.height: 14
                                    icon.color: tabButton.keepAlive ? accentGlow : "#C9B6A3"
                                    implicitWidth: 22
                                    implicitHeight: 22
                                    padding: 0
                                    background: Rectangle {
                                        color: keepAliveButton.hovered ? accentHoverStrong : (tabButton.keepAlive ? accentSurfaceHover : "transparent")
                                        radius: 6
                                    }
                                    onClicked: tabs.setProperty(tabButton.index, "keepAlive", !tabButton.keepAlive)
                                    ToolTip.visible: hovered
                                    ToolTip.text: tabButton.keepAlive ? "Keep running: On — stays active in the background" : "Keep this tab running in the background (e.g. music or video)"
                                    Accessible.name: "Keep tab running in background"
                                }
                                ToolButton {
                                    id: tabCloseButton
                                    focusPolicy: Qt.NoFocus
                                    icon.source: Qt.resolvedUrl("../icons/reyos-close.svg")
                                    icon.width: 12
                                    icon.height: 12
                                    icon.color: tabButton.isCurrent || tabCloseButton.hovered ? "#FFF3E6" : "#C9B6A3"
                                    implicitWidth: 22
                                    implicitHeight: 22
                                    padding: 0
                                    background: Rectangle { radius: 6; color: tabCloseButton.hovered ? accentHoverStrong : "transparent" }
                                    onClicked: window.closeTab(tabButton.index)
                                    ToolTip.visible: hovered
                                    ToolTip.delay: 700
                                    ToolTip.text: "Close tab (Ctrl+W)"
                                    Accessible.name: "Close tab"
                                }
                            }
                        }
                    }
                }

                IconButton {
                    id: newTabButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-plus.svg")
                    iconSize: 18
                    implicitWidth: 34
                    implicitHeight: 34
                    hoverColor: accentSurfaceHover
                    tip: "New tab (Ctrl+T)"
                    onClicked: window.addTab()
                }

                Item { Layout.fillWidth: true }
            }
        }

        ToolBar {
            id: navBar
            Layout.fillWidth: true
            implicitHeight: 54
            leftPadding: 10
            rightPadding: 10
            background: Rectangle {
                color: accentSurfaceToolbar
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: accentSurfaceBase }
            }
            contentItem: RowLayout {
                spacing: 4

                IconButton {
                    id: backButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-back.svg")
                    hoverColor: accentSurfaceHover
                    enabled: currentView && currentView.canGoBack
                    tip: "Back"
                    onClicked: currentView.goBack()
                }
                IconButton {
                    id: forwardButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-forward.svg")
                    hoverColor: accentSurfaceHover
                    enabled: currentView && currentView.canGoForward
                    tip: "Forward"
                    onClicked: currentView.goForward()
                }
                IconButton {
                    id: reloadButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-refresh.svg")
                    iconSize: 19
                    hoverColor: accentSurfaceHover
                    tint: "#FFF3E6"
                    tip: currentView && currentView.loading ? "Stop" : "Reload (Ctrl+R)"
                    onClicked: currentView.loading ? currentView.stop() : currentView.reload()
                }

                Rectangle {
                    id: addressFrame
                    Layout.fillWidth: true
                    Layout.minimumWidth: 240
                    Layout.leftMargin: 6
                    Layout.rightMargin: 6
                    implicitHeight: 40
                    radius: 12
                    color: accentSurfaceWindow
                    border.width: address.activeFocus ? 2 : 1
                    border.color: address.activeFocus ? accentColor : Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.45)

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 10
                        spacing: 4

                        IconButton {
                            id: siteInfoButton
                            implicitWidth: 30
                            implicitHeight: 30
                            iconSize: 17
                            hoverColor: accentSurfaceHover
                            iconSource: window.currentIsHome ? Qt.resolvedUrl("../icons/reyos-search.svg")
                                       : (window.currentIsHttps ? Qt.resolvedUrl("../icons/reyos-lock.svg") : Qt.resolvedUrl("../icons/reyos-warning.svg"))
                            tint: window.currentIsHome || window.currentIsHttps ? "#D7C1AA" : accentGlow
                            enabled: !window.currentIsHome
                            opacity: 1.0
                            tip: window.currentIsHttps ? "Connection is secure — site safety" : "Connection is not secure — site safety"
                            onClicked: siteSafetyDialog.open()
                        }
                        TextField {
                            id: address
                            Layout.fillWidth: true
                            // Steady cursor: a blinking one redraws the whole window twice a second.
                            cursorDelegate: Rectangle { width: 2; color: "#F0A96A"; visible: address.cursorVisible }
                            background: null
                            color: "#FFF3E6"
                            font.pixelSize: 14
                            placeholderText: "Search privately or enter an address"
                            placeholderTextColor: "#9F8873"
                            selectByMouse: true
                            Component.onCompleted: text = window.addressLabel()
                            onAccepted: window.openAddress(text)
                            onActiveFocusChanged: if (activeFocus) Qt.callLater(selectAll)
                            Keys.onEscapePressed: {
                                text = window.addressLabel()
                                focus = false
                            }
                            Accessible.name: "Address and search bar"
                        }
                    }
                }

                IconButton {
                    id: bookmarkButton
                    readonly property bool marked: {
                        browserBackend.bookmarksVersion
                        return currentView ? browserBackend.isBookmarked(currentView.url.toString()) : false
                    }
                    iconSource: marked ? Qt.resolvedUrl("../icons/reyos-star-filled.svg") : Qt.resolvedUrl("../icons/reyos-star.svg")
                    tint: marked ? accentColor : "#FFF3E6"
                    hoverColor: accentSurfaceHover
                    enabled: !window.currentIsHome
                    tip: marked ? "Remove bookmark" : "Bookmark this page"
                    onClicked: window.toggleBookmark()
                }
                IconButton {
                    id: shieldsButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-shields.svg")
                    iconSize: 22
                    hoverColor: accentSurfaceHover
                    opacity: browserBackend.shieldsEnabled && browserBackend.currentSiteShieldsEnabled ? 1.0 : 0.5
                    active: siteSafetyDialog.visible
                    tip: browserBackend.shieldsEnabled ? "ReyOS Shields — " + browserBackend.blockedRequestCount + " blocked this session" : "ReyOS Shields are off"
                    onClicked: siteSafetyDialog.visible ? siteSafetyDialog.close() : siteSafetyDialog.open()
                }
                IconButton {
                    id: downloadsButton
                    visible: !window.compactToolbar || window.activeDownloadCount > 0
                    iconSource: Qt.resolvedUrl("../icons/reyos-download.svg")
                    hoverColor: accentSurfaceHover
                    tint: window.activeDownloadCount > 0 ? accentGlow : "#FFF3E6"
                    badge: window.activeDownloadCount > 0
                    badgeColor: accentColor
                    active: downloadsDialog.visible
                    tip: window.activeDownloadCount > 0 ? window.activeDownloadCount + " download" + (window.activeDownloadCount > 1 ? "s" : "") + " in progress" : "Downloads"
                    onClicked: downloadsDialog.visible ? downloadsDialog.close() : downloadsDialog.open()
                }
                IconButton {
                    id: browserMenuButton
                    iconSource: Qt.resolvedUrl("../icons/reyos-menu.svg")
                    hoverColor: accentSurfaceHover
                    active: browserMenu.visible
                    tip: "Menu"
                    onClicked: browserMenu.visible ? browserMenu.close() : browserMenu.open()
                }
            }
        }

        Rectangle {
            id: bookmarksBarContainer
            Layout.fillWidth: true
            implicitHeight: visible ? 42 : 0
            visible: browserBackend.bookmarks.length > 0
            color: accentSurfaceToolbar
            border.color: accentBorder
            border.width: 0

            property var groupedBar: {
                browserBackend.bookmarksVersion
                var groups = {}
                var order = []
                var list = browserBackend.bookmarks
                for (var i = 0; i < list.length; i++) {
                    var item = list[i]
                    var folder = item.folder || ""
                    var topFolder = folder.length ? folder.split("/")[0] : ""
                    if (!(topFolder in groups)) {
                        groups[topFolder] = []
                        order.push(topFolder)
                    }
                    groups[topFolder].push(item)
                }
                var result = []
                for (var j = 0; j < order.length; j++) {
                    result.push({ folder: order[j], items: groups[order[j]] })
                }
                return result
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                anchors.topMargin: 5
                anchors.bottomMargin: 5
                spacing: 4

                ScrollView {
                    id: bookmarksBarScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    contentWidth: bookmarksBarRow.implicitWidth
                    contentHeight: bookmarksBarRow.implicitHeight

                    Row {
                        id: bookmarksBarRow
                        spacing: 6

                        Repeater {
                            model: bookmarksBarContainer.groupedBar
                        delegate: Row {
                            required property var modelData
                            spacing: 6

                            Repeater {
                                model: modelData.folder.length === 0 ? modelData.items : []
                                delegate: Button {
                                    required property var modelData
                                    implicitHeight: 28
                                    implicitWidth: Math.min(220, bookmarkLabel.implicitWidth + 22)
                                    padding: 0
                                    background: Rectangle {
                                        color: parent.hovered ? accentSurfaceHover : accentSurfaceRaised
                                        border.color: accentBorder
                                        border.width: 1
                                        radius: 7
                                    }
                                    contentItem: Label {
                                        id: bookmarkLabel
                                        text: modelData.title && modelData.title.length ? modelData.title : modelData.url
                                        color: "#FFF3E6"
                                        leftPadding: 11
                                        rightPadding: 11
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    onClicked: window.openBookmarkUrl(modelData.url)
                                    ToolTip.visible: hovered
                                    ToolTip.text: modelData.url
                                }
                            }

                            Button {
                                id: folderChip
                                visible: modelData.folder.length > 0
                                implicitHeight: 28
                                padding: 0
                                background: Rectangle {
                                    color: folderChip.hovered || folderPopup.visible ? accentSurfaceHover : accentSurfaceRaised
                                    border.color: accentBorder
                                    border.width: 1
                                    radius: 7
                                }
                                contentItem: RowLayout {
                                    spacing: 4
                                    Label {
                                        text: modelData.folder
                                        color: "#FFF3E6"
                                        leftPadding: 11
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: "▾"
                                        color: "#D7C1AA"
                                        rightPadding: 10
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                                onClicked: folderPopup.visible ? folderPopup.close() : folderPopup.open()

                                Popup {
                                    id: folderPopup
                                    y: folderChip.height + 4
                                    width: 300
                                    height: Math.min(420, modelData.items.length * 46 + 16)
                                    padding: 6
                                    modal: false
                                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                                    background: Rectangle {
                                        color: accentSurfaceRaised
                                        border.color: accentBorder
                                        border.width: 1
                                        radius: 10
                                    }
                                    contentItem: ScrollView {
                                        clip: true
                                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                        contentWidth: availableWidth
                                        ColumnLayout {
                                            width: parent.width
                                            spacing: 2
                                            Repeater {
                                                model: modelData.items
                                                delegate: Button {
                                                    required property var modelData
                                                    Layout.fillWidth: true
                                                    implicitHeight: 44
                                                    flat: true
                                                    background: Rectangle {
                                                        color: parent.hovered ? accentSurfaceHover : "transparent"
                                                        radius: 6
                                                    }
                                                    contentItem: ColumnLayout {
                                                        spacing: 0
                                                        Label {
                                                            text: modelData.title && modelData.title.length ? modelData.title : modelData.url
                                                            color: "#FFF3E6"
                                                            elide: Text.ElideRight
                                                            Layout.fillWidth: true
                                                            font.pixelSize: 13
                                                        }
                                                        Label {
                                                            text: {
                                                                var folder = modelData.folder || ""
                                                                var slash = folder.indexOf("/")
                                                                return slash >= 0 ? folder.slice(slash + 1) : ""
                                                            }
                                                            visible: text.length > 0
                                                            color: "#9F8873"
                                                            font.pixelSize: 10
                                                            elide: Text.ElideRight
                                                            Layout.fillWidth: true
                                                        }
                                                    }
                                                    onClicked: {
                                                        window.openBookmarkUrl(modelData.url)
                                                        folderPopup.close()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                }

                Button {
                    id: bookmarksOverflowButton
                    visible: bookmarksBarRow.implicitWidth > bookmarksBarScroll.width
                    implicitHeight: 28
                    implicitWidth: 32
                    padding: 0
                    background: Rectangle {
                        color: bookmarksOverflowButton.hovered ? accentSurfaceHover : accentSurfaceRaised
                        border.color: accentBorder
                        border.width: 1
                        radius: 7
                    }
                    contentItem: Label {
                        text: "»"
                        color: "#FFF3E6"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 16
                    }
                    onClicked: bookmarksDialog.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Show all bookmarks"
                }
            }
        }
    }

    Popup {
        id: passwordPrompt
        parent: window.contentItem
        property string origin: ""
        property string username: ""
        property string password: ""
        x: Math.max(12, window.contentItem.width - width - 16)
        y: headerLayout.height + 14
        width: Math.min(410, window.width - 24)
        padding: 14
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: accentSurfaceRaised
            border.color: accentBorder
            border.width: 1
            radius: 12
        }
        contentItem: ColumnLayout {
            spacing: 10
            Label {
                text: "Save password for " + passwordPrompt.origin + "?"
                color: "#FFF3E6"
                font.bold: true
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Label {
                text: "Username: " + passwordPrompt.username
                color: "#D7C1AA"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: "Save"
                    onClicked: {
                        browserBackend.savePassword(passwordPrompt.origin, passwordPrompt.username, passwordPrompt.password)
                        passwordPrompt.close()
                    }
                }
                Button {
                    text: "Never for this site"
                    onClicked: {
                        browserBackend.blockPasswordSaveForOrigin(passwordPrompt.origin)
                        passwordPrompt.close()
                    }
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Not now"
                    onClicked: passwordPrompt.close()
                }
            }
        }
    }

    Dialog {
        id: bookmarksDialog
        title: "Bookmarks"
        modal: true
        width: 460
        height: Math.min(560, window.height - 80)
        anchors.centerIn: parent
        padding: 18
        property string importMessage: ""
        property var groupedBookmarks: {
            browserBackend.bookmarksVersion
            var groups = {}
            var order = []
            var list = browserBackend.bookmarks
            for (var i = 0; i < list.length; i++) {
                var item = list[i]
                var folder = item.folder || ""
                if (!(folder in groups)) {
                    groups[folder] = []
                    order.push(folder)
                }
                groups[folder].push(item)
            }
            order.sort(function (a, b) { return a.length === 0 ? -1 : b.length === 0 ? 1 : a.localeCompare(b) })
            var result = []
            for (var j = 0; j < order.length; j++) {
                result.push({ folder: order[j], items: groups[order[j]] })
            }
            return result
        }
        background: Rectangle {
            color: accentSurfaceRaised
            border.color: accentBorder
            border.width: 1
            radius: 12
        }
        Connections {
            target: browserBackend
            function onBookmarkImportFinished(count, message) {
                bookmarksDialog.importMessage = message
            }
        }
        contentItem: ColumnLayout {
            spacing: 10
            Label {
                visible: browserBackend.bookmarks.length === 0
                text: "No bookmarks yet. Select the bookmark icon beside the address bar to save a page."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: bookmarksDialog.groupedBookmarks
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 4
                            Label {
                                visible: modelData.folder.length > 0
                                text: modelData.folder
                                color: "#F4D5A8"
                                font.bold: true
                                font.pixelSize: 12
                                Layout.topMargin: 6
                            }
                            Repeater {
                                model: modelData.items
                                delegate: Rectangle {
                                    id: bookmarkEntry
                                    required property var modelData
                                    Layout.fillWidth: true
                                    implicitHeight: 66
                                    radius: 7
                                    color: accentSurfaceBase
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 9
                                        spacing: 8
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Label { text: bookmarkEntry.modelData.title; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Label { text: bookmarkEntry.modelData.url; color: "#D7C1AA"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                        }
                                        Button {
                                            text: "Open"
                                            onClicked: {
                                                window.openHistoryPage(bookmarkEntry.modelData.url)
                                                bookmarksDialog.close()
                                            }
                                        }
                                        Button { text: "Remove"; onClicked: browserBackend.removeBookmark(bookmarkEntry.modelData.url) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Label {
                visible: bookmarksDialog.importMessage.length > 0
                text: bookmarksDialog.importMessage
                color: "#F4D5A8"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Import HTML…"; onClicked: browserBackend.chooseBookmarkImport() }
                Item { Layout.fillWidth: true }
                Button { text: "Reset…"; onClicked: resetBookmarksConfirmDialog.open() }
                Button { text: "Close"; onClicked: bookmarksDialog.close() }
            }
        }
    }

    Dialog {
        id: resetBookmarksConfirmDialog
        title: "Reset Bookmarks"
        modal: true
        width: 360
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: "This deletes every saved bookmark. This can't be undone."
                color: "#D7C1AA"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button { text: "Cancel"; onClicked: resetBookmarksConfirmDialog.close() }
                Button {
                    text: "Reset Bookmarks"
                    onClicked: {
                        browserBackend.resetBookmarks()
                        resetBookmarksConfirmDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: passwordsDialog
        title: "Saved Passwords"
        modal: true
        width: 560
        height: 470
        anchors.centerIn: parent
        padding: 18
        property var originsModel: []
        property string importMessage: ""
        onOpened: {
            originsModel = browserBackend.passwordOrigins
            importMessage = ""
        }
        onClosed: {
            originsModel = []
            importMessage = ""
        }
        background: Rectangle {
            color: accentSurfaceRaised
            border.color: accentBorder
            border.width: 1
            radius: 12
        }
        Connections {
            target: browserBackend
            function onPasswordsChanged() {
                if (passwordsDialog.visible) {
                    passwordsDialog.originsModel = browserBackend.passwordOrigins
                }
            }
            function onPasswordImportFinished(imported, message) {
                passwordsDialog.importMessage = message
                if (passwordsDialog.visible) {
                    passwordsDialog.originsModel = browserBackend.passwordOrigins
                }
            }
        }
        contentItem: ColumnLayout {
            spacing: 10
            Label {
                text: "Passwords are stored in your KDE wallet and offered only when you revisit the same origin. You can also import a CSV exported from Opera, Chrome, Edge, or Firefox."
                color: "#D7C1AA"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Label {
                visible: passwordsDialog.originsModel.length === 0
                text: "No saved passwords yet."
                color: "#F4D5A8"
                Layout.fillWidth: true
            }
            Label {
                visible: passwordsDialog.importMessage.length > 0
                text: passwordsDialog.importMessage
                color: "#F4D5A8"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                Column {
                    id: passwordsContent
                    width: parent.width
                    spacing: 8
                    Repeater {
                        model: passwordsDialog.originsModel
                        delegate: Rectangle {
                            required property string modelData
                            width: passwordsContent.width
                            radius: 8
                            color: accentSurfaceBase
                            border.color: accentBorder
                            border.width: 1
                            implicitHeight: passwordColumn.implicitHeight + 18
                            ColumnLayout {
                                id: passwordColumn
                                anchors.fill: parent
                                anchors.margins: 9
                                spacing: 8
                                Label {
                                    text: modelData
                                    color: "#FFF3E6"
                                    font.bold: true
                                    elide: Text.ElideMiddle
                                    Layout.fillWidth: true
                                }
                                Repeater {
                                    model: browserBackend.getPasswordsForOrigin(modelData)
                                    delegate: Rectangle {
                                        required property string username
                                        required property string origin
                                        Layout.fillWidth: true
                                        implicitHeight: 52
                                        radius: 7
                                        color: accentSurfaceRaised
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            spacing: 8
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Label { text: username; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                                                Label { text: "Stored in KWallet"; color: "#D7C1AA"; font.pixelSize: 11; Layout.fillWidth: true }
                                            }
                                            Button { text: "Delete"; onClicked: browserBackend.deletePassword(origin, username) }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Import CSV…"; onClicked: browserBackend.choosePasswordImport() }
                Button { text: "System Password Manager"; visible: !browserBackend.sandboxed; onClicked: browserBackend.openSystemPasswordManager() }
                Item { Layout.fillWidth: true }
                Button { text: "Reset…"; onClicked: resetPasswordsConfirmDialog.open() }
                Button { text: "Close"; onClicked: passwordsDialog.close() }
            }
        }
    }

    Dialog {
        id: resetPasswordsConfirmDialog
        title: "Reset Passwords"
        modal: true
        width: 360
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: "This deletes every saved password from your KDE wallet. This can't be undone."
                color: "#D7C1AA"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button { text: "Cancel"; onClicked: resetPasswordsConfirmDialog.close() }
                Button {
                    text: "Reset Passwords"
                    onClicked: {
                        browserBackend.resetPasswords()
                        resetPasswordsConfirmDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: siteSafetyDialog
        title: "Site Safety"
        parent: window.contentItem
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(400, window.width - 24)
        x: Math.max(12, window.contentItem.width - width - 60)
        y: 4
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: browserBackend.currentSite.length ? browserBackend.currentSite : "New Tab"
                font.bold: true
                font.pixelSize: 18
                color: "#FFF3E6"
                Layout.fillWidth: true
                elide: Text.ElideMiddle
            }
            Label {
                text: currentView && String(currentView.url).indexOf("https:") === 0 ? "Connection: Secure HTTPS" : "Connection: Not secure — this page does not use HTTPS"
                wrapMode: Text.Wrap
                color: currentView && String(currentView.url).indexOf("https:") === 0 ? "#9AD8AE" : accentGlow
                Layout.fillWidth: true
            }
            Label {
                text: "Permissions always ask first. Any approval lasts only for this private browser session."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: accentBorder }
            Label {
                text: "ReyOS Shields: " + (browserBackend.shieldsEnabled ? "On" : "Off") + " · " + browserBackend.blockedRequestCount + " requests blocked this session"
                wrapMode: Text.Wrap
                color: "#F4D5A8"
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: browserBackend.shieldsEnabled ? "Turn Shields Off" : "Turn Shields On"
                    onClicked: browserBackend.toggleShields()
                }
                Button {
                    visible: browserBackend.currentSite.length > 0
                    text: browserBackend.currentSiteShieldsEnabled ? "Disable for this site" : "Enable for this site"
                    onClicked: browserBackend.toggleCurrentSiteShields()
                }
            }
            Label {
                text: "Browsing data is in memory and clears when Reyva closes."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Button { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: siteSafetyDialog.close() }
        }
    }

    Dialog {
        id: installAppNameDialog
        title: "Install as App"
        modal: true
        width: 400
        anchors.centerIn: parent
        padding: 18
        property string pendingUrl: ""
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: "App name"
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            TextField {
                id: installAppNameField
                Layout.fillWidth: true
                selectByMouse: true
                color: "#FFF3E6"
                background: Rectangle { color: accentSurfaceHover; radius: 6; border.color: accentBorder; border.width: 1 }
                onAccepted: if (installAppInstallButton.enabled) installAppInstallButton.clicked()
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button { text: "Cancel"; onClicked: installAppNameDialog.close() }
                Button {
                    id: installAppInstallButton
                    text: "Install"
                    enabled: installAppNameField.text.trim().length > 0
                    onClicked: {
                        var pendingUrl = installAppNameDialog.pendingUrl
                        var pendingTitle = installAppNameField.text.trim()
                        installAppNameDialog.close()
                        window.confirmInstallApp(pendingUrl, pendingTitle)
                    }
                }
            }
        }
    }

    Dialog {
        id: manageAppsDialog
        title: "Installed Apps"
        modal: true
        width: 460
        height: Math.min(480, window.height - 80)
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 10
            Label {
                visible: browserBackend.installedWebApps.length === 0
                text: "No apps installed yet. Use \"Install this site as an app\" on any page to add one."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: browserBackend.installedWebApps
                        delegate: Rectangle {
                            id: webAppEntry
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 60
                            radius: 7
                            color: accentSurfaceBase
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 9
                                spacing: 10
                                Image {
                                    source: webAppEntry.modelData.icon ? Qt.resolvedUrl("file://" + webAppEntry.modelData.icon) : Qt.resolvedUrl("../assets/reyos-browser-logo.png")
                                    sourceSize.width: 36
                                    sourceSize.height: 36
                                    Layout.preferredWidth: 36
                                    Layout.preferredHeight: 36
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Label { text: webAppEntry.modelData.name; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Label { text: webAppEntry.modelData.comment; color: "#D7C1AA"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                                Button { text: "Remove"; onClicked: browserBackend.uninstallWebApp(webAppEntry.modelData.id) }
                            }
                        }
                    }
                }
            }
            Button { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: manageAppsDialog.close() }
        }
    }

    Image {
        id: appIconGrabber
        parent: window.contentItem
        x: -1000
        y: -1000
        width: 128
        height: 128
        fillMode: Image.PreserveAspectFit
        mipmap: true
        visible: true
        property string pageUrl: ""
        property string pageTitle: ""
        onStatusChanged: {
            if (status !== Image.Ready && status !== Image.Error) {
                return
            }
            var url = pageUrl
            var title = pageTitle
            if (status === Image.Error) {
                browserBackend.installAsApp(url, title, "", "")
                return
            }
            grabToImage(function(result) {
                var tmpPath = StandardPaths.writableLocation(StandardPaths.TempLocation).toString().replace(/^file:\/\//, "") + "/reyos-webapp-icon-" + Date.now() + ".png"
                if (result.saveToFile(tmpPath)) {
                    browserBackend.installAsApp(url, title, tmpPath, "")
                } else {
                    browserBackend.installAsApp(url, title, "", "")
                }
            })
        }
    }

    Popup {
        id: browserMenu
        parent: window.contentItem
        x: Math.max(8, window.contentItem.width - width - 10)
        y: 4
        width: 290
        height: Math.min(window.contentItem.height - 12, menuColumn.implicitHeight + 16)
        padding: 8
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }

        component MenuDivider: Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Layout.bottomMargin: 4
            implicitHeight: 1
            color: accentBorder
            opacity: 0.7
        }

        contentItem: Flickable {
            clip: true
            contentHeight: menuColumn.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: menuColumn
                width: parent.width
                spacing: 2

                MenuRow {
                    text: "New Tab"
                    iconSource: Qt.resolvedUrl("../icons/reyos-plus.svg")
                    shortcutText: "Ctrl+T"
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); window.addTab() }
                }
                MenuRow {
                    text: "Reopen Closed Tab"
                    iconSource: Qt.resolvedUrl("../icons/reyos-history.svg")
                    shortcutText: "Ctrl+Shift+T"
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); window.reopenClosedTab() }
                }

                MenuDivider {}

                MenuRow {
                    text: "Bookmarks"
                    iconSource: Qt.resolvedUrl("../icons/reyos-bookmark.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); bookmarksDialog.open() }
                }
                MenuRow {
                    text: "Downloads"
                    iconSource: Qt.resolvedUrl("../icons/reyos-download.svg")
                    shortcutText: window.activeDownloadCount > 0 ? window.activeDownloadCount + " active" : ""
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); downloadsDialog.open() }
                }
                MenuRow {
                    text: "Session History"
                    iconSource: Qt.resolvedUrl("../icons/reyos-history.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); historyDialog.open() }
                }
                MenuRow {
                    text: "Passwords"
                    iconSource: Qt.resolvedUrl("../icons/reyos-password.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); passwordsDialog.open() }
                }
                MenuRow {
                    text: "Install This Site as an App"
                    visible: !browserBackend.sandboxed
                    iconSource: Qt.resolvedUrl("../icons/reyos-webapp.svg")
                    hoverColor: accentSurfaceHover
                    enabled: !window.currentIsHome
                    onClicked: { browserMenu.close(); window.installCurrentAsApp() }
                }
                MenuRow {
                    text: "Manage Web Apps"
                    visible: !browserBackend.sandboxed
                    iconSource: Qt.resolvedUrl("../icons/reyos-webapp.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); manageAppsDialog.open() }
                }

                MenuDivider {}

                MenuRow {
                    text: "Privacy & Shields"
                    iconSource: Qt.resolvedUrl("../icons/reyos-shields.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); siteSafetyDialog.open() }
                }
                MenuRow {
                    text: "Low Memory Mode"
                    iconSource: Qt.resolvedUrl("../icons/reyos-memory.svg")
                    hoverColor: accentSurfaceHover
                    accent: accentColor
                    toggle: true
                    on: browserBackend.lowMemoryMode
                    onClicked: browserBackend.toggleLowMemoryMode()
                }

                MenuDivider {}

                MenuRow {
                    text: window.readerIsActive() ? "Exit Reader Mode" : "Reader Mode"
                    iconSource: Qt.resolvedUrl("../icons/reyos-reader.svg")
                    shortcutText: "Ctrl+Shift+R"
                    hoverColor: accentSurfaceHover
                    enabled: !window.currentIsHome
                    onClicked: { browserMenu.close(); window.openReaderMode() }
                }
                MenuRow {
                    text: "Find in Page"
                    iconSource: Qt.resolvedUrl("../icons/reyos-find.svg")
                    shortcutText: "Ctrl+F"
                    hoverColor: accentSurfaceHover
                    enabled: !window.currentIsHome
                    onClicked: { browserMenu.close(); window.openFind() }
                }

                MenuDivider {}

                MenuRow {
                    text: "Settings"
                    iconSource: Qt.resolvedUrl("../icons/reyos-settings.svg")
                    hoverColor: accentSurfaceHover
                    onClicked: { browserMenu.close(); settingsDialog.open() }
                }
                MenuRow {
                    text: "Quit Reyva"
                    iconSource: Qt.resolvedUrl("../icons/reyos-quit.svg")
                    shortcutText: "Ctrl+Q"
                    hoverColor: accentSurfaceHover
                    onClicked: Qt.quit()
                }
            }
        }
    }

    Dialog {
        id: historyDialog
        title: "Private Session History"
        modal: true
        width: 560
        height: 470
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 10
            Label { text: "Only this browser session · cleared when Reyva closes"; color: "#D7C1AA"; Layout.fillWidth: true }
            Label { visible: sessionHistory.count === 0; text: "No pages visited in this session"; color: "#F4D5A8"; Layout.fillWidth: true }
            ListView {
                model: sessionHistory
                clip: true
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 3
                delegate: ItemDelegate {
                    required property string pageUrl
                    required property string pageTitle
                    width: ListView.view.width
                    text: pageTitle
                    onClicked: window.openHistoryPage(pageUrl)
                    contentItem: ColumnLayout {
                        spacing: 2
                        Label { text: pageTitle; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: pageUrl; color: "#D7C1AA"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    background: Rectangle { color: hovered ? accentSurfaceHover : accentSurfaceBase; radius: 7 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Clear Session History"; enabled: sessionHistory.count > 0; onClicked: sessionHistory.clear() }
                Item { Layout.fillWidth: true }
                Button { text: "Close"; onClicked: historyDialog.close() }
            }
        }
    }

    Dialog {
        id: findDialog
        title: "Find in page"
        modal: false
        width: 430
        x: Math.max(12, window.width - width - 24)
        y: 92
        padding: 14
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 10 }
        onClosed: {
            window.findInPage("", false)
            window.findMatchCount = 0
        }
        contentItem: RowLayout {
            spacing: 8
            TextField {
                id: findField
                Layout.fillWidth: true
                placeholderText: "Find text on this page"
                selectByMouse: true
                onTextChanged: window.findInPage(text, false)
                onAccepted: window.findInPage(text, false)
            }
            Label { text: findField.text.length ? window.findMatchCount + " found" : ""; color: "#F4D5A8"; font.pixelSize: 12 }
            ToolButton { text: "‹"; font.pixelSize: 23; palette.buttonText: "#FFFFFF"; enabled: findField.text.length > 0; onClicked: window.findInPage(findField.text, true); ToolTip.visible: hovered; ToolTip.text: "Previous match" }
            ToolButton { text: "›"; font.pixelSize: 23; palette.buttonText: "#FFFFFF"; enabled: findField.text.length > 0; onClicked: window.findInPage(findField.text, false); ToolTip.visible: hovered; ToolTip.text: "Next match" }
            ToolButton { text: "×"; font.pixelSize: 20; palette.buttonText: "#FFFFFF"; onClicked: findDialog.close(); ToolTip.visible: hovered; ToolTip.text: "Close find" }
        }
    }

    Dialog {
        id: permissionDialog
        property var permissionRequest: null
        property string site: "this website"
        property bool answered: false
        title: "Permission request"
        modal: true
        width: 410
        anchors.centerIn: parent
        padding: 18
        onClosed: {
            if (!answered && permissionRequest) {
                permissionRequest.reject()
            }
        }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: permissionDialog.site + " wants access to a protected feature."; wrapMode: Text.Wrap; color: "#FFF3E6"; Layout.fillWidth: true }
            Label { text: "Allow only for this private browser session?"; wrapMode: Text.Wrap; color: "#D7C1AA"; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    text: "Block"
                    onClicked: {
                        permissionDialog.answered = true
                        permissionDialog.permissionRequest.reject()
                        permissionDialog.close()
                    }
                }
                Button {
                    text: "Allow this session"
                    onClicked: {
                        permissionDialog.answered = true
                        permissionDialog.permissionRequest.grant()
                        permissionDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: settingsDialog
        title: "Reyva Settings"
        modal: true
        width: 455
        anchors.centerIn: parent
        padding: 20
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 14
            Label { text: "Private session"; font.bold: true; font.pixelSize: 19; color: "#FFF3E6" }
            Label { text: "Your choices reset when Reyva closes."; wrapMode: Text.Wrap; color: "#F4D5A8"; Layout.fillWidth: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: accentBorder }
            Label { text: "Search engine"; font.bold: true; color: "#FFF3E6" }
            ComboBox {
                id: searchEnginePicker
                model: ["DuckDuckGo", "Startpage"]
                currentIndex: browserBackend.searchEngine === "Startpage" ? 1 : 0
                Layout.fillWidth: true
                contentItem: Text {
                    leftPadding: 10
                    rightPadding: searchEnginePicker.indicator.width + 10
                    text: searchEnginePicker.displayText
                    color: "#FFF3E6"
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                background: Rectangle { color: accentSurfaceBase; border.color: accentBorder; radius: 7 }
                popup: Popup {
                    y: searchEnginePicker.height - 1
                    width: searchEnginePicker.width
                    implicitHeight: contentItem.implicitHeight
                    padding: 4
                    background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; radius: 7 }
                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: searchEnginePicker.popup.visible ? searchEnginePicker.delegateModel : null
                        currentIndex: searchEnginePicker.highlightedIndex
                    }
                }
                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: searchEnginePicker.width - 8
                    height: 34
                    highlighted: searchEnginePicker.highlightedIndex === index
                    contentItem: Text { text: modelData; color: "#FFF3E6"; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                    background: Rectangle { color: highlighted ? accentSurfaceHover : "transparent"; radius: 5 }
                }
                onActivated: browserBackend.setSearchEngine(currentText)
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: accentBorder }
            Label { text: "Performance"; font.bold: true; color: "#FFF3E6" }
            Switch {
                text: "Low Memory Mode"
                checked: browserBackend.lowMemoryMode
                contentItem: Text { text: parent.text; color: "#FFF3E6"; verticalAlignment: Text.AlignVCenter; leftPadding: parent.indicator.width + 8 }
                onToggled: {
                    if (checked !== browserBackend.lowMemoryMode) {
                        browserBackend.toggleLowMemoryMode()
                    }
                }
            }
            Label { text: "Freezes safe inactive tabs, then discards them later to save memory."; wrapMode: Text.Wrap; color: "#D7C1AA"; Layout.fillWidth: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: accentBorder }
            Label { text: "ReyOS Shields"; font.bold: true; color: "#FFF3E6" }
            Label { text: (browserBackend.shieldsEnabled ? "On" : "Off") + " · " + browserBackend.blockedRequestCount + " requests blocked this session"; wrapMode: Text.Wrap; color: "#F4D5A8"; Layout.fillWidth: true }
            Label { text: "Filter list: " + browserBackend.shieldsDomainCount + " domains · updated " + browserBackend.shieldsLastUpdated; wrapMode: Text.Wrap; color: "#D7C1AA"; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                Button { text: browserBackend.shieldsUpdating ? "Updating…" : "Update filter list"; enabled: !browserBackend.shieldsUpdating; onClicked: browserBackend.updateShieldsFilterList() }
                Label { visible: shieldsUpdateStatus.text.length > 0; id: shieldsUpdateStatus; wrapMode: Text.Wrap; Layout.fillWidth: true; color: "#F4D5A8" }
            }
            Connections {
                target: browserBackend
                function onShieldsUpdateFinished(ok, message) {
                    shieldsUpdateStatus.text = message
                }
            }
            Button {
                Layout.alignment: Qt.AlignRight
                implicitWidth: 82
                contentItem: Text { text: "Close"; color: "#FFF3E6"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { color: parent.hovered ? accentSurfaceHover : accentSurfaceBase; border.color: accentBorder; radius: 7 }
                onClicked: settingsDialog.close()
            }
        }
    }

    Dialog {
        id: downloadsDialog
        title: "Downloads"
        parent: window.contentItem
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(420, window.width - 24)
        height: Math.max(190, Math.min(440, downloads.count * 86 + 125))
        x: Math.max(12, window.contentItem.width - width - 12)
        y: 4
        padding: 16
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 10
            Label { visible: downloads.count === 0; text: "No downloads in this private session"; color: "#D7C1AA"; Layout.fillWidth: true; Layout.fillHeight: true }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: downloads.count > 0
                clip: true
                spacing: 8
                model: downloads
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property int downloadId
                    required property string name
                    required property string status
                    required property double receivedBytes
                    required property double totalBytes
                    required property bool finished
                    required property bool completed
                    width: ListView.view.width
                    height: 76
                    radius: 7
                    color: accentSurfaceBase
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: name; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: status; color: completed ? "#9AD8AE" : "#D7C1AA"; font.pixelSize: 12 }
                        }
                        ProgressBar {
                            visible: !finished
                            from: 0
                            to: totalBytes > 0 ? totalBytes : 1
                            value: totalBytes > 0 ? receivedBytes : 0
                            indeterminate: totalBytes <= 0
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: totalBytes > 0 ? Math.round(receivedBytes / 1024) + " / " + Math.round(totalBytes / 1024) + " KiB" : (finished ? "" : "Preparing download…")
                                color: "#D7C1AA"
                                font.pixelSize: 11
                                Layout.fillWidth: true
                            }
                            Button { visible: !finished; text: "Cancel"; onClicked: window.cancelDownload(downloadId) }
                            Button { visible: completed; text: "Open"; onClicked: window.openDownload(name) }
                            Button { visible: completed; text: "Show in Folder"; onClicked: Qt.openUrlExternally("file://" + window.downloadsPath) }
                        }
                    }
                }
            }
            Button { text: "Open Downloads Folder"; Layout.alignment: Qt.AlignRight; onClicked: Qt.openUrlExternally("file://" + window.downloadsPath) }
        }
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: tabBar.currentIndex

        Repeater {
            id: pages
            model: tabs
            delegate: WebEngineView {
                required property int index
                required property string pageUrl
                required property string pageTitle
                required property string readerOriginalUrl
                required property bool keepAlive

                id: browserView
                property bool selected: index === tabBar.currentIndex

                function updateLifecycle() {
                    if (selected || keepAlive || !browserBackend.lowMemoryMode) {
                        lifecycleTimer.stop()
                        lifecycleState = WebEngineView.LifecycleState.Active
                        return
                    }
                    lifecycleTimer.restart()
                }

                onSelectedChanged: updateLifecycle()
                onKeepAliveChanged: updateLifecycle()
                Component.onCompleted: updateLifecycle()

                Connections {
                    target: browserBackend
                    function onLowMemoryChanged() {
                        browserView.updateLifecycle()
                    }
                }

                Timer {
                    id: lifecycleTimer
                    interval: browserView.lifecycleState === WebEngineView.LifecycleState.Active ? 120000 : 480000
                    repeat: false
                    onTriggered: {
                        if (browserView.selected || browserView.keepAlive || !browserBackend.lowMemoryMode) {
                            return
                        }
                        if (browserView.lifecycleState === WebEngineView.LifecycleState.Active) {
                            if (browserView.recommendedState !== WebEngineView.LifecycleState.Active) {
                                browserView.lifecycleState = WebEngineView.LifecycleState.Frozen
                            }
                            lifecycleTimer.restart()
                        } else if (browserView.lifecycleState === WebEngineView.LifecycleState.Frozen && browserView.recommendedState === WebEngineView.LifecycleState.Discarded) {
                            browserView.lifecycleState = WebEngineView.LifecycleState.Discarded
                        }
                    }
                }

                // One bridge per tab, answering only for that tab's own address.
                // The channel lives in an isolated script world, so the page's
                // own scripts can't reach it at all.
                QtObject {
                    id: tabPasswordBridge
                    WebChannel.id: "passwordBridge"
                    function reportFormSubmit(origin, username, password) {
                        passwordBridge.reportFormSubmit(origin, username, password, browserView.url.toString())
                    }
                    function credentialsFor(origin) {
                        return passwordBridge.credentialsFor(origin, browserView.url.toString())
                    }
                }

                profile: privateProfile
                webChannelWorld: WebEngineScript.ApplicationWorld
                webChannel: WebChannel {
                    registeredObjects: [tabPasswordBridge]
                }
                userScripts.collection: [
                    {
                        name: "reyos-fingerprint-protection",
                        sourceCode: browserBackend.fingerprintScriptSource,
                        injectionPoint: WebEngineScript.DocumentCreation,
                        worldId: WebEngineScript.MainWorld,
                        runsOnSubFrames: true
                    }
                ]
                url: pageUrl
                settings.javascriptCanOpenWindows: false
                settings.pdfViewerEnabled: true
                // pdfViewerEnabled alone isn't enough on this QtWebEngine build --
                // confirmed live (standalone PySide6 repro) that Chromium's internal
                // PDF viewer stays gated off and every PDF falls through to a plain
                // download unless pluginsEnabled is also true. Not a real plugin
                // security surface today (NPAPI/Pepper plugins are long gone from
                // Chromium) -- this attribute just also happens to gate the PDF
                // viewer's internal MIME handler extension.
                settings.pluginsEnabled: true

                onPermissionRequested: function(request) {
                    window.requestPermission(request)
                }
                onContextMenuRequested: function(request) {
                    request.accepted = true
                    pageContextMenu.request = request
                    pageContextMenu.view = browserView
                    pageContextMenu.popup()
                }
                onUrlChanged: {
                    tabs.setProperty(index, "pageUrl", url.toString())
                    window.recordHistory(url.toString(), title)
                    if (index === tabBar.currentIndex) {
                        window.syncCurrentSite()
                    }
                }
                onTitleChanged: {
                    tabs.setProperty(index, "pageTitle", window.isHomeUrl(url.toString()) ? "New Tab" : (title || "New Tab"))
                    window.updateHistoryTitle(url.toString(), title)
                }
                onLoadingChanged: function(loadRequest) {
                    if (loadRequest.status === WebEngineLoadingInfo.LoadSucceededStatus && /^https?:/.test(String(url))) {
                        runJavaScript(browserBackend.passwordScriptSource, WebEngineScript.ApplicationWorld, function() {})
                    }
                }
            }
        }
    }
    NewTabPage {
        id: newTabPage
        anchors.fill: parent
        visible: window.currentIsHome && !window.readerIsActive()
        theme: theme
        shortcuts: browserBackend.shortcuts
        onSearchRequested: function(text) { window.openAddress(text) }
        onShortcutOpened: function(url) { window.openBookmarkUrl(url) }
        onAddShortcutRequested: window.openShortcutDialog(-1)
        onEditShortcutRequested: function(index) { window.openShortcutDialog(index) }
        onRemoveShortcutRequested: function(index) { browserBackend.removeShortcut(index) }
    }

    Dialog {
        id: shortcutDialog
        property int editIndex: -1
        property string errorText: ""
        title: editIndex >= 0 ? "Edit Shortcut" : "Add Shortcut"
        modal: true
        width: Math.min(420, window.width - 32)
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: accentSurfaceRaised; border.color: accentBorder; border.width: 1; radius: 12 }

        function save() {
            if (browserBackend.updateShortcut(editIndex, shortcutNameField.text, shortcutUrlField.text)) {
                close()
            } else {
                errorText = "Enter a web address, for example github.com"
            }
        }

        contentItem: ColumnLayout {
            spacing: 8
            Label { text: "Name"; color: "#D7C1AA" }
            TextField {
                id: shortcutNameField
                Layout.fillWidth: true
                placeholderText: "GitHub"
                selectByMouse: true
                onAccepted: shortcutDialog.save()
            }
            Label { text: "Address"; color: "#D7C1AA"; Layout.topMargin: 4 }
            TextField {
                id: shortcutUrlField
                Layout.fillWidth: true
                placeholderText: "github.com"
                selectByMouse: true
                onTextChanged: shortcutDialog.errorText = ""
                onAccepted: shortcutDialog.save()
            }
            Label {
                visible: shortcutDialog.errorText.length > 0
                text: shortcutDialog.errorText
                color: accentGlow
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Label {
                text: "Shortcuts open in a normal private tab. They are saved on this computer, like bookmarks."
                color: "#9F8873"
                font.pixelSize: 12
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                Layout.topMargin: 4
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                Item { Layout.fillWidth: true }
                Button { text: "Cancel"; onClicked: shortcutDialog.close() }
                Button {
                    text: shortcutDialog.editIndex >= 0 ? "Save" : "Add"
                    enabled: shortcutUrlField.text.trim().length > 0
                    onClicked: shortcutDialog.save()
                }
            }
        }
    }

    Menu {
        id: pageContextMenu
        property var request: null
        property var view: null
        readonly property string linkUrl: request ? String(request.linkUrl) : ""
        readonly property string mediaUrl: request ? String(request.mediaUrl) : ""
        readonly property bool hasSelection: request ? request.selectedText.length > 0 : false
        readonly property bool editable: request ? request.isContentEditable : false
        readonly property bool isImage: request ? request.mediaType === ContextMenuRequest.MediaTypeImage : false
        readonly property bool plainPage: !linkUrl && !hasSelection && !editable && !isImage

        function act(action) {
            if (view) {
                view.triggerWebAction(action)
            }
        }

        MenuItem { text: "Back"; visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0; enabled: pageContextMenu.view && pageContextMenu.view.canGoBack; onTriggered: pageContextMenu.view.goBack() }
        MenuItem { text: "Forward"; visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0; enabled: pageContextMenu.view && pageContextMenu.view.canGoForward; onTriggered: pageContextMenu.view.goForward() }
        MenuItem { text: "Reload"; visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.view.reload() }

        MenuItem { text: "Open Link in New Tab"; visible: pageContextMenu.linkUrl.length > 0; height: visible ? implicitHeight : 0; onTriggered: window.openInNewTab(pageContextMenu.linkUrl) }
        MenuItem { text: "Copy Link Address"; visible: pageContextMenu.linkUrl.length > 0; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.CopyLinkToClipboard) }
        MenuItem { text: "Save Link As…"; visible: pageContextMenu.linkUrl.length > 0; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.DownloadLinkToDisk) }

        MenuItem { text: "Open Image in New Tab"; visible: pageContextMenu.isImage; height: visible ? implicitHeight : 0; onTriggered: window.openInNewTab(pageContextMenu.mediaUrl) }
        MenuItem { text: "Copy Image"; visible: pageContextMenu.isImage; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.CopyImageToClipboard) }
        MenuItem { text: "Save Image As…"; visible: pageContextMenu.isImage; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.DownloadImageToDisk) }

        MenuItem { text: "Cut"; visible: pageContextMenu.editable; height: visible ? implicitHeight : 0; enabled: pageContextMenu.hasSelection; onTriggered: pageContextMenu.act(WebEngineView.Cut) }
        MenuItem { text: "Copy"; visible: pageContextMenu.hasSelection || pageContextMenu.editable; height: visible ? implicitHeight : 0; enabled: pageContextMenu.hasSelection; onTriggered: pageContextMenu.act(WebEngineView.Copy) }
        MenuItem { text: "Paste"; visible: pageContextMenu.editable; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.Paste) }
        MenuItem { text: "Select All"; visible: pageContextMenu.editable; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.SelectAll) }
        MenuItem {
            text: "Search for “" + (pageContextMenu.request ? pageContextMenu.request.selectedText.slice(0, 24) : "") + (pageContextMenu.request && pageContextMenu.request.selectedText.length > 24 ? "…" : "") + "”"
            visible: pageContextMenu.hasSelection && !pageContextMenu.editable
            height: visible ? implicitHeight : 0
            onTriggered: window.openInNewTab(browserBackend.searchBase + encodeURIComponent(pageContextMenu.request.selectedText))
        }

        MenuSeparator { visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0 }
        MenuItem { text: "Save Page As…"; visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0; onTriggered: pageContextMenu.act(WebEngineView.SavePage) }
        MenuItem { text: "View Page Source"; visible: pageContextMenu.plainPage; height: visible ? implicitHeight : 0; onTriggered: window.openInNewTab("view-source:" + pageContextMenu.view.url) }

        background: Rectangle {
            implicitWidth: 230
            color: accentSurfaceRaised
            border.color: accentBorder
            border.width: 1
            radius: 10
        }
    }

}
