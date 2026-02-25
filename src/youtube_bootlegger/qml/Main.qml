import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    width: 1120
    height: 780
    minimumWidth: 920
    minimumHeight: 660
    title: "YouTube Bootlegger"
    visible: true
    color: _c.bg

    /* ── colour tokens ─────────────────────────────────────── */
    QtObject {
        id: _c
        readonly property color bg:           "#0c0c14"
        readonly property color surface:      "#13131f"
        readonly property color card:         "#1a1a2e"
        readonly property color elevated:     "#242440"
        readonly property color inputBg:      "#10101c"
        readonly property color border:       "#252542"
        readonly property color borderFocus:  "#7c3aed"
        readonly property color accent:       "#7c3aed"
        readonly property color accentLight:  "#8b5cf6"
        readonly property color accentHover:  "#6d28d9"
        readonly property color text:         "#e2e8f0"
        readonly property color textSec:      "#94a3b8"
        readonly property color textMuted:    "#64748b"
        readonly property color success:      "#22c55e"
        readonly property color successBg:    "#0d2818"
        readonly property color error:        "#ef4444"
        readonly property color errorBg:      "#2d1111"
        readonly property color warning:      "#f59e0b"
        readonly property int   radius:       10
        readonly property int   radiusSm:     6
    }

    /* ── header bar ────────────────────────────────────────── */
    Rectangle {
        id: header
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 52
        color: _c.surface
        z: 10

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24; anchors.rightMargin: 24
            Text {
                text: "⚡ YouTube Bootlegger"
                color: _c.text
                font { pixelSize: 18; weight: Font.Bold; family: "Segoe UI, Helvetica, Arial, sans-serif" }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "QML Edition"
                color: _c.textMuted
                font.pixelSize: 12
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width; height: 1
            color: _c.border
        }
    }

    /* ── main content ──────────────────────────────────────── */
    RowLayout {
        anchors {
            top: header.bottom; left: parent.left
            right: parent.right; bottom: parent.bottom
            margins: 20
        }
        spacing: 20

        /* ═══ LEFT COLUMN ═══ */
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: 3
            spacing: 16

            /* ── URL input card ── */
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: urlCol.implicitHeight + 32
                color: _c.card; radius: _c.radius
                border.color: _c.border; border.width: 1

                ColumnLayout {
                    id: urlCol
                    anchors { fill: parent; margins: 16 }
                    spacing: 8

                    Text { text: "YouTube URL"; color: _c.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }

                    Rectangle {
                        Layout.fillWidth: true; height: 40
                        color: _c.inputBg; radius: _c.radiusSm
                        border.color: urlField.activeFocus ? _c.borderFocus : _c.border
                        border.width: urlField.activeFocus ? 2 : 1
                        Behavior on border.color { ColorAnimation { duration: 150 } }

                        TextInput {
                            id: urlField
                            anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                            verticalAlignment: Text.AlignVCenter
                            color: _c.text; selectionColor: _c.accent
                            font.pixelSize: 14; clip: true
                            onTextChanged: backend.setUrl(text)

                            Text {
                                anchors { fill: parent; leftMargin: 0 }
                                verticalAlignment: Text.AlignVCenter
                                text: "https://www.youtube.com/watch?v=… or https://youtu.be/…"
                                color: _c.textMuted; font.pixelSize: 14
                                visible: !urlField.text && !urlField.activeFocus
                            }
                        }
                    }

                    Text {
                        text: backend.urlError
                        color: _c.error; font.pixelSize: 11
                        visible: backend.urlError !== ""
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }
            }

            /* ── Video preview ── */
            VideoPreview {
                Layout.fillWidth: true
                colors: _c
            }

            /* ── Tracklist panel ── */
            TracklistPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                colors: _c
            }
        }

        /* ═══ RIGHT COLUMN ═══ */
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: 2
            spacing: 16

            /* ── Metadata card ── */
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: metaCol.implicitHeight + 32
                color: _c.card; radius: _c.radius
                border.color: _c.border; border.width: 1

                ColumnLayout {
                    id: metaCol
                    anchors { fill: parent; margins: 16 }
                    spacing: 10

                    Text { text: "METADATA"; color: _c.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }

                    ColumnLayout {
                        spacing: 4
                        Layout.fillWidth: true
                        Text { text: "Artist"; color: _c.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: _c.inputBg; radius: _c.radiusSm
                            border.color: artistField.activeFocus ? _c.borderFocus : _c.border
                            border.width: artistField.activeFocus ? 2 : 1
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                            TextInput {
                                id: artistField
                                anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                                verticalAlignment: Text.AlignVCenter
                                color: _c.text; font.pixelSize: 13; clip: true
                                onTextChanged: backend.setArtist(text)
                                Text {
                                    anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                    text: "Enter artist name"; color: _c.textMuted; font.pixelSize: 13
                                    visible: !artistField.text && !artistField.activeFocus
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 4
                        Layout.fillWidth: true
                        Text { text: "Album"; color: _c.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: _c.inputBg; radius: _c.radiusSm
                            border.color: albumField.activeFocus ? _c.borderFocus : _c.border
                            border.width: albumField.activeFocus ? 2 : 1
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                            TextInput {
                                id: albumField
                                anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                                verticalAlignment: Text.AlignVCenter
                                color: _c.text; font.pixelSize: 13; clip: true
                                onTextChanged: backend.setAlbum(text)
                                Text {
                                    anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                    text: backend.albumPlaceholder; color: _c.textMuted; font.pixelSize: 13
                                    visible: !albumField.text && !albumField.activeFocus
                                }
                            }
                        }
                    }
                }
            }

            /* ── Output directory card ── */
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: dirCol.implicitHeight + 32
                color: _c.card; radius: _c.radius
                border.color: _c.border; border.width: 1

                ColumnLayout {
                    id: dirCol
                    anchors { fill: parent; margins: 16 }
                    spacing: 8

                    Text { text: "OUTPUT DIRECTORY"; color: _c.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: _c.inputBg; radius: _c.radiusSm
                            border.color: dirField.activeFocus ? _c.borderFocus : _c.border
                            border.width: dirField.activeFocus ? 2 : 1
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                            TextInput {
                                id: dirField
                                anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                                verticalAlignment: Text.AlignVCenter
                                color: _c.text; font.pixelSize: 13; clip: true
                                text: backend.outputDir
                                onTextChanged: backend.setOutputDir(text)
                            }
                        }
                        Rectangle {
                            width: 80; height: 38
                            radius: _c.radiusSm
                            color: browseMA.containsMouse ? _c.elevated : _c.surface
                            border.color: _c.border; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Text { anchors.centerIn: parent; text: "Browse"; color: _c.text; font.pixelSize: 12 }
                            MouseArea {
                                id: browseMA; anchors.fill: parent
                                hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: folderDialog.open()
                            }
                        }
                    }

                    Text {
                        text: backend.dirError; color: _c.error; font.pixelSize: 11
                        visible: backend.dirError !== ""; wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }
            }

            /* ── Progress panel ── */
            ProgressPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                colors: _c
            }

            /* ── Action buttons ── */
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Rectangle {
                    Layout.fillWidth: true; height: 44
                    radius: _c.radiusSm
                    opacity: backend.busy ? 0.5 : 1.0
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: startMA.containsMouse && !backend.busy ? _c.accentHover : _c.accent }
                        GradientStop { position: 1; color: _c.accentLight }
                    }
                    Behavior on opacity { NumberAnimation { duration: 200 } }

                    Text {
                        anchors.centerIn: parent
                        text: "Start Download & Split"
                        color: "white"
                        font { pixelSize: 14; weight: Font.DemiBold }
                    }
                    MouseArea {
                        id: startMA; anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        enabled: !backend.busy
                        onClicked: backend.startPipeline()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true; height: 38
                    radius: _c.radiusSm
                    color: "transparent"
                    border.color: backend.busy ? _c.error : _c.border
                    border.width: 1
                    opacity: backend.busy ? 1.0 : 0.4
                    Behavior on opacity { NumberAnimation { duration: 200 } }

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: backend.busy ? _c.error : _c.textMuted
                        font.pixelSize: 13
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        enabled: backend.busy
                        onClicked: backend.cancelPipeline()
                    }
                }
            }
        }
    }

    /* ── folder dialog ─────────────────────────────────────── */
    FolderDialog {
        id: folderDialog
        title: "Select Output Directory"
        onAccepted: {
            var p = selectedFolder.toString()
            if (p.startsWith("file://")) p = p.substring(7)
            dirField.text = p
            backend.setOutputDir(p)
        }
    }

    /* ── toast / message overlay ───────────────────────────── */
    Connections {
        target: backend
        function onShowMessage(title, message, isError) {
            msgTitle.text = title
            msgBody.text = message
            msgStrip.color = isError ? _c.error : _c.success
            msgOverlay.visible = true
        }
    }

    Rectangle {
        id: msgOverlay; visible: false; z: 100
        anchors.fill: parent; color: "#80000000"

        MouseArea { anchors.fill: parent; onClicked: msgOverlay.visible = false }

        Rectangle {
            anchors.centerIn: parent
            width: 400; height: msgContent.implicitHeight + 48
            color: _c.card; radius: 14
            border.color: _c.border; border.width: 1

            Rectangle { id: msgStrip; width: 4; height: parent.height; radius: 2; anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; color: _c.success }

            ColumnLayout {
                id: msgContent
                anchors { fill: parent; margins: 24; leftMargin: 28 }
                spacing: 8

                Text { id: msgTitle; color: _c.text; font { pixelSize: 16; weight: Font.Bold } }
                Text { id: msgBody; color: _c.textSec; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Item { Layout.fillHeight: true }
                Rectangle {
                    Layout.alignment: Qt.AlignRight
                    width: 72; height: 32; radius: 6
                    color: closeBtnMA.containsMouse ? _c.elevated : _c.surface
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text { anchors.centerIn: parent; text: "OK"; color: _c.text; font { pixelSize: 12; weight: Font.DemiBold } }
                    MouseArea { id: closeBtnMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: msgOverlay.visible = false }
                }
            }
        }
    }

    /* ── ffmpeg warning on startup ─────────────────────────── */
    Component.onCompleted: {
        if (backend.ffmpegMissing) {
            msgTitle.text = "FFmpeg Not Found"
            msgBody.text = "FFmpeg is not installed or not in your PATH.\nPlease install FFmpeg to use this application."
            msgStrip.color = _c.warning
            msgOverlay.visible = true
        }
    }
}
