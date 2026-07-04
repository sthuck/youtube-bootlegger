import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

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
        width: Math.min(parent.width - 48, 580)
        height: Math.min(parent.height - 48, contentScroll.contentHeight + 48)
        color: root.colors.card
        radius: 14
        border.color: root.colors.border; border.width: 1

        MouseArea { anchors.fill: parent }

        ScrollView {
            id: contentScroll
            anchors { fill: parent; margins: 24 }
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                id: content
                width: card.width - 48
                spacing: 20

                Text {
                    text: "How to Use YouTube Bootlegger"
                    color: root.colors.text
                    font { pixelSize: 18; weight: Font.Bold }
                }

                Text {
                    text: "Download live performance audio from YouTube, split it into individual songs using timestamped track lists, and save tagged MP3 files."
                    color: root.colors.textSec
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: "QUICK START"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: "Follow these steps from top to bottom, left to right."
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: [
                        { n: "1", title: "Paste a YouTube URL",
                          body: "Enter a watch or youtu.be link in the URL field. The app fetches video info automatically and shows a preview with title, channel, duration, and thumbnail." },
                        { n: "2", title: "Set the track list template",
                          body: "Define how each line in your track list is formatted. The default template is %songname% - %mm%:%ss%. Adjust it if your timestamps or song names appear in a different order." },
                        { n: "3", title: "Enter the track list",
                          body: "Type one track per line, matching your template. The preview panel on the right validates each line — green rows are valid, red rows have errors (hover for details)." },
                        { n: "4", title: "Fill in metadata",
                          body: "Enter an artist name (required). Album is optional — if left blank, the video title is used when saving files." },
                        { n: "5", title: "Choose an output directory",
                          body: "Pick where to save files. Defaults to your Music folder. Songs are saved in a subfolder named Artist - Album." },
                        { n: "6", title: "Start Download & Split",
                          body: "The app downloads audio with yt-dlp, splits it at each timestamp with FFmpeg, and writes tagged MP3 files with cover art from the video thumbnail. Progress and status appear in the log panel." }
                    ]
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
                    text: "TRACK LIST TEMPLATES"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: "Each line in your track list must match the template. Available placeholders:"
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: [
                        "%songname% — song title (required)",
                        "%mm% — minutes (required)",
                        "%ss% — seconds as two digits (required in template)",
                        "%hh% — hours (only when timestamps include hours)",
                        "%ignore:regex% — skip a pattern, e.g. %ignore:\\d+\\.% for track numbers"
                    ]
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
                    model: [
                        { label: "Default template", code: "%songname% - %mm%:%ss%" },
                        { label: "Example track list", code: "Opening Number - 0:00\nSecond Song - 4:32\nThird Song - 8:15\nFinal Song - 12:47" },
                        { label: "Hour-long sets (template: %hh%:%mm%:%ss% - %songname%)", code: "0:00 - Intro\n1:23:45 - Long Song\n2:05:30 - Encore" },
                        { label: "Brackets around timestamps (template: [%mm%:%ss%] %songname%)", code: "[0:00] Opening Act\n[12:30] Main Set" }
                    ]
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
                    text: "When using %hh%:%mm%:%ss%, each line may use either hh:mm or hh:mm:ss. Only add %hh% when at least one timestamp has a real hour component — do not use it for mm:ss timestamps."
                    color: root.colors.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: "AI ASSIST"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: "Click the AI button next to the track list to auto-detect the best template, artist, and album from your raw track list and video title. Requires an LLM provider configured in Settings (gear icon). Track list text and video title are sent to the selected provider."
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: "OUTPUT"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Text {
                    text: "Files are saved as MP3s in a subfolder under your chosen output directory:\n\n  OutputDir / Artist - Album / 01 - Song Name.mp3\n\nEach file includes artist, album, title, and track number tags, plus cover art from the video thumbnail."
                    color: root.colors.text
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: "REQUIREMENTS"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Repeater {
                    model: [
                        "FFmpeg — required for splitting audio. Install it or set a custom path in Settings.",
                        "yt-dlp — bundled with the app. An external binary is optional in Settings.",
                        "LLM provider — optional, only needed for AI Assist."
                    ]
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
                    text: "TROUBLESHOOTING"
                    color: root.colors.textSec
                    font { pixelSize: 11; weight: Font.DemiBold; letterSpacing: 0.8 }
                }
                Repeater {
                    model: [
                        "FFmpeg not found — install FFmpeg or set its path in Settings.",
                        "Invalid URL — use a standard YouTube watch or youtu.be link.",
                        "Red preview rows — a line does not match the template. Check placeholders and timestamp format.",
                        "Cannot start — artist name is required. Fix any template or directory errors shown in red.",
                        "Cancel — use the Cancel button while a download or split is in progress."
                    ]
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
