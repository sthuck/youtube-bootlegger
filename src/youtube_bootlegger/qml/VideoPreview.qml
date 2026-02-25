import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property QtObject colors

    implicitHeight: Math.max(previewRow.implicitHeight + 32, 140)
    color: colors.card
    radius: colors.radius
    border.color: colors.border
    border.width: 1

    RowLayout {
        id: previewRow
        anchors { fill: parent; margins: 16 }
        spacing: 16

        /* thumbnail */
        Rectangle {
            Layout.preferredWidth: 200
            Layout.preferredHeight: 112
            radius: 8
            color: colors.inputBg
            clip: true

            Image {
                id: thumb
                anchors.fill: parent
                source: backend.videoThumbnailUrl
                fillMode: Image.PreserveAspectCrop
                visible: status === Image.Ready
            }

            Text {
                anchors.centerIn: parent
                visible: !thumb.visible
                text: backend.videoLoading ? "Loading…" : (backend.videoLoaded ? "" : "")
                color: colors.textMuted
                font.pixelSize: 12
            }

            /* duration badge */
            Rectangle {
                visible: backend.videoLoaded && backend.videoDuration !== ""
                anchors { left: parent.left; bottom: parent.bottom; margins: 6 }
                width: durText.implicitWidth + 12; height: 20
                radius: 4; color: "#cc000000"
                Text {
                    id: durText; anchors.centerIn: parent
                    text: backend.videoDuration.replace("Duration: ", "")
                    color: "white"; font { pixelSize: 10; weight: Font.DemiBold }
                }
            }
        }

        /* details */
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 6

            Text {
                text: backend.videoTitle || ""
                color: backend.videoError ? root.colors.error : root.colors.text
                font { pixelSize: 14; weight: Font.Bold }
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                elide: Text.ElideRight
                maximumLineCount: 2
            }

            Text {
                text: backend.videoChannel
                color: root.colors.textSec
                font.pixelSize: 12
                visible: text !== ""
            }

            RowLayout {
                spacing: 12
                visible: backend.videoLoaded

                Repeater {
                    model: {
                        var items = []
                        if (backend.videoViews)  items.push(backend.videoViews)
                        if (backend.videoDate)   items.push(backend.videoDate)
                        return items
                    }

                    Rectangle {
                        required property string modelData
                        width: badgeText.implicitWidth + 16; height: 22
                        radius: 11; color: root.colors.elevated
                        Text {
                            id: badgeText; anchors.centerIn: parent
                            text: modelData
                            color: root.colors.textSec; font.pixelSize: 11
                        }
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }

    /* subtle loading shimmer */
    Rectangle {
        anchors.fill: parent; radius: parent.radius
        visible: backend.videoLoading
        color: "transparent"
        border.color: root.colors.accent; border.width: 1
        opacity: shimmerAnim.running ? 0.6 : 0
        SequentialAnimation on opacity {
            id: shimmerAnim
            running: backend.videoLoading; loops: Animation.Infinite
            NumberAnimation { to: 0.3; duration: 800 }
            NumberAnimation { to: 0.8; duration: 800 }
        }
    }
}
