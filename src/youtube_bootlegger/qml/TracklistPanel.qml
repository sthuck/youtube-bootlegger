import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property QtObject colors
    signal openSettingsRequested()

    // The backend writes AI-found (or undone) track lists into the box.
    Connections {
        target: backend
        function onTracklistTextChanged() {
            if (trackArea.text !== backend.tracklistText) trackArea.text = backend.tracklistText
        }
    }

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
                Rectangle {
                    objectName: "templateSetByAi"
                    visible: backend.templateSetByAi
                    implicitWidth: setByAiText.implicitWidth + 14; implicitHeight: 18
                    radius: 9
                    color: root.colors.elevated
                    border.color: root.colors.accent; border.width: 1
                    Text {
                        id: setByAiText
                        objectName: "templateSetByAiText"
                        anchors.centerIn: parent
                        text: "✨ " + backend.findTexts.setByAi
                        color: root.colors.accentLight
                        font.pixelSize: 10
                    }
                }
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
                    objectName: "templateField"
                    anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                    verticalAlignment: Text.AlignVCenter
                    color: root.colors.text; font { pixelSize: 13; family: "monospace" }
                    clip: true
                    text: backend.currentTemplate
                    onTextChanged: if (text !== backend.currentTemplate) backend.setTemplate(text)
                }
            }

            Text {
                objectName: "templateErrorText"
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
                objectName: "aiButtonRect"
                width: aiButtonText.implicitWidth + 24; height: 28; radius: root.colors.radiusSm
                visible: !backend.aiAnalyzing
                enabled: backend.aiAvailable && !backend.busy
                opacity: enabled ? 1.0 : 0.45
                color: aiMA.containsMouse && enabled ? root.colors.accentHover : root.colors.accent
                Text {
                    id: aiButtonText
                    objectName: "aiButtonText"
                    anchors.centerIn: parent
                    text: "✨ " + backend.aiButtonLabel
                    color: "white"; font { pixelSize: 12; weight: Font.DemiBold }
                }
                MouseArea {
                    id: aiMA
                    objectName: "aiButton"
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (enabled) backend.analyzeTracklistWithAi()
                }
            }

            BusyIndicator {
                objectName: "aiBusyIndicator"
                visible: backend.aiAnalyzing
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                running: backend.aiAnalyzing
            }
        }

        /* ── track finder status: searching > banner > hint, one at a time ── */
        Rectangle {
            objectName: "findSearchingRow"
            Layout.fillWidth: true
            implicitHeight: 36
            visible: backend.findSearching
            radius: root.colors.radiusSm
            color: root.colors.elevated
            border.color: root.colors.border; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 10; rightMargin: 6 }
                spacing: 8
                BusyIndicator {
                    Layout.preferredWidth: 20; Layout.preferredHeight: 20
                    running: backend.findSearching
                }
                Text {
                    objectName: "findSearchingText"
                    text: backend.findTexts.searching
                    color: root.colors.text; font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Rectangle {
                    implicitWidth: stopText.implicitWidth + 20; implicitHeight: 24
                    radius: root.colors.radiusSm
                    color: stopMA.containsMouse ? root.colors.elevated : root.colors.surface
                    border.color: root.colors.border; border.width: 1
                    Text { id: stopText; anchors.centerIn: parent; text: backend.findTexts.stop; color: root.colors.text; font.pixelSize: 12 }
                    MouseArea {
                        id: stopMA
                        objectName: "findStopButton"
                        anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: backend.stopFind()
                    }
                }
            }
        }

        Rectangle {
            objectName: "findBannerRow"
            Layout.fillWidth: true
            implicitHeight: 36
            visible: !backend.findSearching && backend.findBanner !== ""
            radius: root.colors.radiusSm
            color: root.colors.elevated
            border.color: root.colors.accent; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 10; rightMargin: 6 }
                spacing: 8
                Text {
                    objectName: "findBannerText"
                    text: backend.findBanner
                    color: root.colors.text; font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Rectangle {
                    implicitWidth: undoText.implicitWidth + 20; implicitHeight: 24
                    radius: root.colors.radiusSm
                    color: undoMA.containsMouse ? root.colors.accentHover : root.colors.accent
                    Text { id: undoText; anchors.centerIn: parent; text: backend.findTexts.undo; color: "white"; font { pixelSize: 12; weight: Font.DemiBold } }
                    MouseArea {
                        id: undoMA
                        objectName: "findUndoButton"
                        anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: backend.undoFind()
                    }
                }
                Text {
                    text: "✕"; color: root.colors.textMuted; font.pixelSize: 13
                    Layout.preferredWidth: 20
                    horizontalAlignment: Text.AlignHCenter
                    MouseArea {
                        objectName: "findBannerDismiss"
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.dismissFindBanner()
                    }
                }
            }
        }

        Rectangle {
            objectName: "apiHintRow"
            Layout.fillWidth: true
            implicitHeight: hintLayout.implicitHeight + 12
            visible: !backend.findSearching && backend.findBanner === "" && backend.apiHintVisible
            radius: root.colors.radiusSm
            color: root.colors.surface
            border.color: root.colors.border; border.width: 1

            RowLayout {
                id: hintLayout
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 10; rightMargin: 6 }
                spacing: 8
                Text { text: "ⓘ"; color: root.colors.accentLight; font.pixelSize: 13 }
                Text {
                    objectName: "apiHintText"
                    text: backend.findTexts.apiHint
                    color: root.colors.textSec; font.pixelSize: 11
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                Rectangle {
                    implicitWidth: openSettingsText.implicitWidth + 20; implicitHeight: 24
                    radius: root.colors.radiusSm
                    color: openSettingsMA.containsMouse ? root.colors.elevated : root.colors.card
                    border.color: root.colors.border; border.width: 1
                    Text { id: openSettingsText; anchors.centerIn: parent; text: backend.findTexts.openSettings; color: root.colors.text; font.pixelSize: 12 }
                    MouseArea {
                        id: openSettingsMA
                        objectName: "apiHintOpenSettings"
                        anchors.fill: parent
                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.openSettingsRequested()
                    }
                }
                Text {
                    text: "✕"; color: root.colors.textMuted; font.pixelSize: 13
                    Layout.preferredWidth: 20
                    horizontalAlignment: Text.AlignHCenter
                    MouseArea {
                        objectName: "apiHintDismiss"
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.dismissApiHint()
                    }
                }
            }
        }

        /* ── input + preview side by side ── */
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            /* tracklist text area – Flickable + TextArea.flickable for reliable wheel scrolling */
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                Layout.minimumWidth: 120
                Layout.minimumHeight: 80
                color: root.colors.inputBg
                radius: root.colors.radiusSm
                border.color: trackArea.activeFocus ? root.colors.borderFocus : root.colors.border
                border.width: trackArea.activeFocus ? 2 : 1
                clip: true
                Behavior on border.color { ColorAnimation { duration: 150 } }

                Flickable {
                    id: trackFlickable
                    anchors.fill: parent
                    anchors.margins: 1
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        interactive: true
                    }

                    TextArea.flickable: TextArea {
                        id: trackArea
                        objectName: "tracklistArea"
                        color: root.colors.text
                        font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        selectionColor: root.colors.accent
                        padding: 10

                        placeholderText: "Enter one track per line matching your template.\n\nExample (with default template):\nOpening Number - 0:00\nSecond Song - 4:32\nThird Song - 8:15\nFinal Song - 12:47"
                        placeholderTextColor: root.colors.textMuted

                        background: Rectangle { color: "transparent" }

                        onTextChanged: backend.setTracklistText(text)
                    }

                    // TextArea consumes wheel events; explicit handler scrolls the Flickable
                    WheelHandler {
                        target: trackFlickable
                    }
                }
            }

            /* preview panel */
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                Layout.minimumWidth: 120
                spacing: 6

                RowLayout {
                    spacing: 6
                    Text { text: "Preview"; color: root.colors.textSec; font { pixelSize: 11; weight: Font.DemiBold } }
                    Text {
                        objectName: "previewStatusText"
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
                        objectName: "previewList"
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
