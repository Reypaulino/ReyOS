import QtQuick
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// Small rounded status label. tone: "positive", "neutral", "negative", "accent" or "muted".
Rectangle {
    id: pill
    property string text: ""
    property string tone: "muted"
    readonly property color toneColor: tone === "positive" ? Kirigami.Theme.positiveTextColor
        : tone === "neutral" ? Kirigami.Theme.neutralTextColor
        : tone === "negative" ? Kirigami.Theme.negativeTextColor
        : tone === "accent" ? Kirigami.Theme.highlightColor
        : Kirigami.Theme.disabledTextColor

    implicitWidth: label.implicitWidth + Kirigami.Units.largeSpacing * 2
    implicitHeight: label.implicitHeight + Kirigami.Units.smallSpacing
    radius: height / 2
    color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.15)

    Controls.Label {
        id: label
        anchors.centerIn: parent
        text: pill.text
        color: pill.toneColor
        font.bold: true
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }
}
