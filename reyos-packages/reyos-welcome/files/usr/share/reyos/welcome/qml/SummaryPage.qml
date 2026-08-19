import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0

    property var selectedApps: []

    background: Rectangle { color: ReyOSStyle.bg }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing * 2
        spacing: Kirigami.Units.largeSpacing

        Controls.Label {
                text: "Ready to install"
                font.pointSize: 20
                font.bold: true
                color: ReyOSStyle.text
            }

            Controls.Label {
                text: selectedApps.length > 0
                    ? "This will install:"
                    : "Nothing selected — you can skip this step."
                color: ReyOSStyle.text
                opacity: 0.8
            }

            Repeater {
                model: selectedApps
                delegate: Controls.Label {
                    required property var modelData
                    text: "• " + modelData.label
                    color: ReyOSStyle.accent
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                Controls.Button {
                    text: "Back"
                    onClicked: applicationWindow().pageStack.pop()
                }
                Item { Layout.fillWidth: true }
                Controls.Button {
                    text: selectedApps.length > 0 ? "Install" : "Finish"
                    highlighted: true
                    onClicked: applicationWindow().pageStack.push(Qt.resolvedUrl("InstallPage.qml"), { selectedApps: selectedApps })
                }
            }
    }
}
