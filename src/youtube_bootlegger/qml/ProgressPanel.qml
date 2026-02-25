import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property QtObject colors

    color: colors.card
    radius: colors.radius
    border.color: colors.border
    border.width: 1

    ColumnLayout {
        anchors { fill: parent; margins: 16 }
        spacing: 10

        /* ── progress bar ── */
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            RowLayout {
                Text {
                    text: backend.progressStage
                    color: {
                        if (backend.progressStage === "Complete!") return root.colors.success
                        if (backend.progressStage === "Error") return root.colors.error
                        return root.colors.text
                    }
                    font { pixelSize: 12; weight: Font.DemiBold }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: Math.round(backend.progressPercent) + "%"
                    color: root.colors.textSec; font.pixelSize: 11
                    visible: backend.busy || backend.progressPercent > 0
                }
            }

            Rectangle {
                Layout.fillWidth: true; height: 6
                radius: 3; color: root.colors.inputBg

                Rectangle {
                    width: parent.width * (backend.progressPercent / 100)
                    height: parent.height; radius: parent.radius
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: root.colors.accent }
                        GradientStop { position: 1; color: root.colors.accentLight }
                    }
                    Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                }
            }
        }

        /* ── status log ── */
        Text { text: "STATUS LOG"; color: root.colors.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.colors.inputBg
            radius: root.colors.radiusSm
            border.color: root.colors.border; border.width: 1
            clip: true

            ListView {
                id: logList
                anchors { fill: parent; margins: 8 }
                model: backend.statusLogModel
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds

                onCountChanged: {
                    if (count > 0) positionViewAtEnd()
                }

                delegate: Text {
                    required property string message
                    required property string level
                    required property string time
                    width: logList.width

                    text: "[" + time + "] " + message
                    color: {
                        if (level === "error") return root.colors.error
                        if (level === "warn")  return root.colors.warning
                        if (level === "debug") return root.colors.textMuted
                        return root.colors.textSec
                    }
                    font { pixelSize: 11; family: "monospace" }
                    wrapMode: Text.Wrap
                }

                Text {
                    anchors.centerIn: parent
                    visible: logList.count === 0
                    text: "Waiting for activity…"
                    color: root.colors.textMuted; font { pixelSize: 11; italic: true }
                }
            }
        }
    }
}
