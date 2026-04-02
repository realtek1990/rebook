"""ReBook — Internationalization (i18n) module.

Auto-detects macOS system language via NSLocale and provides
translated strings through a simple t("key") API.
Supports 25 languages with automatic fallback to English.
"""
import os

def _detect_language() -> str:
    try:
        from Foundation import NSLocale
        langs = NSLocale.preferredLanguages()
        if langs:
            return str(langs[0])[:2].lower()
    except Exception:
        pass
    for var in ("LANG", "LC_ALL", "LC_MESSAGES"):
        val = os.environ.get(var, "")
        if val:
            return val[:2].lower()
    return "en"

LANG = _detect_language()

# ── Helper to build compact multi-lang dicts ──────────────────────────────
# Format: { "key": {"pl": "...", "en": "...", "de": "...", ...} }

STRINGS = {
    # ═══════════════════════════════════════════════════════════════════
    #  INSTALLER
    # ═══════════════════════════════════════════════════════════════════
    "inst_title": {
        "pl": "📚 ReBook — Kreator instalacji",
        "en": "📚 ReBook — Setup Wizard",
        "de": "📚 ReBook — Installationsassistent",
        "es": "📚 ReBook — Asistente de instalación",
        "fr": "📚 ReBook — Assistant d'installation",
        "pt": "📚 ReBook — Assistente de instalação",
        "cs": "📚 ReBook — Průvodce instalací",
        "sk": "📚 ReBook — Sprievodca inštaláciou",
        "uk": "📚 ReBook — Майстер встановлення",
        "sv": "📚 ReBook — Installationsguide",
        "no": "📚 ReBook — Installasjonsveiviser",
        "nb": "📚 ReBook — Installasjonsveiviser",
        "zh": "📚 ReBook — 安装向导",
        "ja": "📚 ReBook — セットアップウィザード",
        "it": "📚 ReBook — Installazione guidata",
        "sr": "📚 ReBook — Чаробњак за инсталацију",
        "ru": "📚 ReBook — Мастер установки",
        "hr": "📚 ReBook — Čarobnjak za instalaciju",
        "tr": "📚 ReBook — Kurulum Sihirbazı",
        "ar": "📚 ReBook — معالج الإعداد",
        "fa": "📚 ReBook — جادوگر نصب",
        "fi": "📚 ReBook — Asennusopas",
        "da": "📚 ReBook — Installationsguide",
        "nl": "📚 ReBook — Installatiewizard",
        "vi": "📚 ReBook — Trình cài đặt",
        "th": "📚 ReBook — ตัวช่วยติดตั้ง",
        "hu": "📚 ReBook — Telepítési varázsló",
        "ro": "📚 ReBook — Asistent de instalare",
    },
    "inst_subtitle": {
        "pl": "Konwerter PDF / EPUB ze wsparciem sztucznej inteligencji",
        "en": "AI-powered PDF / EPUB converter",
        "de": "KI-gestützter PDF/EPUB-Konverter",
        "es": "Conversor de PDF/EPUB con inteligencia artificial",
        "fr": "Convertisseur PDF/EPUB propulsé par l'IA",
        "pt": "Conversor de PDF/EPUB com inteligência artificial",
        "cs": "Převodník PDF/EPUB s umělou inteligencí",
        "sk": "Prevodník PDF/EPUB s umelou inteligenciou",
        "uk": "Конвертер PDF/EPUB з підтримкою ШІ",
        "sv": "AI-driven PDF/EPUB-konverterare",
        "no": "AI-drevet PDF/EPUB-konverterer",
        "zh": "AI驱动的PDF/EPUB转换器",
        "ja": "AI搭載 PDF/EPUBコンバーター",
        "it": "Convertitore PDF/EPUB con intelligenza artificiale",
        "sr": "PDF/EPUB конвертер са вештачком интелигенцијом",
        "ru": "Конвертер PDF/EPUB с поддержкой ИИ",
        "hr": "PDF/EPUB pretvarač s umjetnom inteligencijom",
        "tr": "Yapay zekâ destekli PDF/EPUB dönüştürücü",
        "ar": "محوّل PDF/EPUB مدعوم بالذكاء الاصطناعي",
        "fa": "مبدل PDF/EPUB با هوش مصنوعی",
        "fi": "Tekoälyllä toimiva PDF/EPUB-muunnin",
        "da": "AI-drevet PDF/EPUB-konverter",
        "nl": "AI-aangedreven PDF/EPUB-converter",
        "vi": "Trình chuyển đổi PDF/EPUB hỗ trợ AI",
        "th": "ตัวแปลง PDF/EPUB ที่ขับเคลื่อนด้วย AI",
        "hu": "AI-alapú PDF/EPUB konverter",
        "ro": "Convertor PDF/EPUB cu inteligență artificială",
    },
    "inst_window_title": {
        "pl": "ReBook — Instalacja",
        "en": "ReBook — Installation",
        "de": "ReBook — Installation",
        "es": "ReBook — Instalación",
        "fr": "ReBook — Installation",
        "pt": "ReBook — Instalação",
        "cs": "ReBook — Instalace",
        "sk": "ReBook — Inštalácia",
        "uk": "ReBook — Встановлення",
        "sv": "ReBook — Installation",
        "no": "ReBook — Installasjon",
        "zh": "ReBook — 安装",
        "ja": "ReBook — インストール",
        "it": "ReBook — Installazione",
        "sr": "ReBook — Инсталација",
        "ru": "ReBook — Установка",
        "hr": "ReBook — Instalacija",
        "tr": "ReBook — Kurulum",
        "ar": "ReBook — التثبيت",
        "fa": "ReBook — نصب",
        "fi": "ReBook — Asennus",
        "da": "ReBook — Installation",
        "nl": "ReBook — Installatie",
        "vi": "ReBook — Cài đặt",
        "th": "ReBook — การติดตั้ง",
        "hu": "ReBook — Telepítés",
        "ro": "ReBook — Instalare",
    },
    "inst_section_header": {
        "pl": "WYBIERZ TRYB INSTALACJI",
        "en": "SELECT INSTALLATION TYPE",
        "de": "INSTALLATIONSTYP WÄHLEN",
        "es": "SELECCIONAR TIPO DE INSTALACIÓN",
        "fr": "CHOISIR LE TYPE D'INSTALLATION",
        "pt": "SELECIONAR TIPO DE INSTALAÇÃO",
        "cs": "ZVOLTE TYP INSTALACE",
        "sk": "VYBERTE TYP INŠTALÁCIE",
        "uk": "ОБЕРІТЬ ТИП ВСТАНОВЛЕННЯ",
        "sv": "VÄLJ INSTALLATIONSTYP",
        "no": "VELG INSTALLASJONSTYPE",
        "zh": "选择安装类型",
        "ja": "インストールタイプを選択",
        "it": "SELEZIONA TIPO DI INSTALLAZIONE",
        "ru": "ВЫБЕРИТЕ ТИП УСТАНОВКИ",
        "tr": "KURULUM TÜRÜNÜ SEÇİN",
        "ar": "اختر نوع التثبيت",
        "fi": "VALITSE ASENNUSTYYPPI",
        "nl": "KIES INSTALLATIETYPE",
        "hu": "VÁLASSZA KI A TELEPÍTÉS TÍPUSÁT",
        "ro": "SELECTAȚI TIPUL DE INSTALARE",
    },
    "inst_light_title": {
        "pl": "⚡ Lekka instalacja  (~100 MB)",
        "en": "⚡ Light installation  (~100 MB)",
        "de": "⚡ Leichte Installation  (~100 MB)",
        "es": "⚡ Instalación ligera  (~100 MB)",
        "fr": "⚡ Installation légère  (~100 Mo)",
        "pt": "⚡ Instalação leve  (~100 MB)",
        "cs": "⚡ Lehká instalace  (~100 MB)",
        "sk": "⚡ Ľahká inštalácia  (~100 MB)",
        "uk": "⚡ Легка установка  (~100 МБ)",
        "sv": "⚡ Lätt installation  (~100 MB)",
        "no": "⚡ Lett installasjon  (~100 MB)",
        "zh": "⚡ 轻量安装  (~100 MB)",
        "ja": "⚡ 軽量インストール  (~100 MB)",
        "it": "⚡ Installazione leggera  (~100 MB)",
        "ru": "⚡ Лёгкая установка  (~100 МБ)",
        "tr": "⚡ Hafif kurulum  (~100 MB)",
        "ar": "⚡ تثبيت خفيف  (~100 ميغابايت)",
        "fi": "⚡ Kevyt asennus  (~100 Mt)",
        "nl": "⚡ Lichte installatie  (~100 MB)",
        "vi": "⚡ Cài đặt nhẹ  (~100 MB)",
        "th": "⚡ ติดตั้งแบบเบา  (~100 MB)",
        "hu": "⚡ Könnyű telepítés  (~100 MB)",
        "ro": "⚡ Instalare ușoară  (~100 MB)",
    },
    "inst_light_desc": {
        "pl": "  •  Konwersja EPUB → EPUB / Markdown / HTML\n  •  Tłumaczenie i korekta AI (Gemini, GPT, Claude, Mistral...)\n  •  30 równoległych wątków — błyskawiczna konwersja\n  •  Wysyłka prosto na Kindle\n  •  ⚠️ Bez obsługi plików PDF (brak OCR)",
        "en": "  •  Convert EPUB → EPUB / Markdown / HTML\n  •  AI translation & correction (Gemini, GPT, Claude, Mistral...)\n  •  30 parallel threads — blazing fast conversion\n  •  Send directly to Kindle\n  •  ⚠️ No PDF support (no OCR)",
        "de": "  •  EPUB → EPUB / Markdown / HTML konvertieren\n  •  KI-Übersetzung & Korrektur (Gemini, GPT, Claude, Mistral...)\n  •  30 parallele Threads — blitzschnelle Konvertierung\n  •  Direkt an Kindle senden\n  •  ⚠️ Keine PDF-Unterstützung (kein OCR)",
        "es": "  •  Convertir EPUB → EPUB / Markdown / HTML\n  •  Traducción y corrección con IA (Gemini, GPT, Claude, Mistral...)\n  •  30 hilos paralelos — conversión ultrarrápida\n  •  Envío directo a Kindle\n  •  ⚠️ Sin soporte PDF (sin OCR)",
        "fr": "  •  Convertir EPUB → EPUB / Markdown / HTML\n  •  Traduction et correction IA (Gemini, GPT, Claude, Mistral...)\n  •  30 threads parallèles — conversion ultra-rapide\n  •  Envoi direct vers Kindle\n  •  ⚠️ Pas de support PDF (pas d'OCR)",
        "pt": "  •  Converter EPUB → EPUB / Markdown / HTML\n  •  Tradução e correção com IA (Gemini, GPT, Claude, Mistral...)\n  •  30 threads paralelos — conversão ultrarrápida\n  •  Envio direto para Kindle\n  •  ⚠️ Sem suporte a PDF (sem OCR)",
        "uk": "  •  Конвертація EPUB → EPUB / Markdown / HTML\n  •  Переклад і корекція ШІ (Gemini, GPT, Claude, Mistral...)\n  •  30 паралельних потоків — блискавична конвертація\n  •  Надсилання на Kindle\n  •  ⚠️ Без підтримки PDF (немає OCR)",
        "ru": "  •  Конвертация EPUB → EPUB / Markdown / HTML\n  •  Перевод и коррекция ИИ (Gemini, GPT, Claude, Mistral...)\n  •  30 параллельных потоков — молниеносная конвертация\n  •  Отправка на Kindle\n  •  ⚠️ Без поддержки PDF (нет OCR)",
        "zh": "  •  转换 EPUB → EPUB / Markdown / HTML\n  •  AI翻译和校正 (Gemini, GPT, Claude, Mistral...)\n  •  30个并行线程 — 极速转换\n  •  直接发送到Kindle\n  •  ⚠️ 不支持PDF（无OCR）",
        "ja": "  •  EPUB → EPUB / Markdown / HTML 変換\n  •  AI翻訳・校正 (Gemini, GPT, Claude, Mistral...)\n  •  30並列スレッド — 超高速変換\n  •  Kindleに直接送信\n  •  ⚠️ PDF非対応（OCRなし）",
        "it": "  •  Converti EPUB → EPUB / Markdown / HTML\n  •  Traduzione e correzione AI (Gemini, GPT, Claude, Mistral...)\n  •  30 thread paralleli — conversione ultraveloce\n  •  Invio diretto a Kindle\n  •  ⚠️ Nessun supporto PDF (nessun OCR)",
        "tr": "  •  EPUB → EPUB / Markdown / HTML dönüştürme\n  •  Yapay zekâ çeviri ve düzeltme (Gemini, GPT, Claude, Mistral...)\n  •  30 paralel iş parçacığı — yıldırım hızında dönüştürme\n  •  Doğrudan Kindle'a gönder\n  •  ⚠️ PDF desteği yok (OCR yok)",
        "nl": "  •  EPUB → EPUB / Markdown / HTML converteren\n  •  AI-vertaling & correctie (Gemini, GPT, Claude, Mistral...)\n  •  30 parallelle threads — razendsnelle conversie\n  •  Direct naar Kindle sturen\n  •  ⚠️ Geen PDF-ondersteuning (geen OCR)",
        "hu": "  •  EPUB → EPUB / Markdown / HTML konvertálás\n  •  AI fordítás és javítás (Gemini, GPT, Claude, Mistral...)\n  •  30 párhuzamos szál — villámgyors konvertálás\n  •  Küldés közvetlenül Kindle-re\n  •  ⚠️ Nincs PDF-támogatás (nincs OCR)",
        "ro": "  •  Conversie EPUB → EPUB / Markdown / HTML\n  •  Traducere și corectare AI (Gemini, GPT, Claude, Mistral...)\n  •  30 fire paralele — conversie ultrarapidă\n  •  Trimitere directă la Kindle\n  •  ⚠️ Fără suport PDF (fără OCR)",
    },
    "inst_full_title": {
        "pl": "📦 Pełna instalacja  (~1.2 GB)",
        "en": "📦 Full installation  (~1.2 GB)",
        "de": "📦 Vollständige Installation  (~1,2 GB)",
        "es": "📦 Instalación completa  (~1,2 GB)",
        "fr": "📦 Installation complète  (~1,2 Go)",
        "pt": "📦 Instalação completa  (~1,2 GB)",
        "cs": "📦 Plná instalace  (~1,2 GB)",
        "sk": "📦 Plná inštalácia  (~1,2 GB)",
        "uk": "📦 Повна установка  (~1,2 ГБ)",
        "sv": "📦 Fullständig installation  (~1,2 GB)",
        "no": "📦 Full installasjon  (~1,2 GB)",
        "zh": "📦 完整安装  (~1.2 GB)",
        "ja": "📦 フルインストール  (~1.2 GB)",
        "it": "📦 Installazione completa  (~1,2 GB)",
        "ru": "📦 Полная установка  (~1,2 ГБ)",
        "tr": "📦 Tam kurulum  (~1,2 GB)",
        "ar": "📦 تثبيت كامل  (~1.2 غيغابايت)",
        "fi": "📦 Täysi asennus  (~1,2 Gt)",
        "nl": "📦 Volledige installatie  (~1,2 GB)",
        "vi": "📦 Cài đặt đầy đủ  (~1.2 GB)",
        "th": "📦 ติดตั้งแบบเต็ม  (~1.2 GB)",
        "hu": "📦 Teljes telepítés  (~1,2 GB)",
        "ro": "📦 Instalare completă  (~1,2 GB)",
    },
    "inst_full_desc": {
        "pl": "  •  Wszystko z wersji Lekkiej\n  •  + Marker OCR — rozpoznawanie tekstu ze skanów PDF\n  •  + PyTorch (~400 MB) i modele wizualne (~500 MB)\n  •  Obsługa plików PDF i EPUB jako wejście\n  •  💡 Marker OCR można doinstalować później",
        "en": "  •  Everything from the Light version\n  •  + Marker OCR — text recognition from PDF scans\n  •  + PyTorch (~400 MB) and vision models (~500 MB)\n  •  Supports both PDF and EPUB as input\n  •  💡 Marker OCR can be installed later",
        "de": "  •  Alles aus der Light-Version\n  •  + Marker OCR — Texterkennung aus PDF-Scans\n  •  + PyTorch (~400 MB) und Bildmodelle (~500 MB)\n  •  PDF- und EPUB-Dateien als Eingabe\n  •  💡 Marker OCR kann später installiert werden",
        "es": "  •  Todo de la versión Ligera\n  •  + Marker OCR — reconocimiento de texto de PDF\n  •  + PyTorch (~400 MB) y modelos de visión (~500 MB)\n  •  Soporta PDF y EPUB como entrada\n  •  💡 Marker OCR se puede instalar después",
        "fr": "  •  Tout de la version Légère\n  •  + Marker OCR — reconnaissance de texte des PDF\n  •  + PyTorch (~400 Mo) et modèles visuels (~500 Mo)\n  •  Supporte PDF et EPUB en entrée\n  •  💡 Marker OCR peut être installé ultérieurement",
        "pt": "  •  Tudo da versão Leve\n  •  + Marker OCR — reconhecimento de texto de PDF\n  •  + PyTorch (~400 MB) e modelos visuais (~500 MB)\n  •  Suporta PDF e EPUB como entrada\n  •  💡 Marker OCR pode ser instalado depois",
        "uk": "  •  Все з Легкої версії\n  •  + Marker OCR — розпізнавання тексту з PDF\n  •  + PyTorch (~400 МБ) і візуальні моделі (~500 МБ)\n  •  Підтримка PDF і EPUB як вхідних файлів\n  •  💡 Marker OCR можна встановити пізніше",
        "ru": "  •  Всё из Лёгкой версии\n  •  + Marker OCR — распознавание текста из PDF\n  •  + PyTorch (~400 МБ) и визуальные модели (~500 МБ)\n  •  Поддержка PDF и EPUB на входе\n  •  💡 Marker OCR можно установить позже",
        "zh": "  •  轻量版所有功能\n  •  + Marker OCR — PDF扫描文字识别\n  •  + PyTorch (~400 MB) 和视觉模型 (~500 MB)\n  •  支持PDF和EPUB作为输入\n  •  💡 Marker OCR可以稍后安装",
        "ja": "  •  軽量版のすべての機能\n  •  + Marker OCR — PDFスキャンのテキスト認識\n  •  + PyTorch (~400 MB) とビジョンモデル (~500 MB)\n  •  PDFとEPUBの両方に対応\n  •  💡 Marker OCRは後からインストール可能",
        "it": "  •  Tutto dalla versione Leggera\n  •  + Marker OCR — riconoscimento testo da PDF\n  •  + PyTorch (~400 MB) e modelli visivi (~500 MB)\n  •  Supporta PDF e EPUB come input\n  •  💡 Marker OCR può essere installato in seguito",
        "tr": "  •  Hafif sürümdeki her şey\n  •  + Marker OCR — PDF taramalarından metin tanıma\n  •  + PyTorch (~400 MB) ve görüntü modelleri (~500 MB)\n  •  Girdi olarak PDF ve EPUB desteği\n  •  💡 Marker OCR daha sonra kurulabilir",
        "nl": "  •  Alles uit de Lichte versie\n  •  + Marker OCR — tekstherkenning uit PDF-scans\n  •  + PyTorch (~400 MB) en beeldmodellen (~500 MB)\n  •  Ondersteunt PDF en EPUB als invoer\n  •  💡 Marker OCR kan later worden geïnstalleerd",
        "hu": "  •  Minden a Könnyű verzióból\n  •  + Marker OCR — szövegfelismerés PDF-ből\n  •  + PyTorch (~400 MB) és vizuális modellek (~500 MB)\n  •  PDF és EPUB fájlok támogatása\n  •  💡 A Marker OCR később is telepíthető",
        "ro": "  •  Totul din versiunea Ușoară\n  •  + Marker OCR — recunoaștere text din PDF\n  •  + PyTorch (~400 MB) și modele vizuale (~500 MB)\n  •  Suport PDF și EPUB ca intrare\n  •  💡 Marker OCR poate fi instalat ulterior",
    },
    "inst_install_btn": {
        "pl": "🚀  Instaluj ReBook", "en": "🚀  Install ReBook",
        "de": "🚀  ReBook installieren", "es": "🚀  Instalar ReBook",
        "fr": "🚀  Installer ReBook", "pt": "🚀  Instalar ReBook",
        "uk": "🚀  Встановити ReBook", "ru": "🚀  Установить ReBook",
        "zh": "🚀  安装 ReBook", "ja": "🚀  ReBookをインストール",
        "it": "🚀  Installa ReBook", "tr": "🚀  ReBook'u Kur",
        "nl": "🚀  ReBook installeren", "vi": "🚀  Cài đặt ReBook",
    },
    "inst_installing": {
        "pl": "⏳  Instalacja w toku…", "en": "⏳  Installing…",
        "de": "⏳  Installation läuft…", "es": "⏳  Instalando…",
        "fr": "⏳  Installation en cours…", "pt": "⏳  Instalando…",
        "uk": "⏳  Встановлення…", "ru": "⏳  Установка…",
        "zh": "⏳  正在安装…", "ja": "⏳  インストール中…",
        "it": "⏳  Installazione in corso…", "tr": "⏳  Kuruluyor…",
        "nl": "⏳  Installeren…",
    },
    "inst_preparing": {
        "pl": "Przygotowywanie...", "en": "Preparing...",
        "de": "Vorbereitung...", "es": "Preparando...",
        "fr": "Préparation...", "pt": "Preparando...",
        "uk": "Підготовка...", "ru": "Подготовка...",
        "zh": "准备中...", "ja": "準備中...",
        "it": "Preparazione...", "tr": "Hazırlanıyor...",
        "nl": "Voorbereiden...",
    },
    "inst_core_progress": {
        "pl": "Instaluję pakiety bazowe (~100 MB)...",
        "en": "Installing core packages (~100 MB)...",
        "de": "Basispakete werden installiert (~100 MB)...",
        "es": "Instalando paquetes base (~100 MB)...",
        "fr": "Installation des paquets de base (~100 Mo)...",
        "pt": "Instalando pacotes base (~100 MB)...",
        "uk": "Встановлення базових пакетів (~100 МБ)...",
        "ru": "Установка базовых пакетов (~100 МБ)...",
        "zh": "正在安装基础包 (~100 MB)...",
        "ja": "基本パッケージをインストール中 (~100 MB)...",
    },
    "inst_marker_progress": {
        "pl": "Instaluję Marker OCR + PyTorch (~1 GB)... To może potrwać kilka minut.",
        "en": "Installing Marker OCR + PyTorch (~1 GB)... This may take a few minutes.",
        "de": "Marker OCR + PyTorch wird installiert (~1 GB)... Dies kann einige Minuten dauern.",
        "es": "Instalando Marker OCR + PyTorch (~1 GB)... Esto puede tardar unos minutos.",
        "fr": "Installation de Marker OCR + PyTorch (~1 Go)... Cela peut prendre quelques minutes.",
        "uk": "Встановлення Marker OCR + PyTorch (~1 ГБ)... Це може зайняти кілька хвилин.",
        "ru": "Установка Marker OCR + PyTorch (~1 ГБ)... Это может занять несколько минут.",
        "zh": "正在安装 Marker OCR + PyTorch (~1 GB)... 这可能需要几分钟。",
        "ja": "Marker OCR + PyTorch をインストール中 (~1 GB)... 数分かかる場合があります。",
    },
    "inst_core_error": {
        "pl": "❌ Błąd instalacji pakietów bazowych",
        "en": "❌ Core package installation failed",
        "de": "❌ Installation der Basispakete fehlgeschlagen",
        "es": "❌ Error en la instalación de paquetes base",
        "ru": "❌ Ошибка установки базовых пакетов",
        "uk": "❌ Помилка встановлення базових пакетів",
        "zh": "❌ 基础包安装失败", "ja": "❌ 基本パッケージのインストールに失敗",
    },
    "inst_marker_warn": {
        "pl": "⚠️ Marker OCR nie został zainstalowany, ale ReBook działa bez niego",
        "en": "⚠️ Marker OCR installation failed, but ReBook works without it",
        "de": "⚠️ Marker OCR konnte nicht installiert werden, ReBook funktioniert aber ohne",
        "ru": "⚠️ Marker OCR не установлен, но ReBook работает без него",
        "uk": "⚠️ Marker OCR не встановлено, але ReBook працює без нього",
    },
    "inst_done": {
        "pl": "✅ Instalacja zakończona!", "en": "✅ Installation complete!",
        "de": "✅ Installation abgeschlossen!", "es": "✅ ¡Instalación completada!",
        "fr": "✅ Installation terminée !", "pt": "✅ Instalação concluída!",
        "uk": "✅ Встановлення завершено!", "ru": "✅ Установка завершена!",
        "zh": "✅ 安装完成！", "ja": "✅ インストール完了！",
        "it": "✅ Installazione completata!", "tr": "✅ Kurulum tamamlandı!",
        "nl": "✅ Installatie voltooid!",
    },
    "inst_launch_btn": {
        "pl": "🚀  Uruchom ReBook!", "en": "🚀  Launch ReBook!",
        "de": "🚀  ReBook starten!", "es": "🚀  ¡Iniciar ReBook!",
        "fr": "🚀  Lancer ReBook !", "pt": "🚀  Iniciar ReBook!",
        "uk": "🚀  Запустити ReBook!", "ru": "🚀  Запустить ReBook!",
        "zh": "🚀  启动 ReBook！", "ja": "🚀  ReBookを起動！",
        "it": "🚀  Avvia ReBook!", "tr": "🚀  ReBook'u Başlat!",
        "nl": "🚀  ReBook starten!",
    },
    "inst_retry_btn": {
        "pl": "🔄  Spróbuj ponownie", "en": "🔄  Try again",
        "de": "🔄  Erneut versuchen", "es": "🔄  Intentar de nuevo",
        "fr": "🔄  Réessayer", "ru": "🔄  Попробовать снова",
        "uk": "🔄  Спробувати знову", "zh": "🔄  重试", "ja": "🔄  再試行",
    },
    "inst_ready": {
        "pl": "✅ Gotowe! Kliknij przycisk aby uruchomić ReBook.",
        "en": "✅ Ready! Click the button to launch ReBook.",
        "de": "✅ Fertig! Klicke auf den Button, um ReBook zu starten.",
        "es": "✅ ¡Listo! Haz clic en el botón para iniciar ReBook.",
        "fr": "✅ Prêt ! Cliquez sur le bouton pour lancer ReBook.",
        "ru": "✅ Готово! Нажмите кнопку, чтобы запустить ReBook.",
        "uk": "✅ Готово! Натисніть кнопку, щоб запустити ReBook.",
        "zh": "✅ 准备就绪！点击按钮启动 ReBook。",
        "ja": "✅ 準備完了！ボタンをクリックしてReBookを起動してください。",
    },
    "inst_marker_hint": {
        "pl": "\n\n💡 Aby później doinstalować Marker OCR,\notwórz Terminal i wpisz:\n~/.pdf2epub-app/env/bin/pip install marker-pdf",
        "en": "\n\n💡 To install Marker OCR later,\nopen Terminal and type:\n~/.pdf2epub-app/env/bin/pip install marker-pdf",
        "de": "\n\n💡 Um Marker OCR später zu installieren,\nöffne Terminal und gib ein:\n~/.pdf2epub-app/env/bin/pip install marker-pdf",
        "ru": "\n\n💡 Чтобы установить Marker OCR позже,\nоткройте Терминал и введите:\n~/.pdf2epub-app/env/bin/pip install marker-pdf",
        "uk": "\n\n💡 Щоб встановити Marker OCR пізніше,\nвідкрийте Термінал і введіть:\n~/.pdf2epub-app/env/bin/pip install marker-pdf",
    },

    # ═══════════════════════════════════════════════════════════════════
    #  MAIN APP GUI
    # ═══════════════════════════════════════════════════════════════════
    "app_title": {"pl": "ReBook", "en": "ReBook"},
    "app_subtitle": {
        "pl": "Konwerter PDF / EPUB ze wsparciem AI",
        "en": "AI-powered PDF / EPUB Converter",
        "de": "KI-gestützter PDF/EPUB-Konverter",
        "es": "Conversor PDF/EPUB con IA",
        "fr": "Convertisseur PDF/EPUB avec IA",
        "pt": "Conversor PDF/EPUB com IA",
        "uk": "Конвертер PDF/EPUB з підтримкою ШІ",
        "ru": "Конвертер PDF/EPUB с поддержкой ИИ",
        "zh": "AI驱动的PDF/EPUB转换器",
        "ja": "AI搭載 PDF/EPUBコンバーター",
        "it": "Convertitore PDF/EPUB con IA",
        "tr": "Yapay zekâ destekli PDF/EPUB dönüştürücü",
        "nl": "AI-aangedreven PDF/EPUB-converter",
    },
    "drop_title": {
        "pl": "Przeciągnij plik PDF, EPUB lub Markdown tutaj",
        "en": "Drag a PDF, EPUB, or Markdown file here",
        "de": "PDF-, EPUB- oder Markdown-Datei hierher ziehen",
        "es": "Arrastra un archivo PDF, EPUB o Markdown aquí",
        "fr": "Déposez un fichier PDF, EPUB ou Markdown ici",
        "pt": "Arraste um arquivo PDF, EPUB ou Markdown aqui",
        "uk": "Перетягніть файл PDF, EPUB або Markdown сюди",
        "ru": "Перетащите файл PDF, EPUB или Markdown сюда",
        "zh": "将PDF、EPUB或Markdown文件拖到此处",
        "ja": "PDF、EPUB、またはMarkdownファイルをここにドラッグ",
        "it": "Trascina un file PDF, EPUB o Markdown qui",
        "tr": "Bir PDF, EPUB veya Markdown dosyası buraya sürükleyin",
        "nl": "Sleep een PDF-, EPUB- of Markdown-bestand hierheen",
    },
    "drop_subtitle": {
        "pl": "lub kliknij aby wybrać plik",
        "en": "or click to select a file",
        "de": "oder klicken, um eine Datei auszuwählen",
        "es": "o haz clic para seleccionar un archivo",
        "fr": "ou cliquez pour sélectionner un fichier",
        "pt": "ou clique para selecionar um arquivo",
        "uk": "або натисніть, щоб вибрати файл",
        "ru": "или нажмите для выбора файла",
        "zh": "或点击选择文件",
        "ja": "またはクリックしてファイルを選択",
        "it": "o fai clic per selezionare un file",
        "tr": "veya dosya seçmek için tıklayın",
        "nl": "of klik om een bestand te selecteren",
    },
    "remove_btn": {
        "pl": "Usuń", "en": "Remove", "de": "Entfernen", "es": "Eliminar",
        "fr": "Supprimer", "pt": "Remover", "uk": "Видалити", "ru": "Удалить",
        "zh": "移除", "ja": "削除", "it": "Rimuovi", "tr": "Kaldır", "nl": "Verwijderen",
    },
    "options_header": {
        "pl": "OPCJE KONWERSJI", "en": "CONVERSION OPTIONS",
        "de": "KONVERTIERUNGSOPTIONEN", "es": "OPCIONES DE CONVERSIÓN",
        "fr": "OPTIONS DE CONVERSION", "uk": "ПАРАМЕТРИ КОНВЕРТАЦІЇ",
        "ru": "ПАРАМЕТРЫ КОНВЕРТАЦИИ", "zh": "转换选项", "ja": "変換オプション",
        "it": "OPZIONI DI CONVERSIONE", "tr": "DÖNÜŞTÜRME SEÇENEKLERİ",
        "nl": "CONVERSIEOPTIES",
    },
    "format_label": {
        "pl": "Format wyjściowy:", "en": "Output format:",
        "de": "Ausgabeformat:", "es": "Formato de salida:",
        "fr": "Format de sortie :", "uk": "Формат виводу:",
        "ru": "Формат вывода:", "zh": "输出格式：", "ja": "出力形式：",
    },
    "ai_check": {
        "pl": "Korekcja AI (wymaga API Key)",
        "en": "AI Correction (requires API Key)",
        "de": "KI-Korrektur (API-Key erforderlich)",
        "es": "Corrección IA (requiere API Key)",
        "fr": "Correction IA (nécessite une clé API)",
        "uk": "Корекція ШІ (потрібен API ключ)",
        "ru": "Коррекция ИИ (требуется API ключ)",
        "zh": "AI校正（需要API密钥）",
        "ja": "AI校正（APIキーが必要）",
    },
    "translate_check": {
        "pl": "Tryb tłumaczenia (zamiast korekty)",
        "en": "Translation mode (instead of correction)",
        "de": "Übersetzungsmodus (statt Korrektur)",
        "es": "Modo traducción (en lugar de corrección)",
        "fr": "Mode traduction (au lieu de correction)",
        "uk": "Режим перекладу (замість корекції)",
        "ru": "Режим перевода (вместо коррекции)",
        "zh": "翻译模式（替代校正）",
        "ja": "翻訳モード（校正の代わり）",
    },
    "lang_from_label": {
        "pl": "Język źródłowy:", "en": "Source language:",
        "de": "Quellsprache:", "es": "Idioma origen:",
        "fr": "Langue source :", "ru": "Исходный язык:",
        "uk": "Мова оригіналу:", "zh": "源语言：", "ja": "原文言語：",
    },
    "lang_from_placeholder": {
        "pl": "np. angielski (lub puste = auto)",
        "en": "e.g. english (or empty = auto)",
        "de": "z.B. englisch (oder leer = auto)",
        "es": "ej. inglés (o vacío = auto)",
        "fr": "ex. anglais (ou vide = auto)",
        "ru": "напр. английский (или пусто = авто)",
        "uk": "напр. англійська (або порожнє = авто)",
        "zh": "例如 英语（或留空=自动）",
        "ja": "例: 英語（空欄=自動検出）",
    },
    "lang_to_label": {
        "pl": "Język docelowy:", "en": "Target language:",
        "de": "Zielsprache:", "es": "Idioma destino:",
        "fr": "Langue cible :", "ru": "Целевой язык:",
        "uk": "Цільова мова:", "zh": "目标语言：", "ja": "翻訳先言語：",
    },
    "convert_btn": {
        "pl": "🚀  Konwertuj", "en": "🚀  Convert",
        "de": "🚀  Konvertieren", "es": "🚀  Convertir",
        "fr": "🚀  Convertir", "uk": "🚀  Конвертувати",
        "ru": "🚀  Конвертировать", "zh": "🚀  转换", "ja": "🚀  変換",
        "it": "🚀  Converti", "tr": "🚀  Dönüştür", "nl": "🚀  Converteren",
    },
    "converting_btn": {
        "pl": "⏳  Konwersja w toku…", "en": "⏳  Converting…",
        "de": "⏳  Konvertierung…", "es": "⏳  Convirtiendo…",
        "fr": "⏳  Conversion…", "ru": "⏳  Конвертация…",
        "uk": "⏳  Конвертація…", "zh": "⏳  转换中…", "ja": "⏳  変換中…",
    },
    "starting": {
        "pl": "Rozpoczynam...", "en": "Starting...",
        "de": "Starte...", "es": "Iniciando...", "fr": "Démarrage...",
        "ru": "Запуск...", "uk": "Запуск...", "zh": "启动中...", "ja": "開始中...",
    },
    "done": {
        "pl": "Gotowe!", "en": "Done!", "de": "Fertig!", "es": "¡Listo!",
        "fr": "Terminé !", "ru": "Готово!", "uk": "Готово!",
        "zh": "完成！", "ja": "完了！", "it": "Fatto!", "tr": "Bitti!",
    },
    "conversion_done": {
        "pl": "✅ Konwersja zakończona!", "en": "✅ Conversion complete!",
        "de": "✅ Konvertierung abgeschlossen!", "es": "✅ ¡Conversión completada!",
        "fr": "✅ Conversion terminée !", "ru": "✅ Конвертация завершена!",
        "uk": "✅ Конвертацію завершено!", "zh": "✅ 转换完成！", "ja": "✅ 変換完了！",
    },
    "save_btn": {
        "pl": "💾 Zapisz plik…", "en": "💾 Save file…",
        "de": "💾 Datei speichern…", "es": "💾 Guardar archivo…",
        "fr": "💾 Enregistrer…", "ru": "💾 Сохранить файл…",
        "uk": "💾 Зберегти файл…", "zh": "💾 保存文件…", "ja": "💾 ファイルを保存…",
    },
    "kindle_btn": {"pl": "📚 Kindle", "en": "📚 Kindle"},
    "save_title": {
        "pl": "Zapisz wynik", "en": "Save result",
        "de": "Ergebnis speichern", "es": "Guardar resultado",
        "fr": "Enregistrer le résultat", "ru": "Сохранить результат",
    },
    "error_title": {
        "pl": "Błąd konwersji", "en": "Conversion error",
        "de": "Konvertierungsfehler", "es": "Error de conversión",
        "fr": "Erreur de conversion", "ru": "Ошибка конвертации",
        "uk": "Помилка конвертації", "zh": "转换错误", "ja": "変換エラー",
    },
    "error_prefix": {
        "pl": "Błąd", "en": "Error", "de": "Fehler", "es": "Error",
        "fr": "Erreur", "ru": "Ошибка", "uk": "Помилка",
        "zh": "错误", "ja": "エラー",
    },

    # ═══════════════════════════════════════════════════════════════════
    #  MENUS & MISC
    # ═══════════════════════════════════════════════════════════════════
    "menu_about": {
        "pl": "O ReBook", "en": "About ReBook", "de": "Über ReBook",
        "es": "Acerca de ReBook", "fr": "À propos de ReBook",
        "ru": "О ReBook", "uk": "Про ReBook", "zh": "关于 ReBook",
        "ja": "ReBookについて",
    },
    "menu_settings": {
        "pl": "Ustawienia\u2026", "en": "Settings\u2026", "de": "Einstellungen\u2026",
        "es": "Configuración\u2026", "fr": "Paramètres\u2026",
        "ru": "Настройки\u2026", "uk": "Налаштування\u2026", "zh": "设置\u2026",
        "ja": "設定\u2026",
    },
    "menu_quit": {
        "pl": "Zamknij ReBook", "en": "Quit ReBook", "de": "ReBook beenden",
        "es": "Salir de ReBook", "fr": "Quitter ReBook",
        "ru": "Выйти из ReBook", "uk": "Вийти з ReBook", "zh": "退出 ReBook",
        "ja": "ReBookを終了",
    },
    "menu_file": {
        "pl": "Plik", "en": "File", "de": "Datei",
        "es": "Archivo", "fr": "Fichier",
        "ru": "Файл", "uk": "Файл", "zh": "文件", "ja": "ファイル",
    },
    "menu_open": {
        "pl": "Otwórz\u2026", "en": "Open\u2026", "de": "Öffnen\u2026",
        "es": "Abrir\u2026", "fr": "Ouvrir\u2026",
        "ru": "Открыть\u2026", "uk": "Відкрити\u2026", "zh": "打开\u2026",
        "ja": "開く\u2026",
    },
    "provider_none": {
        "pl": "Brak (AI wyłączone)", "en": "None (AI disabled)",
        "de": "Keiner (KI deaktiviert)", "es": "Ninguno (IA desactivada)",
        "fr": "Aucun (IA désactivée)", "ru": "Нет (ИИ отключён)",
        "uk": "Немає (ШІ вимкнено)", "zh": "无（AI已禁用）",
        "ja": "なし（AI無効）",
    },
    "settings_llm_header": {
        "pl": "DOSTAWCA AI", "en": "AI PROVIDER",
        "de": "KI-ANBIETER", "es": "PROVEEDOR DE IA",
        "fr": "FOURNISSEUR IA", "ru": "ПРОВАЙДЕР ИИ",
        "uk": "ПРОВАЙДЕР ШІ", "zh": "AI提供商", "ja": "AIプロバイダー",
    },

    # ═══════════════════════════════════════════════════════════════════
    #  SETTINGS
    # ═══════════════════════════════════════════════════════════════════
    "settings_title": {
        "pl": "Ustawienia ReBook", "en": "ReBook Settings",
        "de": "ReBook Einstellungen", "es": "Configuración de ReBook",
        "fr": "Paramètres de ReBook", "ru": "Настройки ReBook",
        "uk": "Налаштування ReBook", "zh": "ReBook 设置", "ja": "ReBook 設定",
    },
    "settings_provider": {
        "pl": "Dostawca LLM:", "en": "LLM Provider:",
        "de": "LLM-Anbieter:", "es": "Proveedor LLM:",
        "fr": "Fournisseur LLM :", "ru": "Провайдер LLM:",
    },
    "settings_model": {
        "pl": "Model:", "en": "Model:", "de": "Modell:",
        "es": "Modelo:", "fr": "Modèle :", "ru": "Модель:",
        "zh": "模型：", "ja": "モデル：",
    },
    "settings_api_key": {
        "pl": "Klucz API:", "en": "API Key:", "de": "API-Schlüssel:",
        "es": "Clave API:", "fr": "Clé API :", "ru": "API ключ:",
        "zh": "API密钥：", "ja": "APIキー：",
    },
    "settings_kindle_header": {
        "pl": "WYSYŁKA NA KINDLE", "en": "SEND TO KINDLE",
        "de": "AN KINDLE SENDEN", "es": "ENVIAR A KINDLE",
        "fr": "ENVOI VERS KINDLE", "ru": "ОТПРАВКА НА KINDLE",
    },
    "settings_kindle_email": {
        "pl": "E-mail Kindle:", "en": "Kindle email:",
    },
    "settings_smtp_email": {
        "pl": "E-mail nadawcy (SMTP):", "en": "Sender email (SMTP):",
        "de": "Absender-E-Mail (SMTP):", "es": "Email remitente (SMTP):",
    },
    "settings_smtp_pass": {
        "pl": "Hasło aplikacji SMTP:", "en": "SMTP app password:",
        "de": "SMTP-App-Passwort:", "es": "Contraseña de app SMTP:",
    },
    "settings_save": {
        "pl": "Zapisz", "en": "Save", "de": "Speichern", "es": "Guardar",
        "fr": "Enregistrer", "ru": "Сохранить", "uk": "Зберегти",
        "zh": "保存", "ja": "保存",
    },
    "settings_cancel": {
        "pl": "Anuluj", "en": "Cancel", "de": "Abbrechen", "es": "Cancelar",
        "fr": "Annuler", "ru": "Отмена", "uk": "Скасувати",
        "zh": "取消", "ja": "キャンセル",
    },
    "settings_save_error": {
        "pl": "Błąd zapisu", "en": "Save error",
        "de": "Speicherfehler", "es": "Error al guardar",
    },

    # ═══════════════════════════════════════════════════════════════════
    #  CONVERTER / CORRECTOR PROGRESS
    # ═══════════════════════════════════════════════════════════════════
    "ocr_skip_md": {
        "pl": "Pominięto OCR — plik Markdown", "en": "OCR skipped — Markdown file",
    },
    "epub_extracting": {
        "pl": "Rozpakowywanie EPUB…", "en": "Extracting EPUB…",
        "de": "EPUB wird entpackt…", "es": "Extrayendo EPUB…",
        "ru": "Распаковка EPUB…", "zh": "正在解压EPUB…",
    },
    "epub_extracted": {
        "pl": "Ekstrakcja EPUB zakończona ({n} ilustracji)",
        "en": "EPUB extraction complete ({n} illustrations)",
    },
    "ocr_running": {
        "pl": "OCR — rozpoznawanie tekstu…", "en": "OCR — recognizing text…",
    },
    "ocr_done": {"pl": "OCR zakończone", "en": "OCR complete"},
    "ai_label_translate": {
        "pl": "Tłumaczenie", "en": "Translation",
        "de": "Übersetzung", "es": "Traducción", "fr": "Traduction",
        "ru": "Перевод", "uk": "Переклад", "zh": "翻译", "ja": "翻訳",
    },
    "ai_label_correct": {
        "pl": "Korekcja AI", "en": "AI Correction",
        "de": "KI-Korrektur", "es": "Corrección IA",
        "ru": "Коррекция ИИ", "uk": "Корекція ШІ", "zh": "AI校正",
    },
    "ai_init": {
        "pl": "{label} — inicjalizacja…", "en": "{label} — initializing…",
    },
    "ai_done": {
        "pl": "{label} zakończona", "en": "{label} complete",
    },
    "export_progress": {
        "pl": "Eksport → {fmt}…", "en": "Exporting → {fmt}…",
    },
    "all_done": {
        "pl": "Gotowe! → {name}", "en": "Done! → {name}",
    },
    "no_api_key": {
        "pl": "⚠️ BRAK KLUCZA API!\nWejdź w Ustawienia (⚙️) u góry po prawej, wybierz dostawcę AI i wklej poprawny klucz swojego konta aby uruchomić tryb tłumaczenia/korekty.",
        "en": "⚠️ NO API KEY!\nGo to Settings (⚙️) in the top right, select an AI provider and paste your API key to enable translation/correction mode.",
        "de": "⚠️ KEIN API-SCHLÜSSEL!\nGehen Sie zu Einstellungen (⚙️) oben rechts, wählen Sie einen KI-Anbieter und fügen Sie Ihren API-Schlüssel ein.",
        "es": "⚠️ ¡SIN CLAVE API!\nVe a Configuración (⚙️) arriba a la derecha, selecciona un proveedor de IA y pega tu clave API.",
        "ru": "⚠️ НЕТ API КЛЮЧА!\nОткройте Настройки (⚙️) справа вверху, выберите провайдера ИИ и вставьте свой API ключ.",
        "uk": "⚠️ НЕМАЄ API КЛЮЧА!\nВідкрийте Налаштування (⚙️) зверху праворуч, виберіть провайдера ШІ та вставте свій API ключ.",
        "zh": "⚠️ 缺少API密钥！\n请在右上角的设置(⚙️)中选择AI提供商并粘贴您的API密钥。",
        "ja": "⚠️ APIキーがありません！\n右上の設定(⚙️)からAIプロバイダーを選択し、APIキーを貼り付けてください。",
    },
    "corr_translate": {
        "pl": "Tłumaczenie", "en": "Translation", "de": "Übersetzung",
        "es": "Traducción", "ru": "Перевод", "zh": "翻译", "ja": "翻訳",
    },
    "corr_correct": {
        "pl": "Korekcja", "en": "Correction", "de": "Korrektur",
        "es": "Corrección", "ru": "Коррекция", "zh": "校正", "ja": "校正",
    },
    "corr_passthrough": {
        "pl": "{mode} bloku {cur}/{tot} (Pass-through)...",
        "en": "{mode} block {cur}/{tot} (Pass-through)...",
    },
    "corr_submitted": {
        "pl": "Zlecono do API paczkę numer {i}/{tot}...",
        "en": "Submitted batch {i}/{tot} to API...",
    },
    "corr_block_done": {
        "pl": "{mode} bloku {cur}/{tot} (~{size}K znaków)...",
        "en": "{mode} block {cur}/{tot} (~{size}K chars)...",
    },
    "corr_retrying": {
        "pl": "🔄 Ponawiam {n} nieudanych segmentów...",
        "en": "🔄 Retrying {n} failed segments...",
    },
    "corr_retry_attempt": {
        "pl": "🔄 Ponowna próba {round}/3 segmentu {seg}...",
        "en": "🔄 Retry attempt {round}/3 for segment {seg}...",
    },
    "corr_retry_ok": {
        "pl": "✅ Segment {seg} odzyskany w próbie {round}!",
        "en": "✅ Segment {seg} recovered on attempt {round}!",
    },
    "corr_missing_warn": {
        "pl": "⚠️ UWAGA: {n} segmentów nie udało się przetłumaczyć mimo ponowień",
        "en": "⚠️ WARNING: {n} segments could not be translated despite retries",
    },
    "kindle_sending": {
        "pl": "Wysyłam na Kindle...", "en": "Sending to Kindle...",
        "de": "Wird an Kindle gesendet...", "es": "Enviando a Kindle...",
        "ru": "Отправка на Kindle...", "zh": "正在发送到Kindle...",
    },
    "kindle_sent": {
        "pl": "📚 Wysłano na Kindle!", "en": "📚 Sent to Kindle!",
    },
    "kindle_error": {
        "pl": "Błąd wysyłki Kindle", "en": "Kindle send error",
    },
    "kindle_no_config": {
        "pl": "Uzupełnij dane Kindle w Ustawieniach (⚙️)",
        "en": "Fill in Kindle settings (⚙️)",
    },
}


def t(key: str, **kwargs) -> str:
    """Get translated string for the current system language.
    Falls back to English, then to the key name in brackets.
    """
    entry = STRINGS.get(key, {})
    text = entry.get(LANG, entry.get("en", f"[{key}]"))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
