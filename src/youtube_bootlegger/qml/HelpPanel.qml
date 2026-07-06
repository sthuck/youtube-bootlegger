import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    required property QtObject colors
    property bool open: false

    readonly property var help: backend.helpContent

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
        width: Math.min(parent.width - 48, 580)
        readonly property real paddedContentHeight: content.implicitHeight + 48
        readonly property real maxHeight: parent.height - 48
        height: Math.min(maxHeight, paddedContentHeight)
        color: root.colors.card
        radius: 14
        border.color: root.colors.border; border.width: 1

        MouseArea { anchors.fill: parent }

        ScrollView {
            id: contentScroll
            anchors { fill: parent; margins: 24 }
            clip: true
            ScrollBar.vertical.policy: card.paddedContentHeight > card.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                id: content
                width: card.width - 48
                spacing: 20

                Text {
                    text: help.title
                    color: root.colors.text
                    font { pixelSize: 18; weight: Font.Bold }
                }

                Text {
                    text: help.intro
                    color: root.colors.textSec
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: help.quickStartTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: help.quickStartIntro
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: help.steps
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 12
                        Layout.fillWidth: true

                        Rectangle {
                            width: 28; height: 28; radius: 14
                            color: root.colors.elevated
                            border.color: root.colors.border; border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: modelData.n
                                color: root.colors.accentLight
                                font { pixelSize: 13; weight: Font.Bold }
                            }
                        }
                        ColumnLayout {
                            spacing: 4
                            Layout.fillWidth: true
                            Text {
                                text: modelData.title
                                color: root.colors.text
                                font { pixelSize: 13; weight: Font.DemiBold }
                            }
                            Text {
                                text: modelData.body
                                color: root.colors.textSec
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                Text {
                    text: help.templateTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: help.templateIntro
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: help.templatePlaceholders
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 8
                        Layout.fillWidth: true
                        Layout.leftMargin: 8
                        Text { text: "•"; color: root.colors.accentLight; font.pixelSize: 13 }
                        Text {
                            text: modelData
                            color: root.colors.textSec
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }

                Repeater {
                    model: help.templateExamples
                    delegate: ColumnLayout {
                        required property var modelData
                        spacing: 4
                        Layout.fillWidth: true

                        Text {
                            text: modelData.label
                            color: root.colors.textMuted
                            font.pixelSize: 11
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: codeText.implicitHeight + 16
                            color: root.colors.inputBg
                            radius: root.colors.radiusSm
                            border.color: root.colors.border; border.width: 1
                            Text {
                                id: codeText
                                anchors { fill: parent; margins: 8 }
                                text: modelData.code
                                color: root.colors.text
                                font { pixelSize: 12; family: "monospace" }
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                Text {
                    text: help.templateNote
                    color: root.colors.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: help.aiTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: help.aiBody
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: help.outputTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: help.outputBody
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: help.requirementsTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Repeater {
                    model: help.requirements
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 8
                        Layout.fillWidth: true
                        Layout.leftMargin: 8
                        Text { text: "•"; color: root.colors.accentLight; font.pixelSize: 13 }
                        Text {
                            text: modelData
                            color: root.colors.textSec
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }

                Text {
                    text: help.troubleshootingTitle
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Repeater {
                    model: help.troubleshooting
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 8
                        Layout.fillWidth: true
                        Layout.leftMargin: 8
                        Text { text: "•"; color: root.colors.accentLight; font.pixelSize: 13 }
                        Text {
                            text: modelData
                            color: root.colors.textSec
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }

                Item { Layout.preferredHeight: 4 }

                Rectangle {
                    Layout.alignment: Qt.AlignRight
                    width: 84; height: 34; radius: root.colors.radiusSm
                    color: closeMA.containsMouse ? root.colors.accentHover : root.colors.accent
                    Behavior on color { ColorAnimation { duration: 120 } }
                    Text { anchors.centerIn: parent; text: "Close"; color: "white"; font { pixelSize: 13; weight: Font.DemiBold } }
                    MouseArea {
                        id: closeMA; anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.open = false
                    }
                }
            }
        }
    }
}
