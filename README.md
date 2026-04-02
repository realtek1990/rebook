# 📚 ReBook — AI-Powered PDF/EPUB Converter

<p align="center">
  <strong>Konwerter plików PDF i EPUB ze wsparciem sztucznej inteligencji</strong><br>
  Tłumaczenie • Korekta • OCR • Natywny macOS
</p>

---

## ✨ Funkcje

- 🔄 **Konwersja formatów** — PDF → EPUB, EPUB → EPUB/Markdown/HTML
- 🤖 **Tłumaczenie AI** — Gemini 3, GPT-5, Claude 4.6, Mistral, GLM i inne
- 📖 **OCR z PDF** — Marker OCR rozpoznaje tekst ze skanów (opcjonalne)
- 📧 **Send-to-Kindle** — wyślij książkę prosto na czytnik
- 🎨 **Natywny interfejs macOS** — Cocoa/AppKit, drag & drop, dark mode
- ⚡ **30 wątków równolegle** — błyskawiczne tłumaczenie całych książek
- 🔁 **Auto-retry** — nieudane segmenty są automatycznie ponawiane

## 📦 Instalacja

### Szybka instalacja (Terminal)

```bash
git clone https://github.com/realtek1990/rebook.git
cd rebook
./install.sh
```

Instalator zapyta Cię o komponenty:

| Opcja | Rozmiar | Możliwości |
|-------|---------|------------|
| **Lekka** | ~100 MB | EPUB ↔ EPUB/MD/HTML + AI + Kindle |
| **Pełna** | ~1.2 GB | Wszystko + OCR z PDF (Marker + PyTorch) |

> 💡 **Marker OCR** można doinstalować później bez reinstalacji całej aplikacji.

### Wymagania

- macOS 12+ (Monterey lub nowszy)
- Python 3.9+
- Klucz API jednego z dostawców AI (Gemini, OpenAI, Anthropic, Mistral...)

## 🚀 Użycie

1. Uruchom **ReBook** z Launchpada lub: `open /Applications/ReBook.app`
2. Kliknij ⚙️ **Ustawienia** i skonfiguruj:
   - Dostawcę AI (np. Google Gemini)
   - Model (np. `gemini-3-flash-preview`)
   - Klucz API
3. Przeciągnij plik PDF/EPUB na okno
4. Wybierz format wyjściowy i kliknij **🚀 Konwertuj**

### Obsługiwane modele AI

| Dostawca | Modele |
|----------|--------|
| **Google Gemini** | `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-2.5-pro` |
| **OpenAI** | `gpt-5-preview`, `gpt-4.5-preview`, `gpt-4o`, `o3-mini` |
| **Anthropic** | `claude-4.6-opus`, `claude-3-7-sonnet-latest` |
| **Mistral** | `mistral-large-latest`, `mistral-medium` |
| **ZhipuAI** | `glm-4-plus`, `glm-4-flash` |
| **Groq** | `llama-3.3-70b-versatile`, `deepseek-r1-distill-llama-70b` |

## 📁 Struktura projektu

```
rebook/
├── install.sh                    # Instalator z wyborem komponentów
├── PDF-Converter.app/            # Natywna aplikacja macOS
│   └── Contents/
│       ├── MacOS/PDF Converter   # Launcher
│       └── Resources/app/
│           ├── native_gui.py     # GUI (Cocoa/AppKit)
│           ├── converter.py      # Pipeline konwersji
│           └── corrector.py      # Silnik AI (LiteLLM)
├── requirements.txt              # Zależności Python
└── README.md
```

## ⚙️ Konfiguracja zaawansowana

Konfiguracja jest zapisywana w `~/.pdf2epub-app/config.json`:

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

### Doinstalowanie Marker OCR później

```bash
source ~/.pdf2epub-app/env/bin/activate
pip install marker-pdf
```

## 📄 Licencja

MIT License — zobacz [LICENSE](LICENSE)
