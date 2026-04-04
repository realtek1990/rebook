"""ReBook for Windows — Native GUI with CustomTkinter.

Full-featured e-book converter with AI translation/correction.
First-run wizard auto-bootstraps a Python venv and installs dependencies.
"""
import json, os, sys, shutil, smtplib, subprocess, threading, queue
from pathlib import Path
from email.message import EmailMessage

# ── Paths ────────────────────────────────────────────────────────────────────
WORKSPACE = Path.home() / ".rebook"
VENV_DIR = WORKSPACE / "env"
CONFIG_FILE = WORKSPACE / "config.json"
CORE_MARKER = WORKSPACE / ".core_installed"
# In PyInstaller frozen mode, data files are in sys._MEIPASS
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).parent

WORKSPACE.mkdir(parents=True, exist_ok=True)

# ── Determine if running under venv ──────────────────────────────────────────
def _in_venv():
    return (VENV_DIR / "Scripts" / "python.exe").exists() and \
           sys.prefix == str(VENV_DIR)

def _venv_python():
    return str(VENV_DIR / "Scripts" / "python.exe")

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
    "mistral": ["mistral-large-latest", "mistral-medium", "pixtral-large-latest",
                "ministral-8b-latest", "ministral-3b-latest", "mistral-small-latest"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "zhipu": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "openai": ["gpt-5-preview", "gpt-4.5-preview", "gpt-4o", "gpt-4o-mini",
               "o3-mini", "o1", "o1-mini"],
    "anthropic": ["claude-4.6-opus", "claude-3-7-sonnet-latest",
                  "claude-3-5-haiku-latest", "claude-3-opus-latest"],
    "gemini": ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-pro"],
    "zhipuai": ["glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
             "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768"],
}

# ─────────────────────────────────────────────────────────────────────────────
#  FIRST-RUN INSTALLER WIZARD
# ─────────────────────────────────────────────────────────────────────────────

class InstallerWizard:
    """Native first-run setup wizard using customtkinter."""

    def __init__(self):
        import customtkinter as ctk
        self.ctk = ctk
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTkToplevel() if hasattr(ctk, '_default_root') and ctk._default_root else ctk.CTk()
        self.root.title(t("inst_window_title"))
        self.root.geometry("560x520")
        self.root.resizable(False, False)

        self._mode = "light"
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.root.destroy()
        sys.exit(0)

    def _build_ui(self):
        ctk = self.ctk
        f = self.root

        # Title
        ctk.CTkLabel(f, text=t("inst_title"), font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(f, text=t("inst_subtitle"), font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray70")).pack(pady=(0, 16))

        # Section header
        ctk.CTkLabel(f, text=t("inst_section_header"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray50", "gray70")).pack(anchor="w", padx=28, pady=(8, 4))

        # Light option
        self._radio_var = ctk.StringVar(value="light")
        light_frame = ctk.CTkFrame(f, corner_radius=8)
        light_frame.pack(fill="x", padx=24, pady=4)
        ctk.CTkRadioButton(light_frame, text=t("inst_light_title"),
                          variable=self._radio_var, value="light",
                          font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(light_frame, text=t("inst_light_desc"), font=ctk.CTkFont(size=11),
                     justify="left", text_color=("gray50", "gray70")).pack(anchor="w", padx=32, pady=(0, 10))

        # Full option
        full_frame = ctk.CTkFrame(f, corner_radius=8)
        full_frame.pack(fill="x", padx=24, pady=4)
        ctk.CTkRadioButton(full_frame, text=t("inst_full_title"),
                          variable=self._radio_var, value="full",
                          font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(full_frame, text=t("inst_full_desc"), font=ctk.CTkFont(size=11),
                     justify="left", text_color=("gray50", "gray70")).pack(anchor="w", padx=32, pady=(0, 10))

        # Progress area (hidden initially)
        self._progress_frame = ctk.CTkFrame(f, corner_radius=8)
        self._progress_label = ctk.CTkLabel(self._progress_frame, text=t("inst_preparing"),
                                            font=ctk.CTkFont(size=12))
        self._progress_label.pack(pady=(10, 4))
        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, width=480)
        self._progress_bar.pack(pady=(0, 10), padx=20)
        self._progress_bar.set(0)

        # Install button
        self._install_btn = ctk.CTkButton(f, text=t("inst_install_btn"),
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          height=42, command=self._start_install)
        self._install_btn.pack(pady=16, padx=24, fill="x")

        # Result label (hidden)
        self._result_label = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=12))

    def _start_install(self):
        self._mode = self._radio_var.get()
        self._install_btn.configure(state="disabled", text=t("inst_installing"))
        self._progress_frame.pack(fill="x", padx=24, pady=4)
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        try:
            # 1. Create venv
            self._update_progress(t("inst_preparing"), 0.05)
            if not (VENV_DIR / "Scripts" / "python.exe").exists():
                subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)],
                             check=True, capture_output=True)

            pip = str(VENV_DIR / "Scripts" / "pip.exe")
            python = _venv_python()

            # 2. Core packages
            self._update_progress(t("inst_core_progress"), 0.15)
            reqs = str(APP_DIR / "requirements.txt")
            r = subprocess.run([pip, "install", "-r", reqs],
                              capture_output=True, text=True)
            if r.returncode != 0:
                self._finish_error(t("inst_core_error") + "\n" + r.stderr[-500:])
                return

            self._update_progress(t("inst_core_progress"), 0.6)

            # 3. Marker (full mode only)
            if self._mode == "full":
                self._update_progress(t("inst_marker_progress"), 0.65)
                r2 = subprocess.run([pip, "install", "marker-pdf"],
                                    capture_output=True, text=True)
                if r2.returncode != 0:
                    self._update_progress(t("inst_marker_warn"), 0.9)

            # 4. Done
            CORE_MARKER.touch()
            self._update_progress(t("inst_done"), 1.0)
            self.root.after(500, self._show_done)

        except Exception as e:
            self._finish_error(str(e))

    def _update_progress(self, msg, pct):
        self.root.after(0, lambda: (
            self._progress_label.configure(text=msg),
            self._progress_bar.set(pct)
        ))

    def _finish_error(self, msg):
        self.root.after(0, lambda: (
            self._progress_label.configure(text=msg, text_color="red"),
            self._install_btn.configure(state="normal", text=t("inst_retry_btn"))
        ))

    def _show_done(self):
        self._install_btn.configure(state="normal", text=t("inst_launch_btn"),
                                    command=self._launch)
        self._result_label.configure(text=t("inst_ready"))
        self._result_label.pack(pady=4)

    def _launch(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return CORE_MARKER.exists()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION GUI
# ─────────────────────────────────────────────────────────────────────────────

class ReBookApp:
    """Main ReBook application window."""

    def __init__(self):
        import customtkinter as ctk
        self.ctk = ctk
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        # Try to use TkinterDnD for native drag&drop
        try:
            from tkinterdnd2 import TkinterDnD, DND_FILES
            self.root = TkinterDnD.Tk()
            self._dnd_available = True
        except ImportError:
            self.root = ctk.CTk()
            self._dnd_available = False
        self.root.title("ReBook")
        self.root.geometry("680x760")
        self.root.minsize(600, 700)

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
                                  text_color=("gray40", "gray80"),
                                  font=ctk.CTkFont(size=18))
        gear_btn.pack(side="right")
        ctk.CTkLabel(f, text=t("app_subtitle"), font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray70")).pack(anchor="w", padx=24, pady=(0, 12))

        # ── Drop Zone / File Badge ──
        self._drop_frame = ctk.CTkFrame(f, height=120, corner_radius=10,
                                         border_width=2, border_color="gray50")
        self._drop_frame.pack(fill="x", padx=24, pady=4)
        self._drop_frame.pack_propagate(False)
        ctk.CTkLabel(self._drop_frame, text="📥", font=ctk.CTkFont(size=36)).pack(pady=(14, 2))
        ctk.CTkLabel(self._drop_frame, text=t("drop_title"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        self._drop_sub = ctk.CTkLabel(self._drop_frame, text=t("drop_subtitle"),
                                       font=ctk.CTkFont(size=11), text_color=("gray50", "gray70"))
        self._drop_sub.pack()
        self._drop_frame.bind("<Button-1>", lambda e: self._open_file())
        for child in self._drop_frame.winfo_children():
            child.bind("<Button-1>", lambda e: self._open_file())

        # Enable native drag & drop if tkinterdnd2 is available
        if self._dnd_available:
            try:
                from tkinterdnd2 import DND_FILES
                self._drop_frame.drop_target_register(DND_FILES)
                self._drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                pass  # DnD not available, click still works

        # File badge (hidden)
        self._file_frame = ctk.CTkFrame(f, height=70, corner_radius=10)
        self._file_label = ctk.CTkLabel(self._file_frame, text="—",
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self._size_label = ctk.CTkLabel(self._file_frame, text="", text_color=("gray50", "gray70"),
                                        font=ctk.CTkFont(size=11))
        self._remove_btn = ctk.CTkButton(self._file_frame, text=t("remove_btn"), width=60,
                                          height=28, command=self._remove_file,
                                          fg_color="gray50")

        # ── Options ──
        ctk.CTkLabel(f, text=t("options_header"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray40", "#90B0D0")).pack(anchor="w", padx=28, pady=(16, 4))

        # Format
        fmt_row = ctk.CTkFrame(f, fg_color="transparent")
        fmt_row.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(fmt_row, text=t("format_label"), font=ctk.CTkFont(size=13)).pack(side="left")
        self._format_var = ctk.StringVar(value="EPUB")
        self._format_menu = ctk.CTkSegmentedButton(fmt_row, values=FORMATS,
                                                     variable=self._format_var)
        self._format_menu.pack(side="right")

        # AI Correction
        self._ai_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(f, text=t("ai_check"), variable=self._ai_var).pack(
            anchor="w", padx=28, pady=4)

        # Translation mode
        self._translate_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f, text=t("translate_check"), variable=self._translate_var,
                        command=self._toggle_translate).pack(anchor="w", padx=28, pady=4)

        # Translate images (hidden, shown when translate enabled)
        self._translate_img_var = ctk.BooleanVar(value=False)
        self._translate_img_check = ctk.CTkCheckBox(
            f, text=t("translate_images_check"),
            variable=self._translate_img_var,
            font=ctk.CTkFont(size=11),
        )

        # Language fields (hidden)
        self._lang_frame = ctk.CTkFrame(f, fg_color="transparent")
        r1 = ctk.CTkFrame(self._lang_frame, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text=t("lang_from_label"), width=110,
                     font=ctk.CTkFont(size=11), text_color=("gray50", "gray70")).pack(side="left")
        self._lang_from = ctk.CTkEntry(r1, placeholder_text=t("lang_from_placeholder"))
        self._lang_from.pack(side="left", fill="x", expand=True)
        r2 = ctk.CTkFrame(self._lang_frame, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text=t("lang_to_label"), width=110,
                     font=ctk.CTkFont(size=11), text_color=("gray50", "gray70")).pack(side="left")
        self._lang_to = ctk.CTkEntry(r2)
        self._lang_to.insert(0, "polski")
        self._lang_to.pack(side="left", fill="x", expand=True)

        # Convert button
        self._convert_btn = ctk.CTkButton(f, text=t("convert_btn"),
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           height=42, command=self._start_conversion,
                                           state="disabled")
        self._convert_btn.pack(fill="x", padx=24, pady=(16, 4))

        # Progress
        self._progress_bar = ctk.CTkProgressBar(f, width=600)
        self._progress_bar.set(0)
        self._stage_label = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=("gray50", "gray70"))

        # Log
        self._log_box = ctk.CTkTextbox(f, height=130, font=ctk.CTkFont(family="Consolas", size=10),
                                        state="disabled")

        # Result area
        self._result_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._result_label = ctk.CTkLabel(self._result_frame, text=t("conversion_done"),
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          text_color=("#2d8f2d", "#5dce5d"))
        self._result_label.pack(pady=(4, 8))
        btn_row = ctk.CTkFrame(self._result_frame, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text=t("save_btn"), command=self._save_result).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text=t("kindle_btn"), command=self._send_kindle,
                      fg_color="gray50").pack(side="left", padx=4)

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

        self._convert_btn.configure(state="normal")
        self._result_frame.pack_forget()

    def _remove_file(self):
        self._selected_file = None
        self._file_frame.pack_forget()
        self._drop_frame.pack(fill="x", padx=24, pady=4, before=self._convert_btn.master.winfo_children()[0])
        # Re-pack drop frame in the right place
        self._drop_frame.pack(fill="x", padx=24, pady=4)
        self._convert_btn.configure(state="disabled")
        self._result_frame.pack_forget()

    def _toggle_translate(self):
        if self._translate_var.get():
            self._lang_frame.pack(fill="x", padx=28, pady=4)
            self._translate_img_check.pack(anchor="w", padx=44, pady=2)
        else:
            self._lang_frame.pack_forget()
            self._translate_img_check.pack_forget()
            self._translate_img_var.set(False)

    # ── Settings ──

    def _open_settings(self):
        ctk = self.ctk
        win = ctk.CTkToplevel(self.root)
        win.title(t("settings_title"))
        win.geometry("460x680")
        win.resizable(False, False)
        win.grab_set()

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

        # ── Marker OCR Section ──
        ctk.CTkLabel(win, text=t("settings_marker_header"),
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray50", "gray70")).pack(
            anchor="w", padx=20, pady=(16, 4))

        marker_bin = WORKSPACE / "env" / "Scripts" / "marker_single.exe"
        marker_ok = marker_bin.exists()
        status_key = "settings_marker_installed" if marker_ok else "settings_marker_not_installed"
        marker_status = ctk.CTkLabel(win, text=t(status_key), font=ctk.CTkFont(size=11),
            text_color=("#2d8f2d", "#5dce5d") if marker_ok else ("orange", "orange"))
        marker_status.pack(anchor="w", padx=20, pady=(2, 4))

        if not marker_ok:
            marker_btn = ctk.CTkButton(win, text=t("settings_marker_install_btn"),
                                        height=32, command=lambda: self._install_marker_win(
                                            win, marker_btn, marker_status))
            marker_btn.pack(fill="x", padx=20, pady=2)

        # Buttons
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=16)

        def _save():
            idx = prov_names.index(prov_var.get()) if prov_var.get() in prov_names else 0
            save_config({
                "llm_provider": prov_keys[idx],
                "model_name": model_var.get(),
                "api_key": api_entry.get(),
                "kindle_email": kindle_entry.get(),
                "smtp_email": smtp_entry.get(),
                "smtp_pass": smtp_pass.get(),
            })
            win.destroy()

        ctk.CTkButton(btn_row, text=t("settings_save"), command=_save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text=t("settings_cancel"), fg_color="gray50",
                      command=win.destroy).pack(side="right", padx=4)

    def _install_marker_win(self, win, btn, status_label):
        btn.configure(state="disabled", text=t("settings_marker_installing"))
        def _do():
            pip = str(WORKSPACE / "env" / "Scripts" / "pip.exe")
            try:
                r = subprocess.run([pip, "install", "marker-pdf"],
                                   capture_output=True, text=True, timeout=600)
                if r.returncode == 0:
                    win.after(0, lambda: (
                        btn.pack_forget(),
                        status_label.configure(text=t("settings_marker_done"),
                                               text_color=("#2d8f2d", "#5dce5d")),
                    ))
                else:
                    win.after(0, lambda: (
                        btn.configure(state="normal", text=t("settings_marker_install_btn")),
                        status_label.configure(text=t("settings_marker_error"), text_color="red"),
                    ))
            except Exception as e:
                win.after(0, lambda: (
                    btn.configure(state="normal", text=t("settings_marker_install_btn")),
                    status_label.configure(text=t("settings_marker_error"), text_color="red"),
                ))
        threading.Thread(target=_do, daemon=True).start()

    # ── Conversion ──

    def _start_conversion(self):
        if not self._selected_file or self._converting:
            return
        self._converting = True
        self._convert_btn.configure(state="disabled", text=t("converting_btn"))
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
        use_llm = self._ai_var.get() or translate
        lang_from = self._lang_from.get() if translate else ""
        lang_to = self._lang_to.get() if translate else "polski"

        args = (str(self._selected_file), fmt, use_llm, translate, translate_images, lang_from, lang_to)
        threading.Thread(target=self._run_conversion, args=args, daemon=True).start()

    def _run_conversion(self, path, fmt, use_llm, translate, translate_images, lang_from, lang_to):
        # Run under venv python
        try:
            import converter
            result = converter.convert_file(
                path, fmt, use_llm, translate, translate_images, lang_from, lang_to,
                progress_callback=self._on_progress,
            )
            self._ui_queue.put(("done", result))
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
            elif kind == "error":
                self._conversion_error(data)
        self.root.after(100, self._poll_queue)

    def _update_progress(self, info):
        stage, pct, msg = info["stage"], info["pct"], info["msg"]
        total = pct / 100
        if stage == "ocr": total = pct * 0.004
        elif stage == "correction": total = 0.4 + pct * 0.003
        elif stage == "verification": total = 0.7 + pct * 0.001
        elif stage == "images": total = 0.8 + pct * 0.001
        elif stage == "export": total = 0.9 + pct * 0.001
        elif stage == "done": total = 1.0
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
        self._progress_bar.set(1.0)
        self._stage_label.configure(text=t("done"))
        self._result_frame.pack(fill="x", padx=24, pady=8)
        self._append_log(t("all_done", name=Path(output_path).name))

    def _conversion_error(self, error_msg):
        self._converting = False
        self._convert_btn.configure(state="normal", text=t("convert_btn"))
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
    # ── PyInstaller bundle: everything is already inside the .exe ─────────
    frozen = getattr(sys, 'frozen', False)

    if frozen:
        # All deps are bundled — skip venv/pip, go straight to app
        # Ensure WORKSPACE exists for config
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        CORE_MARKER.touch()  # mark as "installed"
        app = ReBookApp()
        app.run()
        return

    # ── Running from source (dev mode) ────────────────────────────────────
    try:
        import customtkinter  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "customtkinter"],
                      capture_output=True)

    # Check if first run
    if not CORE_MARKER.exists():
        wizard = InstallerWizard()
        if not wizard.run():
            sys.exit(0)

    # Re-exec under venv if needed
    venv_py = _venv_python()
    if os.path.exists(venv_py) and sys.executable != venv_py:
        os.execv(venv_py, [venv_py, __file__] + sys.argv[1:])

    # Launch main app
    app = ReBookApp()
    app.run()


if __name__ == "__main__":
    main()
