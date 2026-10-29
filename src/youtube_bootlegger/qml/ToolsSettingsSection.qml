import QtQuick
import QtQuick.Layouts

/* Settings → Runtime tools: where each tool comes from, plus
   Download missing / Verify / Open folder. */
ColumnLayout {
    id: root
    required property QtObject colors
    readonly property QtObject tools: backend.tools

    spacing: 8

    Text {
        objectName: "toolsSectionTitle"
        text: root.tools.texts.sectionTitle
        color: root.colors.textMuted
        font.pixelSize: 12
    }

    // A count model keeps the rows (and their objectNames) when statuses
    // refresh; only their texts rebind.
    Repeater {
        objectName: "toolStatusList"
        model: root.tools.statuses.length
        delegate: ColumnLayout {
            id: statusRow
            required property int index
            readonly property var status: root.tools.statuses[index]
            Layout.fillWidth: true
            spacing: 1
            Text {
                text: statusRow.status.label
                color: root.colors.text
                font { pixelSize: 13; weight: Font.DemiBold }
            }
            Text {
                objectName: "toolStatus_" + statusRow.status.id
                text: statusRow.status.text
                color: root.colors.textSec
                font.pixelSize: 11
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
        }
    }

    Text {
        objectName: "toolsBlockedText"
        text: root.tools.startBlockedReason
        visible: text !== ""
        color: root.colors.warning
        font.pixelSize: 11
        wrapMode: Text.Wrap
        Layout.fillWidth: true
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        ToolsButton {
            name: "toolsDownloadButton"
            label: root.tools.texts.downloadMissing
            active: !root.tools.downloading
            onClicked: root.tools.downloadMissing()
        }
        ToolsButton {
            name: "toolsVerifyButton"
            label: root.tools.texts.verify
            active: !root.tools.downloading
            onClicked: root.tools.verify()
        }
        ToolsButton {
            name: "toolsOpenFolderButton"
            label: root.tools.texts.openFolder
            active: !root.tools.downloading && root.tools.canOpenFolder
            onClicked: root.tools.openFolder()
        }
    }

    component ToolsButton: Rectangle {
        id: button
        required property string name
        required property string label
        required property bool active
        signal clicked()

        Layout.preferredWidth: buttonText.implicitWidth + 24
        height: 30
        radius: root.colors.radiusSm
        opacity: active ? 1.0 : 0.4
        color: buttonMA.containsMouse && buttonMA.enabled ? root.colors.elevated : root.colors.surface
        border.color: root.colors.border; border.width: 1

        Text {
            id: buttonText
            anchors.centerIn: parent
            text: button.label
            color: root.colors.text
            font.pixelSize: 12
        }
        MouseArea {
            id: buttonMA
            objectName: button.name
            anchors.fill: parent
            enabled: button.active
            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: button.clicked()
        }
    }
}
