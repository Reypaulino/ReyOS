import QtQuick

// QML `enum` blocks are exposed as static-like values on the type itself
// (MessageType.Positive), matching how Kirigami.MessageType.Positive reads
// at every call site -- no singleton/instantiation needed.
QtObject {
    enum Type { Information, Positive, Warning, Error }
}
