# 📚 ReBook — AI-Powered PDF/EPUB Converter

<p align="center">
  <strong>Translate and convert e-books with state-of-the-art AI</strong><br>
  Translation • Correction • OCR • macOS • Windows • Linux • 27 Languages
</p>

---

## ✨ Features

- 🔄 **Format conversion** — PDF → EPUB, EPUB → EPUB/Markdown/HTML
- 🤖 **AI translation** — Gemini 3, GPT-5, Claude 4.6, Mistral, GLM, Groq
- 📖 **PDF OCR** — Marker OCR extracts text from scans (optional)
- 📧 **Send to Kindle** — one-click delivery via email or USB
- 🌍 **27 languages** — UI auto-detects your system language
- ⚡ **30 parallel threads** — translate entire books in minutes
- 🔁 **Auto-retry** — failed segments are automatically retried (up to 3 rounds)
- ⛔ **Stop button** — cancel running conversions at any time
- 🎨 **Language ComboBox** — pick from 27 languages with autocomplete

## 📦 Installation

### 🍎 macOS

1. Download **[ReBook.dmg](https://github.com/realtek1990/rebook/releases/latest/download/ReBook.dmg)** (2.8 MB)
2. Open the DMG and drag **ReBook** to **Applications**
3. **First launch**: Right-click → **Open** → click **Open** in the Gatekeeper dialog
4. The setup wizard will guide you through dependency installation

> ⚠️ **Gatekeeper**: Since ReBook is not notarized, macOS may show a warning. Right-click → Open to bypass. Or run:
> ```bash
> xattr -cr /Applications/ReBook.app
> ```

### 🪟 Windows

1. Download **[ReBook-Windows-Installer.exe](https://github.com/realtek1990/rebook/releases/latest/download/ReBook-Windows-Installer.exe)** (106 MB)
2. Run the installer — it creates a desktop shortcut and start menu entry
3. Launch **ReBook** and configure your AI API key in **⚙️ Settings**

> 💡 All dependencies are bundled inside the .exe — no Python or pip required.

### 🐧 Linux

1. Download **[ReBook-Linux](https://github.com/realtek1990/rebook/releases/latest/download/ReBook-Linux)**
2. Make it executable and run:
   ```bash
   chmod +x ReBook-Linux
   ./ReBook-Linux
   ```
3. Configure your AI API key in **⚙️ Settings**

> 💡 Requires `python3-tk` for GUI. Install if missing:
> ```bash
> # Debian/Ubuntu
> sudo apt install python3-tk
> # Fedora
> sudo dnf install python3-tkinter
> # Arch
> sudo pacman -S tk
> ```

### Installation Options (first launch)

| Option | Size | Capabilities |
|--------|------|-------------|
| **⚡ Light** | ~100 MB | EPUB ↔ EPUB/MD/HTML + AI + Kindle |
| **📦 Full** | ~1.2 GB | Everything + PDF OCR (Marker + PyTorch) |

> 💡 Marker OCR can be installed later from **⚙️ Settings** without reinstalling the app.

### System Requirements

| Platform | Requirements |
|----------|-------------|
| 🍎 macOS | 11.0+ (Big Sur+), Apple Silicon or Intel, Python 3.9+ |
| 🪟 Windows | 10/11, 64-bit, no additional dependencies |
| 🐧 Linux | Ubuntu 20.04+ / Fedora 36+ / Arch, python3-tk |
| 🔑 All | API key from any supported AI provider |

## 🚀 Usage

1. Launch **ReBook**
2. Click ⚙️ **Settings** and configure:
   - AI provider (e.g. Google Gemini)
   - Model (e.g. `gemini-3-flash-preview`)
   - API key
3. Drag a PDF/EPUB file onto the window (or click to browse)
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

Auto-detected from your system language:

🇵🇱 Polski • 🇬🇧 English • 🇩🇪 Deutsch • 🇪🇸 Español • 🇫🇷 Français • 🇵🇹 Português • 🇮🇹 Italiano • 🇳🇱 Nederlands • 🇨🇿 Čeština • 🇸🇰 Slovenčina • 🇺🇦 Українська • 🇷🇺 Русский • 🇭🇺 Magyar • 🇷🇴 Română • 🇭🇷 Hrvatski • 🇷🇸 Srpski • 🇹🇷 Türkçe • 🇸🇪 Svenska • 🇳🇴 Norsk • 🇩🇰 Dansk • 🇫🇮 Suomi • 🇨🇳 中文 • 🇯🇵 日本語 • 🇻🇳 Tiếng Việt • 🇹🇭 ไทย • 🇸🇦 العربية • 🇮🇷 فارسی

## 📁 Project Structure

```
rebook/
├── ReBook.app/                   # Native macOS application
│   └── Contents/Resources/app/
│       ├── native_gui.py         # macOS GUI (Cocoa/AppKit)
│       ├── converter.py          # Conversion pipeline
│       ├── corrector.py          # AI engine (LiteLLM)
│       ├── image_translator.py   # AI image translation
│       └── i18n.py               # 27-language translations
├── windows/
│   ├── rebook_win.py             # Windows GUI (CustomTkinter)
│   ├── installer.iss             # Inno Setup script
│   └── BUILD_INSTRUCTIONS_WIN.md
├── linux/
│   ├── rebook_linux.py           # Linux GUI (CustomTkinter)
│   └── dist/                     # Build artifacts
├── assets/
│   └── icon.ico                  # Multi-resolution app icon
├── .github/workflows/
│   └── build_windows.yml         # CI: builds all 3 platforms
├── build_dmg.sh                  # macOS DMG builder
├── sync_backend.sh               # Sync backend across platforms
└── README.md
```

## ⚙️ Advanced Configuration

Settings are stored in:
- **macOS**: `~/.pdf2epub-app/config.json`
- **Windows/Linux**: `~/.rebook/config.json`

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

### Install Marker OCR separately

```bash
# macOS
~/.pdf2epub-app/env/bin/pip install marker-pdf

# Windows/Linux
~/.rebook/env/bin/pip install marker-pdf
```

## 📄 License

MIT License — see [LICENSE](LICENSE)
