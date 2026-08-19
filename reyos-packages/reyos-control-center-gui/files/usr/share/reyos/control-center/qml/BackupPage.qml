import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Backup Center"

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
                Kirigami.Heading { text: "Protect your system"; level: 2 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Timeshift creates restore points for your system files. Your personal documents are not included, so keep those in a separate backup as well."
                }
                Controls.Button {
                    text: "Open Timeshift"
                    icon.name: "document-save"
                    highlighted: true
                    onClicked: backend.openTimeshift()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Recommended setup"; level: 3 }
                Controls.Label { text: "1. Choose a backup location with enough free space." }
                Controls.Label { text: "2. Create a first restore point before making major changes." }
                Controls.Label { text: "3. Enable a schedule only after confirming a restore point succeeds." }
            }
        }
    }
}
