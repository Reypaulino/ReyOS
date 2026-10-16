import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// A short card at the top of the window that says what just changed
// ("Saved: ..."). Both apps' windows have one and expose notify(text):
// pages call applicationWindow().notify(...) after a setting changes.
// It closes by itself after a few seconds, or on a click.
Controls.Popup {
    id: popup
    property string message: ""
    property bool ok: true

    function show(text, success) {
        message = text
        ok = success === undefined ? true : success
        hideTimer.restart()
        open()
    }

    parent: Controls.Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Kirigami.Units.gridUnit * 3
    width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Math.max(Kirigami.Units.gridUnit * 16, row.implicitWidth + leftPadding + rightPadding))
    padding: Kirigami.Units.largeSpacing
    modal: false
    focus: false
    closePolicy: Controls.Popup.NoAutoClose

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Kirigami.Units.shortDuration } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Kirigami.Units.longDuration } }

    background: Rectangle {
        radius: Kirigami.Units.cornerRadius * 2
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: popup.ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
    }

    contentItem: RowLayout {
        id: row
        spacing: Kirigami.Units.largeSpacing
        Kirigami.Icon {
            source: popup.ok ? "dialog-ok-apply" : "dialog-warning"
            color: popup.ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
            Layout.alignment: Qt.AlignTop
        }
        Controls.Label {
            Layout.fillWidth: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 28
            text: popup.message
            wrapMode: Text.Wrap
        }
    }

    TapHandler { onTapped: popup.close() }
    Timer { id: hideTimer; interval: 4500; onTriggered: popup.close() }
}
