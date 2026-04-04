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

# ── Configuration ─────────────────────────────────────────────────────────────
WORKSPACE = Path.home() / ".pdf2epub-app"
CONFIG_FILE = WORKSPACE / "config.json"
WORKSPACE.mkdir(parents=True, exist_ok=True)

W, H = 660, 740
PAD = 24
CW = W - 2 * PAD

def _providers():
    return [
    (t("provider_none"), "Brak"),
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
    "mistral": ["mistral-large-latest", "mistral-medium", "pixtral-large-latest", "ministral-8b-latest", "ministral-3b-latest", "mistral-small-latest"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "zhipu": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "openai": ["gpt-5-preview", "gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "o3-mini", "o1", "o1-mini"],
    "anthropic": ["claude-4.6-opus", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest"],
    "gemini": ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-pro"],
    "zhipuai": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768"]
}

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
            self._settingsWindow = None
            self._dropView = None
            self._fileBadgeView = None
            self._convertBtn = None
            self._window = None
        return self

    def applicationDidFinishLaunching_(self, note):
        global _app_delegate
        _app_delegate = self
        import traceback
        _LOG = open("/tmp/rebook_crash.log", "w")
        try:
            _LOG.write("Building menu...\n"); _LOG.flush()
            self._buildMenu()
            _LOG.write("Building window...\n"); _LOG.flush()
            self._buildWindow()
            _LOG.write("Building settings sheet...\n"); _LOG.flush()
            self._buildSettingsSheet()
            _LOG.write("Activating...\n"); _LOG.flush()
            self._window.makeKeyWindow()
            NSApp.activateIgnoringOtherApps_(True)
            _LOG.write("Done!\n"); _LOG.flush()
        except Exception as e:
            _LOG.write(f"CRASH: {e}\n")
            traceback.print_exc(file=_LOG)
            _LOG.flush()
        finally:
            _LOG.close()

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
        title.setFrame_(NSMakeRect(PAD, top - 44, CW - 40, 28))
        cv.addSubview_(title)

        sub = _label(t("app_subtitle"), size=12, color=NSColor.secondaryLabelColor())
        sub.setFrame_(NSMakeRect(PAD, top - 62, CW, 16))
        cv.addSubview_(sub)

        gear = NSButton.alloc().initWithFrame_(NSMakeRect(W - PAD - 36, top - 48, 36, 36))
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

        top -= 76

        self._dropView = DropView.alloc().initWithFrame_(NSMakeRect(PAD, top - 120, CW, 120))
        cv.addSubview_(self._dropView)

        self._fileBadgeView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 120, CW, 120))
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
        
        top -= 130

        sep = NSBox.alloc().initWithFrame_(NSMakeRect(PAD, top, CW, 1))
        sep.setBoxType_(NSBoxSeparator)
        cv.addSubview_(sep)
        top -= 16

        optH = _label(t("options_header"), size=11, bold=True, color=NSColor.secondaryLabelColor())
        optH.setFrame_(NSMakeRect(PAD, top - 14, CW, 14))
        cv.addSubview_(optH)
        top -= 28

        fmtLabel = _label(t("format_label"), size=13)
        fmtLabel.setFrame_(NSMakeRect(PAD, top - 22, 140, 20))
        cv.addSubview_(fmtLabel)

        self._formatCtrl = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(PAD + 150, top - 24, 260, 26))
        self._formatCtrl.setSegmentCount_(3)
        for i, t in enumerate(FORMATS):
            self._formatCtrl.setLabel_forSegment_(t, i)
            self._formatCtrl.setWidth_forSegment_(80, i)
        self._formatCtrl.setSelectedSegment_(0)
        self._formatCtrl.setSegmentStyle_(NSSegmentStyleRounded)
        cv.addSubview_(self._formatCtrl)
        top -= 38

        self._aiCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 22, CW, 20))
        self._aiCheck.setButtonType_(NSSwitchButton)
        self._aiCheck.setTitle_(t("ai_check"))
        self._aiCheck.setState_(NSOnState)
        cv.addSubview_(self._aiCheck)
        top -= 30

        self._translateCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 22, CW, 20))
        self._translateCheck.setButtonType_(NSSwitchButton)
        self._translateCheck.setTitle_(t("translate_check"))
        self._translateCheck.setTarget_(self)
        self._translateCheck.setAction_("toggleTranslate:")
        cv.addSubview_(self._translateCheck)
        top -= 28

        self._translateImgCheck = NSButton.alloc().initWithFrame_(NSMakeRect(PAD + 20, top - 22, CW - 20, 20))
        self._translateImgCheck.setButtonType_(NSSwitchButton)
        self._translateImgCheck.setTitle_(t("translate_images_check"))
        self._translateImgCheck.setFont_(NSFont.systemFontOfSize_(11))
        self._translateImgCheck.setHidden_(True)
        cv.addSubview_(self._translateImgCheck)
        top -= 26

        self._langView = NSView.alloc().initWithFrame_(NSMakeRect(PAD, top - 60, CW, 56))
        self._langView.setHidden_(True)
        ll1 = _label(t("lang_from_label"), size=11, color=NSColor.secondaryLabelColor())
        ll1.setFrame_(NSMakeRect(0, 32, 110, 16))
        self._langView.addSubview_(ll1)
        self._langFromField = _textfield(t("lang_from_placeholder"))
        self._langFromField.setFrame_(NSMakeRect(112, 30, CW - 112, 22))
        self._langView.addSubview_(self._langFromField)
        ll2 = _label(t("lang_to_label"), size=11, color=NSColor.secondaryLabelColor())
        ll2.setFrame_(NSMakeRect(0, 4, 110, 16))
        self._langView.addSubview_(ll2)
        self._langToField = _textfield("polski")
        self._langToField.setStringValue_("polski")
        self._langToField.setFrame_(NSMakeRect(112, 2, CW - 112, 22))
        self._langView.addSubview_(self._langToField)
        cv.addSubview_(self._langView)
        top -= 68

        self._convertBtn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, top - 40, CW, 40))
        self._convertBtn.setBezelStyle_(NSBezelStyleRounded)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._convertBtn.setFont_(NSFont.systemFontOfSize_weight_(14, 0.3))
        self._convertBtn.setTarget_(self)
        self._convertBtn.setAction_("startConversion:")
        self._convertBtn.setKeyEquivalent_("\r")
        self._convertBtn.setEnabled_(False)
        cv.addSubview_(self._convertBtn)
        top -= 52

        self._progressBar = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(PAD, top - 6, CW, 6))
        self._progressBar.setStyle_(NSProgressIndicatorBarStyle)
        self._progressBar.setIndeterminate_(False)
        self._progressBar.setMinValue_(0)
        self._progressBar.setMaxValue_(100)
        self._progressBar.setDoubleValue_(0)
        self._progressBar.setHidden_(True)
        cv.addSubview_(self._progressBar)
        top -= 14

        self._stageLabel = _label("", size=12, color=NSColor.secondaryLabelColor())
        self._stageLabel.setFrame_(NSMakeRect(PAD, top - 16, CW, 16))
        self._stageLabel.setHidden_(True)
        cv.addSubview_(self._stageLabel)
        top -= 24

        self._logScroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(PAD, top - 150, CW, 150))
        self._logScroll.setBorderType_(NSBezelBorder)
        self._logScroll.setHasVerticalScroller_(True)
        self._logScroll.setHidden_(True)
        self._logText = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, CW - 16, 150))
        self._logText.setEditable_(False)
        self._logText.setFont_(NSFont.monospacedSystemFontOfSize_weight_(10, 0.0))
        self._logText.setTextColor_(NSColor.secondaryLabelColor())
        self._logText.setBackgroundColor_(NSColor.textBackgroundColor())
        self._logScroll.setDocumentView_(self._logText)
        cv.addSubview_(self._logScroll)
        top -= 158

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
        cv.addSubview_(self._resultView)

        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()


    @objc.python_method
    def _buildSettingsSheet(self):
        try:
            sw = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 440, 420), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
            sw.setTitle_(t("settings_title"))
            self._settingsWindow = sw
            
            sv = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 440, 420))
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
        if not show:
            self._translateImgCheck.setState_(NSOffState)

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
        self._convertBtn.setEnabled_(False)
        self._convertBtn.setTitle_(t("converting_btn"))
        self._resultView.setHidden_(True)
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
        use_llm = bool(self._aiCheck.state()) or translate
        lang_from = str(self._langFromField.stringValue()) if translate else ""
        lang_to = str(self._langToField.stringValue()) if translate else "polski"

        args = (str(self._selectedFile), fmt, use_llm, translate, translate_images, lang_from, lang_to)
        threading.Thread(target=self._runConversion, args=args, daemon=True).start()

    @objc.python_method
    def _runConversion(self, path, fmt, use_llm, translate, translate_images, lang_from, lang_to):
        import converter
        try:
            result = converter.convert_file(
                path, fmt, use_llm, translate, translate_images, lang_from, lang_to,
                progress_callback=self._onProgress,
            )
            self._scheduleUI("_conversionDone", result)
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
        if stage == "ocr": total = pct * 0.4
        elif stage == "correction": total = 40 + pct * 0.3
        elif stage == "verification": total = 70 + pct * 0.1
        elif stage == "images": total = 80 + pct * 0.1
        elif stage == "export": total = 90 + pct * 0.1
        elif stage == "done": total = 100
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
    def _conversionDone(self, output_path):
        self._outputPath = output_path
        self._converting = False
        self._convertBtn.setEnabled_(True)
        self._convertBtn.setTitle_(t("convert_btn"))
        self._progressBar.setDoubleValue_(100)
        self._stageLabel.setStringValue_(t("done"))
        self._resultView.setHidden_(False)
        self._appendLog(t("all_done", name=Path(output_path).name))

    @objc.python_method
    def _conversionError(self, error_msg):
        self._converting = False
        self._convertBtn.setEnabled_(True)
        self._convertBtn.setTitle_(t("convert_btn"))
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
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()

if __name__ == "__main__":
    main()
