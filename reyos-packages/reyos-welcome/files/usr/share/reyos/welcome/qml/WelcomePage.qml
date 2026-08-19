import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0
    background: Rectangle { color: ReyOSStyle.bg }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Kirigami.Units.largeSpacing * 2
        width: parent.width * 0.7

        Image {
            source: Qt.resolvedUrl("../assets/reyos-r-penguin-hq.png")
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 112
            Layout.preferredHeight: 112
        }

        Controls.Label {
            text: "ReyOS"
            font.pointSize: 24
            font.bold: true
            color: ReyOSStyle.text
            Layout.alignment: Qt.AlignHCenter
        }

        Controls.Label {
            text: "SIMPLE · SAFE · READY TO PLAY"
            font.letterSpacing: 2
            color: ReyOSStyle.accent
            Layout.alignment: Qt.AlignHCenter
        }

        Controls.Label {
            text: "Let's pick the software you want — takes about a minute."
            color: ReyOSStyle.text
            opacity: 0.8
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
        }

        Controls.Button {
            text: "Get Started"
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Kirigami.Units.largeSpacing
            highlighted: true
            onClicked: applicationWindow().pageStack.push(Qt.resolvedUrl("SoftwarePage.qml"))
        }

        Controls.Button {
            text: "Skip for now"
            flat: true
            Layout.alignment: Qt.AlignHCenter
            onClicked: Qt.quit()
        }
    }
}
