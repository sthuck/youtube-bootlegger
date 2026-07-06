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
        width: 520
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

            /* ── AI assistant ── */
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                Text {
                    text: "AI ASSISTANT"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }

                Text {
                    text: "Lite opens ChatGPT in your browser — no API key. Built-in providers send track list text and video title to the selected API using credentials stored locally."
                    color: root.colors.textMuted
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: [
                        { id: "chatgpt_lite", label: "Lite (ChatGPT)" },
                        { id: "openai", label: "OpenAI" },
                        { id: "anthropic", label: "Anthropic" },
                        { id: "vertex", label: "Google Gemini (API key)" },
                        { id: "openai_compatible", label: "OpenAI compatible" }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        height: 34
                        radius: root.colors.radiusSm
                        color: backend.llmProvider === modelData.id ? root.colors.elevated : root.colors.inputBg
                        border.color: backend.llmProvider === modelData.id ? root.colors.accent : root.colors.border
                        border.width: 1
                        Text {
                            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                            text: modelData.label
                            color: root.colors.text
                            font.pixelSize: 13
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.setLlmProvider(modelData.id)
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: backend.llmProvider === "openai"
                    opacity: visible ? 1.0 : 0.0

                    Text { text: "OpenAI API key"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: openaiKeyField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: openaiKeyField.activeFocus ? 2 : 1
                        TextInput {
                            id: openaiKeyField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            echoMode: TextInput.Password
                            text: backend.openaiApiKey
                            onEditingFinished: backend.setOpenaiApiKey(text)
                        }
                    }

                    Text { text: "Model"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: openaiModelField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: openaiModelField.activeFocus ? 2 : 1
                        TextInput {
                            id: openaiModelField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.openaiModel
                            onEditingFinished: backend.setOpenaiModel(text)
                            Text {
                                anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                text: "gpt-5.4-mini"
                                color: root.colors.textMuted; font.pixelSize: 12
                                visible: !openaiModelField.text && !openaiModelField.activeFocus
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: backend.llmProvider === "anthropic"
                    opacity: visible ? 1.0 : 0.0

                    Text { text: "Anthropic API key"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: anthropicKeyField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: anthropicKeyField.activeFocus ? 2 : 1
                        TextInput {
                            id: anthropicKeyField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            echoMode: TextInput.Password
                            text: backend.anthropicApiKey
                            onEditingFinished: backend.setAnthropicApiKey(text)
                        }
                    }

                    Text { text: "Model"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: anthropicModelField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: anthropicModelField.activeFocus ? 2 : 1
                        TextInput {
                            id: anthropicModelField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.anthropicModel
                            onEditingFinished: backend.setAnthropicModel(text)
                            Text {
                                anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                text: "claude-sonnet-5"
                                color: root.colors.textMuted; font.pixelSize: 12
                                visible: !anthropicModelField.text && !anthropicModelField.activeFocus
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: backend.llmProvider === "vertex"
                    opacity: visible ? 1.0 : 0.0

                    Text { text: "Google AI Studio API key"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: vertexKeyField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: vertexKeyField.activeFocus ? 2 : 1
                        TextInput {
                            id: vertexKeyField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            echoMode: TextInput.Password
                            text: backend.vertexApiKey
                            onEditingFinished: backend.setVertexApiKey(text)
                        }
                    }

                    Text { text: "Model"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: vertexModelField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: vertexModelField.activeFocus ? 2 : 1
                        TextInput {
                            id: vertexModelField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.vertexModel
                            onEditingFinished: backend.setVertexModel(text)
                            Text {
                                anchors.fill: parent; verticalAlignment: Text.AlignVCenter
                                text: "gemini-2.0-flash"
                                color: root.colors.textMuted; font.pixelSize: 12
                                visible: !vertexModelField.text && !vertexModelField.activeFocus
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: backend.llmProvider === "openai_compatible"
                    opacity: visible ? 1.0 : 0.0

                    Text { text: "Base URL"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: compatibleUrlField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: compatibleUrlField.activeFocus ? 2 : 1
                        TextInput {
                            id: compatibleUrlField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.compatibleBaseUrl
                            onEditingFinished: backend.setCompatibleBaseUrl(text)
                        }
                    }

                    Text { text: "Bearer token (optional)"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: compatibleTokenField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: compatibleTokenField.activeFocus ? 2 : 1
                        TextInput {
                            id: compatibleTokenField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            echoMode: TextInput.Password
                            text: backend.compatibleBearerToken
                            onEditingFinished: backend.setCompatibleBearerToken(text)
                        }
                    }

                    Text { text: "Model"; color: root.colors.textMuted; font.pixelSize: 12 }
                    Rectangle {
                        Layout.fillWidth: true; height: 36
                        color: root.colors.inputBg; radius: root.colors.radiusSm
                        border.color: compatibleModelField.activeFocus ? root.colors.borderFocus : root.colors.border
                        border.width: compatibleModelField.activeFocus ? 2 : 1
                        TextInput {
                            id: compatibleModelField
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            verticalAlignment: Text.AlignVCenter
                            color: root.colors.text; font.pixelSize: 13; clip: true
                            text: backend.compatibleModel
                            onEditingFinished: backend.setCompatibleModel(text)
                        }
                    }
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
                        openaiKeyField.editingFinished()
                        openaiModelField.editingFinished()
                        anthropicKeyField.editingFinished()
                        anthropicModelField.editingFinished()
                        vertexKeyField.editingFinished()
                        vertexModelField.editingFinished()
                        compatibleUrlField.editingFinished()
                        compatibleTokenField.editingFinished()
                        compatibleModelField.editingFinished()
                        root.open = false
                    }
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
