# 📚 ReBook — AI-Powered PDF/EPUB Converter

<p align="center">
  <strong>Translate and convert e-books with state-of-the-art AI</strong><br>
  Translation • Correction • OCR • macOS • Windows • Linux • BSD • Android • 27 Languages
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

### 🤖 Android

1. Download **[ReBook.apk](https://github.com/realtek1990/rebook/releases/latest/download/ReBook.apk)** (~60 MB)
2. On your phone: **Settings → Security → Install from unknown sources** → enable for your browser
3. Open the downloaded APK and tap **Install**
4. Launch **ReBook** and configure your AI API key in **⚙️ Settings**

> 💡 Uses **Google ML Kit** for on-device PDF OCR — works offline, no additional downloads, supports 100+ languages.

### 👾 BSD (FreeBSD / OpenBSD / NetBSD)

1. Install Python 3 and Tk:
```bash
# FreeBSD
pkg install python3 py39-tkinter
# OpenBSD
pkg_add python3 py3-tkinter
# NetBSD
pkgin install python39 py39-tkinter
```
2. Clone the repo and run:
```bash
git clone https://github.com/realtek1990/rebook.git
cd rebook/bsd
python3 rebook_bsd.py
```

> 💡 BSD port uses `sysctl hw.physmem` for RAM detection. All other features are identical to Linux.

### Installation Options (desktop, first launch)

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
| 👾 BSD | FreeBSD 13+ / OpenBSD 7+ / NetBSD, python3-tk |
| 🤖 Android | 8.0+ (API 26+), ~60 MB, ML Kit OCR (built-in) |
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
├── bsd/
│   ├── rebook_bsd.py             # BSD GUI (sysctl RAM, POSIX paths)
│   └── dist/                     # Backend (corrector, converter, i18n)
├── android/                       # 🤖 Native Android app
│   ├── app/src/main/java/com/rebook/app/
│   │   ├── domain/               # Converter, Corrector, OcrEngine, EpubWriter
│   │   ├── ui/                   # Compose screens (Home, Settings)
│   │   └── data/                 # AppConfig (DataStore)
│   ├── app/src/main/res/         # strings.xml (EN, PL), icons
│   └── build.gradle.kts          # Gradle config
├── assets/
│   └── icon.ico                  # Multi-resolution app icon
├── .github/workflows/
│   └── build_windows.yml         # CI: builds all 5 platforms
├── build_dmg.sh                  # macOS DMG builder
├── sync_backend.sh               # Sync backend across platforms
└── README.md
```

## ⚙️ Advanced Configuration

Settings are stored in:
- **macOS**: `~/.pdf2epub-app/config.json`
- **Windows/Linux**: `~/.rebook/config.json`
- **Android**: `DataStore` (internal app storage, encrypted)

```json
{
  "llm_provider": "gemini",
  "model_name": "gemini-3-flash-preview",
  "api_key": "YOUR_GEMINI_API_KEY",
  "kindle_email": "your-kindle@kindle.com",
  "smtp_email": "your@gmail.com",
  "smtp_pass": "app-password",

  "ocr_provider": "auto",
  "ocr_api_key": "YOUR_MISTRAL_API_KEY",
  "ocr_model": "mistral-ocr-latest"
}
```

> `ocr_provider`: `"auto"` | `"mistral"` | `"gemini"` | `"marker"`  
> `ocr_api_key`: leave empty to reuse the main `api_key`

### Install Marker OCR separately

```bash
# macOS
~/.pdf2epub-app/env/bin/pip install marker-pdf

# Windows/Linux
~/.rebook/env/bin/pip install marker-pdf
```

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🔐 Code Signing Policy

Free code signing provided by [SignPath.io](https://about.signpath.io),  
certificate by [SignPath Foundation](https://signpath.org).

**Team roles:**
- Committers & Approvers: [Owners](https://github.com/realtek1990/rebook)

**Privacy Policy:**  
ReBook does not transfer any information to networked systems unless explicitly requested by the user.

- **API keys** entered in Settings are stored locally (`config.json` / Android DataStore) and sent only to the AI provider selected by the user (Gemini, Mistral, OpenAI, etc.).
- **OCR keys** (Mistral OCR, Gemini) are sent only to the respective API endpoint during PDF processing.
- **No telemetry**, no analytics, no tracking of any kind.
- Files being converted are processed locally (Marker OCR) or sent to the cloud OCR API only if the user has configured and selected a cloud OCR provider.
