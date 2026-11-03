import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Sidebar entry: 40px, solid accent when current; icon-only (with tooltip) when compact.
AbstractButton {
    id: root
    property string iconName: "box"
    property string label: ""
    property bool current: false
    property bool compact: false
    implicitHeight: 44
    Layout.fillWidth: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: label
    Accessible.role: Accessible.PageTab
    ToolTip.visible: compact && hovered
    ToolTip.text: label
    ToolTip.delay: 300

    background: Rectangle {
        radius: theme.radius
        color: root.current ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.15)
             : root.hovered ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.12) : "transparent"
        border.width: root.visualFocus ? 2 : 0
        border.color: root.current ? theme.onAccent : theme.accent
    }
    contentItem: RowLayout {
        spacing: 12
        Item { implicitWidth: 0 }
        Icon { name: root.iconName; size: 18; color: root.current ? theme.accent : theme.text }
        Label {
            visible: !root.compact
            text: root.label
            color: root.current ? theme.accent : theme.text
            font.pixelSize: 14
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
    }
    leftPadding: root.compact ? (width - 18) / 2 : 12
    rightPadding: 12
}
