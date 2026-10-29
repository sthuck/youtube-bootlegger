import QtQuick
import QtQuick.Layouts

/* Runtime-tools banner: download progress, Cancel/Retry/Download, or an error.
   Everything it shows comes from backend.tools (app_logic.runtime_tools). */
Rectangle {
    id: root
    required property QtObject colors
    readonly property QtObject tools: backend.tools

    visible: tools.bannerVisible
    implicitHeight: visible ? row.implicitHeight + 20 : 0
    color: tools.bannerIsError ? colors.errorBg : colors.elevated

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width; height: 1
        color: root.tools.bannerIsError ? root.colors.error : root.colors.border
    }

    RowLayout {
        id: row
        anchors {
            left: parent.left; right: parent.right
            verticalCenter: parent.verticalCenter
            leftMargin: 24; rightMargin: 24
        }
        spacing: 16

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                objectName: "toolsBannerText"
                text: root.tools.bannerText
                color: root.tools.bannerIsError ? root.colors.error : root.colors.text
                font.pixelSize: 13
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            /* progress bar; indeterminate while the size is unknown */
            Rectangle {
                id: track
                objectName: "toolsBannerProgress"
                property real value: root.tools.bannerProgress
                property bool indeterminate: value < 0
                visible: root.tools.downloading
                Layout.fillWidth: true
                height: 6; radius: 3
                color: root.colors.inputBg
                clip: true

                Rectangle {
                    visible: !track.indeterminate
                    width: track.width * Math.max(0, Math.min(1, track.value))
                    height: parent.height; radius: 3
                    color: root.colors.accent
                }

                Rectangle {
                    id: sweep
                    visible: track.indeterminate
                    width: track.width / 4
                    height: parent.height; radius: 3
                    color: root.colors.accentLight
                    NumberAnimation on x {
                        running: track.visible && track.indeterminate
                        loops: Animation.Infinite
                        from: -sweep.width; to: track.width
                        duration: 1200
                    }
                }
            }
        }

        Rectangle {
            visible: root.tools.bannerActionLabel !== ""
            Layout.preferredWidth: Math.max(88, actionText.implicitWidth + 28)
            Layout.preferredHeight: 32
            radius: root.colors.radiusSm
            color: actionMA.containsMouse ? root.colors.card : root.colors.surface
            border.color: root.tools.bannerIsError ? root.colors.error : root.colors.border
            border.width: 1

            Text {
                id: actionText
                objectName: "toolsBannerButtonText"
                anchors.centerIn: parent
                text: root.tools.bannerActionLabel
                color: root.colors.text
                font { pixelSize: 12; weight: Font.DemiBold }
            }
            MouseArea {
                id: actionMA
                objectName: "toolsBannerButton"
                anchors.fill: parent
                hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: root.tools.triggerBannerAction()
            }
        }
    }
}
