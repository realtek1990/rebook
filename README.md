# 📚 ReBook — AI-Powered PDF/EPUB Converter

<p align="center">
  <strong>Translate and convert e-books with state-of-the-art AI</strong><br>
  Translation • Correction • OCR • Native macOS • 27 Languages
</p>

---

## ✨ Features

- 🔄 **Format conversion** — PDF → EPUB, EPUB → EPUB/Markdown/HTML
- 🤖 **AI translation** — Gemini 3, GPT-5, Claude 4.6, Mistral, GLM, Groq
- 📖 **PDF OCR** — Marker OCR extracts text from scans (optional)
- 📧 **Send to Kindle** — one-click delivery via email or USB
- 🎨 **Native macOS GUI** — Cocoa/AppKit, drag & drop
- ⚡ **30 parallel threads** — translate entire books in minutes
- 🔁 **Auto-retry** — failed segments are automatically retried (up to 3 rounds)
- 🌍 **27 languages** — UI auto-detects your system language

## 📦 Installation

### Download (recommended)

1. Download **[ReBook.dmg](https://github.com/realtek1990/rebook/releases/latest/download/ReBook.dmg)** (2.8 MB)
2. Open the DMG and drag **ReBook** to **Applications**
3. **First launch**: Right-click (or Control+click) ReBook → **Open** → click **Open** in the dialog
4. The setup wizard will guide you through dependency installation

> ⚠️ **macOS Gatekeeper**: Since ReBook is not signed with an Apple Developer certificate, macOS may show a warning on first launch. Use Right-click → Open to bypass this. Alternatively, run in Terminal:
> ```bash
> xattr -cr /Applications/ReBook.app
> ```

On first launch, choose your installation type:

| Option | Size | Capabilities |
|--------|------|-------------|
| **⚡ Light** | ~100 MB | EPUB ↔ EPUB/MD/HTML + AI + Kindle |
| **📦 Full** | ~1.2 GB | Everything + PDF OCR (Marker + PyTorch) |

> 💡 Marker OCR can be installed later without reinstalling the app.

### System Requirements

- macOS 11.0+ (Big Sur or later), Apple Silicon or Intel
- Python 3.9+ ([Homebrew](https://brew.sh) recommended)
- API key from any supported AI provider

## 🚀 Usage

1. Launch **ReBook** from Launchpad or Applications
2. Click ⚙️ **Settings** and configure:
   - AI provider (e.g. Google Gemini)
   - Model (e.g. `gemini-3-flash-preview`)
   - API key
3. Drag a PDF/EPUB file onto the window
4. Choose output format and click **🚀 Convert**

### Supported AI Models

| Provider | Models |
|----------|--------|
| **Google Gemini** | `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-2.5-pro` |
| **OpenAI** | `gpt-5-preview`, `gpt-4.5-preview`, `gpt-4o`, `o3-mini` |
| **Anthropic** | `claude-4.6-opus`, `claude-3-7-sonnet-latest` |
| **Mistral** | `mistral-large-latest`, `mistral-medium` |
| **ZhipuAI** | `glm-4-plus`, `glm-4-flash` |
| **Groq** | `llama-3.3-70b-versatile`, `deepseek-r1-distill-llama-70b` |

## 🌍 Supported Interface Languages

Auto-detected from your macOS system language:

🇵🇱 Polski • 🇬🇧 English • 🇩🇪 Deutsch • 🇪🇸 Español • 🇫🇷 Français • 🇵🇹 Português • 🇮🇹 Italiano • 🇳🇱 Nederlands • 🇨🇿 Čeština • 🇸🇰 Slovenčina • 🇺🇦 Українська • 🇷🇺 Русский • 🇭🇺 Magyar • 🇷🇴 Română • 🇭🇷 Hrvatski • 🇷🇸 Srpski • 🇹🇷 Türkçe • 🇸🇪 Svenska • 🇳🇴 Norsk • 🇩🇰 Dansk • 🇫🇮 Suomi • 🇨🇳 中文 • 🇯🇵 日本語 • 🇻🇳 Tiếng Việt • 🇹🇭 ไทย • 🇸🇦 العربية • 🇮🇷 فارسی

## 📁 Project Structure

```
rebook/
├── ReBook.app/                   # Native macOS application
│   └── Contents/
│       ├── MacOS/ReBook          # Launcher + first-run installer
│       └── Resources/app/
│           ├── native_gui.py     # Main GUI (Cocoa/AppKit)
│           ├── converter.py      # Conversion pipeline
│           ├── corrector.py      # AI engine (LiteLLM)
│           └── i18n.py           # 27-language translations
├── build_dmg.sh                  # Build distributable DMG
├── requirements.txt              # Python dependencies
└── README.md
```

## ⚙️ Advanced Configuration

Settings are stored in `~/.pdf2epub-app/config.json`:

```json
{
  "llm_provider": "gemini",
  "model_name": "gemini-3-flash-preview",
  "api_key": "YOUR_API_KEY",
  "kindle_email": "your-kindle@kindle.com",
  "smtp_email": "your@gmail.com",
  "smtp_pass": "app-password"
}
```

### Install Marker OCR later

```bash
~/.pdf2epub-app/env/bin/pip install marker-pdf
```

## 📄 License

MIT License — see [LICENSE](LICENSE)
