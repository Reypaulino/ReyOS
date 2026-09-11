import QtQuick

// Kirigami.Icon resolves freedesktop icon-theme names. Qt's built-in
// "image://icontheme/" provider does the same lookup, no registration
// needed. Wrapped in a plain Item (not Image) because Image already has
// its own `source: url` property, and re-declaring it would collide with
// this component's `source: "icon-name"` string API used at every call site.
Item {
    id: root
    property string source: ""
    // Real Kirigami.Icon is `source: "name"`; Kirigami.PlaceholderMessage's
    // `icon` sub-property is a grouped `icon.name: "name"` instead -- both
    // spellings are used across this app's QML, so both resolve here.
    property alias name: root.source
    implicitWidth: img.sourceSize.width
    implicitHeight: img.sourceSize.height

    Image {
        id: img
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        smooth: true
        source: root.source.length ? ("image://icontheme/" + root.source) : ""
    }
}
