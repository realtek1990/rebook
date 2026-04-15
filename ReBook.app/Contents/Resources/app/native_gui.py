"""ReBook — Native macOS GUI (Cocoa/AppKit via PyObjC)."""
import json
import os
import queue
import shutil
import smtplib
import threading
from email.message import EmailMessage
from pathlib import Path

import objc
from AppKit import *
from Foundation import *
from i18n import t
import tts_engine

# ── Configuration ─────────────────────────────────────────────────────────────
WORKSPACE = Path.home() / ".pdf2epub-app"
CONFIG_FILE = WORKSPACE / "config.json"
WORKSPACE.mkdir(parents=True, exist_ok=True)

W, H = 660, 800
PAD = 24
CW = W - 2 * PAD

def _providers():
    return [
    (t("provider_none"), "Brak"),
    ("NVIDIA NIM", "nvidia"),
    ("Mistral AI", "mistral"),
    ("Kimi / Moonshot", "moonshot"),
    ("Zhipu AI", "zhipu"),
    ("OpenAI", "openai"),
    ("Anthropic", "anthropic"),
    ("Google Gemini", "gemini"),
    ("GLM / ZhipuAI", "zhipuai"),
    ("Groq", "groq"),
    ]

FORMATS = ["EPUB", "Markdown", "HTML"]
FORMAT_KEYS = ["epub", "md", "html"]

MODELS = {
    "gemini": ["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-pro"],
    "openai": ["gpt-5.4-mini", "gpt-5.3-instant", "gpt-5.4-pro", "gpt-5.4-thinking", "o3-mini"],
    "anthropic": ["claude-sonnet-4.6", "claude-opus-4.6", "claude-3-5-haiku-latest"],
    "mistral": ["mistral-small-4", "mistral-large-latest", "pixtral-large-latest", "ministral-8b-latest"],
    "nvidia": [
        "mistralai/mistral-small-4-119b-2603",
        "qwen/qwen3.5-122b-a10b",
        "deepseek-ai/deepseek-v3.2",
        "meta/llama-3.3-70b-instruct",
        "google/gemma-3-27b-it",
    ],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "zhipu": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "zhipuai": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768"]
}

LANGUAGES = [
    "polski", "angielski", "niemiecki", "francuski", "hiszpański",
    "włoski", "portugalski", "rosyjski", "ukraiński", "czeski",
    "słowacki", "chiński", "japoński", "koreański", "turecki",
    "arabski", "holenderski", "szwedzki", "norweski", "duński",
    "fiński", "wietnamski", "tajski", "węgierski", "rumuński",
    "serbski", "chorwacki",
]

def load_config():
    try:
        return json.load(open(CONFIG_FILE))
    except Exception:
        return {}

def save_config_file(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _label(text, size=13, bold=False, color=None):
    lbl = NSTextField.labelWithString_(text)
    weight = 0.3 if bold else 0.0  # NSFontWeightSemibold=0.3
    lbl.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
    if color:
        lbl.setTextColor_(color)
    return lbl

def _textfield(placeholder="", secure=False):
    cls = NSSecureTextField if secure else NSTextField
    f = cls.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
    f.setPlaceholderString_(placeholder)
    f.setFont_(NSFont.systemFontOfSize_(12))
    return f

# ── Global app delegate reference (for DropView callbacks) ────────────────────
_app_delegate = None

# ── Drop View ─────────────────────────────────────────────────────────────────

class DropView(NSView):
    """Drag-and-drop target area."""

    def isFlipped(self): return True

    def initWithFrame_(self, frame):
        self = objc.super(DropView, self).initWithFrame_(frame)
        if self is None: return None
        self._highlighted = False
        self.registerForDraggedTypes_([NSPasteboardTypeFileURL])

        w = frame.size.width
        icon = _label("\U0001F4E5", size=42)
        icon.setAlignment_(NSTextAlignmentCenter)
        icon.setFrame_(NSMakeRect(0, 18, w, 50))
        self.addSubview_(icon)

        title = _label(t("drop_title"), size=14, bold=True)
        title.setAlignment_(NSTextAlignmentCenter)
        title.setFrame_(NSMakeRect(0, 68, w, 20))
        self.addSubview_(title)

        sub = _label(t("drop_subtitle"), size=11, color=NSColor.secondaryLabelColor())
        sub.setAlignment_(NSTextAlignmentCenter)
        sub.setFrame_(NSMakeRect(0, 90, w, 16))
        self.addSubview_(sub)
        return self

    def drawRect_(self, rect):
        b = NSInsetRect(self.bounds(), 1.5, 1.5)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 10, 10)
        path.setLineWidth_(1.5)
        if self._highlighted:
            NSColor.controlAccentColor().colorWithAlphaComponent_(0.15).setFill()
            path.fill()
            NSColor.controlAccentColor().setStroke()
        else:
            NSColor.separatorColor().setStroke()
        path.setLineDash_count_phase_([6.0, 4.0], 2, 0)
        path.stroke()

    def draggingEntered_(self, sender):
        self._highlighted = True
        self.setNeedsDisplay_(True)
        return NSDragOperationCopy

    def draggingExited_(self, sender):
        self._highlighted = False
        self.setNeedsDisplay_(True)

    def prepareForDragOperation_(self, sender):
        return True

    def performDragOperation_(self, sender):
        try:
            self._highlighted = False
            self.setNeedsDisplay_(True)
            pb = sender.draggingPasteboard()
            urls = pb.readObjectsForClasses_options_([NSURL], {NSPasteboardURLReadingFileURLsOnlyKey: True})
            if urls and len(urls) > 0:
                p = urls[0].path()
                if Path(p).suffix.lower() in (".pdf", ".epub", ".md"):
                    if _app_delegate:
                        _app_delegate.fileDropped_(p)
                    return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            if _app_delegate:
                _app_delegate._showAlert(t("error_prefix"), str(e))
        return False

    def mouseDown_(self, event):
        if _app_delegate:
            _app_delegate.openFileDialog_(None)


# ── Main Application Delegate ─────────────────────────────────────────────────

class AppDelegate(NSObject):
    """Main controller: builds window, handles actions, runs conversion."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self:
            self._selectedFile = None
            self._outputPath = None
            self._converting = False
            self._ui_queue = queue.Queue()
            # UI refs
            self._providerPopup = None
            self._modelField = None
            self._apiKeyField = None
            self._kindleEmailField = None
            self._smtpEmailField = None
            self._smtpPassField = None
            self._ocrProviderPopup = None
            self._ocrKeyField = None
            self._settingsWindow = None
            self._dropView = None
            self._fileBadgeView = None
            self._convertBtn = None
            self._window = None
        return self

    def applicationDidFinishLaunching_(self, note):
        global _app_delegate
        _app_delegate = self
        try:
            self._buildMenu()
            self._buildWindow()
            self._buildSettingsSheet()
            self._window.makeKeyWindow()
            NSApp.activateIgnoringOtherApps_(True)
        except Exception as e:
            import traceback, sys
            traceback.print_exc()
            with open("/tmp/rebook_crash.log", "w") as f:
                traceback.print_exc(file=f)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    @objc.python_method
    def _buildMenu(self):
        bar = NSMenu.alloc().init()
        appItem = NSMenuItem.alloc().init()
        appMenu = NSMenu.alloc().init()
        appMenu.addItemWithTitle_action_keyEquivalent_(t("menu_about"), "orderFrontStandardAboutPanel:", "")
        appMenu.addItem_(NSMenuItem.separatorItem())
        s = appMenu.addItemWithTitle_action_keyEquivalent_(t("menu_settings"), "openSettings:", ",")
        s.setTarget_(self)
        appMenu.addItem_(NSMenuItem.separatorItem())
        appMenu.addItemWithTitle_action_keyEquivalent_(t("menu_quit"), "terminate:", "q")
        appItem.setSubmenu_(appMenu)
        bar.addItem_(appItem)

        fItem = NSMenuItem.alloc().init()
        fMenu = NSMenu.alloc().initWithTitle_(t("menu_file"))
        o = fMenu.addItemWithTitle_action_keyEquivalent_(t("menu_open"), "openFileDialog:", "o")
        o.setTarget_(self)
        fItem.setSubmenu_(fMenu)
        bar.addItem_(fItem)

        NSApp.setMainMenu_(bar)

    @objc.python_method
    def _buildWindow(self):
        mask = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), mask, NSBackingStoreBuffered, False)
        self._window.setTitle_("ReBook")
        # Center on screen explicitly using screen coordinates
        screen = NSScreen.mainScreen()
        if screen:
            sf = screen.visibleFrame()
            x = sf.origin.x + (sf.size.width - W) / 2
            y = sf.origin.y + (sf.size.height - H) / 2
            self._window.setFrameOrigin_(NSMakePoint(x, y))
        else:
            self._window.center()

        # Używamy systemowego contentView okna bez nadpisywania go
        cv = self._window.contentView()
        
        top = H  # 740

        # Miejsca zaczynamy od góry i schodzimy w dół układając layout
        title = _label("ReBook", size=22, bold=True)
        title.setFrame_(NSMakeRect(PAD, top - 36, CW - 40, 28))
        cv.addSubview_(title)

        sub = _label(t("app_subtitle"), size=12, color=NSColor.secondaryLabelColor())
        sub.setFrame_(NSMakeRect(PAD, top - 52, CW, 16))
        cv.addSubview_(sub)

        gear = NSButton.alloc().initWithFrame_(NSMakeRect(W - PAD - 36, top - 40, 36, 36))
        gear.setBezelStyle_(NSBezelStyleRounded)
        sfImg = NSImage.imageWithSystemSymbolName_accessibilityDescription_("gearshape", t("menu_settings"))
        if sfImg:
            gear.setImage_(sfImg)
            gear.setTitle_("")
        else:
            gear.setTitle_("\u2699\uFE0F")
        gear.setTarget_(self)
        gear.setAction_("openSettings:")
        cv.addSubview_(gear)

        top -= 58

        self._dropView = DropView.alloc().initWithFrame_(NSMakeRect(PAD, top - 100, CW, 100))
        cv.addSubview_(self._dropView)

        self._fileBadgeView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 100, CW, 100))
        self._fileBadgeView.setHidden_(True)
        self._fileLabel = _label("\u2014", size=13, bold=True)
        self._fileLabel.setFrame_(NSMakeRect(8, 62, CW - 80, 18))
        self._fileLabel.setLineBreakMode_(NSLineBreakByTruncatingMiddle)
        self._fileBadgeView.addSubview_(self._fileLabel)
        self._sizeLabel = _label("", size=11, color=NSColor.secondaryLabelColor())
        self._sizeLabel.setFrame_(NSMakeRect(8, 44, CW - 80, 16))
        self._fileBadgeView.addSubview_(self._sizeLabel)
        rmBtn = NSButton.alloc().initWithFrame_(NSMakeRect(CW - 60, 48, 52, 28))
        rmBtn.setBezelStyle_(NSBezelStyleRounded)
        rmBtn.setTitle_(t("remove_btn"))
        rmBtn.setTarget_(self)
        rmBtn.setAction_("removeFile:")
        self._fileBadgeView.addSubview_(rmBtn)
        cv.addSubview_(self._fileBadgeView)
        
        top -= 108

        sep = NSBox.alloc().initWithFrame_(NSMakeRect(PAD, top, CW, 1))
        sep.setBoxType_(NSBoxSeparator)
        cv.addSubview_(sep)
        top -= 10

        optH = _label(t("options_header"), size=11, bold=True, color=NSColor.secondaryLabelColor())
        optH.setFrame_(NSMakeRect(PAD, top - 14, CW, 14))
        cv.addSubview_(optH)
        top -= 22

        fmtLabel = _label(t("format_label"), size=13)
        fmtLabel.setFrame_(NSMakeRect(PAD, top - 22, 140, 20))
        cv.addSubview_(fmtLabel)

        self._formatCtrl = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(PAD + 150, top - 24, 260, 26))
        self._formatCtrl.setSegmentCount_(3)
        for i, fmt in enumerate(FORMATS):
            self._formatCtrl.setLabel_forSegment_(fmt, i)
            self._formatCtrl.setWidth_forSegment_(80, i)
        self._formatCtrl.setSelectedSegment_(0)
        self._formatCtrl.setSegmentStyle_(NSSegmentStyleRounded)
        cv.addSubview_(self._formatCtrl)
        top -= 32

        self._aiCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 22, CW, 20))
        self._aiCheck.setButtonType_(NSSwitchButton)
        self._aiCheck.setTitle_(t("ai_check"))
        self._aiCheck.setState_(NSOnState)
        cv.addSubview_(self._aiCheck)
        top -= 24

        # ── Page Range (PDF only, hidden by default) ──────────────────
        self._pageRangeView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 30, CW, 28))
        self._pageRangeView.setHidden_(True)
        prLbl = _label("📄 Zakres stron:", size=11, color=NSColor.secondaryLabelColor())
        prLbl.setFrame_(NSMakeRect(0, 6, 90, 16))
        self._pageRangeView.addSubview_(prLbl)
        self._pageStartField = NSTextField.alloc().initWithFrame_(NSMakeRect(92, 2, 60, 22))
        self._pageStartField.setPlaceholderString_("Od")
        self._pageStartField.setFont_(NSFont.systemFontOfSize_(11))
        self._pageRangeView.addSubview_(self._pageStartField)
        dashLbl = _label("–", size=13)
        dashLbl.setFrame_(NSMakeRect(155, 6, 10, 16))
        self._pageRangeView.addSubview_(dashLbl)
        self._pageEndField = NSTextField.alloc().initWithFrame_(NSMakeRect(168, 2, 60, 22))
        self._pageEndField.setPlaceholderString_("Do")
        self._pageEndField.setFont_(NSFont.systemFontOfSize_(11))
        self._pageRangeView.addSubview_(self._pageEndField)
        self._pageCountLabel = _label("", size=10, color=NSColor.tertiaryLabelColor())
        self._pageCountLabel.setFrame_(NSMakeRect(236, 6, 180, 16))
        self._pageRangeView.addSubview_(self._pageCountLabel)
        cv.addSubview_(self._pageRangeView)
        top -= 28

        self._translateCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 22, CW, 20))
        self._translateCheck.setButtonType_(NSSwitchButton)
        self._translateCheck.setTitle_(t("translate_check"))
        self._translateCheck.setTarget_(self)
        self._translateCheck.setAction_("toggleTranslate:")
        cv.addSubview_(self._translateCheck)
        top -= 22

        self._translateImgCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD + 20, top - 22, CW - 20, 20))
        self._translateImgCheck.setButtonType_(NSSwitchButton)
        self._translateImgCheck.setTitle_(t("translate_images_check"))
        self._translateImgCheck.setFont_(NSFont.systemFontOfSize_(11))
        self._translateImgCheck.setHidden_(True)
        cv.addSubview_(self._translateImgCheck)
        top -= 24

        self._verifyCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD + 20, top - 22, CW - 20, 20))
        self._verifyCheck.setButtonType_(NSSwitchButton)
        self._verifyCheck.setTitle_("🔍 Weryfikacja LLM (dokładna, extra koszt)")
        self._verifyCheck.setFont_(NSFont.systemFontOfSize_(11))
        self._verifyCheck.setHidden_(True)
        self._verifyCheck.setState_(NSOffState)
        cv.addSubview_(self._verifyCheck)
        top -= 24

        self._langView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 60, CW, 56))
        self._langView.setHidden_(True)
        ll1 = _label(t("lang_from_label"), size=11, color=NSColor.secondaryLabelColor())
        ll1.setFrame_(NSMakeRect(0, 32, 110, 16))
        self._langView.addSubview_(ll1)
        self._langFromField = NSComboBox.alloc().initWithFrame_(NSMakeRect(112, 30, CW - 112, 24))
        self._langFromField.setFont_(NSFont.systemFontOfSize_(12))
        self._langFromField.addItemsWithObjectValues_(LANGUAGES)
        self._langFromField.setPlaceholderString_(t("lang_from_placeholder"))
        self._langFromField.setCompletes_(True)
        self._langFromField.setNumberOfVisibleItems_(10)
        self._langView.addSubview_(self._langFromField)
        ll2 = _label(t("lang_to_label"), size=11, color=NSColor.secondaryLabelColor())
        ll2.setFrame_(NSMakeRect(0, 4, 110, 16))
        self._langView.addSubview_(ll2)
        self._langToField = NSComboBox.alloc().initWithFrame_(NSMakeRect(112, 2, CW - 112, 24))
        self._langToField.setFont_(NSFont.systemFontOfSize_(12))
        self._langToField.addItemsWithObjectValues_(LANGUAGES)
        self._langToField.setStringValue_("polski")
        self._langToField.setCompletes_(True)
        self._langToField.setNumberOfVisibleItems_(10)
        self._langToField.setDelegate_(self)   # triggers comboBoxSelectionDidChange:
        self._langView.addSubview_(self._langToField)
        cv.addSubview_(self._langView)
        top -= 62

        self._convertBtn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 36, CW - 100, 36))
        self._convertBtn.setBezelStyle_(NSBezelStyleRounded)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._convertBtn.setFont_(NSFont.systemFontOfSize_weight_(14, 0.3))
        self._convertBtn.setTarget_(self)
        self._convertBtn.setAction_("startConversion:")
        self._convertBtn.setKeyEquivalent_("\r")
        self._convertBtn.setEnabled_(False)
        cv.addSubview_(self._convertBtn)

        self._stopBtn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD + CW - 90, top - 36, 90, 36))
        self._stopBtn.setBezelStyle_(NSBezelStyleRounded)
        self._stopBtn.setTitle_("⛔ Stop")
        self._stopBtn.setFont_(NSFont.systemFontOfSize_weight_(13, 0.3))
        self._stopBtn.setTarget_(self)
        self._stopBtn.setAction_("stopConversion:")
        self._stopBtn.setHidden_(True)
        cv.addSubview_(self._stopBtn)
        top -= 44

        # ── Audiobook panel — always visible ─────────────────────────────
        sep_ab = NSBox.alloc().initWithFrame_(NSMakeRect(PAD, top, CW, 1))
        sep_ab.setBoxType_(NSBoxSeparator)
        cv.addSubview_(sep_ab)
        top -= 8

        abHeader = _label("🎧 Audiobook", size=13, bold=True)
        abHeader.setFrame_(NSMakeRect(PAD, top - 16, CW, 16))
        cv.addSubview_(abHeader)
        top -= 22

        self._audiobookPanel = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 86, CW, 86))

        # Voice popup — label only (contents filled by _refreshVoicesForLang)
        voiceLbl = _label("🎙 Głos:", size=12)
        voiceLbl.setFrame_(NSMakeRect(0, 64, 55, 16))
        self._audiobookPanel.addSubview_(voiceLbl)

        self._voicePopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(58, 60, 200, 24), False)
        self._audiobookPanel.addSubview_(self._voicePopup)
        self._voiceKeys = []
        self._refreshVoicesForLang("polski")   # populate for default language

        # Sample play button
        self._sampleBtn = NSButton.alloc().initWithFrame_(NSMakeRect(265, 60, 90, 24))
        self._sampleBtn.setBezelStyle_(NSBezelStyleRounded)
        self._sampleBtn.setTitle_("▶ Sample")
        self._sampleBtn.setFont_(NSFont.systemFontOfSize_(12))
        self._sampleBtn.setTarget_(self)
        self._sampleBtn.setAction_("playVoiceSample:")
        self._audiobookPanel.addSubview_(self._sampleBtn)

        # EPUB source label
        self._audiobookEpubLabel = _label("Źródło: brak (skonwertuj lub wybierz EPUB)", size=11, color=NSColor.secondaryLabelColor())
        self._audiobookEpubLabel.setFrame_(NSMakeRect(0, 42, CW - 140, 16))
        self._audiobookPanel.addSubview_(self._audiobookEpubLabel)

        # Pick EPUB button
        pickEpubBtn = NSButton.alloc().initWithFrame_(NSMakeRect(CW - 130, 38, 128, 24))
        pickEpubBtn.setBezelStyle_(NSBezelStyleRounded)
        pickEpubBtn.setTitle_("📂 Wybierz EPUB")
        pickEpubBtn.setFont_(NSFont.systemFontOfSize_(11))
        pickEpubBtn.setTarget_(self)
        pickEpubBtn.setAction_("pickAudiobookEpub:")
        self._audiobookPanel.addSubview_(pickEpubBtn)
        self._audiobookPickedEpub = None  # path to manually picked epub

        # Generate audiobook button
        self._audiobookBtn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 8, CW - 2, 26))
        self._audiobookBtn.setBezelStyle_(NSBezelStyleRounded)
        self._audiobookBtn.setTitle_("🎧 Generuj audiobook")
        self._audiobookBtn.setFont_(NSFont.systemFontOfSize_weight_(13, 0.3))
        self._audiobookBtn.setTarget_(self)
        self._audiobookBtn.setAction_("startAudiobook:")
        self._audiobookPanel.addSubview_(self._audiobookBtn)

        cv.addSubview_(self._audiobookPanel)
        top -= 92

        self._progressBar = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(PAD, top - 6, CW, 6))
        self._progressBar.setStyle_(NSProgressIndicatorBarStyle)
        self._progressBar.setIndeterminate_(False)
        self._progressBar.setMinValue_(0)
        self._progressBar.setMaxValue_(100)
        self._progressBar.setDoubleValue_(0)
        self._progressBar.setHidden_(True)
        cv.addSubview_(self._progressBar)
        top -= 10

        self._stageLabel = _label("", size=12, color=NSColor.secondaryLabelColor())
        self._stageLabel.setFrame_(NSMakeRect(PAD, top - 16, CW, 16))
        self._stageLabel.setHidden_(True)
        cv.addSubview_(self._stageLabel)
        top -= 18

        self._logScroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(PAD, top - 80, CW, 80))
        self._logScroll.setBorderType_(NSBezelBorder)
        self._logScroll.setHasVerticalScroller_(True)
        self._logScroll.setHidden_(True)
        self._logText = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, CW - 16, 80))
        self._logText.setEditable_(False)
        self._logText.setFont_(NSFont.monospacedSystemFontOfSize_weight_(10, 0.0))
        self._logText.setTextColor_(NSColor.secondaryLabelColor())
        self._logText.setBackgroundColor_(NSColor.textBackgroundColor())
        self._logScroll.setDocumentView_(self._logText)
        cv.addSubview_(self._logScroll)
        top -= 88

        self._resultView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 56, CW, 50))
        self._resultView.setHidden_(True)
        rl = _label(t("conversion_done"), size=14, bold=True)
        rl.setTextColor_(NSColor.systemGreenColor())
        rl.setFrame_(NSMakeRect(0, 26, CW, 20))
        self._resultView.addSubview_(rl)
        self._downloadBtn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 130, 28))
        self._downloadBtn.setBezelStyle_(NSBezelStyleRounded)
        self._downloadBtn.setTitle_(t("save_btn"))
        self._downloadBtn.setTarget_(self)
        self._downloadBtn.setAction_("saveResult:")
        self._resultView.addSubview_(self._downloadBtn)
        self._kindleBtn = NSButton.alloc().initWithFrame_(NSMakeRect(138, 0, 100, 28))
        self._kindleBtn.setBezelStyle_(NSBezelStyleRounded)
        self._kindleBtn.setTitle_(t("kindle_btn"))
        self._kindleBtn.setTarget_(self)
        self._kindleBtn.setAction_("sendKindle:")
        self._resultView.addSubview_(self._kindleBtn)

        # Show in Finder button
        self._revealBtn = NSButton.alloc().initWithFrame_(NSMakeRect(246, 0, 140, 28))
        self._revealBtn.setBezelStyle_(NSBezelStyleRounded)
        self._revealBtn.setTitle_("📂 Pokaż w Finderze")
        self._revealBtn.setTarget_(self)
        self._revealBtn.setAction_("revealInFinder:")
        self._resultView.addSubview_(self._revealBtn)

        # Audiobook result button (shown after audiobook generation)
        self._audiobookResultBtn = NSButton.alloc().initWithFrame_(NSMakeRect(394, 0, 130, 28))
        self._audiobookResultBtn.setBezelStyle_(NSBezelStyleRounded)
        self._audiobookResultBtn.setTitle_("📂 Otwórz folder")
        self._audiobookResultBtn.setTarget_(self)
        self._audiobookResultBtn.setAction_("openAudiobookFolder:")
        self._audiobookResultBtn.setHidden_(True)
        self._resultView.addSubview_(self._audiobookResultBtn)

        cv.addSubview_(self._resultView)

        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()


    @objc.python_method
    def _buildSettingsSheet(self):
        try:
            SW_H = 560
            sw = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 440, SW_H), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
            sw.setTitle_(t("settings_title"))
            self._settingsWindow = sw
            
            sv = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 440, SW_H))
            sw.setContentView_(sv)
            
            p = 20
            cw = 400
            cancelBtn = NSButton.alloc().initWithFrame_(NSMakeRect(cw - 60, 16, 80, 28))
            cancelBtn.setBezelStyle_(NSBezelStyleRounded)
            cancelBtn.setTitle_(t("settings_cancel"))
            cancelBtn.setTarget_(self)
            cancelBtn.setAction_("closeSettings:")
            cancelBtn.setKeyEquivalent_("\x1b")
            sv.addSubview_(cancelBtn)

            saveBtn = NSButton.alloc().initWithFrame_(NSMakeRect(cw - 150, 16, 80, 28))
            saveBtn.setBezelStyle_(NSBezelStyleRounded)
            saveBtn.setTitle_(t("settings_save"))
            saveBtn.setTarget_(self)
            saveBtn.setAction_("saveSettings:")
            saveBtn.setKeyEquivalent_("\r")
            sv.addSubview_(saveBtn)

            y = 56
            lbl = _label(t("settings_smtp_pass"), size=11)
            lbl.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl)
            self._smtpPassField = _textfield("App Password", secure=True)
            self._smtpPassField.setFrame_(NSMakeRect(p + 105, y - 2, cw - 105, 24))
            sv.addSubview_(self._smtpPassField)
            y += 30

            lbl2 = _label(t("settings_smtp_email"), size=11)
            lbl2.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl2)
            self._smtpEmailField = _textfield("twoj@gmail.com")
            self._smtpEmailField.setFrame_(NSMakeRect(p + 105, y - 2, cw - 105, 24))
            sv.addSubview_(self._smtpEmailField)
            y += 30

            lbl3 = _label(t("settings_kindle_email"), size=11)
            lbl3.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl3)
            self._kindleEmailField = _textfield("nazwa@kindle.com")
            self._kindleEmailField.setFrame_(NSMakeRect(p + 105, y - 2, cw - 105, 24))
            sv.addSubview_(self._kindleEmailField)
            y += 28

            kindleSec = _label(t("settings_kindle_header"), size=11, bold=True, color=NSColor.secondaryLabelColor())
            kindleSec.setFrame_(NSMakeRect(p, y, cw, 14))
            sv.addSubview_(kindleSec)
            y += 24

            sep2 = NSBox.alloc().initWithFrame_(NSMakeRect(p, y, cw, 1))
            sep2.setBoxType_(NSBoxSeparator)
            sv.addSubview_(sep2)
            y += 16

            lbl4 = _label(t("settings_api_key"), size=11)
            lbl4.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl4)
            self._apiKeyField = _textfield("sk-...", secure=True)
            self._apiKeyField.setFrame_(NSMakeRect(p + 105, y - 2, cw - 105, 24))
            sv.addSubview_(self._apiKeyField)
            y += 30

            lbl5 = _label(t("settings_model"), size=11)
            lbl5.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl5)
            self._modelField = NSComboBox.alloc().initWithFrame_(NSMakeRect(p + 105, y - 2, cw - 105, 24))
            self._modelField.setPlaceholderString_("Wpisz lub wybierz model...")
            sv.addSubview_(self._modelField)
            y += 30

            lbl6 = _label(t("settings_provider"), size=11)
            lbl6.setFrame_(NSMakeRect(p, y, 100, 14))
            sv.addSubview_(lbl6)
            self._providerPopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(p + 105, y - 4, cw - 105, 26), False)
            self._providerPopup.setTarget_(self)
            self._providerPopup.setAction_("providerChanged:")
            for ptitle, _ in _providers():
                self._providerPopup.addItemWithTitle_(ptitle)
            sv.addSubview_(self._providerPopup)
            y += 28

            llmSec = _label(t("settings_llm_header"), size=11, bold=True, color=NSColor.secondaryLabelColor())
            llmSec.setFrame_(NSMakeRect(p, y, cw, 14))
            sv.addSubview_(llmSec)
            y += 24

            # ── OCR Provider Section ─────────────────────────────────────
            sep_ocr = NSBox.alloc().initWithFrame_(NSMakeRect(p, y, cw, 1))
            sep_ocr.setBoxType_(NSBoxSeparator)
            sv.addSubview_(sep_ocr)
            y += 16

            ocrSec = _label("OCR", size=11, bold=True, color=NSColor.secondaryLabelColor())
            ocrSec.setFrame_(NSMakeRect(p, y, cw, 14))
            sv.addSubview_(ocrSec)
            y += 24

            ocrProvLabel = _label("Provider OCR:", size=12)
            ocrProvLabel.setFrame_(NSMakeRect(p, y, cw, 16))
            sv.addSubview_(ocrProvLabel)
            y += 20

            self._ocrProviderPopup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(p, y, cw, 26))
            ocr_prov_options = ["Auto (najlepszy dostępny)", "Mistral OCR", "Gemini Cloud OCR"]
            for opt in ocr_prov_options:
                self._ocrProviderPopup.addItemWithTitle_(opt)
            sv.addSubview_(self._ocrProviderPopup)
            y += 32

            ocrKeyLabel = _label("Klucz OCR (pusty = użyj klucza głównego):", size=12)
            ocrKeyLabel.setFrame_(NSMakeRect(p, y, cw, 16))
            sv.addSubview_(ocrKeyLabel)
            y += 20

            self._ocrKeyField = _textfield("", secure=True)
            self._ocrKeyField.setFrame_(NSMakeRect(p, y, cw, 24))
            sv.addSubview_(self._ocrKeyField)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._showAlert(t("error_prefix"), str(e))

    @objc.IBAction
    def openFileDialog_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setTitle_(t("menu_open"))
        panel.setAllowedFileTypes_(["pdf", "epub", "md"])
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() == NSModalResponseOK:
            url = panel.URLs()[0]
            self.fileDropped_(url.path())

    @objc.python_method
    def fileDropped_(self, path):
        try:
            self._selectedFile = str(path)
            p = Path(str(path))
            size_mb = p.stat().st_size / (1024 * 1024)
            self._fileLabel.setStringValue_(f"\U0001F4C4  {p.name}")
            self._sizeLabel.setStringValue_(f"{size_mb:.1f} MB")
            self._dropView.setHidden_(True)
            self._fileBadgeView.setHidden_(False)
            self._convertBtn.setEnabled_(True)
            # Show page range panel for PDFs
            is_pdf = p.suffix.lower() == ".pdf"
            self._pageRangeView.setHidden_(not is_pdf)
            if is_pdf:
                try:
                    import corrector
                    total = corrector.get_pdf_page_count(str(p))
                    self._pageCountLabel.setStringValue_(f"(z {total} stron)")
                    self._pageStartField.setStringValue_("")
                    self._pageEndField.setStringValue_("")
                except Exception:
                    self._pageCountLabel.setStringValue_("")
        except Exception as e:
            self._showAlert(t("error_prefix"), str(e))

    @objc.IBAction
    def removeFile_(self, sender):
        self._selectedFile = None
        self._dropView.setHidden_(False)
        self._fileBadgeView.setHidden_(True)
        self._convertBtn.setEnabled_(False)
        self._resultView.setHidden_(True)

    @objc.IBAction
    def toggleTranslate_(self, sender):
        show = self._translateCheck.state() == NSOnState
        self._langView.setHidden_(not show)
        self._translateImgCheck.setHidden_(not show)
        self._verifyCheck.setHidden_(not show)
        if not show:
            self._translateImgCheck.setState_(NSOffState)
            self._verifyCheck.setState_(NSOffState)

    @objc.IBAction
    def providerChanged_(self, sender):
        idx = self._providerPopup.indexOfSelectedItem()
        prov_key = _providers()[idx][1]
        self._updateModelList(prov_key)

    @objc.python_method
    def _updateModelList(self, prov_key):
        self._modelField.removeAllItems()
        models = MODELS.get(prov_key, [])
        if models:
            self._modelField.addItemsWithObjectValues_(models)



    @objc.IBAction
    def openSettings_(self, sender):
        try:
            cfg = load_config()
            prov = cfg.get("llm_provider", "Brak")
            provs = _providers()
            idx = next((i for i, (_, v) in enumerate(provs) if v == prov), 0)
            self._providerPopup.selectItemAtIndex_(idx)
            self._updateModelList(provs[idx][1])
            self._modelField.setStringValue_(cfg.get("model_name", ""))
            self._apiKeyField.setStringValue_(cfg.get("api_key", ""))
            self._kindleEmailField.setStringValue_(cfg.get("kindle_email", ""))
            self._smtpEmailField.setStringValue_(cfg.get("smtp_email", ""))
            self._smtpPassField.setStringValue_(cfg.get("smtp_pass", ""))
            # OCR fields
            ocr_map = {"auto": 0, "mistral": 1, "gemini": 2}
            ocr_idx = ocr_map.get(cfg.get("ocr_provider", "auto"), 0)
            if self._ocrProviderPopup:
                self._ocrProviderPopup.selectItemAtIndex_(ocr_idx)
            if self._ocrKeyField:
                self._ocrKeyField.setStringValue_(cfg.get("ocr_api_key", ""))
            NSApp.beginSheet_modalForWindow_modalDelegate_didEndSelector_contextInfo_(self._settingsWindow, self._window, None, None, None)
        except Exception as e:
            self._showAlert(t("error_prefix"), str(e))

    @objc.IBAction
    def closeSettings_(self, sender):
        NSApp.endSheet_(self._settingsWindow)
        self._settingsWindow.orderOut_(None)

    @objc.IBAction
    def saveSettings_(self, sender):
        try:
            idx = self._providerPopup.indexOfSelectedItem()
            provs = _providers()
            data = {
                "llm_provider": provs[idx][1],
                "model_name": str(self._modelField.stringValue()),
                "api_key": str(self._apiKeyField.stringValue()),
                "kindle_email": str(self._kindleEmailField.stringValue()),
                "smtp_email": str(self._smtpEmailField.stringValue()),
                "smtp_pass": str(self._smtpPassField.stringValue()),
                "ocr_provider": ["auto", "mistral", "gemini"][self._ocrProviderPopup.indexOfSelectedItem()] if self._ocrProviderPopup else "auto",
                "ocr_api_key": str(self._ocrKeyField.stringValue()) if self._ocrKeyField else "",
            }
            save_config_file(data)
            NSApp.endSheet_(self._settingsWindow)
            self._settingsWindow.orderOut_(None)
        except Exception as e:
            self._showAlert(t("settings_save_error"), str(e))

    @objc.IBAction
    def startConversion_(self, sender):
        if not self._selectedFile or self._converting:
            return
        self._converting = True
        self._cancelFlag = False
        self._convertBtn.setEnabled_(False)
        self._convertBtn.setTitle_(t("converting_btn"))
        self._stopBtn.setHidden_(False)
        self._resultView.setHidden_(True)
        # audiobookPanel is always visible — don't hide it
        self._progressBar.setDoubleValue_(0)
        self._progressBar.setHidden_(False)
        self._stageLabel.setStringValue_(t("starting"))
        self._stageLabel.setHidden_(False)
        self._logScroll.setHidden_(False)
        self._logText.setString_("")

        fmt_idx = self._formatCtrl.selectedSegment()
        fmt = FORMAT_KEYS[fmt_idx]
        translate = bool(self._translateCheck.state())
        translate_images = bool(self._translateImgCheck.state()) if translate else False
        verify = bool(self._verifyCheck.state()) if translate else False
        use_llm = bool(self._aiCheck.state()) or translate
        lang_from = str(self._langFromField.stringValue()) if translate else ""
        lang_to = str(self._langToField.stringValue()) if translate else "polski"

        # Page range (PDF only)
        page_start = 0
        page_end = 0
        try:
            ps_str = str(self._pageStartField.stringValue()).strip()
            pe_str = str(self._pageEndField.stringValue()).strip()
            if ps_str:
                page_start = int(ps_str)
            if pe_str:
                page_end = int(pe_str)
        except (ValueError, AttributeError):
            pass

        args = (str(self._selectedFile), fmt, use_llm, translate, translate_images, lang_from, lang_to, page_start, page_end, verify)
        threading.Thread(target=self._runConversion, args=args, daemon=True).start()

    def _refreshVoicesForLang(self, lang_to: str):
        """Repopulate the voice popup with voices appropriate for lang_to."""
        voices = tts_engine.voices_for(lang_to)   # dict key→label
        self._voicePopup.removeAllItems()
        for lbl in voices.values():
            self._voicePopup.addItemWithTitle_(lbl)
        self._voiceKeys = list(voices.keys())

    def comboBoxSelectionDidChange_(self, notification):
        """Called by NSComboBox when user selects an item (lang_to delegate)."""
        lang_to = str(self._langToField.stringValue())
        if lang_to:
            self._refreshVoicesForLang(lang_to)

    @objc.IBAction
    def playVoiceSample_(self, sender):
        """Preview the selected TTS voice with a short sample."""
        idx = self._voicePopup.indexOfSelectedItem()
        voice = self._voiceKeys[idx]
        self._sampleBtn.setEnabled_(False)
        self._sampleBtn.setTitle_("⏳")

        def _done(err):
            def _ui(_):
                self._sampleBtn.setEnabled_(True)
                self._sampleBtn.setTitle_("▶ Sample")
                if err:
                    self._showAlert("Błąd sampla", err)
            self._scheduleUI("_noop", _ui)
        tts_engine.generate_sample(voice, _done)

    @objc.IBAction
    def pickAudiobookEpub_(self, sender):
        """Let user pick any EPUB file for audiobook generation (independent of conversion)."""
        panel = NSOpenPanel.openPanel()
        panel.setTitle_("Wybierz plik EPUB")
        panel.setAllowedFileTypes_(["epub"])
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() == NSModalResponseOK:
            path = str(panel.URLs()[0].path())
            self._audiobookPickedEpub = path
            name = Path(path).name
            self._audiobookEpubLabel.setStringValue_(f"📖 {name}")

    @objc.IBAction
    def startAudiobook_(self, sender):
        """Generate audiobook from EPUB (picked, converted, or selected)."""
        # Priority: 1) manually picked EPUB, 2) conversion output, 3) selected file
        picked = getattr(self, '_audiobookPickedEpub', None)
        if picked and str(picked).endswith('.epub'):
            src = str(picked)
        else:
            src = getattr(self, '_outputPath', None)
            if not src or not str(src).endswith('.epub'):
                sel = getattr(self, '_selectedFile', None)
                if sel and str(sel).endswith('.epub'):
                    src = str(sel)
                else:
                    self._showAlert("Audiobook", "Wybierz plik EPUB — kliknij '📂 Wybierz EPUB' lub skonwertuj dokument.")
                    return

        # Extract chapter list and show selection dialog
        try:
            chapters = tts_engine.list_chapters(str(src))
        except Exception as e:
            self._showAlert("Błąd", str(e))
            return

        if not chapters:
            self._showAlert("Błąd", "EPUB nie zawiera rozdziałów.")
            return

        selected = self._showChapterSelector(chapters)
        if selected is None:  # user cancelled
            return

        idx = self._voicePopup.indexOfSelectedItem()
        voice = self._voiceKeys[idx]
        voice_name = list(tts_engine.VOICES.values())[idx]

        src_path = Path(str(src))
        out_dir = src_path.parent / f"{src_path.stem}_audiobook"

        self._audiobookBtn.setEnabled_(False)
        self._audiobookBtn.setTitle_("⏳ Generuję…")
        self._progressBar.setDoubleValue_(0)
        self._progressBar.setHidden_(False)
        self._stageLabel.setStringValue_(f"🎙 Audiobook: {voice_name} ({len(selected)}/{len(chapters)} rozdziałów)")
        self._stageLabel.setHidden_(False)
        self._logScroll.setHidden_(False)
        self._appendLog(f"Audiobook: {src_path.name} → {out_dir.name}/ ({len(selected)}/{len(chapters)} rozdziałów)")
        self._audiobookOutputDir = str(out_dir)

        def _progress(cur, total, msg):
            pct = (cur / total * 100) if total else 0
            self._scheduleUI("_updateAudiobookProgress", {"pct": pct, "msg": msg})

        def _run():
            try:
                paths = tts_engine.generate_audiobook(
                    epub_path=str(src),
                    voice=voice,
                    output_dir=str(out_dir),
                    progress_cb=_progress,
                    selected_chapters=selected,
                )
                self._scheduleUI("_audiobookDone", len(paths))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._scheduleUI("_audiobookError", str(e))

        threading.Thread(target=_run, daemon=True).start()

    @objc.python_method
    def _showChapterSelector(self, chapters):
        """Show chapter selection dialog. Returns list of selected indices or None if cancelled."""
        from AppKit import (NSAlert, NSScrollView, NSView, NSButton,
                          NSMakeRect, NSSwitchButton, NSAlertFirstButtonReturn)

        alert = NSAlert.alloc().init()
        alert.setMessageText_("📋 Wybierz rozdziały")
        alert.setInformativeText_(f"Znaleziono {len(chapters)} rozdziałów. Odznacz te, których nie chcesz w audiobooku.")
        alert.addButtonWithTitle_("🎧 Generuj")
        alert.addButtonWithTitle_("Anuluj")

        # Container view
        h_per_row = 22
        max_visible = min(len(chapters), 15)
        view_h = max_visible * h_per_row + 40  # +40 for Select All button
        container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 400, view_h))

        # Select All / Deselect All toggle
        toggle = NSButton.alloc().initWithFrame_(NSMakeRect(0, view_h - 28, 200, 24))
        toggle.setButtonType_(NSSwitchButton)
        toggle.setTitle_("Zaznacz / Odznacz wszystkie")
        toggle.setState_(1)  # checked
        container.addSubview_(toggle)

        # Scrollable area for chapters
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 400, view_h - 36))
        inner_h = len(chapters) * h_per_row
        inner = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 380, inner_h))

        checkboxes = []
        for i, ch in enumerate(chapters):
            y = inner_h - (i + 1) * h_per_row
            words = len(ch.text.split())
            label = f"{i+1}. {ch.title[:50]}  (~{words} słów)"
            cb = NSButton.alloc().initWithFrame_(NSMakeRect(4, y, 370, 20))
            cb.setButtonType_(NSSwitchButton)
            cb.setTitle_(label)
            cb.setState_(1)
            inner.addSubview_(cb)
            checkboxes.append(cb)

        scroll.setDocumentView_(inner)
        scroll.setHasVerticalScroller_(True)
        container.addSubview_(scroll)

        # Wire toggle to all checkboxes
        class ToggleTarget(NSObject):
            def toggleAll_(self, sender):
                state = sender.state()
                for cb in checkboxes:
                    cb.setState_(state)
        toggle_target = ToggleTarget.alloc().init()
        toggle.setTarget_(toggle_target)
        toggle.setAction_(objc.selector(toggle_target.toggleAll_, signature=b'v@:@'))

        alert.setAccessoryView_(container)

        result = alert.runModal()
        if result != NSAlertFirstButtonReturn:
            return None

        selected = [chapters[i].index for i, cb in enumerate(checkboxes) if cb.state()]
        if not selected:
            self._showAlert("Audiobook", "Nie wybrano żadnych rozdziałów.")
            return None

        return selected

    @objc.IBAction
    def openAudiobookFolder_(self, sender):
        folder = getattr(self, '_audiobookOutputDir', None)
        if folder:
            import subprocess
            subprocess.Popen(["open", folder])

    @objc.IBAction
    def stopConversion_(self, sender):
        """User clicked Stop — set cancel flag and kill any running subprocess."""
        self._cancelFlag = True
        self._stageLabel.setStringValue_("⛔ Zatrzymywanie…")
        self._appendLog("⛔ Zatrzymywanie konwersji…")

    @objc.python_method
    def _runConversion(self, path, fmt, use_llm, translate, translate_images, lang_from, lang_to, page_start=0, page_end=0, verify=False):
        import converter
        try:
            # Pass cancel_flag checker as part of progress callback
            def _progress_with_cancel(stage, pct, msg):
                if self._cancelFlag:
                    raise InterruptedError("⛔ Konwersja zatrzymana przez użytkownika")
                self._onProgress(stage, pct, msg)

            # ── PDF → PDF layout-preserving translation ──────────────────────
            if fmt == "pdf" and use_llm and translate:
                result = converter.translate_pdf(
                    input_path=path,
                    lang_from=lang_from,
                    lang_to=lang_to,
                    page_start=page_start,
                    page_end=page_end,
                    progress_callback=_progress_with_cancel,
                )
            else:
                result = converter.convert_file(
                    input_path=path,
                    output_format=fmt,
                    use_llm=use_llm,
                    use_translate=translate,
                    translate_images=translate_images,
                    verify_translation=verify,
                    lang_from=lang_from,
                    lang_to=lang_to,
                    progress_callback=_progress_with_cancel,
                    page_start=page_start,
                    page_end=page_end,
                )
            self._scheduleUI("_conversionDone", result)
        except InterruptedError:
            self._scheduleUI("_conversionCancelled", None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._scheduleUI("_conversionError", str(e))


    @objc.python_method
    def _onProgress(self, stage, pct, msg):
        self._scheduleUI("_updateProgress", {"stage": stage, "pct": pct, "msg": msg})

    @objc.python_method
    def _scheduleUI(self, method, data):
        self._ui_queue.put((method, data))
        self.performSelectorOnMainThread_withObject_waitUntilDone_("processQueue:", None, False)

    @objc.IBAction
    def processQueue_(self, _):
        while not self._ui_queue.empty():
            method, data = self._ui_queue.get_nowait()
            getattr(self, method)(data)

    @objc.python_method
    def _updateProgress(self, info):
        stage, pct, msg = info["stage"], info["pct"], info["msg"]
        total = 100
        if stage == "ocr":           total = pct * 0.4
        elif stage == "correction":  total = 40 + pct * 0.3
        elif stage == "verification":total = 70 + pct * 0.1
        elif stage == "images":      total = 80 + pct * 0.1
        elif stage == "export":      total = 90 + pct * 0.1
        elif stage == "translate_pdf": total = pct          # full 0-100
        elif stage == "done":        total = 100
        self._progressBar.setDoubleValue_(total)
        self._progressBar.displayIfNeeded()
        self._stageLabel.setStringValue_(msg)
        self._appendLog(msg)

    @objc.python_method
    def _appendLog(self, msg):
        import time
        line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
        storage = self._logText.textStorage()
        storage.beginEditing()
        storage.appendAttributedString_(NSAttributedString.alloc().initWithString_(line))
        storage.endEditing()
        self._logText.scrollRangeToVisible_(NSMakeRange(storage.length(), 0))

    @objc.python_method
    def _noop(self, fn):
        """Utility: run arbitrary callable on main thread."""
        if callable(fn):
            fn(None)

    @objc.python_method
    def _updateAudiobookProgress(self, info):
        self._progressBar.setDoubleValue_(info["pct"])
        self._progressBar.displayIfNeeded()
        self._stageLabel.setStringValue_(info["msg"])
        self._appendLog(info["msg"])

    @objc.python_method
    def _audiobookDone(self, count):
        self._audiobookBtn.setEnabled_(True)
        self._audiobookBtn.setTitle_("🎧 Generuj audiobook")
        self._progressBar.setDoubleValue_(100)
        self._stageLabel.setStringValue_(f"✅ Audiobook gotowy! {count} rozdziałów.")
        self._audiobookResultBtn.setHidden_(False)
        self._appendLog(f"✅ Audiobook: {count} plików MP3 + playlist.m3u")

    @objc.python_method
    def _audiobookError(self, err):
        self._audiobookBtn.setEnabled_(True)
        self._audiobookBtn.setTitle_("🎧 Generuj audiobook")
        self._stageLabel.setStringValue_(f"❌ Błąd: {err[:80]}")
        self._showAlert("Błąd audiobooka", err)

    @objc.python_method
    def _conversionDone(self, output_path):
        self._outputPath = output_path
        self._converting = False
        self._convertBtn.setEnabled_(True)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._stopBtn.setHidden_(True)
        self._progressBar.setDoubleValue_(100)
        self._stageLabel.setStringValue_(t("done"))
        self._resultView.setHidden_(False)
        self._appendLog(t("all_done", name=Path(output_path).name))
        # Update audiobook panel EPUB source label when conversion produces EPUB
        if str(output_path).endswith('.epub'):
            self._audiobookResultBtn.setHidden_(True)
            name = Path(output_path).name
            self._audiobookEpubLabel.setStringValue_(f"📖 {name}")
            self._audiobookPickedEpub = None  # prefer conversion output

    @objc.python_method
    def _conversionCancelled(self, _):
        self._converting = False
        self._convertBtn.setEnabled_(True)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._stopBtn.setHidden_(True)
        self._progressBar.setHidden_(True)
        self._stageLabel.setStringValue_("⛔ Konwersja zatrzymana")
        self._appendLog("⛔ Konwersja zatrzymana przez użytkownika")

    @objc.python_method
    def _conversionError(self, error_msg):
        self._converting = False
        self._convertBtn.setEnabled_(True)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._stopBtn.setHidden_(True)
        self._progressBar.setHidden_(True)
        self._stageLabel.setStringValue_(f"{t('error_prefix')}: {error_msg}")
        self._appendLog(f"{t('error_prefix')}: {error_msg}")
        alert = NSAlert.alloc().init()
        alert.setMessageText_(t("error_title"))
        alert.setInformativeText_(str(error_msg)[:500])
        alert.setAlertStyle_(NSAlertStyleWarning)
        alert.runModal()

    @objc.IBAction
    def saveResult_(self, sender):
        if not self._outputPath: return
        src = Path(self._outputPath)
        panel = NSSavePanel.savePanel()
        panel.setTitle_(t("save_title"))
        panel.setNameFieldStringValue_(src.name)
        if panel.runModal() == NSModalResponseOK:
            dest = panel.URL().path()
            shutil.copy2(str(src), dest)

    @objc.IBAction
    def revealInFinder_(self, sender):
        if not self._outputPath: return
        from AppKit import NSWorkspace, NSURL
        url = NSURL.fileURLWithPath_(str(self._outputPath))
        NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([url])

    @objc.IBAction
    def sendKindle_(self, sender):
        if not self._outputPath: return
        cfg = load_config()
        src = Path(self._outputPath)

        if cfg.get("kindle_email") and cfg.get("smtp_email") and cfg.get("smtp_pass"):
            try:
                msg = EmailMessage()
                msg["Subject"] = "Convert"
                msg["From"] = cfg["smtp_email"]
                msg["To"] = cfg["kindle_email"]
                msg.set_content(f"Przesyłam: {src.name}")
                with open(src, "rb") as f:
                    msg.add_attachment(f.read(), maintype="application", subtype="epub+zip", filename=src.name)
                with smtplib.SMTP("smtp.gmail.com", 587) as s:
                    s.starttls()
                    s.login(cfg["smtp_email"], cfg["smtp_pass"])
                    s.send_message(msg)
                self._showAlert("✅", t("kindle_sent"))
                return
            except Exception as e:
                self._showAlert(t("kindle_error"), str(e))
                return

        kindle = Path("/Volumes/Kindle/documents")
        if kindle.exists():
            shutil.copy2(str(src), kindle / src.name)
            self._showAlert("✅", t("kindle_sent"))
        else:
            self._showAlert(t("kindle_error"), t("kindle_no_config"))

    @objc.python_method
    def _showAlert(self, title, msg):
        a = NSAlert.alloc().init()
        a.setMessageText_(title)
        a.setInformativeText_(msg)
        a.runModal()

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    # Explicitly set app icon — when launched via os.execv from venv Python,
    # macOS doesn't pick up the bundle's CFBundleIconFile automatically
    icon_path = Path(__file__).parent.parent / "AppIcon.icns"
    if icon_path.exists():
        icon_image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
        if icon_image:
            app.setApplicationIconImage_(icon_image)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()

if __name__ == "__main__":
    main()
