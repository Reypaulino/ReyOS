import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../kirishim" as Kirigami

Rectangle {
    id: card
    property var item
    signal resume()

    Layout.preferredWidth: 260
    Layout.preferredHeight: 170
    color: Kirigami.Theme.backgroundColor
    border.color: Qt.rgba(0, 0, 0, 0.25)
    border.width: 1
    radius: 8

    RowLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Image {
            Layout.preferredWidth: 90
            Layout.fillHeight: true
            fillMode: Image.PreserveAspectCrop
            source: item.cover_cache_path ? ("file://" + item.cover_cache_path) : ""
            asynchronous: true
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Kirigami.Units.smallSpacing

            Controls.Label {
                Layout.fillWidth: true
                text: item.title
                font.bold: true
                elide: Text.ElideRight
                wrapMode: Text.Wrap
                maximumLineCount: 2
            }
            Item { Layout.fillHeight: true }
            Controls.Label {
                text: Math.round(item.progress_percent) + "%"
                opacity: 0.7
            }
            Controls.ProgressBar {
                Layout.fillWidth: true
                from: 0; to: 100
                value: item.progress_percent
            }
            Controls.Button {
                Layout.fillWidth: true
                text: "Resume"
                onClicked: card.resume()
            }
        }
    }
}
