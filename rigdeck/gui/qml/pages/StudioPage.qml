import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import RigDeck

PageScroll {
    id: page
    property bool shown: true
    readonly property var d: screenStudio.draft
    readonly property var cool: typeof cooler !== "undefined" ? cooler : null
    readonly property bool uploading: cool !== null && cool.busy !== ""
    property int liveTick: 0
    readonly property bool portfolioMode: page.d.preset === "Projects" || page.d.preset === "Live projects" || page.d.preset === "Tank"
    readonly property bool tankMode: page.d.preset === "Tank"
    readonly property bool liveMode: page.d.preset === "Live projects"
    // A built snapshot replaces the live canvas so the clip itself is what gets reviewed.
    readonly property bool showLive: page.liveMode && !screenStudio.ready
    Timer { interval: appState.reduceMotion ? 1000 : 40; running: page.shown && page.showLive && !screenStudio.busy; repeat: true; onTriggered: page.liveTick++ }
    PageHeader {
        title: "Screen Studio"
        subtitle: "A little screen. Entirely yours."
        status: page.cool && page.cool.connected ? "WATERFORCE connected" : "Offline editor"
        tone: page.cool && page.cool.connected ? theme.live : theme.muted
    }
    GridLayout {
        Layout.fillWidth: true
        columns: page.pageWidth > 820 ? 2 : 1
        columnSpacing: 24; rowSpacing: 20
        Panel {
            Layout.fillWidth: true
            Layout.preferredWidth: 420
            Layout.alignment: Qt.AlignTop
            title: "The canvas"; subtitle: "320 × 320 · circular LCD"
            Item {
                Layout.fillWidth: true; implicitHeight: Math.min(width, 380) + 16
                Rectangle {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 12, 350); height: width; radius: width / 2
                    color: (screenStudio.preview || page.showLive) ? theme.panel : "#070c12"; border.color: theme.border; border.width: (screenStudio.preview || page.showLive) ? 0 : 6
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 12
                        radius: width / 2; color: "transparent"; border.color: theme.accent; opacity: 0.35; visible: !screenStudio.preview && !page.showLive
                    }
                    Item {
                        anchors.fill: parent; anchors.margins: 18
                        AnimatedImage {
                            id: animation
                            anchors.fill: parent; source: screenStudio.preview
                            playing: page.shown && !appState.reduceMotion && !screenStudio.busy
                            visible: !appState.reduceMotion && !page.showLive; cache: false
                        }
                        Image { id: poster; anchors.fill: parent; source: screenStudio.poster; visible: appState.reduceMotion && !page.showLive }
                        Image { anchors.fill: parent; source: page.showLive ? "image://studio/"+(appState.reduceMotion ? "still/" : "live/")+page.liveTick : ""; visible: page.showLive; cache: false }
                        Canvas {
                            anchors.fill: parent
                            Connections { target: theme; function onChanged() { parent.requestPaint() } }
                            onWidthChanged: requestPaint()
                            onHeightChanged: requestPaint()
                            onPaint: {
                                const c = getContext("2d"); c.reset()
                                c.fillStyle = theme.panel
                                c.beginPath(); c.rect(0, 0, width, height)
                                c.arc(width/2, height/2, width/2, 0, 2*Math.PI, true)
                                c.fill()
                            }
                        }
                        Column {
                            anchors.centerIn: parent; spacing: 12; visible: screenStudio.preview === "" && !page.showLive
                            Label { anchors.horizontalCenter: parent.horizontalCenter; text: "YOUR NEXT\nSIGNATURE"; horizontalAlignment: Text.AlignHCenter; color: "#edf5fc"; font.pixelSize: 25; font.bold: true }
                            Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Create a preview to begin"; color: "#a0b4c8"; font.pixelSize: 12 }
                        }
                    }
                }
            }
            Label {
                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                text: screenStudio.busy ? (screenStudio.note !== "" ? screenStudio.note : "Rendering your design…")
                      : screenStudio.ready ? (page.liveMode ? "Snapshot ready. These numbers stay on the cooler until you send a new one." : "Preview ready · review before sending")
                      : page.liveMode ? screenStudio.liveStatus
                      : screenStudio.preview ? "Design changed · rebuild the preview" : "Your current cooler screen stays unchanged"
                color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                Button { objectName: "renderButton"; text: screenStudio.busy ? "Rendering…" : "Build preview"; highlighted: true; enabled: !screenStudio.busy && !page.uploading; onClicked: screenStudio.render() }
                Button {
                    text: "Send to cooler"
                    enabled: screenStudio.ready && !screenStudio.busy && page.cool && page.cool.connected && !page.uploading
                    onClicked: page.cool.uploadStudio(screenStudio.output)
                    ToolTip.visible: hovered
                    ToolTip.text: "Play only this design; keep older files stored"
                }
                Button { visible: page.liveMode && screenStudio.ready; text: "Back to live"; enabled: !screenStudio.busy; onClicked: screenStudio.clearPreview() }
            }
            Label { Layout.fillWidth: true; visible: page.uploading; text: page.cool ? page.cool.busy : ""; color: theme.accent; wrapMode: Text.WordWrap }
            Banner { visible: screenStudio.error !== ""; tone: "error"; text: screenStudio.error }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.preferredWidth: 450; Layout.alignment: Qt.AlignTop; spacing: 16
            Panel {
                title: "Make it yours"; subtitle: "Type, colour, movement and depth"
                Layout.fillWidth: true
                enabled: !screenStudio.busy && !page.uploading
                Label { text: "Design"; color: theme.muted }
                ComboBox {
                    objectName: "presetPicker"; Layout.fillWidth: true; model: ["Signature", "Traffic", "Projects", "Live projects", "Tank"]
                    currentIndex: model.indexOf(page.d.preset)
                    Accessible.name: "Design preset"
                    onActivated: screenStudio.edit("preset", currentText)
                }
                Label { text: "Headline"; color: theme.muted; visible: page.d.preset === "Signature" }
                TextField {
                    objectName: "headlineInput"; Layout.fillWidth: true; text: page.d.text; maximumLength: 64
                    visible: page.d.preset === "Signature"; Accessible.name: "Headline"
                    onTextEdited: screenStudio.edit("text", text)
                }
                TextField {
                    Layout.fillWidth: true; text: page.d.subtitle; maximumLength: 80; placeholderText: "Supporting text"
                    visible: page.d.preset === "Signature"; Accessible.name: "Supporting text"
                    onTextEdited: screenStudio.edit("subtitle", text)
                }
                ComboBox {
                    Layout.fillWidth: true; model: screenStudio.fonts; currentIndex: screenStudio.fonts.indexOf(page.d.font)
                    visible: page.d.preset === "Signature"; Accessible.name: "Typeface"
                    onActivated: screenStudio.edit("font", currentText)
                }
                RowLayout {
                    visible: page.d.preset === "Signature"
                    Label { text: "Size"; color: theme.muted }
                    SpinBox { from: 12; to: 48; value: page.d.size; Accessible.name: "Text size"; onValueModified: screenStudio.edit("size", value) }
                    Label { text: "Position"; color: theme.muted }
                    SpinBox { from: 60; to: 240; value: page.d.y; Accessible.name: "Vertical text position"; onValueModified: screenStudio.edit("y", value) }
                }
                RowLayout {
                    visible: !page.portfolioMode
                    Layout.fillWidth: true
                    Button { text: "Accent colour"; onClicked: { colors.selectedColor = page.d.color; colors.open() } }
                    Rectangle { width: 26; height: 26; radius: 13; color: page.d.color; border.color: theme.border }
                    Button { text: "Background"; onClicked: { backgroundColor.selectedColor = page.d.background; backgroundColor.open() } }
                }
                RowLayout {
                    Layout.fillWidth: true
                    ComboBox { visible: !page.liveMode; Layout.fillWidth: true; model: ["Orbit", "Pulse", "Still"]; currentIndex: model.indexOf(page.d.effect); Accessible.name: "Animation effect"; onActivated: screenStudio.edit("effect", currentText) }
                    CheckBox { visible: page.liveMode; Layout.fillWidth: true; text: "Replay minute history"; checked: page.d.effect !== "Still"; onToggled: screenStudio.edit("effect", checked ? "Orbit" : "Still") }
                    SpinBox { from: 3; to: 12; value: page.d.duration; Accessible.name: page.liveMode ? "Seconds per site" : "Clip duration in seconds"; onValueModified: screenStudio.edit("duration", value) }
                    Label { text: page.liveMode ? "sec / site" : "sec"; color: theme.muted }
                }
                RowLayout {
                    visible: !page.portfolioMode
                    Button { text: "Choose logo"; onClicked: logoFile.open() }
                    Button { text: "Clear logo"; enabled: page.d.logo !== ""; onClicked: screenStudio.edit("logo", "") }
                }
                Label { visible: !page.portfolioMode; Layout.fillWidth: true; text: page.d.logo ? page.d.logo.split("/").pop() : "PNG, WebP, JPEG or SVG"; color: theme.muted; font.pixelSize: 12; elide: Text.ElideMiddle }
                RowLayout {
                    visible: !page.portfolioMode
                    Button { text: "Photo / video"; onClicked: mediaFile.open() }
                    Button { text: "Clear media"; enabled: page.d.media !== ""; onClicked: screenStudio.edit("media", "") }
                }
                Label { visible: !page.portfolioMode; Layout.fillWidth: true; text: page.d.media ? page.d.media.split("/").pop() : "Centre-cropped to fit the circular screen"; color: theme.muted; font.pixelSize: 12; elide: Text.ElideMiddle }
            }
            Panel {
                Layout.fillWidth: true; visible: page.d.preset !== "Signature"
                title: page.tankMode ? "The tank" : page.d.preset === "Traffic" ? "MacDigital · search pulse" : "Your project rotation"
                subtitle: page.tankMode ? "One site's Google numbers, surfacing one by one." : page.liveMode ? "See when traffic arrived and how it was served." : "Real numbers. A cinematic presentation."
                Label { Layout.fillWidth: true; visible: !page.tankMode; text: page.liveMode ? screenStudio.liveStatus : page.d.preset === "Projects" ? screenStudio.projects.map(p => p.name).join(" · ") : screenStudio.trafficInfo; color: theme.text; wrapMode: Text.WordWrap; font.pixelSize: 13 }
                Label { visible: page.tankMode; Layout.fillWidth: true; text: "Times shown on Google, the change against the 28 days before, clicks, and how many searches the site appears for, on page one and in the top three. Each number surfaces from a porthole of glowing coolant in the site's colour while its logo turns above."; color: theme.text; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                Label { visible: page.tankMode; Layout.fillWidth: true; text: "Rendered with Blender from the numbers last fetched by the daily update. A number that has not changed is reused; a new one takes about five minutes. Once a day the update sends a fresh clip on its own."; color: theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                Label { visible: !page.tankMode; Layout.fillWidth: true; text: page.liveMode ? "Cloudflare request analytics refresh every minute while this page is open. Requests include bots and assets, not unique visitors." : "Rotates search clicks, impressions and CTR with a daily impressions chart. Search Console measures Google search, not all visitors. Import a fresh 28-day snapshot to update it."; color: theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                Label { visible: page.liveMode; Layout.fillWidth: true; text: "The waterline is the last 15 minutes, oldest on the left. A taller wave means more requests that minute, on one shared scale across your sites. Droplets are requests, up to 24 a minute, and the count climbs to the real total. Calm water means no requests. An empty glass means no data."; color: theme.text; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                Label { visible: page.liveMode; Layout.fillWidth: true; text: "The cooler plays saved clips, so Send to cooler stores a snapshot marked with its time. Those numbers stay until you send a new one."; color: theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                Button { visible: !page.portfolioMode; text: "Import analytics snapshot"; enabled: !screenStudio.busy; onClicked: statsFile.open() }
                Button { visible: page.liveMode; text: "Refresh Cloudflare now"; onClicked: screenStudio.refreshLive() }
                Label { visible: page.portfolioMode; Layout.fillWidth: true; text: screenStudio.projects.map(p => p.name).join(" · "); color: theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12 }
            }
        }
    }
    Component.onCompleted: { if (!page.liveMode && !screenStudio.preview && !screenStudio.busy) screenStudio.render() }
    ColorDialog { id: colors; title: "Accent colour"; onAccepted: screenStudio.edit("color", selectedColor.toString()) }
    ColorDialog { id: backgroundColor; title: "Background colour"; onAccepted: screenStudio.edit("background", selectedColor.toString()) }
    FileDialog { id: logoFile; title: "Choose your logo"; nameFilters: ["Images (*.svg *.png *.webp *.jpg *.jpeg)"]; onAccepted: screenStudio.chooseFile("logo", selectedFile.toString()) }
    FileDialog { id: mediaFile; title: "Choose a photo or animation"; nameFilters: ["Media (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mkv *.webm)"]; onAccepted: screenStudio.chooseFile("media", selectedFile.toString()) }
    FileDialog { id: statsFile; title: "Import Search Console snapshot"; nameFilters: ["JSON snapshot (*.json)"]; onAccepted: screenStudio.importStats(selectedFile.toString()) }
}
