import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebChannel
import QtWebEngine

ApplicationWindow {
    id: window
    width: 1200
    height: 760
    minimumWidth: 760
    minimumHeight: 520
    visible: true
    title: currentView && currentView.title ? currentView.title + " — ReyOS Browser" : "ReyOS Browser"
    color: "#15110E"

    property var currentView: pages.itemAt(tabBar.currentIndex)
    property var downloadRequests: ({})
    property var closedTabsStack: []
    property int findMatchCount: 0
    readonly property string downloadsPath: StandardPaths.writableLocation(StandardPaths.DownloadLocation).toString().replace(/^file:\/\//, "")
    readonly property url homeUrl: Qt.resolvedUrl("../home.html")

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
        if (!currentView) {
            return ""
        }
        return isHomeUrl(currentView.url.toString()) ? "New Tab" : currentView.url.toString()
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
                downloads.setProperty(i, "finished", true)
                downloads.setProperty(i, "completed", completed)
                downloads.setProperty(i, "state", completed ? "Completed" : (cancelled ? "Cancelled" : "Failed: " + download.interruptReasonString))
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
            state: "Starting",
            receivedBytes: download.receivedBytes,
            totalBytes: download.totalBytes,
            finished: false,
            completed: false
        })
        downloadRequests[download.id] = download
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
        return "<!--reyos-reader-view--><!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Reader: " + t + "</title><style>:root{color-scheme:dark}body{margin:0;background:linear-gradient(145deg,#15110E,#241A13);color:#FFF3E6;font:19px/1.8 Georgia,serif}.shell{max-width:900px;margin:42px auto;padding:0 24px 72px}.mast{border:1px solid #8E5A2E;border-bottom:0;border-radius:18px 18px 0 0;padding:24px 34px 20px;background:linear-gradient(135deg,#3B291C,#302217)}.brand{font:700 13px system-ui,sans-serif;letter-spacing:1.2px;color:#F0B46A;text-transform:uppercase}.source{margin-top:9px;color:#F4D5A8;font:13px system-ui,sans-serif;word-break:break-all}article{background:#211711;border:1px solid #8E5A2E;border-radius:0 0 18px 18px;padding:34px;box-shadow:0 18px 52px #0008;white-space:pre-wrap}h1{font:700 37px/1.18 system-ui,sans-serif;letter-spacing:-.7px;color:#fff;margin:0}</style></head><body><main class=\"shell\"><header class=\"mast\"><div class=\"brand\">ReyOS Reader</div><h1>" + t + "</h1><div class=\"source\">" + u + "</div></header><article>" + body + "</article></main></body></html>"
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

    function initializeFirstTab() {
        if (tabs.count === 0) {
            addTab()
        }
    }

    function addTab() {
        tabs.append({ pageUrl: homeUrl.toString(), pageTitle: "New Tab", readerOriginalUrl: "", keepAlive: false })
        tabBar.currentIndex = tabs.count - 1
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

    QtObject {
        id: passwordBridgeChannelObject
        WebChannel.id: "passwordBridge"
        function reportFormSubmit(origin, username, password) {
            passwordBridge.reportFormSubmit(origin, username, password)
        }
        function credentialsFor(origin, callback) {
            callback(passwordBridge.credentialsFor(origin))
        }
    }

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

        TabBar {
            id: tabBar
            Layout.fillWidth: true
            currentIndex: 0
            onCurrentIndexChanged: Qt.callLater(window.syncCurrentSite)
            background: Rectangle { color: "#211711" }

            Repeater {
                model: tabs
                delegate: TabButton {
                    id: tabButton
                    required property int index
                    required property string pageTitle
                    required property bool keepAlive
                    text: pageTitle.length > 22 ? pageTitle.slice(0, 21) + "…" : pageTitle
                    onClicked: tabBar.currentIndex = index
                    background: Rectangle {
                        color: tabButton.checked ? "#C97932" : (tabButton.hovered ? "#3B291C" : "#211711")
                        radius: 6
                    }
                    contentItem: RowLayout {
                        spacing: 2
                        Label {
                            text: tabButton.text
                            color: "#FFFFFF"
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            text: pages.itemAt(index) && pages.itemAt(index).lifecycleState === WebEngineView.LifecycleState.Discarded ? "◌" : (pages.itemAt(index) && pages.itemAt(index).lifecycleState === WebEngineView.LifecycleState.Frozen ? "❄" : "")
                            color: "#F4D5A8"
                            font.pixelSize: 19
                            font.bold: true
                        }
                        ToolButton {
                            id: keepAliveButton
                            icon.source: Qt.resolvedUrl("../icons/reyos-pin.svg")
                            icon.width: 18
                            icon.height: 18
                            implicitWidth: 26
                            implicitHeight: 26
                            opacity: tabButton.keepAlive ? 1.0 : 0.75
                            background: Rectangle {
                                color: keepAliveButton.hovered ? "#4A3420" : (tabButton.keepAlive ? "#3B291C" : "transparent")
                                radius: 6
                            }
                            onClicked: tabs.setProperty(tabButton.index, "keepAlive", !tabButton.keepAlive)
                            ToolTip.visible: hovered
                            ToolTip.text: tabButton.keepAlive ? "Keep running: On — stays active in the background" : "Keep this tab running in the background (e.g. music or video)"
                            Accessible.name: "Keep tab running in background"
                        }
                        ToolButton {
                            text: "×"
                            onClicked: window.closeTab(tabButton.index)
                        }
                    }
                }
            }

            TabButton {
                text: "+"
                font.pixelSize: 27
                implicitWidth: 48
                implicitHeight: 38
                palette.buttonText: "#FFFFFF"
                background: Rectangle { color: parent.hovered ? "#3B291C" : "transparent"; radius: 6 }
                onClicked: window.addTab()
            }
        }

        ToolBar {
            Layout.fillWidth: true
            implicitHeight: 46
            background: Rectangle { color: "#302217" }
            contentItem: RowLayout {
                spacing: 3

                ToolButton {
                    id: backButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-back.svg")
                    icon.width: 22
                    icon.height: 22
                    implicitWidth: 40
                    implicitHeight: 42
                    enabled: currentView && currentView.canGoBack
                    opacity: enabled ? 1.0 : 0.5
                    background: Rectangle { color: backButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: currentView.goBack()
                    ToolTip.visible: hovered
                    ToolTip.text: "Back"
                    Accessible.name: "Back"
                }

                ToolButton {
                    id: forwardButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-forward.svg")
                    icon.width: 22
                    icon.height: 22
                    implicitWidth: 40
                    implicitHeight: 42
                    enabled: currentView && currentView.canGoForward
                    opacity: enabled ? 1.0 : 0.5
                    background: Rectangle { color: forwardButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: currentView.goForward()
                    ToolTip.visible: hovered
                    ToolTip.text: "Forward"
                    Accessible.name: "Forward"
                }

                ToolButton {
                    id: reloadButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-refresh.svg")
                    icon.width: 20
                    icon.height: 20
                    implicitWidth: 38
                    implicitHeight: 42
                    background: Rectangle { color: reloadButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: currentView.reload()
                    ToolTip.visible: hovered
                    ToolTip.text: "Reload"
                    Accessible.name: "Reload"
                }

                TextField {
                    id: address
                    Layout.fillWidth: true
                    Layout.preferredWidth: 520
                    Layout.minimumWidth: 280
                    implicitHeight: 32
                    placeholderText: "Search privately or enter an address"
                    text: window.addressLabel()
                    selectByMouse: true
                    onAccepted: window.openAddress(text)
                }

                ToolButton {
                    id: bookmarkButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-bookmark.svg")
                    icon.width: 21
                    icon.height: 21
                    implicitWidth: 38
                    implicitHeight: 42
                    opacity: currentView && browserBackend.isBookmarked(currentView.url.toString()) ? 1.0 : 0.72
                    background: Rectangle { color: bookmarkButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: window.toggleBookmark()
                    ToolTip.visible: hovered
                    ToolTip.text: currentView && browserBackend.isBookmarked(currentView.url.toString()) ? "Remove bookmark" : "Bookmark this page"
                    Accessible.name: "Bookmark this page"
                }

                ToolButton {
                    id: readerButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-reader.svg")
                    icon.width: 20
                    icon.height: 20
                    implicitWidth: 38
                    implicitHeight: 42
                    opacity: window.readerIsActive() ? 0.72 : 1.0
                    background: Rectangle { color: readerButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: window.openReaderMode()
                    ToolTip.visible: hovered
                    ToolTip.text: window.readerIsActive() ? "Return to original page" : "Reader Mode"
                    Accessible.name: "Reader Mode"
                }

                ToolButton {
                    id: historyButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-history.svg")
                    icon.width: 20
                    icon.height: 20
                    implicitWidth: 38
                    implicitHeight: 42
                    background: Rectangle { color: historyButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: historyDialog.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Private session history"
                    Accessible.name: "Private session history"
                }

                ToolButton {
                    id: memoryButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-memory.svg")
                    icon.width: 20
                    icon.height: 20
                    implicitWidth: 38
                    implicitHeight: 42
                    opacity: browserBackend.lowMemoryMode ? 1.0 : 0.5
                    background: Rectangle { color: memoryButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: browserBackend.toggleLowMemoryMode()
                    ToolTip.visible: hovered
                    ToolTip.text: browserBackend.lowMemoryMode ? "Low Memory Mode: On" : "Low Memory Mode: Off"
                    Accessible.name: "Low Memory Mode"
                }

                ToolButton {
                    id: shieldsButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-shields.svg")
                    icon.width: 23
                    icon.height: 23
                    implicitWidth: 40
                    implicitHeight: 42
                    opacity: browserBackend.shieldsEnabled ? 1.0 : 0.5
                    background: Rectangle { color: shieldsButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: siteSafetyDialog.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Site Safety"
                    Accessible.name: "Site Safety"
                }

                ToolButton {
                    id: browserMenuButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-menu.svg")
                    icon.width: 22
                    icon.height: 22
                    implicitWidth: 38
                    implicitHeight: 42
                    background: Rectangle { color: browserMenuButton.hovered ? "#3B291C" : "transparent"; radius: 8 }
                    onClicked: browserMenu.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Browser menu"
                    Accessible.name: "Browser menu"
                }
            }
        }

        Rectangle {
            id: bookmarksBarContainer
            Layout.fillWidth: true
            implicitHeight: visible ? 42 : 0
            visible: browserBackend.bookmarks.length > 0
            color: "#241A13"
            border.color: "#8E5A2E"
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
                                        color: parent.hovered ? "#3B291C" : "#302217"
                                        border.color: "#8E5A2E"
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
                                    color: folderChip.hovered || folderPopup.visible ? "#3B291C" : "#302217"
                                    border.color: "#8E5A2E"
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
                                        color: "#302217"
                                        border.color: "#8E5A2E"
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
                                                        color: parent.hovered ? "#3B291C" : "transparent"
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
                        color: bookmarksOverflowButton.hovered ? "#3B291C" : "#302217"
                        border.color: "#8E5A2E"
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
            color: "#302217"
            border.color: "#8E5A2E"
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
            color: "#302217"
            border.color: "#8E5A2E"
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
                                    color: "#211711"
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
                Button { text: "Close"; onClicked: bookmarksDialog.close() }
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
            color: "#302217"
            border.color: "#8E5A2E"
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
                            color: "#211711"
                            border.color: "#8E5A2E"
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
                                        color: "#302217"
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
                Item { Layout.fillWidth: true }
                Button { text: "Close"; onClicked: passwordsDialog.close() }
            }
        }
    }

    Dialog {
        id: siteSafetyDialog
        title: "Site Safety"
        modal: true
        width: 450
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 12 }
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
                text: currentView && currentView.url.scheme === "https" ? "Connection: Secure HTTPS" : "Connection: Not secure — this page does not use HTTPS"
                wrapMode: Text.Wrap
                color: currentView && currentView.url.scheme === "https" ? "#9AD8AE" : "#F0B46A"
                Layout.fillWidth: true
            }
            Label {
                text: "Permissions always ask first. Any approval lasts only for this private browser session."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E" }
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
                text: "Browsing data is in memory and clears when ReyOS Browser closes."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Button { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: siteSafetyDialog.close() }
        }
    }

    Popup {
        id: browserMenu
        parent: window.contentItem
        x: Math.max(8, window.contentItem.width - width - 10)
        y: 4
        width: 278
        height: contentItem.implicitHeight + 16
        padding: 8
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 10 }
        contentItem: ColumnLayout {
            spacing: 3

            Button {
                id: bookmarksMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: bookmarksMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-bookmark.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Bookmarks"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    bookmarksDialog.open()
                }
            }

            Button {
                id: passwordsMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: passwordsMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-settings.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Passwords"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    passwordsDialog.open()
                }
            }

            Button {
                id: openSystemPasswordsMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: openSystemPasswordsMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-settings.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Open System Password Manager"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    browserBackend.openSystemPasswordManager()
                }
            }

            Button {
                id: findMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: findMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-find.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Find in page"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    window.openFind()
                }
            }

            Button {
                id: downloadsMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: downloadsMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-download.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Downloads"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    downloadsDialog.open()
                }
            }

            Button {
                id: shieldsMenuButton
                enabled: browserBackend.currentSite.length > 0
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: shieldsMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image {
                        source: Qt.resolvedUrl("../icons/reyos-shields.svg")
                        sourceSize.width: 20
                        sourceSize.height: 20
                        opacity: shieldsMenuButton.enabled ? 1.0 : 0.45
                        Layout.leftMargin: 10
                    }
                    Label {
                        text: browserBackend.currentSiteShieldsEnabled ? "Disable shields for this site" : "Enable shields for this site"
                        color: shieldsMenuButton.enabled ? "#FFF3E6" : "#9F8873"
                        font.pixelSize: 14
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
                onClicked: {
                    browserMenu.close()
                    browserBackend.toggleCurrentSiteShields()
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E"; Layout.topMargin: 3; Layout.bottomMargin: 3 }

            Button {
                id: settingsMenuButton
                Layout.fillWidth: true
                implicitHeight: 36
                background: Rectangle { color: settingsMenuButton.hovered ? "#3B291C" : "transparent"; radius: 7 }
                contentItem: RowLayout {
                    spacing: 10
                    Image { source: Qt.resolvedUrl("../icons/reyos-settings.svg"); sourceSize.width: 20; sourceSize.height: 20; Layout.leftMargin: 10 }
                    Label { text: "Browser Settings"; color: "#FFF3E6"; font.pixelSize: 14; Layout.fillWidth: true }
                }
                onClicked: {
                    browserMenu.close()
                    settingsDialog.open()
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
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 10
            Label { text: "Only this browser session · cleared when ReyOS Browser closes"; color: "#D7C1AA"; Layout.fillWidth: true }
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
                    background: Rectangle { color: hovered ? "#3B291C" : "#211711"; radius: 7 }
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
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 10 }
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
        title: "ReyOS Browser Settings"
        modal: true
        width: 455
        anchors.centerIn: parent
        padding: 20
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 14
            Label { text: "Private session"; font.bold: true; font.pixelSize: 19; color: "#FFF3E6" }
            Label { text: "Your choices reset when ReyOS Browser closes."; wrapMode: Text.Wrap; color: "#F4D5A8"; Layout.fillWidth: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E" }
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
                background: Rectangle { color: "#211711"; border.color: "#8E5A2E"; radius: 7 }
                popup: Popup {
                    y: searchEnginePicker.height - 1
                    width: searchEnginePicker.width
                    implicitHeight: contentItem.implicitHeight
                    padding: 4
                    background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; radius: 7 }
                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: searchEnginePicker.popup.visible ? searchEnginePicker.delegateModel : null
                        currentIndex: searchEnginePicker.highlightedIndex
                    }
                }
                delegate: ItemDelegate {
                    required property var modelData
                    width: searchEnginePicker.width - 8
                    height: 34
                    highlighted: searchEnginePicker.highlightedIndex === index
                    contentItem: Text { text: modelData; color: "#FFF3E6"; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                    background: Rectangle { color: highlighted ? "#3B291C" : "transparent"; radius: 5 }
                }
                onActivated: browserBackend.setSearchEngine(currentText)
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E" }
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
            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E" }
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
                background: Rectangle { color: parent.hovered ? "#3B291C" : "#211711"; border.color: "#8E5A2E"; radius: 7 }
                onClicked: settingsDialog.close()
            }
        }
    }

    Dialog {
        id: downloadsDialog
        title: "Downloads"
        modal: true
        width: 460
        height: Math.max(205, Math.min(440, downloads.count * 86 + 125))
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 10
            Label { visible: downloads.count === 0; text: "No downloads in this private session"; color: "#D7C1AA" }
            Repeater {
                model: downloads
                delegate: Rectangle {
                    required property int downloadId
                    required property string name
                    required property string state
                    required property double receivedBytes
                    required property double totalBytes
                    required property bool finished
                    required property bool completed
                    Layout.fillWidth: true
                    implicitHeight: 76
                    radius: 7
                    color: "#211711"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: name; color: "#FFF3E6"; elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: state; color: completed ? "#9AD8AE" : "#D7C1AA"; font.pixelSize: 12 }
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
                            Button { visible: completed; text: "Open File"; onClicked: window.openDownload(name) }
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
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

                profile: privateProfile
                webChannel: WebChannel {
                    registeredObjects: [passwordBridgeChannelObject]
                }
                url: pageUrl
                settings.javascriptCanOpenWindows: false
                settings.pdfViewerEnabled: true

                onPermissionRequested: function(request) {
                    window.requestPermission(request)
                }
                onUrlChanged: {
                    tabs.setProperty(index, "pageUrl", url.toString())
                    window.recordHistory(url.toString(), title)
                    if (index === tabBar.currentIndex) {
                        browserBackend.setCurrentSite(url.toString())
                    }
                }
                onTitleChanged: {
                    tabs.setProperty(index, "pageTitle", window.isHomeUrl(url.toString()) ? "New Tab" : (title || "New Tab"))
                    window.updateHistoryTitle(url.toString(), title)
                }
                onLoadingChanged: function(loadRequest) {
                    if (loadRequest.status === WebEngineLoadingInfo.LoadSucceededStatus && (url.scheme === "http" || url.scheme === "https")) {
                        runJavaScript(browserBackend.passwordScriptSource)
                    }
                }
            }
        }
    }
}
