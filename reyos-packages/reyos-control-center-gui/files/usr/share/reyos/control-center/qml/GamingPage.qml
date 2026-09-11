import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Gaming"

    property bool busy: false
    property bool steamInstalled: false
    property bool gamemodeInstalled: false

    function refreshStatus() {
        var status = backend.gamingStatus()
        steamInstalled = status.steamInstalled
        gamemodeInstalled = status.gamemodeInstalled
    }

    Component.onCompleted: refreshStatus()

    Connections {
        target: backend
        function onGamingProgress(line) {
            logArea.append(line)
        }
        function onGamingFinished(ok, message) {
            busy = false
            logArea.append(ok ? "\n✓ " + message : "\n✗ " + message)
            if (ok) refreshStatus()
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Steam & GameMode"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Installs Steam (with 32-bit compatibility libraries) and GameMode, which requests a temporary performance boost from the system while a game is running."
                }
                Controls.Label {
                    Layout.fillWidth: true
                    color: steamInstalled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                    text: "Steam: " + (steamInstalled ? "Installed" : "Not installed")
                }
                Controls.Label {
                    Layout.fillWidth: true
                    color: gamemodeInstalled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                    text: "GameMode: " + (gamemodeInstalled ? "Installed" : "Not installed")
                }
                Controls.Button {
                    text: (steamInstalled && gamemodeInstalled) ? "Reinstall / repair" : "Install"
                    highlighted: true
                    enabled: !busy
                    onClicked: { busy = true; logArea.text = ""; backend.installGaming() }
                }
            }
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: busy
            visible: busy
        }

        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            visible: logArea.text.length > 0
            Controls.TextArea {
                id: logArea
                readOnly: true
                wrapMode: TextEdit.Wrap
                font.family: "monospace"
                font.pointSize: 9
            }
        }
    }
}
