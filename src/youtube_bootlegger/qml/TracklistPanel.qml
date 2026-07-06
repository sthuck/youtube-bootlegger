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
        spacing: 12

        /* ── template row ── */
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            RowLayout {
                spacing: 8
                Text { text: "TEMPLATE"; color: root.colors.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }
                Text { text: "Placeholders: %songname%, %hh%, %mm%, %ss%, %ignore:regex%"; color: root.colors.textMuted; font.pixelSize: 10 }
                Item { Layout.fillWidth: true }
            }

            Rectangle {
                Layout.fillWidth: true; height: 36
                color: root.colors.inputBg; radius: root.colors.radiusSm
                border.color: tplField.activeFocus ? root.colors.borderFocus
                              : (backend.templateError ? root.colors.warning : root.colors.border)
                border.width: tplField.activeFocus ? 2 : 1
                Behavior on border.color { ColorAnimation { duration: 150 } }
                TextInput {
                    id: tplField
                    anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                    verticalAlignment: Text.AlignVCenter
                    color: root.colors.text; font { pixelSize: 13; family: "monospace" }
                    clip: true
                    text: backend.currentTemplate
                    onTextChanged: if (text !== backend.currentTemplate) backend.setTemplate(text)
                }
            }

            Text {
                text: backend.templateError; color: root.colors.warning; font.pixelSize: 10
                visible: backend.templateError !== ""
                Layout.fillWidth: true; wrapMode: Text.Wrap
            }
        }

        /* ── track list label + AI ── */
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "TRACK LIST"; color: root.colors.textSec; font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 } }
            Item { Layout.fillWidth: true }

            Rectangle {
                width: 52; height: 28; radius: root.colors.radiusSm
                visible: !backend.aiAnalyzing
                enabled: backend.aiAvailable && !backend.busy
                opacity: enabled ? 1.0 : 0.45
                color: aiMA.containsMouse && enabled ? root.colors.accentHover : root.colors.accent
                Text { anchors.centerIn: parent; text: "AI"; color: "white"; font { pixelSize: 12; weight: Font.DemiBold } }
                MouseArea {
                    id: aiMA; anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (enabled) backend.analyzeTracklistWithAi()
                }
            }

            BusyIndicator {
                visible: backend.aiAnalyzing
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                running: backend.aiAnalyzing
            }
        }

        /* ── input + preview side by side ── */
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            /* tracklist text area – bordered container with ScrollView for wheel scrolling */
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 120
                Layout.minimumHeight: 80
                color: root.colors.inputBg
                radius: root.colors.radiusSm
                border.color: trackArea.activeFocus ? root.colors.borderFocus : root.colors.border
                border.width: trackArea.activeFocus ? 2 : 1
                clip: true
                Behavior on border.color { ColorAnimation { duration: 150 } }

                ScrollView {
                    id: trackScroll
                    anchors.fill: parent
                    anchors.margins: 1
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    ScrollBar.vertical.interactive: true

                    TextArea {
                        id: trackArea
                        color: root.colors.text
                        font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        selectionColor: root.colors.accent
                        padding: 10

                        placeholderText: "Enter one track per line matching your template.\n\nExample (with default template):\nOpening Number - 0:00\nSecond Song - 4:32\nThird Song - 8:15\nFinal Song - 12:47"
                        placeholderTextColor: root.colors.textMuted

                        onTextChanged: backend.setTracklistText(text)
                    }
                }
            }

            /* preview panel */
            ColumnLayout {
                Layout.fillHeight: true
                Layout.preferredWidth: 220
                Layout.minimumWidth: 160
                spacing: 6

                RowLayout {
                    spacing: 6
                    Text { text: "Preview"; color: root.colors.textSec; font { pixelSize: 11; weight: Font.DemiBold } }
                    Text {
                        text: backend.previewStatus
                        color: backend.previewValid ? root.colors.success : root.colors.error
                        font.pixelSize: 11; visible: text !== ""
                    }
                    Item { Layout.fillWidth: true }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: root.colors.inputBg
                    radius: root.colors.radiusSm
                    border.color: root.colors.border; border.width: 1
                    clip: true

                    ListView {
                        id: previewList
                        anchors { fill: parent; margins: 6 }
                        model: backend.trackPreviewModel
                        spacing: 3
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            interactive: true
                        }

                        delegate: Rectangle {
                            required property int trackIndex
                            required property string trackName
                            required property string timestamp
                            required property bool isValid
                            required property string trackError

                            width: previewList.width
                            height: 26
                            radius: 4
                            color: isValid ? root.colors.successBg : root.colors.errorBg

                            RowLayout {
                                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                spacing: 6

                                Text {
                                    text: (trackIndex < 10 ? "0" : "") + trackIndex + "."
                                    color: root.colors.textMuted; font.pixelSize: 10
                                    Layout.preferredWidth: 24
                                }
                                Text {
                                    text: timestamp
                                    color: isValid ? root.colors.success : root.colors.error
                                    font { pixelSize: 10; family: "monospace" }
                                    Layout.preferredWidth: 46
                                }
                                Text {
                                    text: trackName
                                    color: root.colors.text; font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            ToolTip.text: trackError
                            ToolTip.visible: trackError !== "" && trackMA.containsMouse
                            MouseArea {
                                id: trackMA
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: previewList.count === 0
                            text: "Enter tracks to see preview"
                            color: root.colors.textMuted; font { pixelSize: 12; italic: true }
                        }
                    }
                }
            }
        }
    }
}
