"""ReBook for Windows — Native GUI with CustomTkinter.

Full-featured e-book converter with AI translation/correction.
"""
import json, os, sys, shutil, smtplib, threading, queue
from pathlib import Path
from email.message import EmailMessage

# tts_engine is bundled alongside this script
sys.path.insert(0, str(Path(__file__).parent))
try:
    import tts_engine
except Exception:
    tts_engine = None

# ── Paths ────────────────────────────────────────────────────────────────────
WORKSPACE = Path.home() / ".rebook"
CONFIG_FILE = WORKSPACE / "config.json"
# In PyInstaller frozen mode, data files are in sys._MEIPASS
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).parent

WORKSPACE.mkdir(parents=True, exist_ok=True)


def _get_system_ram_gb():
    """Return total physical RAM in GB."""
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        return 99.0  # assume enough RAM if detection fails

# ── Config ───────────────────────────────────────────────────────────────────
def load_config():
    try: return json.load(open(CONFIG_FILE))
    except Exception: return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ── i18n ─────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(APP_DIR))
from i18n import t, LANG

# ── Providers & Models ───────────────────────────────────────────────────────
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
    "nvidia": [
        "mistralai/mistral-small-4-119b-2603",
        "qwen/qwen3.5-122b-a10b",
        "deepseek-ai/deepseek-v3.2",
        "meta/llama-3.3-70b-instruct",
        "google/gemma-3-27b-it",
    ],
    "mistral": ["mistral-large-latest", "mistral-medium", "pixtral-large-latest",
                "ministral-8b-latest", "ministral-3b-latest", "mistral-small-latest"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "zhipu": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "openai": ["gpt-5-preview", "gpt-4.5-preview", "gpt-4o", "gpt-4o-mini",
               "o3-mini", "o1", "o1-mini"],
    "anthropic": ["claude-4.6-opus", "claude-3-7-sonnet-latest",
                  "claude-3-5-haiku-latest", "claude-3-opus-latest"],
    "gemini": ["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-pro"],
    "zhipuai": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
             "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768"],
}

LANGUAGES = [
    "polski", "angielski", "niemiecki", "francuski", "hiszpański",
    "włoski", "portugalski", "rosyjski", "ukraiński", "czeski",
    "słowacki", "chiński", "japoński", "koreański", "turecki",
    "arabski", "holenderski", "szwedzki", "norweski", "duński",
    "fiński", "wietnamski", "tajski", "węgierski", "rumuński",
    "serbski", "chorwacki",
]




# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION GUI
# ─────────────────────────────────────────────────────────────────────────────

class ReBookApp:
    """Main ReBook application window."""

    def __init__(self):
        import customtkinter as ctk
        self.ctk = ctk
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Hybrid CTk + DnD root: dark mode theming + native drag & drop
        self._dnd_available = False
        try:
            from tkinterdnd2 import TkinterDnD

            class _CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.TkdndVersion = TkinterDnD._require(self)

            self.root = _CTkDnD()
            self._dnd_available = True
        except Exception:
            self.root = ctk.CTk()
            self._dnd_available = False
        self.root.title("ReBook")
        self.root.geometry("680x760")
        self.root.minsize(600, 700)

        # ── App Icon ──
        try:
            _ico = APP_DIR / "assets" / "icon.ico"
            if not _ico.exists():
                _ico = APP_DIR.parent / "assets" / "icon.ico"
            if _ico.exists():
                self.root.iconbitmap(str(_ico))
        except Exception:
            pass

        self._selected_file = None
        self._output_path = None
        self._converting = False
        self._ui_queue = queue.Queue()

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        ctk = self.ctk
        f = self.root

        # ── Header ──
        header = ctk.CTkFrame(f, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(16, 0))
        ctk.CTkLabel(header, text="ReBook", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        gear_btn = ctk.CTkButton(header, text="⚙️", width=36, height=36,
                                  command=self._open_settings, fg_color="transparent",
                                  text_color=("gray20", "gray80"),
                                  font=ctk.CTkFont(size=18))
        gear_btn.pack(side="right")
        ctk.CTkLabel(f, text=t("app_subtitle"), font=ctk.CTkFont(size=12),
                     text_color=("gray30", "gray70")).pack(anchor="w", padx=24, pady=(0, 12))

        # ── Drop Zone / File Badge ──
        self._drop_frame = ctk.CTkFrame(f, height=120, corner_radius=10,
                                         border_width=2, border_color="gray50")
        self._drop_frame.pack(fill="x", padx=24, pady=4)
        self._drop_frame.pack_propagate(False)
        ctk.CTkLabel(self._drop_frame, text="📥", font=ctk.CTkFont(size=36)).pack(pady=(14, 2))
        ctk.CTkLabel(self._drop_frame, text=t("drop_title"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        self._drop_sub = ctk.CTkLabel(self._drop_frame, text=t("drop_subtitle"),
                                       font=ctk.CTkFont(size=11), text_color=("gray30", "gray70"))
        self._drop_sub.pack()
        self._drop_frame.bind("<Button-1>", lambda e: self._open_file())
        for child in self._drop_frame.winfo_children():
            child.bind("<Button-1>", lambda e: self._open_file())

        # Enable native drag & drop if tkinterdnd2 is available
        if self._dnd_available:
            try:
                from tkinterdnd2 import DND_FILES
                # CTk widgets don't inherit DnDWrapper — register on root instead
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"DnD registration failed: {e}")
                self._dnd_available = False

        # File badge (hidden)
        self._file_frame = ctk.CTkFrame(f, height=70, corner_radius=10)
        self._file_label = ctk.CTkLabel(self._file_frame, text="—",
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self._size_label = ctk.CTkLabel(self._file_frame, text="", text_color=("gray30", "gray70"),
                                        font=ctk.CTkFont(size=11))
        self._remove_btn = ctk.CTkButton(self._file_frame, text=t("remove_btn"), width=60,
                                          height=28, command=self._remove_file,
                                          fg_color="gray50")

        # ── Options ──
        ctk.CTkLabel(f, text=t("options_header"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("#1a5276", "#90B0D0")).pack(anchor="w", padx=28, pady=(16, 4))

        # Format
        fmt_row = ctk.CTkFrame(f, fg_color="transparent")
        fmt_row.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(fmt_row, text=t("format_label"), font=ctk.CTkFont(size=13),
                     text_color=("gray10", "gray90")).pack(side="left")
        self._format_var = ctk.StringVar(value="EPUB")
        self._format_menu = ctk.CTkSegmentedButton(fmt_row, values=FORMATS,
                                                     variable=self._format_var)
        self._format_menu.pack(side="right")

        # AI Correction
        self._ai_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(f, text=t("ai_check"), variable=self._ai_var,
                        text_color=("gray10", "gray90")).pack(
            anchor="w", padx=28, pady=4)

        # Page range (PDF only, hidden by default)
        self._page_range_frame = ctk.CTkFrame(f, fg_color="transparent")
        pr_lbl = ctk.CTkLabel(self._page_range_frame, text="📄 Zakres stron:",
                              font=ctk.CTkFont(size=11),
                              text_color=("gray30", "gray70"))
        pr_lbl.pack(side="left", padx=(0, 6))
        self._page_start_var = ctk.StringVar(value="")
        self._page_start_entry = ctk.CTkEntry(self._page_range_frame, width=60,
                                              placeholder_text="Od",
                                              textvariable=self._page_start_var)
        self._page_start_entry.pack(side="left", padx=2)
        ctk.CTkLabel(self._page_range_frame, text="–",
                     font=ctk.CTkFont(size=13)).pack(side="left", padx=2)
        self._page_end_var = ctk.StringVar(value="")
        self._page_end_entry = ctk.CTkEntry(self._page_range_frame, width=60,
                                            placeholder_text="Do",
                                            textvariable=self._page_end_var)
        self._page_end_entry.pack(side="left", padx=2)
        self._page_count_label = ctk.CTkLabel(self._page_range_frame, text="",
                                              font=ctk.CTkFont(size=10),
                                              text_color=("gray50", "gray60"))
        self._page_count_label.pack(side="left", padx=(8, 0))
        # Hidden initially — shown when a PDF is selected

        # Translation mode
        self._translate_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f, text=t("translate_check"), variable=self._translate_var,
                        text_color=("gray10", "gray90"),
                        command=self._toggle_translate).pack(anchor="w", padx=28, pady=4)

        # Translate images (hidden, shown when translate enabled)
        self._translate_img_var = ctk.BooleanVar(value=False)
        self._translate_img_check = ctk.CTkCheckBox(
            f, text=t("translate_images_check"),
            variable=self._translate_img_var,
            font=ctk.CTkFont(size=11),
            text_color=("gray10", "gray90"),
        )

        # LLM verification (hidden, shown when translate enabled)
        self._verify_var = ctk.BooleanVar(value=False)
        self._verify_check = ctk.CTkCheckBox(
            f, text="🔍 Weryfikacja LLM (dokładna, extra koszt)",
            variable=self._verify_var,
            font=ctk.CTkFont(size=11),
            text_color=("gray10", "gray90"),
        )

        self._lang_frame = ctk.CTkFrame(f, fg_color="transparent")
        r1 = ctk.CTkFrame(self._lang_frame, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text=t("lang_from_label"), width=110,
                     font=ctk.CTkFont(size=11), text_color=("gray30", "gray70")).pack(side="left")
        self._lang_from = ctk.CTkComboBox(r1, values=LANGUAGES)
        self._lang_from.set("")
        self._lang_from.pack(side="left", fill="x", expand=True)
        r2 = ctk.CTkFrame(self._lang_frame, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text=t("lang_to_label"), width=110,
                     font=ctk.CTkFont(size=11), text_color=("gray30", "gray70")).pack(side="left")
        self._lang_to = ctk.CTkComboBox(r2, values=LANGUAGES)
        self._lang_to.set("polski")
        self._lang_to.pack(side="left", fill="x", expand=True)

        # ── Pipeline — krok Audiobook ──────────────────────────────────────────
        ctk.CTkLabel(f, text="🔗 Pipeline — opcjonalne kroki:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("#1a5276", "#90B0D0")).pack(anchor="w", padx=28, pady=(14, 2))

        self._pipeline_audiobook_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            f, text="🎧 Po konwersji → generuj Audiobook automatycznie",
            variable=self._pipeline_audiobook_var,
            text_color=("gray10", "gray90"),
            command=self._on_pipeline_audiobook_toggle,
        ).pack(anchor="w", padx=28, pady=2)

        # Voice for pipeline audiobook
        self._pipeline_voice_frame = ctk.CTkFrame(f, fg_color="transparent")
        pvr = ctk.CTkFrame(self._pipeline_voice_frame, fg_color="transparent")
        pvr.pack(fill="x", padx=44, pady=2)
        ctk.CTkLabel(pvr, text="Głos:", font=ctk.CTkFont(size=11),
                     text_color=("gray30", "gray70"), width=50).pack(side="left")
        if tts_engine:
            _pipeline_voice_labels = list(tts_engine.VOICES.values())
            _pipeline_voice_keys   = list(tts_engine.VOICES.keys())
        else:
            _pipeline_voice_labels = ["Marek (PL, Męski)", "Zofia (PL, Żeński)"]
            _pipeline_voice_keys   = ["pl-PL-MarekNeural", "pl-PL-ZofiaNeural"]
        self._pipeline_voice_keys   = _pipeline_voice_keys
        import tkinter as _tk
        self._pipeline_voice_var = _tk.StringVar(value=_pipeline_voice_labels[0])
        ctk.CTkOptionMenu(
            pvr, variable=self._pipeline_voice_var,
            values=_pipeline_voice_labels, width=200,
        ).pack(side="left", padx=4)

        # Convert + Stop buttons
        btn_frame = ctk.CTkFrame(f, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(16, 4))
        self._convert_btn = ctk.CTkButton(btn_frame, text=t("convert_btn"),
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           height=42, command=self._start_conversion,
                                           state="disabled")
        self._convert_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._stop_btn = ctk.CTkButton(btn_frame, text="⛔ Stop",
                                        font=ctk.CTkFont(size=13, weight="bold"),
                                        height=42, width=90, command=self._stop_conversion,
                                        fg_color="#8B0000", hover_color="#A52A2A")
        # Hidden initially
        self._stop_btn.pack_forget()

        # Progress
        self._progress_bar = ctk.CTkProgressBar(f, width=600)
        self._progress_bar.set(0)
        self._stage_label = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=("gray50", "gray70"))

        # Log
        self._log_box = ctk.CTkTextbox(f, height=130, font=ctk.CTkFont(family="Consolas", size=10),
                                        state="disabled")

        # Result area
        self._result_frame = ctk.CTkFrame(f, corner_radius=10)
        self._result_label = ctk.CTkLabel(self._result_frame, text=t("conversion_done"),
                                          font=ctk.CTkFont(size=16, weight="bold"),
                                          text_color=("#2d8f2d", "#5dce5d"))
        self._result_label.pack(pady=(12, 8))
        btn_row = ctk.CTkFrame(self._result_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 12))
        ctk.CTkButton(btn_row, text=t("save_btn"), command=self._save_result,
                      height=36, font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text=t("open_folder_btn"), command=self._open_output_folder,
                      height=36, fg_color="#2d6a4f").pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text=t("kindle_btn"), command=self._send_kindle,
                      height=36, fg_color="gray50").pack(side="left", padx=4)

        # ── Audiobook panel — always visible ─────────────────────────────────────────
        self._audiobook_frame = ctk.CTkFrame(self._result_frame, fg_color="transparent")

        ctk.CTkLabel(self._audiobook_frame, text="─" * 40,
                     text_color=("gray60", "gray50")).pack(pady=(4, 0))
        ctk.CTkLabel(self._audiobook_frame, text="🎧 Audiobook",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(4, 2))

        # EPUB source row
        epub_row = ctk.CTkFrame(self._audiobook_frame, fg_color="transparent")
        epub_row.pack(fill="x", padx=16, pady=(0, 2))
        self._audiobook_epub_label = ctk.CTkLabel(
            epub_row, text="Brak pliku EPUB — wybierz lub konwertuj",
            font=ctk.CTkFont(size=11), text_color=("gray50", "gray60")
        )
        self._audiobook_epub_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            epub_row, text="📂 Wybierz EPUB", width=130, height=28,
            command=self._pick_audiobook_epub, fg_color="#3a5a8a"
        ).pack(side="right")

        voice_row = ctk.CTkFrame(self._audiobook_frame, fg_color="transparent")
        voice_row.pack(fill="x", padx=16, pady=4)

        if tts_engine:
            self._voice_keys = list(tts_engine.VOICES.keys())
            voice_labels = list(tts_engine.VOICES.values())
        else:
            self._voice_keys = ["pl-PL-MarekNeural", "pl-PL-ZofiaNeural"]
            voice_labels = ["Marek (PL, Męski)", "Zofia (PL, żeński)"]

        import tkinter as tk
        self._voice_var = tk.StringVar(value=voice_labels[0])
        self._voice_combo = ctk.CTkOptionMenu(
            voice_row, variable=self._voice_var,
            values=voice_labels, width=220,
            command=lambda _: None
        )
        self._voice_combo.pack(side="left", padx=(0, 6))

        self._sample_btn = ctk.CTkButton(
            voice_row, text="▶ Sample", width=90, height=30,
            command=self._play_tts_sample, fg_color="#4a6fa5"
        )
        self._sample_btn.pack(side="left")

        self._audiobook_btn = ctk.CTkButton(
            self._audiobook_frame, text="🎧 Generuj audiobook",
            height=36, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_audiobook,
            fg_color="#6a4c93", hover_color="#7d5aad"
        )
        self._audiobook_btn.pack(fill="x", padx=16, pady=(4, 2))

        self._audiobook_status = ctk.CTkLabel(
            self._audiobook_frame, text="", font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray70")
        )
        self._audiobook_status.pack(pady=2)

        self._audiobook_folder_btn = ctk.CTkButton(
            self._audiobook_frame, text="📂 Otwórz folder z audiobokiem",
            height=32, command=self._open_audiobook_folder,
            fg_color="#2d6a4f"
        )
        # Hidden until generation completes
        self._audiobook_output_dir = None
        self._audiobook_epub_path = None  # path of EPUB to convert to audiobook
        # Panel is always visible
        self._audiobook_frame.pack(fill="x", padx=8, pady=(4, 8))

    # ── File handling ──

    def _open_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title=t("menu_open"),
            filetypes=[("Supported files", "*.pdf *.epub *.md"),
                       ("All files", "*.*")]
        )
        if path:
            self._set_file(path)

    def _on_drop(self, event):
        """Handle drag & drop from Windows Explorer."""
        raw = event.data
        # Windows tkdnd wraps paths with spaces in {curly braces}
        if raw.startswith('{'):
            path = raw.strip('{}')
        else:
            path = raw.strip()
        # Take only first file if multiple dropped
        if '\n' in path:
            path = path.split('\n')[0].strip()
        p = Path(path)
        if p.exists() and p.suffix.lower() in ('.pdf', '.epub', '.md'):
            self._set_file(str(p))

    def _set_file(self, path):
        p = Path(path)
        self._selected_file = str(p)
        size_mb = p.stat().st_size / (1024 * 1024)
        self._file_label.configure(text=f"📄  {p.name}")
        self._size_label.configure(text=f"{size_mb:.1f} MB")
        self._drop_frame.pack_forget()

        self._file_frame.pack(fill="x", padx=24, pady=4)
        self._file_frame.pack_propagate(False)
        self._file_label.pack(anchor="w", padx=12, pady=(10, 0))
        self._size_label.pack(anchor="w", padx=12)
        self._remove_btn.pack(anchor="e", padx=12, pady=(0, 8))

        # Show page range panel for PDFs
        is_pdf = p.suffix.lower() == ".pdf"
        if is_pdf:
            self._page_range_frame.pack(fill="x", padx=28, pady=4)
            try:
                sys.path.insert(0, str(APP_DIR))
                import corrector
                total = corrector.get_pdf_page_count(str(p))
                self._page_count_label.configure(text=f"(z {total} stron)")
            except Exception:
                self._page_count_label.configure(text="")
            self._page_start_var.set("")
            self._page_end_var.set("")
        else:
            self._page_range_frame.pack_forget()

        self._convert_btn.configure(state="normal")
        self._result_frame.pack_forget()

    def _remove_file(self):
        self._selected_file = None
        self._file_frame.pack_forget()
        self._drop_frame.pack(fill="x", padx=24, pady=4)
        self._convert_btn.configure(state="disabled")
        self._result_frame.pack_forget()

    def _toggle_translate(self):
        if self._translate_var.get():
            self._lang_frame.pack(fill="x", padx=28, pady=4)
            self._translate_img_check.pack(anchor="w", padx=44, pady=2)
            self._verify_check.pack(anchor="w", padx=44, pady=2)
        else:
            self._lang_frame.pack_forget()
            self._translate_img_check.pack_forget()
            self._verify_check.pack_forget()
            self._translate_img_var.set(False)
            self._verify_var.set(False)

    def _on_pipeline_audiobook_toggle(self):
        if self._pipeline_audiobook_var.get():
            self._pipeline_voice_frame.pack(fill="x", padx=28, pady=(0, 4))
        else:
            self._pipeline_voice_frame.pack_forget()

    # ── Settings ──

    def _open_settings(self):
        ctk = self.ctk
        win = ctk.CTkToplevel(self.root)
        win.title(t("settings_title"))
        win.geometry("460x680")
        win.resizable(False, False)
        # On Linux, CTkToplevel may render empty if grab_set() is called
        # before widgets are packed. We call it at the end instead.

        cfg = load_config()

        # Provider
        ctk.CTkLabel(win, text=t("settings_llm_header"),
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray50", "gray70")).pack(
            anchor="w", padx=20, pady=(16, 4))

        provs = _providers()
        prov_names = [p[0] for p in provs]
        prov_keys = [p[1] for p in provs]
        cur_prov = cfg.get("llm_provider", "Brak")
        cur_idx = prov_keys.index(cur_prov) if cur_prov in prov_keys else 0

        prov_var = ctk.StringVar(value=prov_names[cur_idx])
        ctk.CTkLabel(win, text=t("settings_provider")).pack(anchor="w", padx=20, pady=(4, 0))
        prov_menu = ctk.CTkOptionMenu(win, values=prov_names, variable=prov_var,
                                       command=lambda v: _update_models(v))
        prov_menu.pack(fill="x", padx=20, pady=2)

        # Model
        ctk.CTkLabel(win, text=t("settings_model")).pack(anchor="w", padx=20, pady=(8, 0))
        model_var = ctk.StringVar(value=cfg.get("model_name", ""))
        model_entry = ctk.CTkEntry(win, textvariable=model_var)
        model_entry.pack(fill="x", padx=20, pady=2)

        def _update_models(prov_name):
            idx = prov_names.index(prov_name) if prov_name in prov_names else 0
            key = prov_keys[idx]
            models = MODELS.get(key, [])
            if models:
                model_var.set(models[0])

        # API Key
        ctk.CTkLabel(win, text=t("settings_api_key")).pack(anchor="w", padx=20, pady=(8, 0))
        api_entry = ctk.CTkEntry(win, show="•")
        api_entry.insert(0, cfg.get("api_key", ""))
        api_entry.pack(fill="x", padx=20, pady=2)

        # Kindle section
        ctk.CTkLabel(win, text=t("settings_kindle_header"),
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray50", "gray70")).pack(
            anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(win, text=t("settings_kindle_email")).pack(anchor="w", padx=20, pady=(4, 0))
        kindle_entry = ctk.CTkEntry(win)
        kindle_entry.insert(0, cfg.get("kindle_email", ""))
        kindle_entry.pack(fill="x", padx=20, pady=2)

        ctk.CTkLabel(win, text=t("settings_smtp_email")).pack(anchor="w", padx=20, pady=(4, 0))
        smtp_entry = ctk.CTkEntry(win)
        smtp_entry.insert(0, cfg.get("smtp_email", ""))
        smtp_entry.pack(fill="x", padx=20, pady=2)

        ctk.CTkLabel(win, text=t("settings_smtp_pass")).pack(anchor="w", padx=20, pady=(4, 0))
        smtp_pass = ctk.CTkEntry(win, show="•")
        smtp_pass.insert(0, cfg.get("smtp_pass", ""))
        smtp_pass.pack(fill="x", padx=20, pady=2)

        # ── OCR Provider Section ──
        ctk.CTkLabel(win, text="OCR",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray50", "gray70")).pack(
            anchor="w", padx=20, pady=(16, 4))

        ocr_providers_display = ["Auto (najlepszy dostępny)", "Mistral OCR", "Gemini Cloud OCR"]
        ocr_providers_keys    = ["auto", "mistral", "gemini"]
        cur_ocr = cfg.get("ocr_provider", "auto")
        cur_ocr_idx = ocr_providers_keys.index(cur_ocr) if cur_ocr in ocr_providers_keys else 0

        ocr_prov_var = ctk.StringVar(value=ocr_providers_display[cur_ocr_idx])
        ctk.CTkLabel(win, text="Provider OCR:").pack(anchor="w", padx=20, pady=(4, 0))
        ctk.CTkOptionMenu(win, values=ocr_providers_display, variable=ocr_prov_var).pack(fill="x", padx=20, pady=2)

        ctk.CTkLabel(win, text="Klucz OCR (pusty = użyj klucza głównego):").pack(anchor="w", padx=20, pady=(8, 0))
        ocr_key_entry = ctk.CTkEntry(win, show="•")
        ocr_key_entry.insert(0, cfg.get("ocr_api_key", ""))
        ocr_key_entry.pack(fill="x", padx=20, pady=2)

        # Buttons
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=16)

        def _save():
            idx = prov_names.index(prov_var.get()) if prov_var.get() in prov_names else 0
            ocr_idx = ocr_providers_display.index(ocr_prov_var.get()) if ocr_prov_var.get() in ocr_providers_display else 0
            save_config({
                "llm_provider": prov_keys[idx],
                "model_name": model_var.get(),
                "api_key": api_entry.get(),
                "kindle_email": kindle_entry.get(),
                "smtp_email": smtp_entry.get(),
                "smtp_pass": smtp_pass.get(),
                "ocr_provider": ocr_providers_keys[ocr_idx],
                "ocr_api_key": ocr_key_entry.get(),
            })
            win.destroy()

        ctk.CTkButton(btn_row, text=t("settings_save"), command=_save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text=t("settings_cancel"), fg_color="gray50",
                      command=win.destroy).pack(side="right", padx=4)

        # Finalize window — grab_set AFTER all widgets are packed (fixes empty window on Linux)
        win.update()
        win.after(100, lambda: (win.lift(), win.focus_force(), win.grab_set()))

    # ── Conversion ──

    def _start_conversion(self):
        if not self._selected_file or self._converting:
            return

        self._converting = True
        self._cancel_flag = False
        self._convert_btn.configure(state="disabled", text=t("converting_btn"))
        self._stop_btn.pack(side="right", padx=(4, 0))
        self._result_frame.pack_forget()
        self._progress_bar.set(0)
        self._progress_bar.pack(fill="x", padx=24, pady=(8, 2))
        self._stage_label.configure(text=t("starting"))
        self._stage_label.pack(anchor="w", padx=28)
        self._log_box.pack(fill="x", padx=24, pady=4)
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        fmt_idx = FORMATS.index(self._format_var.get())
        fmt = FORMAT_KEYS[fmt_idx]
        translate = self._translate_var.get()
        translate_images = self._translate_img_var.get() if translate else False
        verify = self._verify_var.get() if translate else False
        use_llm = self._ai_var.get() or translate
        lang_from = self._lang_from.get() if translate else ""
        lang_to = self._lang_to.get() if translate else "polski"

        args = (str(self._selected_file), fmt, use_llm, translate, translate_images, lang_from, lang_to, 0, 0, verify)

        # Page range (PDF only)
        page_start = 0
        page_end = 0
        try:
            ps = self._page_start_var.get().strip()
            pe = self._page_end_var.get().strip()
            if ps:
                page_start = int(ps)
            if pe:
                page_end = int(pe)
        except (ValueError, AttributeError):
            pass

        args = args[:-2] + (page_start, page_end) + (verify,)
        threading.Thread(target=self._run_conversion, args=args, daemon=True).start()

    def _stop_conversion(self):
        """User clicked Stop — set cancel flag."""
        self._cancel_flag = True
        self._stage_label.configure(text="⛔ Zatrzymywanie…")
        self._append_log("⛔ Zatrzymywanie konwersji…")

    def _run_conversion(self, path, fmt, use_llm, translate, translate_images, lang_from, lang_to, page_start=0, page_end=0, verify=False):
        try:
            import converter

            def _progress_with_cancel(stage, pct, msg):
                if self._cancel_flag:
                    raise InterruptedError("⛔ Konwersja zatrzymana przez użytkownika")
                self._on_progress(stage, pct, msg)

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
            self._ui_queue.put(("done", result))
        except InterruptedError:
            self._ui_queue.put(("cancelled", None))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._ui_queue.put(("error", str(e)))

    def _on_progress(self, stage, pct, msg):
        self._ui_queue.put(("progress", {"stage": stage, "pct": pct, "msg": msg}))

    def _poll_queue(self):
        while not self._ui_queue.empty():
            kind, data = self._ui_queue.get_nowait()
            if kind == "progress":
                self._update_progress(data)
            elif kind == "done":
                self._conversion_done(data)
            elif kind == "cancelled":
                self._conversion_cancelled()
            elif kind == "error":
                self._conversion_error(data)
        self.root.after(100, self._poll_queue)

    def _update_progress(self, info):
        stage, pct, msg = info["stage"], info["pct"], info["msg"]
        # Map each stage to a sub-range of the overall 0.0→1.0 progress bar.
        # Stages: ocr(0-35%), correction(35-55%), verification(55-85%), images(85-90%), export(90-100%)
        stage_map = {
            "ocr":          (0.00, 0.35),
            "correction":   (0.35, 0.55),
            "verification": (0.55, 0.85),
            "images":       (0.85, 0.90),
            "export":       (0.90, 1.00),
            "done":         (1.00, 1.00),
        }
        if stage not in stage_map:
            # Unknown stage — update label but don't move bar erratically
            self._stage_label.configure(text=msg)
            self._append_log(msg)
            return
        lo, hi = stage_map[stage]
        total = lo + (pct / 100.0) * (hi - lo)
        self._progress_bar.set(min(total, 1.0))
        self._stage_label.configure(text=msg)
        self._append_log(msg)

    def _append_log(self, msg):
        import time
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _conversion_done(self, output_path):
        self._output_path = output_path
        self._converting = False
        self._convert_btn.configure(state="normal", text=t("convert_btn"))
        self._stop_btn.pack_forget()
        self._progress_bar.set(1.0)
        self._stage_label.configure(text=t("done"))
        self._log_box.pack_forget()  # hide log to make room for result
        self._result_frame.pack(fill="x", padx=24, pady=8)
        self._append_log(t("all_done", name=Path(output_path).name))
        # Update audiobook panel EPUB source when conversion produces EPUB
        if str(output_path).endswith('.epub') and tts_engine:
            self._audiobook_epub_path = str(output_path)
            name = Path(output_path).name
            self._audiobook_epub_label.configure(
                text=f"📖 {name}", text_color=("gray30", "gray80")
            )
            self._audiobook_status.configure(text="")
            self._audiobook_folder_btn.pack_forget()
        # Panel is always visible — no pack/pack_forget needed

        # ── Pipeline: auto-generate audiobook if checkbox is set ─────────────
        if (str(output_path).endswith('.epub')
                and tts_engine
                and self._pipeline_audiobook_var.get()):
            self._append_log("🔗 Pipeline: uruchamiam generowanie audiobooka…")
            # Set the pipeline voice as the audiobook voice and kick off
            voice_label = self._pipeline_voice_var.get()
            voice_labels = list(tts_engine.VOICES.values())
            idx = voice_labels.index(voice_label) if voice_label in voice_labels else 0
            # Set voice in the audiobook panel selector too (for consistency)
            self._voice_var.set(voice_label)
            # Auto-trigger after short delay so UI can update
            self.root.after(500, self._generate_audiobook)

    def _pick_audiobook_epub(self):
        """Let user pick any EPUB file for audiobook generation."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Wybierz plik EPUB do audiobooka",
            filetypes=[("Pliki EPUB", "*.epub"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self._audiobook_epub_path = path
            import os
            name = os.path.basename(path)
            self._audiobook_epub_label.configure(
                text=f"📖 {name}", text_color=("gray30", "gray80")
            )
            self._audiobook_status.configure(text="")
            self._audiobook_folder_btn.pack_forget()

    def _play_tts_sample(self):
        if not tts_engine:
            return
        self._sample_btn.configure(text="⏳", state="disabled")
        voice_label = self._voice_var.get()
        voice_labels = list(tts_engine.VOICES.values())
        idx = voice_labels.index(voice_label) if voice_label in voice_labels else 0
        voice = self._voice_keys[idx]

        def _done(err):
            self.root.after(0, lambda: self._sample_btn.configure(text="▶ Sample", state="normal"))
            if err:
                self.root.after(0, lambda: self._audiobook_status.configure(
                    text=f"❌ {err[:60]}", text_color="red"))
        tts_engine.generate_sample(voice, _done)

    def _generate_audiobook(self):
        if not tts_engine:
            return
        # Priority: 1) explicitly picked EPUB, 2) conversion output, 3) loaded input file
        src = getattr(self, '_audiobook_epub_path', None)
        if not src or not str(src).endswith('.epub'):
            src = getattr(self, '_output_path', None)
        if not src or not str(src).endswith('.epub'):
            sel = getattr(self, '_selected_file', None)
            if sel and str(sel).endswith('.epub'):
                src = sel
            else:
                self._audiobook_status.configure(
                    text="❌ Najpierw skonwertuj plik do EPUB", text_color="red")
                return

        # Extract chapters and show selection dialog
        try:
            chapters = tts_engine.list_chapters(str(src))
        except Exception as e:
            self._audiobook_status.configure(text=f"❌ {str(e)[:80]}", text_color="red")
            return
        if not chapters:
            self._audiobook_status.configure(text="❌ EPUB nie zawiera rozdziałów", text_color="red")
            return

        selected = self._show_chapter_selector(chapters)
        if selected is None:  # user cancelled
            return

        voice_label = self._voice_var.get()
        voice_labels = list(tts_engine.VOICES.values())
        idx = voice_labels.index(voice_label) if voice_label in voice_labels else 0
        voice = self._voice_keys[idx]

        src_path = Path(str(src))
        out_dir = src_path.parent / f"{src_path.stem}_audiobook"
        self._audiobook_output_dir = str(out_dir)

        self._audiobook_btn.configure(state="disabled", text="⏳ Generuję…")
        self._audiobook_status.configure(
            text=f"Generowanie {len(selected)}/{len(chapters)} rozdziałów…",
            text_color=("gray50", "gray70"))
        self._audiobook_folder_btn.pack_forget()

        def _progress(cur, total, msg):
            self.root.after(0, lambda: self._audiobook_status.configure(text=msg))

        def _run():
            try:
                paths = tts_engine.generate_audiobook(
                    epub_path=str(src),
                    voice=voice,
                    output_dir=str(out_dir),
                    progress_cb=_progress,
                    selected_chapters=selected,
                )
                self.root.after(0, lambda: self._audiobook_done(len(paths)))
            except Exception as e:
                import traceback; traceback.print_exc()
                self.root.after(0, lambda: self._audiobook_error(str(e)))

        threading.Thread(target=_run, daemon=True).start()

    def _show_chapter_selector(self, chapters):
        """Show chapter selection dialog. Returns list of selected indices or None."""
        result = [None]  # mutable for closure

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("📋 Wybierz rozdziały")
        dialog.geometry("460x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)

        ctk.CTkLabel(dialog, text=f"Znaleziono {len(chapters)} rozdziałów:",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))

        # Select all / deselect all
        all_var = ctk.BooleanVar(value=True)
        check_vars = []

        def toggle_all():
            state = all_var.get()
            for v in check_vars:
                v.set(state)

        ctk.CTkCheckBox(dialog, text="Zaznacz / Odznacz wszystkie",
                        variable=all_var, command=toggle_all,
                        font=ctk.CTkFont(size=12, weight="bold")).pack(padx=16, anchor="w", pady=4)

        # Scrollable chapter list
        scroll = ctk.CTkScrollableFrame(dialog, height=350)
        scroll.pack(fill="both", expand=True, padx=12, pady=4)

        for i, ch in enumerate(chapters):
            var = ctk.BooleanVar(value=True)
            check_vars.append(var)
            words = len(ch.text.split())
            label = f"{i+1}. {ch.title[:45]}  (~{words} słów)"
            ctk.CTkCheckBox(scroll, text=label, variable=var,
                            font=ctk.CTkFont(size=11)).pack(anchor="w", pady=1)

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=8)

        def on_cancel():
            dialog.destroy()

        def on_generate():
            result[0] = [chapters[i].index for i, v in enumerate(check_vars) if v.get()]
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Anuluj", width=100,
                      fg_color="gray40", command=on_cancel).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="🎧 Generuj", width=160,
                      command=on_generate).pack(side="right", padx=4)

        dialog.wait_window()

        if result[0] is not None and len(result[0]) == 0:
            self._audiobook_status.configure(text="Nie wybrano żadnych rozdziałów", text_color="orange")
            return None

        return result[0]

    def _audiobook_done(self, count):
        self._audiobook_btn.configure(state="normal", text="🎧 Generuj audiobook")
        self._audiobook_status.configure(
            text=f"✅ Gotowe! {count} rozdziałów MP3 + playlist.m3u",
            text_color=("#2d8f2d", "#5dce5d")
        )
        self._audiobook_folder_btn.pack(fill="x", padx=16, pady=(2, 8))

    def _audiobook_error(self, err):
        self._audiobook_btn.configure(state="normal", text="🎧 Generuj audiobook")
        self._audiobook_status.configure(
            text=f"❌ {err[:80]}", text_color="red")

    def _open_audiobook_folder(self):
        folder = self._audiobook_output_dir
        if folder and Path(folder).exists():
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])


    def _conversion_cancelled(self):
        self._converting = False
        self._convert_btn.configure(state="normal", text=t("convert_btn"))
        self._stop_btn.pack_forget()
        self._progress_bar.pack_forget()
        self._stage_label.configure(text="⛔ Konwersja zatrzymana")
        self._append_log("⛔ Konwersja zatrzymana przez użytkownika")

    def _conversion_error(self, error_msg):
        self._converting = False
        self._convert_btn.configure(state="normal", text=t("convert_btn"))
        self._stop_btn.pack_forget()
        self._stage_label.configure(text=f"{t('error_prefix')}: {error_msg}")
        self._append_log(f"{t('error_prefix')}: {error_msg}")
        from tkinter import messagebox
        messagebox.showerror(t("error_title"), str(error_msg)[:500])

    # ── Save / Kindle ──

    def _save_result(self):
        if not self._output_path: return
        from tkinter import filedialog
        src = Path(self._output_path)
        dest = filedialog.asksaveasfilename(
            title=t("save_title"),
            initialfile=src.name,
            defaultextension=src.suffix,
        )
        if dest:
            shutil.copy2(str(src), dest)

    def _open_output_folder(self):
        if not self._output_path: return
        folder = str(Path(self._output_path).parent)
        try:
            os.startfile(folder)
        except Exception:
            pass

    def _send_kindle(self):
        if not self._output_path: return
        cfg = load_config()
        src = Path(self._output_path)
        from tkinter import messagebox

        if cfg.get("kindle_email") and cfg.get("smtp_email") and cfg.get("smtp_pass"):
            try:
                msg = EmailMessage()
                msg["Subject"] = "Convert"
                msg["From"] = cfg["smtp_email"]
                msg["To"] = cfg["kindle_email"]
                msg.set_content(f"Sending: {src.name}")
                with open(src, "rb") as fp:
                    msg.add_attachment(fp.read(), maintype="application",
                                      subtype="epub+zip", filename=src.name)
                with smtplib.SMTP("smtp.gmail.com", 587) as s:
                    s.starttls()
                    s.login(cfg["smtp_email"], cfg["smtp_pass"])
                    s.send_message(msg)
                messagebox.showinfo("✅", t("kindle_sent"))
                return
            except Exception as e:
                messagebox.showerror(t("kindle_error"), str(e))
                return
        messagebox.showwarning(t("kindle_error"), t("kindle_no_config"))

    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── Plug & Play: no venv, no wizard ──────────────────────────────────
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    try:
        import customtkinter  # noqa
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "customtkinter"],
                      capture_output=True)

    # Launch main app directly — plug & play
    app = ReBookApp()
    app.run()


if __name__ == "__main__":
    main()
