# 📖 ReBook

**AI-powered book translator & OCR corrector.**  
Drop a PDF or EPUB, get a polished, Kindle-ready e-book in any language — in minutes.

ReBook extracts text from your book, sends it through an AI language model for translation or OCR correction, and assembles a clean EPUB with cover art, table of contents, and proper chapter structure.

---

## ✨ Features

- **Translate entire books** between 30+ languages with literary quality
- **Fix OCR errors** in scanned PDFs — split words, broken punctuation, encoding artifacts
- **Multi-provider AI** — Google Gemini (default), OpenAI, Mistral, Grok, or any OpenAI-compatible API
- **Blazing fast** — 30 parallel API threads translate a 400-page book in ~3 minutes
- **Preserves structure** — cover images, chapter breaks, Markdown formatting
- **Cleans artifacts** — strips XML declarations, HTML tags, DOCTYPE junk from source files
- **PDF & EPUB input** — uses [Marker](https://github.com/VikParuchuri/marker) for PDF OCR

---

## 🚀 Quick Start

```bash
# 1. Clone & install
git clone https://github.com/youruser/rebook.git
cd rebook
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env and add your Gemini API key

# 3. Translate a book
python3 rebook.py book.epub translated.epub --mode translate --lang-from en --lang-to pl

# 4. Fix OCR errors in a scanned PDF
python3 rebook.py scan.pdf corrected.epub --mode correct
```

---

## 📋 Usage

```
python3 rebook.py INPUT OUTPUT [options]

positional arguments:
  input_file          Input PDF or EPUB file
  output_epub         Output EPUB file path

options:
  --mode {correct,translate}   Mode: 'correct' or 'translate' (default: correct)
  --lang-to LANG               Target language code (default: pl)
  --lang-from LANG             Source language code (default: auto-detect)
  --provider PROVIDER          LLM provider: gemini, openai, mistral, grok, custom
  --model MODEL                Override model name
  --base-url URL               Custom API endpoint (for 'custom' provider)
  --workers N                  Parallel API threads (default: 30)
  --title TITLE                EPUB title
  --author AUTHOR              EPUB author
  --marker-cmd CMD             Marker OCR command path (default: marker_single)
```

### Examples

```bash
# English -> Polish with Gemini (default)
python3 rebook.py book.epub book_pl.epub --mode translate --lang-from en --lang-to pl

# English -> Spanish with Mistral Magistral
python3 rebook.py book.epub book_es.epub --mode translate --lang-to es --provider mistral

# English -> German with OpenAI GPT-4o
python3 rebook.py book.epub book_de.epub --mode translate --lang-to de --provider openai --model gpt-4o

# OCR correction (no translation)
python3 rebook.py scanned.pdf fixed.epub --mode correct

# Use a local Ollama model
python3 rebook.py book.epub out.epub --mode translate --provider custom \
  --base-url http://localhost:11434/v1/chat/completions --model llama3
```

---

## 🤖 Supported Providers

| Provider | Flag | Default Model | Env Variable |
|---|---|---|---|
| **Google Gemini** | `--provider gemini` | `gemini-3-flash-preview` | `GEMINI_API_KEY` |
| **OpenAI** | `--provider openai` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| **Mistral** | `--provider mistral` | `magistral-medium-latest` | `MISTRAL_API_KEY` |
| **xAI (Grok)** | `--provider grok` | `grok-3-fast` | `XAI_API_KEY` |
| **Custom** | `--provider custom` | — | `LLM_API_KEY` + `LLM_BASE_URL` |

### Why we recommend Gemini 3 Flash

We benchmarked five models on the same book passage (literary prose, EN→PL):

| Model | Speed | Paragraphs | Literary Quality | Cost (400p book) |
|---|---|---|---|---|
| **Gemini 3.0 Flash** | **9.7s** ⭐ | ✅ Preserved | ⭐⭐⭐⭐⭐ | **~$0.10** |
| Grok 4.1 Fast | 15.9s | ❌ Broken | ⭐⭐⭐ | ~$3.85 |
| Gemini 2.5 Flash | 16.9s | ✅ Preserved | ⭐⭐⭐ | ~$0.15 |
| Magistral Medium | 70.2s | ✅ Preserved | ⭐⭐⭐⭐ | ~$1.54 |
| Kimi K2.5 | 97.4s | ✅ Preserved | ⭐⭐⭐⭐⭐ | plan-based |

**Gemini 3.0 Flash** delivers the best combination of speed, quality, and cost:
- **Fastest** — 9.7s per block (entire book in ~3 min with 30 threads)
- **Cheapest** — ~$0.10 for a full 400-page book (~380K tokens)
- **Best literary quality** — natural phrasing, no paraphrasing, preserves paragraph structure
- **No censorship issues** on standard literary content
- **Zero rate-limit problems** at 30 concurrent requests

Grok is fast but breaks paragraph structure (inserts line breaks between sentences). Magistral has excellent quality but is 7× slower. Kimi K2.5 matches Gemini's quality but burns 4.4× more tokens due to internal reasoning.

---

## 🌍 Supported Languages

ReBook supports translation between any languages supported by the underlying LLM. Pre-configured language codes:

`pl` `en` `de` `fr` `es` `it` `pt` `nl` `cs` `sk` `uk` `ru` `ja` `ko` `zh` `ar` `tr` `sv` `da` `no` `fi` `hu` `ro` `bg` `hr` `el` `he` `th` `vi` `id` `ms` `hi`

You can also use full language names: `--lang-to "Brazilian Portuguese"`

---

## 📦 Requirements

```
pip install -r requirements.txt
```

Core dependencies: `markdown`, `EbookLib`, `beautifulsoup4`, `markdownify`, `python-dotenv`

For PDF input, you also need [Marker](https://github.com/VikParuchuri/marker):
```
pip install marker-pdf
```

---

## 📝 License

MIT
