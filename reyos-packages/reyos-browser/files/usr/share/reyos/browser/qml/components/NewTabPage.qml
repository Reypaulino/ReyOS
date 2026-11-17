import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: page
    property var theme
    property var shortcuts: []
    property int maxShortcuts: 12
    // Dashboard: what the owner found for the text and kind below (see
    // reyva_core.dashboard_results). Local only; the web is searched only
    // when the "Search the web" row is chosen.
    property var results: []
    property string searchEngine: "DuckDuckGo"
    property bool appsAvailable: false
    property string kind: "all"
    property int highlighted: 0
    readonly property Item searchBoxItem: searchBox  // for the guided tour
    readonly property string query: searchField.text.trim()
    readonly property bool showingResults: query.length > 0 || kind !== "all"
    readonly property bool hasWebRow: query.length > 0
    readonly property int rowCount: (hasWebRow ? 1 : 0) + results.length

    signal searchRequested(string text)
    signal shortcutOpened(string url)
    signal addShortcutRequested()
    signal editShortcutRequested(int index)
    signal removeShortcutRequested(int index)
    signal resultsWanted(string text, string kind)
    signal tabActivated(int index)
    signal bookmarkOpened(string url)
    signal appLaunched(string appId)

    function focusSearch() {
        searchField.text = ""
        kind = "all"
        searchField.forceActiveFocus()
    }

    function refreshResults() {
        highlighted = 0
        resultsWanted(query, kind)
    }

    onKindChanged: refreshResults()

    function activate(row) {
        if (hasWebRow && row === 0) {
            page.searchRequested(searchField.text)
            searchField.text = ""
            return
        }
        var entry = results[row - (hasWebRow ? 1 : 0)]
        if (!entry) {
            return
        }
        searchField.text = ""
        kind = "all"
        if (entry.kind === "tab") page.tabActivated(entry.index)
        else if (entry.kind === "app") page.appLaunched(entry.id)
        else if (entry.kind === "bookmark") page.bookmarkOpened(entry.url)
    }

    function sectionTitle(entryKind) {
        return entryKind === "tab" ? "Open tabs" : (entryKind === "app" ? "Web apps" : "Bookmarks")
    }

    readonly property bool compact: height < 780
    color: theme.windowBg

    // Painted once per resize or Look change; nothing animates.
    Canvas {
        id: waves
        anchors.fill: parent
        property color accent: page.theme.accent
        onAccentChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            var w = width, h = height
            ctx.reset()
            function wave(y0, amp, alpha, flip) {
                var g = ctx.createLinearGradient(0, y0 - amp, 0, y0 + amp * 3)
                g.addColorStop(0, Qt.rgba(accent.r, accent.g, accent.b, alpha))
                g.addColorStop(1, Qt.rgba(accent.r, accent.g, accent.b, 0))
                ctx.fillStyle = g
                ctx.beginPath()
                ctx.moveTo(0, y0 + (flip ? amp : -amp) * 0.4)
                ctx.bezierCurveTo(w * 0.28, y0 - amp * (flip ? -1 : 1),
                                  w * 0.62, y0 + amp * (flip ? -1.2 : 1.2),
                                  w, y0 - amp * 0.6)
                ctx.lineTo(w, h)
                ctx.lineTo(0, h)
                ctx.closePath()
                ctx.fill()
            }
            wave(h * 0.30, h * 0.10, 0.13, false)
            wave(h * 0.42, h * 0.08, 0.06, true)
            var bottom = ctx.createLinearGradient(0, h * 0.75, 0, h)
            bottom.addColorStop(0, Qt.rgba(0, 0, 0, 0))
            bottom.addColorStop(1, Qt.rgba(accent.r, accent.g, accent.b, 0.07))
            ctx.fillStyle = bottom
            ctx.fillRect(0, h * 0.75, w, h * 0.25)
        }
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: Math.max(height, column.implicitHeight + 64)
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        onHeightChanged: returnToBounds()
        onContentHeightChanged: returnToBounds()
        ScrollBar.vertical: ScrollBar { policy: scroller.contentHeight > scroller.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

        ColumnLayout {
            id: column
            width: Math.min(scroller.width - 48, 1120)
            x: (scroller.width - width) / 2
            y: Math.max(page.compact ? 20 : 32, (scroller.height - implicitHeight) / 2)
            spacing: 0

            Image {
                Layout.alignment: Qt.AlignHCenter
                source: Qt.resolvedUrl("../../assets/reyos-browser-logo.png")
                sourceSize.width: page.compact ? 64 : 84
                sourceSize.height: page.compact ? 64 : 84
                Layout.preferredWidth: page.compact ? 64 : 84
                Layout.preferredHeight: page.compact ? 64 : 84
                mipmap: true
            }

            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: page.compact ? 8 : 14
                textFormat: Text.StyledText
                text: "Rey<font color=\"" + page.theme.accent + "\">va</font>"
                color: "#FFFFFF"
                font.pixelSize: page.width < 640 || page.compact ? 36 : 44
                font.weight: Font.Bold
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 6
                text: "Private by default"
                color: "#FFF3E6"
                font.pixelSize: 20
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 6
                Layout.maximumWidth: column.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: "Your browsing session is cleared when Reyva closes."
                color: "#BBA896"
                font.pixelSize: 14
            }

            Rectangle {
                id: searchBox
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: page.compact ? 20 : 28
                Layout.preferredWidth: Math.min(column.width, 760)
                implicitHeight: page.compact ? 52 : 58
                radius: 16
                color: Qt.rgba(page.theme.toolbar.r, page.theme.toolbar.g, page.theme.toolbar.b, 0.92)
                border.width: searchField.activeFocus ? 2 : 1
                border.color: searchField.activeFocus ? page.theme.accent
                                                      : Qt.rgba(page.theme.accent.r, page.theme.accent.g, page.theme.accent.b, 0.6)

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 7
                    spacing: 10
                    Image {
                        source: Qt.resolvedUrl("../../icons/reyos-search.svg")
                        sourceSize.width: 20
                        sourceSize.height: 20
                        opacity: 0.8
                    }
                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        // Steady cursor: a blinking one redraws the whole window twice a second.
                        cursorDelegate: Rectangle { width: 2; color: "#F0A96A"; visible: searchField.cursorVisible }
                        background: null
                        color: "#FFF3E6"
                        placeholderText: "Search the web, your tabs and bookmarks…"
                        placeholderTextColor: "#9F8873"
                        font.pixelSize: 16
                        selectByMouse: true
                        onTextChanged: page.refreshResults()
                        onAccepted: {
                            if (page.rowCount > 0) {
                                page.activate(page.highlighted)
                            }
                        }
                        Keys.onDownPressed: page.highlighted = Math.min(page.rowCount - 1, page.highlighted + 1)
                        Keys.onUpPressed: page.highlighted = Math.max(0, page.highlighted - 1)
                        Keys.onEscapePressed: {
                            text = ""
                            page.kind = "all"
                        }
                        Accessible.name: "Search the web, your open tabs, bookmarks and apps"
                        Accessible.description: "Up and Down pick a result, Enter opens it"
                    }
                    Button {
                        id: searchButton
                        implicitWidth: 52
                        implicitHeight: 44
                        focusPolicy: Qt.NoFocus
                        icon.source: Qt.resolvedUrl("../../icons/reyos-search.svg")
                        icon.width: 22
                        icon.height: 22
                        icon.color: "#FFFFFF"
                        background: Rectangle {
                            radius: 11
                            color: searchButton.down ? Qt.darker(page.theme.accent, 1.15)
                                 : (searchButton.hovered ? Qt.lighter(page.theme.accent, 1.08) : page.theme.accent)
                        }
                        onClicked: {
                            if (searchField.text.trim().length) {
                                page.searchRequested(searchField.text)
                                searchField.text = ""
                            }
                        }
                        Accessible.name: "Search the web"
                    }
                }
            }

            Row {
                id: kindChips
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 12
                spacing: 6
                Repeater {
                    model: [
                        { kind: "all", label: "All" },
                        { kind: "tab", label: "Open tabs" },
                        { kind: "bookmark", label: "Bookmarks" },
                        { kind: "app", label: "Web apps" }
                    ]
                    delegate: Button {
                        id: chip
                        required property var modelData
                        visible: modelData.kind !== "app" || page.appsAvailable
                        checkable: false
                        focusPolicy: Qt.NoFocus
                        implicitHeight: 30
                        leftPadding: 14
                        rightPadding: 14
                        readonly property bool selected: page.kind === modelData.kind
                        onClicked: {
                            page.kind = selected && modelData.kind !== "all" ? "all" : modelData.kind
                            searchField.forceActiveFocus()
                        }
                        contentItem: Text {
                            text: chip.modelData.label
                            color: chip.selected ? "#FFFFFF" : "#D7C1AA"
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            radius: 15
                            color: chip.selected ? page.theme.accent : (chip.hovered ? page.theme.hover : Qt.rgba(page.theme.raised.r, page.theme.raised.g, page.theme.raised.b, 0.72))
                            border.color: Qt.rgba(page.theme.border.r, page.theme.border.g, page.theme.border.b, 0.6)
                        }
                        Accessible.name: "Show " + modelData.label
                        Accessible.role: Accessible.RadioButton
                        Accessible.checked: selected
                    }
                }
            }

            // Results: replaces the shortcuts while you type or pick a kind.
            Rectangle {
                id: resultsBox
                visible: page.showingResults
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 12
                Layout.preferredWidth: Math.min(column.width, 760)
                implicitHeight: resultsColumn.implicitHeight + 12
                radius: 14
                color: Qt.rgba(page.theme.raised.r, page.theme.raised.g, page.theme.raised.b, 0.92)
                border.color: Qt.rgba(page.theme.border.r, page.theme.border.g, page.theme.border.b, 0.6)

                ColumnLayout {
                    id: resultsColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 6
                    spacing: 2

                    ResultRow {
                        visible: page.hasWebRow
                        Layout.fillWidth: true
                        theme: page.theme
                        kind: "web"
                        title: "Search " + page.searchEngine + " for “" + page.query + "”"
                        detail: "Only this goes to the search engine, not your tabs or bookmarks"
                        current: page.highlighted === 0
                        onClicked: page.activate(0)
                    }

                    Repeater {
                        model: page.results
                        delegate: ColumnLayout {
                            id: resultEntry
                            required property var modelData
                            required property int index
                            readonly property int row: index + (page.hasWebRow ? 1 : 0)
                            Layout.fillWidth: true
                            spacing: 2
                            Label {
                                visible: resultEntry.index === 0 || page.results[resultEntry.index - 1].kind !== resultEntry.modelData.kind
                                text: page.sectionTitle(resultEntry.modelData.kind).toUpperCase()
                                color: "#BBA896"
                                font.pixelSize: 10
                                font.bold: true
                                font.letterSpacing: 1
                                Layout.leftMargin: 10
                                Layout.topMargin: 6
                            }
                            ResultRow {
                                Layout.fillWidth: true
                                theme: page.theme
                                kind: resultEntry.modelData.kind
                                title: resultEntry.modelData.title
                                detail: resultEntry.modelData.detail || ""
                                iconUrl: resultEntry.modelData.icon || ""
                                sleepState: resultEntry.modelData.state || ""
                                alreadyOpen: resultEntry.modelData.open === true
                                current: page.highlighted === resultEntry.row
                                onClicked: page.activate(resultEntry.row)
                            }
                        }
                    }

                    Label {
                        visible: page.results.length === 0
                        text: page.kind === "tab" ? "No other open tabs" + (page.query.length ? " match" : "")
                            : page.kind === "bookmark" ? (page.query.length ? "No bookmarks match" : "No bookmarks yet. Add some with the star in the address bar, or import them from Settings.")
                            : page.kind === "app" ? (page.query.length ? "No web apps match" : "No web apps yet. On any site, open the menu and choose Install This Site as an App.")
                            : "No open tabs, bookmarks or apps match. Press Enter to search the web."
                        color: "#9F8873"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.margins: 10
                    }
                }
            }

            Flow {
                id: shortcutFlow
                visible: !page.showingResults
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: page.compact ? 20 : 30
                readonly property int tileWidth: 112
                readonly property int perRow: Math.max(1, Math.floor((column.width + spacing) / (tileWidth + spacing)))
                readonly property int tileCount: page.shortcuts.length + (page.shortcuts.length < page.maxShortcuts ? 1 : 0)
                Layout.preferredWidth: Math.min(tileCount, perRow) * (tileWidth + spacing) - spacing
                spacing: 14

                Repeater {
                    model: page.shortcuts
                    delegate: ShortcutTile {
                        required property var modelData
                        required property int index
                        theme: page.theme
                        title: modelData.title
                        url: modelData.url
                        onClicked: page.shortcutOpened(modelData.url)
                        onEditRequested: page.editShortcutRequested(index)
                        onRemoveRequested: page.removeShortcutRequested(index)
                    }
                }
                ShortcutTile {
                    visible: page.shortcuts.length < page.maxShortcuts
                    theme: page.theme
                    isAddTile: true
                    onClicked: page.addShortcutRequested()
                }
            }

            Label {
                visible: page.shortcuts.length === 0 && !page.showingResults
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 10
                text: "Add the sites you visit most. Shortcuts open in a normal private tab."
                color: "#9F8873"
                font.pixelSize: 13
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                Layout.maximumWidth: column.width
            }

            Rectangle {
                id: cards
                visible: !page.showingResults
                Layout.fillWidth: true
                Layout.topMargin: page.compact ? 24 : 44
                implicitHeight: cardGrid.implicitHeight + 8
                radius: 18
                color: Qt.rgba(page.theme.raised.r, page.theme.raised.g, page.theme.raised.b, 0.45)
                border.width: 1
                border.color: Qt.rgba(page.theme.border.r, page.theme.border.g, page.theme.border.b, 0.45)

                GridLayout {
                    id: cardGrid
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 4
                    columns: cards.width >= 900 ? 4 : (cards.width >= 520 ? 2 : 1)
                    rowSpacing: 0
                    columnSpacing: 0

                    PrivacyCard {
                        theme: page.theme
                        iconSource: Qt.resolvedUrl("../../icons/reyos-shield-outline.svg")
                        title: "Built for Privacy"
                        body: "No account. No tracking. No built-in VPN."
                    }
                    PrivacyCard {
                        theme: page.theme
                        iconSource: Qt.resolvedUrl("../../icons/reyos-clear.svg")
                        title: "Session Clears on Exit"
                        divider: cardGrid.columns > 1
                        body: "Tabs, history and temporary browsing data are removed when you close the browser."
                    }
                    PrivacyCard {
                        theme: page.theme
                        iconSource: Qt.resolvedUrl("../../icons/reyos-password.svg")
                        title: "Saved Passwords"
                        divider: cardGrid.columns === 4
                        body: "Optionally save login credentials for easier access."
                    }
                    PrivacyCard {
                        theme: page.theme
                        iconSource: Qt.resolvedUrl(!browserBackend.webAppsSupported ? "../../icons/reyos-shields.svg" : "../../icons/reyos-webapp.svg")
                        title: !browserBackend.webAppsSupported ? "Shields On" : "Web Apps"
                        divider: cardGrid.columns > 1
                        body: !browserBackend.webAppsSupported
                            ? "Trackers and ads are blocked on every site, with per-site exceptions."
                            : "Install selected sites as apps when you want a persistent login."
                    }
                }
            }
        }
    }
}
