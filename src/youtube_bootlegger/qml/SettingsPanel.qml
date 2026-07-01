import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Item {
    id: root
    required property QtObject colors
    property bool open: false

    anchors.fill: parent
    visible: open
    z: 90

    Rectangle {
        anchors.fill: parent
        color: "#80000000"
        MouseArea { anchors.fill: parent; onClicked: root.open = false }
    }

    Rectangle {
        id: card
        anchors.centerIn: parent
        width: 460
        implicitHeight: content.implicitHeight + 48
        color: root.colors.card
        radius: 14
        border.color: root.colors.border; border.width: 1

        MouseArea { anchors.fill: parent }

        ColumnLayout {
            id: content
            anchors { fill: parent; margins: 24 }
            spacing: 16

            Text { text: "Settings"; color: root.colors.text; font { pixelSize: 18; weight: Font.Bold } }

            /* ── use external yt-dlp toggle ── */
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Rectangle {
                    width: 40; height: 22; radius: 11
                    color: backend.useExternalYtdlp ? root.colors.accent : root.colors.inputBg
                    border.color: root.colors.border; border.width: 1
                    Behavior on color { ColorAnimation { duration: 150 } }

                    Rectangle {
                        width: 18; height: 18; radius: 9
                        color: "white"
                        anchors.verticalCenter: parent.verticalCenter
                        x: backend.useExternalYtdlp ? parent.width - width - 2 : 2
                        Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setUseExternalYtdlp(!backend.useExternalYtdlp)
                    }
                }
                Text { text: "Use external yt-dlp executable"; color: root.colors.text; font.pixelSize: 13 }
            }

            /* ── yt-dlp path ── */
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                enabled: backend.useExternalYtdlp
                opacity: backend.useExternalYtdlp ? 1.0 : 0.4
                Behavior on opacity { NumberAnimation { duration: 150 } }

                Text { text: "yt-dlp path"; color: root.colors.textMuted; font.pixelSize: 12 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: ytdlpPathField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: ytdlpPathField.activeFocus ? 2 : 1
                        Behavior on border.color { ColorAnimation { duration: 150 } }
                        TextInput {
                            id: ytdlpPathField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.ytdlpPath
                            onEditingFinished: backend.setYtdlpPath(text)
                            Text {
                                anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                text: "Leave empty to use \"yt-dlp\" from PATH"
                                color: root.colors.textMuted; font.pixelSize: 12
                                visible: !ytdlpPathField.text && !ytdlpPathField.activeFocus
                            }
                        }
                    }
                    Rectangle {
                        width: 76; height: 36; radius: root.colors.radiusSm
                        color: ytdlpBrowseMA.containsMouse ? root.colors.elevated : root.colors.surface
                        border.color: root.colors.border; border.width: 1
                        Text { anchors.centerIn: parent; text: "Browse"; color: root.colors.text; font.pixelSize: 12 }
                        MouseArea {
                            id: ytdlpBrowseMA; anchors.fill: parent
                            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: ytdlpFileDialog.open()
                        }
                    }
                }
            }

            /* ── ffmpeg path ── */
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text { text: "ffmpeg path"; color: root.colors.textMuted; font.pixelSize: 12 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: ffmpegPathField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: ffmpegPathField.activeFocus ? 2 : 1
                        Behavior on border.color { ColorAnimation { duration: 150 } }
                        TextInput {
                            id: ffmpegPathField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.ffmpegPath
                            onEditingFinished: backend.setFfmpegPath(text)
                            Text {
                                anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                text: "Leave empty to use \"ffmpeg\" from PATH"
                                color: root.colors.textMuted; font.pixelSize: 12
                                visible: !ffmpegPathField.text && !ffmpegPathField.activeFocus
                            }
                        }
                    }
                    Rectangle {
                        width: 76; height: 36; radius: root.colors.radiusSm
                        color: ffmpegBrowseMA.containsMouse ? root.colors.elevated : root.colors.surface
                        border.color: root.colors.border; border.width: 1
                        Text { anchors.centerIn: parent; text: "Browse"; color: root.colors.text; font.pixelSize: 12 }
                        MouseArea {
                            id: ffmpegBrowseMA; anchors.fill: parent
                            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: ffmpegFileDialog.open()
                        }
                    }
                }

                Text {
                    text: backend.ffmpegMissing ? "FFmpeg not found at this location" : ""
                    color: root.colors.warning; font.pixelSize: 11
                    visible: backend.ffmpegMissing
                }
            }

            Item { Layout.preferredHeight: 4 }

            Rectangle {
                Layout.alignment: Qt.AlignRight
                width: 84; height: 34; radius: root.colors.radiusSm
                color: closeMA.containsMouse ? root.colors.accentHover : root.colors.accent
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "Done"; color: "white"; font { pixelSize: 13; weight: Font.DemiBold } }
                MouseArea {
                    id: closeMA; anchors.fill: parent
                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        ytdlpPathField.editingFinished()
                        ffmpegPathField.editingFinished()
                        root.open = false
                    }
                }
            }
        }
    }

    FileDialog {
        id: ytdlpFileDialog
        title: "Select yt-dlp executable"
        onAccepted: {
            var p = selectedFile.toString()
            if (p.startsWith("file://")) p = p.substring(7)
            ytdlpPathField.text = p
            backend.setYtdlpPath(p)
        }
    }

    FileDialog {
        id: ffmpegFileDialog
        title: "Select ffmpeg executable"
        onAccepted: {
            var p = selectedFile.toString()
            if (p.startsWith("file://")) p = p.substring(7)
            ffmpegPathField.text = p
            backend.setFfmpegPath(p)
        }
    }
}
