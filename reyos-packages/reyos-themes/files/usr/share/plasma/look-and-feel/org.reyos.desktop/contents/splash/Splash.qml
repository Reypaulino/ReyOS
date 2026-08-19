import QtQuick 2.15
import QtQuick.Window 2.15

Rectangle {
    id: root
    color: "#0e0e12"

    // Required by Plasma's splash loader; we don't need per-stage behavior.
    property int stage

    Image {
        id: logo
        source: "images/watermark.png"
        anchors.centerIn: parent
        width: Math.min(root.width * 0.35, 480)
        fillMode: Image.PreserveAspectFit
    }

    Row {
        id: dots
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: logo.bottom
        anchors.topMargin: 36
        spacing: 12

        Repeater {
            model: 3
            delegate: Rectangle {
                width: 10
                height: 10
                radius: 5
                color: "#C97932"
                opacity: 0.3

                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    PauseAnimation { duration: index * 200 }
                    NumberAnimation { to: 1.0; duration: 400; easing.type: Easing.InOutQuad }
                    NumberAnimation { to: 0.3; duration: 400; easing.type: Easing.InOutQuad }
                }
            }
        }
    }
}
