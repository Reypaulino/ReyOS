import QtQuick
import QtQuick.Controls as Controls

Controls.Page {
    // Real Kirigami.Page has a built-in `actions` list rendered into the
    // shell's global toolbar. This app's ApplicationWindow shim reads the
    // same property directly off the StackView's currentItem.
    property list<QtObject> actions: []
}
