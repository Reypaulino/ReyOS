import QtQuick.Controls as Controls

Controls.Label {
    property int level: 1
    font.bold: true
    font.pixelSize: level <= 1 ? 26 : level === 2 ? 22 : level === 3 ? 18 : level === 4 ? 16 : 14
}
