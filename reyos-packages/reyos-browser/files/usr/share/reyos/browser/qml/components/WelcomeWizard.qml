import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// First-run welcome: what Reyva keeps private, bringing bookmarks (and
// optionally passwords) from another browser, and the search engine. Every
// step can be skipped; it's shown once (settings.json onboardingCompleted)
// and again from Settings > Welcome tour. Imports use the same backend code
// as Bookmarks and Passwords.
Item {
    id: wizard
    property var theme
    property int step: 0
    property string bookmarkResult: ""
    property string passwordResult: ""
    readonly property int lastStep: 4
    visible: false
    signal closed()

    function open() {
        step = 0
        bookmarkResult = ""
        passwordResult = ""
        visible = true
        forceActiveFocus()
        // The New Tab page focuses its search box a moment after start-up;
        // take the keyboard back so Enter/Esc work here.
        Qt.callLater(function() { wizard.forceActiveFocus() })
    }

    function finish() {
        visible = false
        browserBackend.setOnboardingCompleted(true)
        closed()
    }

    Keys.onEscapePressed: finish()
    Keys.onReturnPressed: step < lastStep ? step++ : finish()

    Connections {
        target: browserBackend
        enabled: wizard.visible
        function onBookmarkImportFinished(count, message) { wizard.bookmarkResult = message }
        function onPasswordImportFinished(count, message) { wizard.passwordResult = message }
    }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.62)
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(wheel) { wheel.accepted = true } }
    }

    component Step: ColumnLayout {
        spacing: 12
        Layout.fillWidth: true
    }
    component Body: Label {
        color: "#D7C1AA"
        font.pixelSize: 14
        wrapMode: Text.Wrap
        Layout.fillWidth: true
    }
    component Heading: Label {
        color: "#FFF3E6"
        font.pixelSize: 22
        font.bold: true
        wrapMode: Text.Wrap
        Layout.fillWidth: true
    }
    component Action: Button {
        id: action
        property bool primary: false
        leftPadding: 16
        rightPadding: 16
        contentItem: Text {
            text: action.text
            color: action.enabled ? "#FFF3E6" : "#9F8873"
            font.pixelSize: 13
            font.bold: action.primary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitHeight: 36
            implicitWidth: 96
            radius: 8
            color: action.primary ? (action.hovered ? Qt.lighter(wizard.theme.accent, 1.08) : wizard.theme.accent)
                                  : (action.hovered ? wizard.theme.hover : wizard.theme.raised)
            border.color: wizard.theme.border
        }
    }

    Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(600, parent.width - 32)
        height: Math.min(cardColumn.implicitHeight + 48, parent.height - 32)
        radius: 16
        color: theme.raised
        border.color: theme.border

        Flickable {
            anchors.fill: parent
            anchors.margins: 24
            contentHeight: cardColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: cardColumn
                width: parent.width
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    Image {
                        source: Qt.resolvedUrl("../../assets/reyos-browser-logo.png")
                        sourceSize.width: 36
                        sourceSize.height: 36
                        Layout.preferredWidth: 36
                        Layout.preferredHeight: 36
                    }
                    Label {
                        text: "Step " + (wizard.step + 1) + " of " + (wizard.lastStep + 1)
                        color: "#BBA896"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignRight
                    }
                }

                Step {
                    visible: wizard.step === 0
                    Heading { text: "Welcome to Reyva" }
                    Body { text: "Reyva is private by default. A few things to know:" }
                    Body {
                        textFormat: Text.StyledText
                        text: "• <b>Your session is cleared when Reyva closes</b>: history, cookies and site data live in memory only.<br>"
                            + "• <b>Shields</b> block known ads and trackers on every site.<br>"
                            + "• <b>Saved passwords</b> go to your system's password wallet, never to us.<br>"
                            + "• <b>No account, no telemetry.</b> Reyva doesn't send anything about you anywhere.<br>"
                            + "• Sites you <b>install as apps</b> keep their own sign-in, in their own window."
                    }
                    Body { text: "The next steps bring your bookmarks over and pick a search engine. You can skip any of them."; color: "#BBA896"; font.pixelSize: 13 }
                }

                Step {
                    visible: wizard.step === 1
                    Heading { text: "Bring your bookmarks" }
                    Body { text: "Reyva can't read another browser's data directly. Save your bookmarks from it as an HTML file, then choose that file here." }
                    Body {
                        textFormat: Text.StyledText
                        font.pixelSize: 13
                        text: "<b>Chrome, Edge, Brave, Opera, Vivaldi:</b> Bookmarks → Bookmark manager → ⋮ → Export bookmarks.<br>"
                            + "<b>Firefox:</b> Bookmarks → Manage bookmarks → Import and Backup → Export Bookmarks to HTML.<br>"
                            + "<b>Safari:</b> File → Export → Bookmarks."
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Action { text: "Choose bookmark file…"; onClicked: browserBackend.chooseBookmarkImport() }
                        Item { Layout.fillWidth: true }
                    }
                    Body { visible: wizard.bookmarkResult.length > 0; text: wizard.bookmarkResult; color: "#F4D5A8" }
                }

                Step {
                    visible: wizard.step === 2
                    Heading { text: "Passwords (optional)" }
                    Body { text: "Most browsers can export saved passwords as a CSV file. Reyva puts them in your system's password wallet." }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: csvWarning.implicitHeight + 20
                        radius: 8
                        color: theme.base
                        border.color: theme.accent
                        Label {
                            id: csvWarning
                            anchors.fill: parent
                            anchors.margins: 10
                            text: "A password CSV isn't encrypted: anyone who opens it can read every password in it. After importing, delete the file and empty the Trash."
                            color: "#F4D5A8"
                            font.pixelSize: 13
                            wrapMode: Text.Wrap
                        }
                    }
                    Body {
                        visible: wizard.visible && wizard.step === 2 && browserBackend.passwordWalletMissing()
                        text: browserBackend.passwordWalletSetupNote()
                        color: "#F4D5A8"
                        font.pixelSize: 13
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Action { text: "Choose password CSV…"; onClicked: browserBackend.choosePasswordImport() }
                        Item { Layout.fillWidth: true }
                    }
                    Body { visible: wizard.passwordResult.length > 0; text: wizard.passwordResult; color: "#F4D5A8" }
                }

                Step {
                    visible: wizard.step === 3
                    Heading { text: "Search engine" }
                    Body { text: "Used for the address bar and the New Tab page. Neither tracks you, and you can change it in Settings." }
                    Repeater {
                        model: [
                            { name: "DuckDuckGo", about: "Private search with its own results." },
                            { name: "Startpage", about: "Google's results, without Google seeing you." }
                        ]
                        delegate: ColumnLayout {
                            id: engineChoice
                            required property var modelData
                            spacing: 0
                            RadioButton {
                                text: engineChoice.modelData.name
                                font.pixelSize: 14
                                checked: browserBackend.searchEngine === engineChoice.modelData.name
                                onClicked: browserBackend.setSearchEngine(engineChoice.modelData.name)
                            }
                            Label { text: engineChoice.modelData.about; color: "#BBA896"; font.pixelSize: 12; Layout.leftMargin: 30 }
                        }
                    }
                }

                Step {
                    visible: wizard.step === 4
                    Heading { text: "You're all set" }
                    Body {
                        textFormat: Text.StyledText
                        text: "• Type on the New Tab page to find an open tab, a bookmark or one of your web apps.<br>"
                            + "• <b>Ctrl+Shift+A</b> searches your open tabs from anywhere.<br>"
                            + "• Low Memory Mode puts tabs you haven't used for a while to sleep. Pin a tab to keep it running.<br>"
                            + "• Settings has tabs on the side, and an opt-in to reopen your tabs after a crash."
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Action { text: "Skip"; visible: wizard.step < wizard.lastStep; onClicked: wizard.finish() }
                    Item { Layout.fillWidth: true }
                    Action { text: "Back"; visible: wizard.step > 0; onClicked: wizard.step-- }
                    Action {
                        primary: true
                        text: wizard.step === wizard.lastStep ? "Start browsing" : "Next"
                        onClicked: wizard.step < wizard.lastStep ? wizard.step++ : wizard.finish()
                    }
                }
            }
        }
    }
}
