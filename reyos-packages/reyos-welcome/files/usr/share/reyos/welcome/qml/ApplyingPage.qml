import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0

    // Whether to open Control Center's Updates page once branding finishes
    // — set by whichever DonePage button pushed this page.
    property bool openUpdatesAfter: false
    property bool handled: false

    background: Rectangle { color: ReyOSStyle.bg }

    function finish() {
        if (handled) return
        handled = true
        if (openUpdatesAfter) backend.openControlCenterUpdates()
        Qt.quit()
    }

    Connections {
        target: backend
        function onBrandingFinished(ok, message) { finish() }
    }

    Component.onCompleted: backend.startBranding()

    // Safety net — apply_panel_layout's own retry loops are bounded but can
    // legitimately take close to a minute; don't trap the user here forever
    // if something upstream genuinely hangs.
    Timer {
        interval: 120000
        running: true
        onTriggered: finish()
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Kirigami.Units.largeSpacing * 2
        width: parent.width * 0.7

        Controls.BusyIndicator {
            running: true
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 64
            Layout.preferredHeight: 64
        }

        Controls.Label {
            text: "Setting up your desktop…"
            font.pointSize: 20
            font.bold: true
            color: ReyOSStyle.text
            Layout.alignment: Qt.AlignHCenter
        }

        Controls.Label {
            text: "This only takes a moment."
            color: ReyOSStyle.text
            opacity: 0.8
            Layout.alignment: Qt.AlignHCenter
        }
    }
}
