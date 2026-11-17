import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// First-run guided tour. A welcome card, then one step per part of the
// window: the rest of the window is dimmed, the part being explained is lit
// and outlined, and a bubble next to it says what it does. Bookmark and
// password import and the search engine choice happen inside the steps
// (same backend calls as Bookmarks, Passwords and Settings). Every step can
// be skipped; shown once (settings.json onboardingCompleted) and again from
// Settings > Welcome tour.
Item {
    id: tour
    property var theme
    // [{ target: Item or null, title, body, extra: "" | "search" | "import" }]
    property var steps: []
    property int step: 0
    property string bookmarkResult: ""
    property string passwordResult: ""
    readonly property var current: steps.length ? steps[Math.min(step, steps.length - 1)] : null
    readonly property bool lastStep: step >= steps.length - 1
    // Re-measured when the step or the window size changes.
    property rect hole: Qt.rect(0, 0, 0, 0)
    readonly property bool hasHole: hole.width > 0
    visible: false
    signal closed()

    function open() {
        step = 0
        bookmarkResult = ""
        passwordResult = ""
        visible = true
        measure()
        forceActiveFocus()
        // The New Tab page focuses its search box a moment after start-up;
        // take the keyboard back so Enter/Esc work here.
        Qt.callLater(function() { tour.forceActiveFocus(); tour.measure() })
    }

    function finish() {
        visible = false
        browserBackend.setOnboardingCompleted(true)
        closed()
    }

    function next() { if (lastStep) finish(); else { step++; measure() } }
    function back() { if (step > 0) { step--; measure() } }

    function measure() {
        var target = current ? current.target : null
        if (!target || !target.visible || target.width <= 0) {
            hole = Qt.rect(0, 0, 0, 0)
            return
        }
        var p = target.mapToItem(tour, 0, 0)
        var pad = 6
        hole = Qt.rect(p.x - pad, p.y - pad, target.width + 2 * pad, target.height + 2 * pad)
    }

    onWidthChanged: if (visible) measure()
    onHeightChanged: if (visible) measure()

    Keys.onEscapePressed: finish()
    Keys.onReturnPressed: next()
    Keys.onRightPressed: next()
    Keys.onLeftPressed: back()

    Connections {
        target: browserBackend
        enabled: tour.visible
        function onBookmarkImportFinished(count, message) { tour.bookmarkResult = message }
        function onPasswordImportFinished(count, message) { tour.passwordResult = message }
    }

    // Dim everything except the hole (four rectangles around it).
    readonly property color dim: Qt.rgba(0, 0, 0, 0.66)
    Rectangle { color: tour.dim; x: 0; y: 0; width: parent.width; height: tour.hasHole ? tour.hole.y : parent.height }
    Rectangle { visible: tour.hasHole; color: tour.dim; x: 0; y: tour.hole.y; width: tour.hole.x; height: tour.hole.height }
    Rectangle { visible: tour.hasHole; color: tour.dim; x: tour.hole.x + tour.hole.width; y: tour.hole.y; width: parent.width - x; height: tour.hole.height }
    Rectangle { visible: tour.hasHole; color: tour.dim; x: 0; y: tour.hole.y + tour.hole.height; width: parent.width; height: parent.height - y }
    Rectangle {
        visible: tour.hasHole
        x: tour.hole.x; y: tour.hole.y; width: tour.hole.width; height: tour.hole.height
        color: "transparent"
        radius: 10
        border.width: 2
        border.color: tour.theme.accent
    }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(wheel) { wheel.accepted = true } }

    component Body: Label {
        color: "#D7C1AA"
        font.pixelSize: 13
        wrapMode: Text.Wrap
        textFormat: Text.StyledText
        Layout.fillWidth: true
    }
    component Action: Button {
        id: action
        property bool primary: false
        leftPadding: 14
        rightPadding: 14
        focusPolicy: Qt.NoFocus
        contentItem: Text {
            text: action.text
            color: action.enabled ? "#FFF3E6" : "#9F8873"
            font.pixelSize: 13
            font.bold: action.primary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitHeight: 34
            implicitWidth: 80
            radius: 8
            color: action.primary ? (action.hovered ? Qt.lighter(tour.theme.accent, 1.08) : tour.theme.accent)
                                  : (action.hovered ? tour.theme.hover : tour.theme.raised)
            border.color: tour.theme.border
        }
    }

    // The bubble: under the lit part when there's room, else above it; the
    // welcome and the last step sit in the middle.
    Rectangle {
        id: bubble
        width: Math.min(tour.hasHole ? 420 : 520, tour.width - 32)
        height: bubbleColumn.implicitHeight + 36
        radius: 14
        color: tour.theme.raised
        border.color: tour.theme.accent
        readonly property bool below: tour.hole.y + tour.hole.height + 14 + height < tour.height - 8
        x: tour.hasHole ? Math.max(16, Math.min(tour.width - width - 16, tour.hole.x + tour.hole.width / 2 - width / 2)) : (tour.width - width) / 2
        y: tour.hasHole ? (below ? tour.hole.y + tour.hole.height + 14 : Math.max(8, tour.hole.y - height - 14)) : (tour.height - height) / 2

        // Little pointer towards the lit part.
        Rectangle {
            visible: tour.hasHole
            width: 14; height: 14; rotation: 45
            color: tour.theme.raised
            border.color: tour.theme.accent
            x: Math.max(18, Math.min(bubble.width - 32, tour.hole.x + tour.hole.width / 2 - bubble.x - 7))
            y: bubble.below ? -7 : bubble.height - 7
            z: -1
        }

        ColumnLayout {
            id: bubbleColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 18
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Image {
                    visible: !tour.hasHole
                    source: Qt.resolvedUrl("../../assets/reyos-browser-logo.png")
                    sourceSize.width: 32
                    sourceSize.height: 32
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                }
                Label {
                    text: tour.current ? tour.current.title : ""
                    color: "#FFF3E6"
                    font.pixelSize: tour.hasHole ? 17 : 21
                    font.bold: true
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                Label { text: (tour.step + 1) + " / " + tour.steps.length; color: "#BBA896"; font.pixelSize: 12 }
            }
            Body { text: tour.current ? tour.current.body : "" }

            // Search engine choice (address bar step).
            ColumnLayout {
                visible: tour.current !== null && tour.current.extra === "search"
                spacing: 2
                Repeater {
                    model: [
                        { name: "DuckDuckGo", about: "Private search with its own results." },
                        { name: "Startpage", about: "Google's results, without Google seeing you." }
                    ]
                    delegate: RowLayout {
                        id: engineChoice
                        required property var modelData
                        spacing: 4
                        RadioButton {
                            text: engineChoice.modelData.name
                            focusPolicy: Qt.NoFocus
                            checked: browserBackend.searchEngine === engineChoice.modelData.name
                            onClicked: browserBackend.setSearchEngine(engineChoice.modelData.name)
                        }
                        Label { text: engineChoice.modelData.about; color: "#BBA896"; font.pixelSize: 12 }
                    }
                }
            }

            // Bookmarks and passwords from another browser (menu step).
            ColumnLayout {
                visible: tour.current !== null && tour.current.extra === "import"
                spacing: 8
                Layout.fillWidth: true
                Body {
                    font.pixelSize: 12
                    text: "Save them from your old browser first:<br>"
                        + "<b>Chrome, Edge, Brave, Opera:</b> Bookmark manager → ⋮ → Export bookmarks.<br>"
                        + "<b>Firefox:</b> Manage bookmarks → Import and Backup → Export to HTML.<br>"
                        + "<b>Safari:</b> File → Export → Bookmarks."
                }
                RowLayout {
                    Layout.fillWidth: true
                    Action { text: "Import bookmarks…"; onClicked: browserBackend.chooseBookmarkImport() }
                    Action { text: "Import passwords…"; onClicked: browserBackend.choosePasswordImport() }
                    Item { Layout.fillWidth: true }
                }
                Body { visible: tour.bookmarkResult.length > 0; text: tour.bookmarkResult; color: "#F4D5A8" }
                Body { visible: tour.passwordResult.length > 0; text: tour.passwordResult; color: "#F4D5A8" }
                Body {
                    font.pixelSize: 12
                    color: "#F4D5A8"
                    text: "A password CSV file isn't encrypted: anyone who opens it can read every password. Delete it (and empty the Trash) after importing."
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 4
                Action { text: tour.step === 0 ? "Skip the tour" : "Skip"; visible: !tour.lastStep; onClicked: tour.finish() }
                Item { Layout.fillWidth: true }
                Action { text: "Back"; visible: tour.step > 0; onClicked: tour.back() }
                Action {
                    primary: true
                    text: tour.step === 0 ? "Show me around" : (tour.lastStep ? "Start browsing" : "Next")
                    onClicked: tour.next()
                }
            }
        }
    }
}
