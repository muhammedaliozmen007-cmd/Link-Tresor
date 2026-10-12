"""Link-Tresor – Links, Notizen und Dateien mit einem Klick ins GitHub-Repo.

Start:  Link-Tresor.exe (Windows)  oder  python link_tresor.pyw
"""

import json
import os
import platform
import queue
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
import webbrowser
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import converter  # noqa: E402
import tiktok  # noqa: E402
import youtube  # noqa: E402
import updater  # noqa: E402
from github_api import BELL_PREFIX, GitHubClient, GitHubError  # noqa: E402
from tresor import (  # noqa: E402
    DEFAULT_FOLDER,
    MAX_FILE_BYTES,
    Tresor,
    folder_dir,
    note_label,
    parse_link_line,
    parse_note,
)

# Drag & Drop ist optional (pip install tkinterdnd2)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseTk = TkinterDnD.Tk
    HAS_DND = True
except Exception:
    BaseTk = tk.Tk
    HAS_DND = False

APP_NAME = "Link-Tresor"
# Daten (Tresor, Feedback, Klingel) liegen im privaten Repo, die App selbst (Code + Updates) im öffentlichen
DEFAULT_REPO = "muhammedaliozmen007-cmd/Link-Tresor-Privat"
APP_REPO = "muhammedaliozmen007-cmd/Link-Tresor"
# Früher lag beides zusammen in APP_REPO – solche Einstellungen auf das private Repo umstellen
OLD_DATA_REPOS = {APP_REPO.lower()}
DEFAULT_BRANCH = "main"
TOKEN_URL = "https://github.com/settings/tokens/new?scopes=repo&description=Link-Tresor"
# Klingel-Button: so oft mit GitHub abgleichen / so lange lokal Bekanntes ergänzen
BELL_REFRESH_MS = 60_000
FRESH_SECONDS = 120

# Branches aus früheren Versionen, die durch den Standard-Branch (main) ersetzt wurden
OLD_BRANCHES = {"claude/dreamy-brown-udjssv"}

FONT = "Segoe UI"

# ---------------------------------------------------------------- Dark Mode
C = {
    "bg": "#1e1f22",
    "surface": "#2b2d31",
    "field": "#383a40",
    "border": "#4e5058",
    "text": "#e8e9eb",
    "muted": "#9ca3af",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_text": "#ffffff",
    "error": "#f87171",
    "ok": "#4ade80",
    "link": "#60a5fa",
}


def apply_dark_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=C["bg"])

    style.configure(
        ".",
        background=C["bg"],
        foreground=C["text"],
        fieldbackground=C["field"],
        bordercolor=C["border"],
        lightcolor=C["surface"],
        darkcolor=C["surface"],
        troughcolor=C["surface"],
        selectbackground=C["accent"],
        selectforeground=C["accent_text"],
        insertcolor=C["text"],
        focuscolor=C["accent"],
        font=(FONT, 10),
    )
    style.configure("TFrame", background=C["bg"])
    style.configure("Card.TFrame", background=C["surface"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"])
    style.configure("Card.TLabel", background=C["surface"], foreground=C["text"])
    style.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"])
    style.configure("CardMuted.TLabel", background=C["surface"], foreground=C["muted"])
    style.configure("Title.TLabel", background=C["bg"], foreground=C["text"], font=(FONT, 15, "bold"))
    style.configure("Link.TLabel", background=C["surface"], foreground=C["link"])
    style.configure("Error.TLabel", background=C["surface"], foreground=C["error"])
    style.configure("Status.TLabel", background=C["bg"], foreground=C["muted"])

    style.configure(
        "TButton",
        background=C["field"],
        foreground=C["text"],
        bordercolor=C["field"],
        lightcolor=C["field"],
        darkcolor=C["field"],
        padding=(10, 5),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("disabled", C["surface"]), ("pressed", C["surface"]), ("active", C["border"])],
        foreground=[("disabled", C["muted"])],
        bordercolor=[("focus", C["accent"])],
    )
    style.configure(
        "Accent.TButton",
        background=C["accent"],
        foreground=C["accent_text"],
        bordercolor=C["accent"],
        lightcolor=C["accent"],
        darkcolor=C["accent"],
        padding=(14, 7),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", C["field"]), ("pressed", C["accent_hover"]), ("active", C["accent_hover"])],
        bordercolor=[("active", C["accent_hover"])],
    )

    style.configure(
        "TEntry",
        fieldbackground=C["field"],
        foreground=C["text"],
        insertcolor=C["text"],
        bordercolor=C["border"],
        lightcolor=C["field"],
        darkcolor=C["field"],
        padding=6,
    )
    style.map("TEntry", bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])])

    style.configure(
        "TRadiobutton",
        background=C["surface"],
        foreground=C["text"],
        indicatorbackground=C["field"],
        indicatorforeground=C["accent"],
    )
    style.map(
        "TRadiobutton",
        background=[("active", C["surface"])],
        indicatorbackground=[("selected", C["accent"])],
    )

    style.configure(
        "TCheckbutton",
        background=C["surface"],
        foreground=C["text"],
        indicatorbackground=C["field"],
        indicatorforeground=C["accent_text"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", C["surface"])],
        indicatorbackground=[("selected", C["accent"])],
    )

    style.configure(
        "Horizontal.TProgressbar",
        background=C["accent"],
        troughcolor=C["field"],
        bordercolor=C["border"],
        lightcolor=C["accent"],
        darkcolor=C["accent"],
    )

    style.configure("TNotebook", background=C["bg"], bordercolor=C["bg"], tabmargins=(0, 0, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=C["bg"],
        foreground=C["muted"],
        bordercolor=C["bg"],
        lightcolor=C["bg"],
        padding=(14, 7),
        font=(FONT, 10),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", C["surface"]), ("active", C["surface"])],
        foreground=[("selected", C["text"]), ("active", C["text"])],
        lightcolor=[("selected", C["surface"])],
        bordercolor=[("selected", C["surface"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=C["field"],
        background=C["field"],
        foreground=C["text"],
        arrowcolor=C["text"],
        bordercolor=C["border"],
        lightcolor=C["field"],
        darkcolor=C["field"],
        padding=5,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", C["field"])],
        foreground=[("readonly", C["text"])],
        selectbackground=[("readonly", C["field"])],
        selectforeground=[("readonly", C["text"])],
        bordercolor=[("focus", C["accent"])],
        arrowcolor=[("disabled", C["muted"])],
    )
    root.option_add("*TCombobox*Listbox.background", C["field"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["accent_text"])
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))


def text_widget_opts(listbox=False):
    """Farben für klassische tk-Widgets (Text, Listbox)."""
    opts = dict(
        bg=C["field"],
        fg=C["text"],
        selectbackground=C["accent"],
        selectforeground=C["accent_text"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["accent"],
        font=(FONT, 10),
    )
    if not listbox:
        opts["insertbackground"] = C["text"]
    return opts


def dark_titlebar(window):
    """Dunkle Fenster-Titelleiste unter Windows 10/11."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (neu / alt)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        pass


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def enable_dpi_awareness():
    """Ohne das skaliert Windows das Fenster bei 125 %/150 % hoch -> alles verwischt."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # pro Monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def set_icon(window):
    try:
        window.iconbitmap(default=resource("icon.ico"))
    except tk.TclError:
        pass


# ----------------------------------------------------------------- Config
def config_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    if cfg.get("branch") in OLD_BRANCHES:
        cfg["branch"] = ""
        save_config(cfg)
    if (cfg.get("repo") or "").strip().strip("/").lower() in OLD_DATA_REPOS:
        cfg["repo"] = DEFAULT_REPO
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------- Dialoge
class Dialog(tk.Toplevel):
    def __init__(self, master, title):
        super().__init__(master)
        self.withdraw()
        self.title(title)
        self.configure(bg=C["surface"])
        self.resizable(False, False)
        self.transient(master)
        set_icon(self)
        self.body = ttk.Frame(self, padding=18, style="Card.TFrame")
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self, focus):
        self.update_idletasks()
        m = self.master
        x = m.winfo_rootx() + (m.winfo_width() - self.winfo_reqwidth()) // 2
        y = m.winfo_rooty() + (m.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        dark_titlebar(self)
        self.grab_set()
        focus.focus_set()


class SettingsDialog(Dialog):
    def __init__(self, master, cfg):
        super().__init__(master, "Einstellungen")
        self.result = None
        frm = self.body

        ttk.Label(frm, text="GitHub-Repository (besitzer/name):", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.repo = ttk.Entry(frm, width=48)
        self.repo.insert(0, cfg.get("repo", DEFAULT_REPO))
        self.repo.grid(row=1, column=0, sticky="we", pady=(4, 12))

        ttk.Label(frm, text="Branch (leer = main):", style="Card.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        self.branch = ttk.Entry(frm, width=48)
        self.branch.insert(0, cfg.get("branch", ""))
        self.branch.grid(row=3, column=0, sticky="we", pady=(4, 12))

        ttk.Label(frm, text="GitHub-Token:", style="Card.TLabel").grid(row=4, column=0, sticky="w")
        self.token = ttk.Entry(frm, width=48, show="•")
        self.token.insert(0, cfg.get("token", ""))
        self.token.grid(row=5, column=0, sticky="we", pady=(4, 4))

        link = ttk.Label(frm, text="Token erstellen (Haken bei „repo“) ↗", style="Link.TLabel", cursor="hand2")
        link.grid(row=6, column=0, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(TOKEN_URL))

        self.status = ttk.Label(frm, text="", style="Error.TLabel", wraplength=380)
        self.status.grid(row=7, column=0, sticky="w", pady=(10, 0))

        btns = ttk.Frame(frm, style="Card.TFrame")
        btns.grid(row=8, column=0, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        self.save_btn = ttk.Button(btns, text="Prüfen & speichern", style="Accent.TButton", command=self.on_save)
        self.save_btn.pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self.on_save())
        self.show(self.token)

    def on_save(self):
        cfg = {
            "repo": self.repo.get().strip(),
            "branch": self.branch.get().strip(),
            "token": self.token.get().strip(),
        }
        if not cfg["repo"] or "/" not in cfg["repo"] or not cfg["token"]:
            self.status.config(text="Bitte Repository (besitzer/name) und Token angeben.")
            return
        self.status.config(text="Prüfe Verbindung …", style="CardMuted.TLabel")
        self.save_btn.config(state="disabled")
        self.update_idletasks()
        try:
            GitHubClient(cfg["token"], cfg["repo"]).check()
        except GitHubError as e:
            self.status.config(text=str(e), style="Error.TLabel")
            self.save_btn.config(state="normal")
            return
        self.result = cfg
        self.destroy()


class FeedbackDialog(Dialog):
    KINDS = {
        "vorschlag": ("💡 Vorschlag", "💡"),
        "fehler": ("🐞 Fehler melden", "🐞"),
    }

    def __init__(self, app):
        super().__init__(app, "Feedback")
        self.app = app
        frm = self.body
        frm.columnconfigure(0, weight=1)

        ttk.Label(
            frm,
            text="Wird als Issue gespeichert. Wenn du fertig bist: „🔔 Claude rufen“ klicken.",
            style="CardMuted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        kinds = ttk.Frame(frm, style="Card.TFrame")
        kinds.grid(row=1, column=0, sticky="w", pady=(0, 10))
        self.kind = tk.StringVar(value="vorschlag")
        for key, (label, _) in self.KINDS.items():
            ttk.Radiobutton(kinds, text=label, value=key, variable=self.kind).pack(side="left", padx=(0, 16))

        ttk.Label(frm, text="Titel:", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.title_entry = ttk.Entry(frm, width=56)
        self.title_entry.grid(row=3, column=0, sticky="we", pady=(4, 12))

        ttk.Label(frm, text="Beschreibung:", style="Card.TLabel").grid(row=4, column=0, sticky="w")
        self.text = tk.Text(frm, height=9, width=56, wrap="word", padx=8, pady=6, **text_widget_opts())
        self.text.grid(row=5, column=0, sticky="nsew", pady=(4, 6))

        self.status = ttk.Label(frm, text="", style="Error.TLabel", wraplength=420)
        self.status.grid(row=6, column=0, sticky="w")

        btns = ttk.Frame(frm, style="Card.TFrame")
        btns.grid(row=7, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        self.send_btn = ttk.Button(btns, text="Senden", style="Accent.TButton", command=self.on_send)
        self.send_btn.pack(side="right", padx=(0, 8))

        self.show(self.title_entry)

    def on_send(self):
        title = self.title_entry.get().strip()
        desc = self.text.get("1.0", "end").strip()
        if not title:
            self.status.config(text="Bitte einen Titel eingeben.")
            self.title_entry.focus_set()
            return
        try:
            client = self.app.client()
        except GitHubError as e:
            self.status.config(text=str(e))
            return

        kind = self.kind.get()
        emoji = self.KINDS[kind][1]
        body = (
            (desc or "_Keine Beschreibung._")
            + f"\n\n---\n_Gesendet aus Link-Tresor {updater.current_version()} · "
            + f"{platform.system()} {platform.release()}_"
        )
        self.send_btn.config(state="disabled")
        self.status.config(text="Sende …", style="CardMuted.TLabel")

        def done(url):
            self.destroy()
            number = url.rstrip("/").rsplit("/", 1)[-1] if url else ""
            self.app.set_status(
                f"✔ Feedback #{number} gespeichert. Noch mehr? Sonst mit „🔔 Claude rufen“ abschicken."
            )
            if number.isdigit():
                self.app.feedback_created(int(number), f"{emoji} {title}")

        def failed(err):
            if self.winfo_exists():
                self.send_btn.config(state="normal")
                self.status.config(text=str(err), style="Error.TLabel")

        self.app.run_job(
            "Speichere Feedback",
            lambda: client.create_issue(f"{emoji} {title}", body, ["feedback", kind]),
            done,
            on_error=failed,
        )


class NameDialog(Dialog):
    """Fragt nach einem Namen (Ordner anlegen / umbenennen)."""

    def __init__(self, master, title, label, initial=""):
        super().__init__(master, title)
        self.result = None
        ttk.Label(self.body, text=label, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.entry = ttk.Entry(self.body, width=40)
        self.entry.insert(0, initial)
        self.entry.select_range(0, "end")
        self.entry.grid(row=1, column=0, sticky="we", pady=(4, 12))
        btns = ttk.Frame(self.body, style="Card.TFrame")
        btns.grid(row=2, column=0, sticky="e")
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="OK", style="Accent.TButton", command=self.on_ok).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.on_ok())
        self.show(self.entry)

    def on_ok(self):
        if self.entry.get().strip():
            self.result = self.entry.get().strip()
            self.destroy()


class EditLinkDialog(Dialog):
    """Link bearbeiten: Adresse, Titel, Notiz."""

    def __init__(self, master, url, title, note, heading="Link bearbeiten"):
        super().__init__(master, heading)
        self.result = None
        self.entries = []
        fields = (("Link (URL):", url), ("Titel (optional):", title), ("Notiz (optional):", note))
        for row, (label, value) in enumerate(fields):
            ttk.Label(self.body, text=label, style="Card.TLabel").grid(row=row * 2, column=0, sticky="w")
            e = ttk.Entry(self.body, width=60)
            e.insert(0, value)
            e.grid(row=row * 2 + 1, column=0, sticky="we", pady=(4, 12))
            self.entries.append(e)
        btns = ttk.Frame(self.body, style="Card.TFrame")
        btns.grid(row=6, column=0, sticky="e")
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Speichern", style="Accent.TButton", command=self.on_ok).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.on_ok())
        self.show(self.entries[0])

    def on_ok(self):
        url, title, note = (e.get() for e in self.entries)
        if not url.strip():
            self.entries[0].focus_set()
            return
        self.result = (url, title, note)
        self.destroy()


class EditNoteDialog(Dialog):
    """Notiz bearbeiten: Titel und Text."""

    def __init__(self, master, title, text, heading="Notiz bearbeiten"):
        super().__init__(master, heading)
        self.resizable(True, True)
        self.result = None
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(3, weight=1)
        ttk.Label(self.body, text="Titel:", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.title_entry = ttk.Entry(self.body, width=60)
        self.title_entry.insert(0, title)
        self.title_entry.grid(row=1, column=0, sticky="we", pady=(4, 12))
        ttk.Label(self.body, text="Text:", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.text = tk.Text(self.body, width=70, height=18, wrap="word", padx=10, pady=8, **text_widget_opts())
        self.text.insert("1.0", text)
        self.text.grid(row=3, column=0, sticky="nsew", pady=(4, 12))
        btns = ttk.Frame(self.body, style="Card.TFrame")
        btns.grid(row=4, column=0, sticky="e")
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Speichern", style="Accent.TButton", command=self.on_ok).pack(side="right", padx=(0, 8))
        self.show(self.text)

    def on_ok(self):
        title, text = self.title_entry.get(), self.text.get("1.0", "end")
        if not title.strip() and not text.strip():
            return
        self.result = (title, text)
        self.destroy()


class NoteViewer(Dialog):
    def __init__(self, master, title, text, url, on_edit=None):
        super().__init__(master, title)
        self.resizable(True, True)
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        box = tk.Text(self.body, width=70, height=22, wrap="word", padx=10, pady=8, **text_widget_opts())
        box.insert("1.0", text)
        box.config(state="disabled")
        box.grid(row=0, column=0, sticky="nsew")
        btns = ttk.Frame(self.body, style="Card.TFrame")
        btns.grid(row=1, column=0, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Schließen", style="Accent.TButton", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Auf GitHub öffnen ↗", command=lambda: webbrowser.open(url)).pack(
            side="right", padx=(0, 8)
        )
        self.copy_btn = ttk.Button(btns, text="📋 Kopieren", command=lambda: self.copy(text))
        self.copy_btn.pack(side="right", padx=(0, 8))
        if on_edit:
            ttk.Button(btns, text="✎ Bearbeiten", command=lambda: (self.destroy(), on_edit())).pack(
                side="right", padx=(0, 8)
            )
        self.show(box)

    def copy(self, text):
        """Inhalt der Notiz (ohne Überschrift und Datum) in die Zwischenablage."""
        content = parse_note(text)[2] or text.strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.copy_btn.config(text="✔ Kopiert")
        self.after(1500, lambda: self.copy_btn.winfo_exists() and self.copy_btn.config(text="📋 Kopieren"))


# -------------------------------------------------------------------- App
class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(APP_NAME)
        scale = max(self.winfo_fpixels("1i") / 96, 1.0)
        self.geometry(f"{int(880 * scale)}x{int(620 * scale)}")
        self.minsize(int(640 * scale), int(540 * scale))
        set_icon(self)
        apply_dark_theme(self)

        self.cfg = load_config()
        self.jobs = queue.Queue()
        self.busy = 0
        self.update_info = None
        self.open_feedback_items = []  # [(nummer, titel, schon_gerufen)]
        # Lokal bekannt, aber evtl. noch nicht in GitHubs Listen: nummer -> (titel, läuft ab um)
        self.fresh_feedback = {}
        self.fresh_rung = {}
        self.folder = self.cfg.get("folder") or DEFAULT_FOLDER
        # Übersicht: lokaler Stand je Ordner, wird sofort angezeigt und im Hintergrund abgeglichen
        self.cache = {}
        self.hidden = {}  # gerade gelöscht: key -> läuft ab um
        self.added = {}  # gerade hinzugefügt: ordner -> [(art, eintrag, läuft ab um)]

        updater.cleanup_old()
        self._build_ui()
        self.deiconify()
        dark_titlebar(self)
        self.after(100, self._poll_jobs)

        if not self.cfg.get("token"):
            self.after(200, self.open_settings)
        else:
            self.after(200, self.refresh_folders)
            self.after(800, lambda: self.check_update(silent=True))
            self.after(1200, self.refresh_bell)
        self.after(BELL_REFRESH_MS, self._bell_timer)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        top = ttk.Frame(self, padding=(16, 12, 16, 0))
        top.pack(fill="x")
        self.logo = self._load_logo()
        ttk.Label(top, text=" Link-Tresor", image=self.logo, compound="left", style="Title.TLabel").pack(
            side="left"
        )
        ttk.Label(top, text=updater.current_version(), style="Muted.TLabel").pack(
            side="left", padx=(8, 0), pady=(6, 0)
        )

        self.gear = self._load_icon("gear", (16, 20, 24, 32))
        if self.gear:
            ttk.Button(top, image=self.gear, command=self.open_settings, padding=(10, 6)).pack(side="right")
        else:
            ttk.Button(top, text="⚙", width=3, command=self.open_settings).pack(side="right")
        self.update_btn = ttk.Button(top, text="⬆ Update", command=self.check_update)
        self.update_btn.pack(side="right", padx=(6, 6))
        self.bell_btn = ttk.Button(top, text="🔔 Claude rufen", command=self.ring_claude)
        self.bell_btn.pack(side="right", padx=(6, 0))
        ttk.Button(top, text="💡 Feedback", command=self.open_feedback).pack(side="right")
        ttk.Button(top, text="🌐 GitHub", command=self.open_github).pack(side="right", padx=(0, 6))

        bar = ttk.Frame(self, padding=(16, 12, 16, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text="📁 Ordner:", style="TLabel").pack(side="left")
        self.folder_box = ttk.Combobox(bar, state="readonly", width=28, values=[self.folder])
        self.folder_box.set(self.folder)
        self.folder_box.pack(side="left", padx=(8, 8))
        self.folder_box.bind("<<ComboboxSelected>>", self._on_folder_selected)
        ttk.Button(bar, text="＋ Neu", command=self.new_folder).pack(side="left")
        self.rename_btn = ttk.Button(bar, text="✎ Umbenennen", command=self.rename_folder)
        self.rename_btn.pack(side="left", padx=(6, 0))
        self.delete_folder_btn = ttk.Button(bar, text="🗑 Löschen", command=self.delete_folder)
        self.delete_folder_btn.pack(side="left", padx=(6, 0))
        self._update_rename_btn()

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=12)

        self._build_overview_tab()
        self._build_tiktok_tab()
        self._build_youtube_tab()
        self._build_mp3_tab()

        # Fortschrittsleiste für Up-/Downloads (nur sichtbar, solange etwas läuft)
        self.transfer = ttk.Frame(self, padding=(16, 0, 16, 6))
        self.transfer_bar = ttk.Progressbar(self.transfer, mode="determinate", maximum=1000)
        self.transfer_bar.pack(fill="x")
        self.transfer_label = ttk.Label(self.transfer, text="", style="Status.TLabel")
        self.transfer_label.pack(fill="x", pady=(2, 0))
        self._transfer_state = None

        self.status = ttk.Label(self, text="Bereit.", style="Status.TLabel", padding=(16, 0, 16, 10))
        # unten verankern (vor den Tabs packen), sonst drücken die Tabs Status und Leiste aus dem Fenster
        self.status.pack(fill="x", side="bottom", before=self.tabs)

        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._apply_tab_order()
        self._dragged_tab = None
        self.tabs.bind("<ButtonPress-1>", self._tab_press, add="+")
        self.tabs.bind("<B1-Motion>", self._tab_drag, add="+")
        self.tabs.bind("<ButtonRelease-1>", self._tab_release, add="+")

    def _load_icon(self, name, sizes):
        """Symbol passend zur Bildschirm-Skalierung (16 px bei 100 %)."""
        scale = self.winfo_fpixels("1i") / 96
        want = 16 * scale
        size = min(sizes, key=lambda s: (s < want, abs(s - want)))
        try:
            return tk.PhotoImage(file=resource(f"{name}-{size}.png"))
        except tk.TclError:
            return None

    def _load_logo(self):
        """Logo passend zur Bildschirm-Skalierung laden (scharf statt hochgerechnet)."""
        scale = self.winfo_fpixels("1i") / 96
        size = 64 if scale >= 1.75 else 48 if scale >= 1.25 else 32
        try:
            return tk.PhotoImage(file=resource(f"logo-{size}.png"))
        except tk.TclError:
            return None

    def _new_tab(self, title):
        tab = ttk.Frame(self.tabs, padding=16, style="Card.TFrame")
        self.tabs.add(tab, text=title)
        tab.columnconfigure(0, weight=1)
        return tab

    def _build_tiktok_tab(self):
        tab = self._new_tab("🎵 TikTok")
        tab.rowconfigure(4, weight=1)

        ttk.Label(
            tab, text="TikTok-Links (einer pro Zeile – auch mehrere auf einmal):", style="Card.TLabel"
        ).grid(row=0, column=0, sticky="w")
        self.tt_links = tk.Text(tab, height=4, wrap="word", padx=8, pady=6, **text_widget_opts())
        self.tt_links.grid(row=1, column=0, sticky="we", pady=(4, 10))

        opts = ttk.Frame(tab, style="Card.TFrame")
        opts.grid(row=2, column=0, sticky="we")
        opts.columnconfigure(1, weight=1)
        self.tt_target = tk.StringVar(value=self.cfg.get("tiktok_target", "pc"))
        self.tt_kind = tk.StringVar(value=self.cfg.get("tiktok_kind", "video"))
        self.tt_keep_link = tk.BooleanVar(value=self.cfg.get("tiktok_link", True))
        ttk.Label(opts, text="Als:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        kinds = ttk.Frame(opts, style="Card.TFrame")
        kinds.grid(row=0, column=1, sticky="w", pady=(0, 8))
        ttk.Radiobutton(
            kinds, text="🎬 Video", value="video", variable=self.tt_kind, command=self._tt_options_changed
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            kinds, text="🎵 Nur Ton (MP3)", value="mp3", variable=self.tt_kind, command=self._tt_options_changed
        ).pack(side="left")
        ttk.Label(opts, text="Speichern:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Radiobutton(
            opts, text="💻 Auf diesem PC", value="pc", variable=self.tt_target, command=self._tt_options_changed
        ).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(
            opts,
            text="🔒 Im Tresor (aktueller Ordner)",
            value="tresor",
            variable=self.tt_target,
            command=self._tt_options_changed,
        ).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            opts, text="Link zusätzlich im Tresor merken", variable=self.tt_keep_link, command=self._tt_options_changed
        ).grid(row=3, column=1, sticky="w", pady=(4, 0))

        where = ttk.Frame(tab, style="Card.TFrame")
        where.grid(row=3, column=0, sticky="we", pady=(8, 8))
        where.columnconfigure(0, weight=1)
        self.tt_folder_label = ttk.Label(where, text="", style="CardMuted.TLabel")
        self.tt_folder_label.grid(row=0, column=0, sticky="w")
        self.tt_change_btn = ttk.Button(where, text="Ändern …", command=self._tt_choose_folder)
        self.tt_change_btn.grid(row=0, column=1, padx=(6, 0))
        self.tt_open_btn = ttk.Button(where, text="📂 Öffnen", command=self._tt_open_folder)
        self.tt_open_btn.grid(row=0, column=2, padx=(6, 0))

        self.tt_log = tk.Text(tab, height=5, wrap="word", padx=8, pady=6, state="disabled", **text_widget_opts())
        self.tt_log.grid(row=4, column=0, sticky="nsew")

        row = ttk.Frame(tab, style="Card.TFrame")
        row.grid(row=5, column=0, sticky="we", pady=(10, 0))
        ttk.Button(row, text="📋 Aus Zwischenablage", command=self._tt_paste).pack(side="left")
        self.tt_btn = ttk.Button(row, text="⬇ Herunterladen", style="Accent.TButton", command=self.download_tiktok)
        self.tt_btn.pack(side="right")
        self._tt_options_changed()

    def _build_youtube_tab(self):
        tab = self._new_tab("▶ YouTube")
        tab.rowconfigure(4, weight=1)

        ttk.Label(
            tab, text="YouTube-Links – Videos, Shorts, Playlists oder Kanäle (einer pro Zeile):", style="Card.TLabel"
        ).grid(row=0, column=0, sticky="w")
        self.yt_links = tk.Text(tab, height=4, wrap="word", padx=8, pady=6, **text_widget_opts())
        self.yt_links.grid(row=1, column=0, sticky="we", pady=(4, 10))

        opts = ttk.Frame(tab, style="Card.TFrame")
        opts.grid(row=2, column=0, sticky="we")
        saved = self.cfg.get("youtube_format", "best")
        self.yt_kind = tk.StringVar(value="mp3" if saved == "mp3" else "video")
        ttk.Label(opts, text="Als:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        kinds = ttk.Frame(opts, style="Card.TFrame")
        kinds.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            kinds, text="🎬 Video", value="video", variable=self.yt_kind, command=self._yt_options_changed
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            kinds, text="🎵 Nur Ton (MP3)", value="mp3", variable=self.yt_kind, command=self._yt_options_changed
        ).pack(side="left")
        ttk.Label(opts, text="Qualität:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0)
        )
        self.yt_quality_keys = ["best", "1080", "720"]
        self.yt_format = ttk.Combobox(
            opts, state="readonly", width=24, values=["Beste Qualität", "Höchstens 1080p", "Höchstens 720p"]
        )
        self.yt_format.current(self.yt_quality_keys.index(saved) if saved in self.yt_quality_keys else 0)
        self.yt_format.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.yt_format.bind("<<ComboboxSelected>>", lambda e: self._yt_options_changed())
        self.yt_subs = tk.BooleanVar(value=self.cfg.get("youtube_subs", False))
        self.yt_keep_link = tk.BooleanVar(value=self.cfg.get("youtube_link", True))
        ttk.Checkbutton(
            opts, text="Untertitel einbetten (Deutsch/Englisch)", variable=self.yt_subs, command=self._yt_options_changed
        ).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            opts, text="Link zusätzlich im Tresor merken", variable=self.yt_keep_link, command=self._yt_options_changed
        ).grid(row=3, column=1, sticky="w", pady=(4, 0))

        where = ttk.Frame(tab, style="Card.TFrame")
        where.grid(row=3, column=0, sticky="we", pady=(8, 8))
        where.columnconfigure(0, weight=1)
        self.yt_folder_label = ttk.Label(where, text="", style="CardMuted.TLabel")
        self.yt_folder_label.grid(row=0, column=0, sticky="w")
        ttk.Button(where, text="Ändern …", command=self._yt_choose_folder).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(where, text="📂 Öffnen", command=lambda: self._open_folder(self._yt_folder())).grid(
            row=0, column=2, padx=(6, 0)
        )

        self.yt_log = tk.Text(tab, height=5, wrap="word", padx=8, pady=6, state="disabled", **text_widget_opts())
        self.yt_log.grid(row=4, column=0, sticky="nsew")

        row = ttk.Frame(tab, style="Card.TFrame")
        row.grid(row=5, column=0, sticky="we", pady=(10, 0))
        ttk.Button(row, text="📋 Aus Zwischenablage", command=self._yt_paste).pack(side="left")
        self.yt_btn = ttk.Button(row, text="⬇ Herunterladen", style="Accent.TButton", command=self.download_youtube)
        self.yt_btn.pack(side="right")
        self.yt_cancel_btn = ttk.Button(row, text="⏹ Abbrechen", command=self._yt_cancel)
        self.yt_cancel_btn.pack(side="right", padx=(0, 6))
        self.yt_cancel_btn.state(["disabled"])
        self.yt_running = None
        self._yt_options_changed()

    def _build_mp3_tab(self):
        tab = self._new_tab("🎧 MP3")
        tab.rowconfigure(3, weight=1)
        ttk.Label(
            tab,
            text="Videos (oder andere Audio-/Videodateien) in reine MP3-Dateien umwandeln:",
            style="Card.TLabel",
        ).grid(row=0, column=0, sticky="w")

        opts = ttk.Frame(tab, style="Card.TFrame")
        opts.grid(row=1, column=0, sticky="we", pady=(10, 0))
        ttk.Label(opts, text="Qualität:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.mp3_quality_keys = list(converter.QUALITIES)
        self.mp3_quality = ttk.Combobox(
            opts, state="readonly", width=32, values=[label for label, _ in converter.QUALITIES.values()]
        )
        saved = self.cfg.get("mp3_quality", "best")
        self.mp3_quality.current(self.mp3_quality_keys.index(saved) if saved in self.mp3_quality_keys else 0)
        self.mp3_quality.grid(row=0, column=1, sticky="w")
        self.mp3_quality.bind("<<ComboboxSelected>>", lambda e: self._mp3_options_changed())
        ttk.Label(opts, text="Speichern:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0)
        )
        self.mp3_target = tk.StringVar(value=self.cfg.get("mp3_target", "same"))
        ttk.Radiobutton(
            opts, text="Neben dem Video", value="same", variable=self.mp3_target, command=self._mp3_options_changed
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            opts, text="In einem Ordner:", value="folder", variable=self.mp3_target, command=self._mp3_options_changed
        ).grid(row=2, column=1, sticky="w", pady=(4, 0))

        where = ttk.Frame(tab, style="Card.TFrame")
        where.grid(row=2, column=0, sticky="we", pady=(6, 8))
        where.columnconfigure(0, weight=1)
        self.mp3_folder_label = ttk.Label(where, text="", style="CardMuted.TLabel")
        self.mp3_folder_label.grid(row=0, column=0, sticky="w")
        ttk.Button(where, text="Ändern …", command=self._mp3_choose_folder).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(where, text="📂 Öffnen", command=lambda: self._open_folder(self._mp3_folder())).grid(
            row=0, column=2, padx=(6, 0)
        )

        hint = "Videos hierher ziehen oder unten auswählen." if HAS_DND else "Videos unten auswählen."
        self.mp3_log = tk.Text(tab, height=6, wrap="word", padx=8, pady=6, **text_widget_opts())
        self.mp3_log.insert("1.0", hint + "\n")
        self.mp3_log.config(state="disabled")
        self.mp3_log.grid(row=3, column=0, sticky="nsew")
        if HAS_DND:
            self.mp3_log.drop_target_register(DND_FILES)
            self.mp3_log.dnd_bind(
                "<<Drop>>", lambda e: self.convert_mp3([p for p in self.tk.splitlist(e.data) if os.path.isfile(p)])
            )

        row = ttk.Frame(tab, style="Card.TFrame")
        row.grid(row=4, column=0, sticky="we", pady=(10, 0))
        self.mp3_btn = ttk.Button(
            row, text="📂 Videos auswählen und umwandeln …", style="Accent.TButton", command=self._mp3_choose_files
        )
        self.mp3_btn.pack(side="right")
        self.mp3_cancel_btn = ttk.Button(row, text="⏹ Abbrechen", command=self._mp3_cancel)
        self.mp3_cancel_btn.pack(side="right", padx=(0, 6))
        self.mp3_cancel_btn.state(["disabled"])
        self.mp3_running = None
        self._mp3_options_changed()

    def _build_overview_tab(self):
        tab = self._new_tab("📚 Übersicht")
        self.overview_tab = tab
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(2, weight=1)
        tab.rowconfigure(2, weight=1)

        search = ttk.Frame(tab, style="Card.TFrame")
        search.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 10))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="🔍", style="Card.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="we")
        self.search_var.trace_add("write", lambda *a: (self._render(), self.set_status(self._summary())))
        self.search_entry.bind("<Escape>", lambda e: self.search_var.set(""))
        ttk.Button(search, text="✕", width=3, command=lambda: self.search_var.set("")).grid(row=0, column=2, padx=(6, 0))

        lists = {}
        for col, (key, label) in enumerate(
            (("links", "🔗 Links"), ("notes", "📝 Notizen"), ("files", "📁 Dateien"))
        ):
            ttk.Label(tab, text=label, style="Card.TLabel").grid(
                row=1, column=col, sticky="w", padx=(0 if col == 0 else 10, 0)
            )
            lb = tk.Listbox(tab, activestyle="none", width=24, **text_widget_opts(listbox=True))
            lb.grid(row=2, column=col, sticky="nsew", pady=(4, 6), padx=(0 if col == 0 else 10, 0))
            lists[key] = lb
        tab.columnconfigure(0, weight=1)
        self.links_list, self.notes_list, self.files_list = lists["links"], lists["notes"], lists["files"]
        self._links, self._files = [], []
        self._link_urls, self._note_paths, self._file_paths = [], [], []
        self.links_list.bind("<Double-Button-1>", self._only_on_item(self._open_selected_link))
        self.notes_list.bind("<Double-Button-1>", self._only_on_item(self._open_selected_note))
        self.files_list.bind("<Double-Button-1>", self._only_on_item(self._open_selected_file))
        self._selected_list = None
        for lb in (self.links_list, self.notes_list, self.files_list):
            # Klick auf die leere Fläche unter den Einträgen: nichts auswählen (Tk nimmt sonst den letzten)
            lb.bind("<Button-1>", self._only_on_item(lambda e: None, clear=True))
            lb.bind("<<ListboxSelect>>", lambda e, lb=lb: self._remember_list(lb))
            lb.bind("<Button-3>", self._context_menu)
        if HAS_DND:
            # Dateien einfach in die Dateien-Box ziehen
            self.files_list.drop_target_register(DND_FILES)
            self.files_list.dnd_bind("<<Drop>>", self._on_drop)
            lb.bind("<Delete>", lambda e: self.delete_selected())
            lb.bind("<F2>", lambda e: self.edit_selected())

        btns = ttk.Frame(tab, style="Card.TFrame")
        btns.grid(row=3, column=0, columnspan=3, sticky="we", pady=(6, 0))
        ttk.Label(btns, text="Rechtsklick: ＋ Neu · Bearbeiten · Entfernen", style="CardMuted.TLabel").pack(
            side="left"
        )
        ttk.Button(btns, text="↻ Aktualisieren", command=self.refresh_overview).pack(side="right")
        ttk.Button(btns, text="Auf GitHub ↗", command=self.open_repo).pack(side="right", padx=(0, 6))
        self.delete_btn = ttk.Button(btns, text="🗑 Löschen", command=self.delete_selected)
        self.delete_btn.pack(side="right", padx=(0, 6))
        self.delete_btn.state(["disabled"])
        self.edit_btn = ttk.Button(btns, text="✎ Bearbeiten", command=self.edit_selected)
        self.edit_btn.pack(side="right", padx=(0, 6))
        self.edit_btn.state(["disabled"])

    # ------------------------------------------------------------- Helfer
    def client(self):
        if not self.cfg.get("token"):
            raise GitHubError("Bitte zuerst in den Einstellungen Repo und Token eintragen.")
        return GitHubClient(self.cfg["token"], self.cfg["repo"], self.cfg.get("branch") or DEFAULT_BRANCH)

    def tresor(self):
        return Tresor(self.client(), self.folder)

    def set_status(self, text):
        self.status.config(text=text)

    # ----------------------------------------------- Fortschrittsleiste
    @staticmethod
    def _fmt_bytes(n):
        return f"{n / 1048576:.1f} MB".replace(".", ",") if n >= 1048576 else f"{max(n, 0) // 1024} KB"

    @staticmethod
    def _fmt_eta(seconds):
        if seconds is None or seconds < 0:
            return ""
        seconds = int(seconds + 0.5)
        if seconds < 60:
            return f"noch ca. {max(seconds, 1)} s"
        return f"noch ca. {seconds // 60} min {seconds % 60:02d} s"

    def transfer_start(self, title):
        """Leiste einblenden (aus dem UI-Thread)."""
        self._transfer_state = {"title": title, "start": time.time(), "shown": 0.0}
        self.transfer_bar.config(value=0)
        self.transfer_label.config(text=f"{title} …")
        self.transfer.pack(fill="x", side="bottom", after=self.status)

    def transfer_progress(self, done=0, total=0, percent=None, eta=None, note=""):
        """Fortschritt melden – darf aus Hintergrund-Threads aufgerufen werden."""
        self.jobs.put(("call", lambda: self._transfer_show(done, total, percent, eta, note)))

    def _transfer_show(self, done, total, percent, eta, note):
        st = self._transfer_state
        if not st:
            return
        now = time.time()
        if now - st["shown"] < 0.15 and not (total and done >= total):
            return  # nicht zu oft neu zeichnen
        st["shown"] = now
        if percent is None:
            percent = done * 100 / total if total else 0
        if eta is None and total and done:
            elapsed = now - st["start"]
            eta = (total - done) * elapsed / done if elapsed > 0.5 else None
        parts = [f"{st['title']}: {percent:.0f} %"]
        if total:
            parts.append(f"{self._fmt_bytes(done)} von {self._fmt_bytes(total)}")
        if self._fmt_eta(eta):
            parts.append(self._fmt_eta(eta))
        if note:
            parts.append(note)
        self.transfer_bar.config(value=min(1000, percent * 10))
        self.transfer_label.config(text=" · ".join(parts))

    def transfer_end(self):
        self._transfer_state = None
        self.transfer.pack_forget()

    def run_job(self, label, func, on_done=None, on_error=None, quiet=False):
        """Führt func im Hintergrund aus, damit die Oberfläche nicht einfriert."""
        self.busy += 1
        if not quiet:
            self.set_status(label + " …")
            self.config(cursor="watch")

        def worker():
            try:
                result = func()
                self.jobs.put((on_done, on_error, quiet, result, None))
            except Exception as e:  # noqa: BLE001
                self.jobs.put((on_done, on_error, quiet, None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        try:
            while True:
                item = self.jobs.get_nowait()
                if item[0] == "status":
                    self.set_status(item[1])
                    continue
                if item[0] == "call":
                    item[1]()
                    continue
                on_done, on_error, quiet, result, error = item
                self.busy -= 1
                if self.busy == 0:
                    self.config(cursor="")
                if error:
                    if on_error:
                        on_error(error)
                    elif not quiet:
                        self.set_status("Fehler: " + str(error))
                        messagebox.showerror(APP_NAME, str(error), parent=self)
                elif on_done:
                    on_done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll_jobs)

    # ------------------------------------------------------------- Aktionen
    def open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        self.wait_window(dlg)
        if dlg.result:
            self.cfg = dlg.result
            save_config(self.cfg)
            branch = self.cfg["branch"] or DEFAULT_BRANCH
            self.set_status(f"Verbunden mit {self.cfg['repo']} ({branch}).")
            self.refresh_folders()

    def open_feedback(self):
        if not self.cfg.get("token"):
            messagebox.showinfo(APP_NAME, "Bitte zuerst in den Einstellungen einen Token eintragen.", parent=self)
            self.open_settings()
            return
        FeedbackDialog(self)

    # ------------------------------------------------------------- Klingel
    def _bell_timer(self):
        """Klingel-Button regelmäßig abgleichen (z. B. wenn Claude Feedbacks erledigt hat)."""
        if self.cfg.get("token"):
            self.refresh_bell()
        self.after(BELL_REFRESH_MS, self._bell_timer)

    def _merge_fresh(self, items):
        """GitHub liefert neue Issues/Kommentare manchmal erst Sekunden später – lokal Bekanntes ergänzen."""
        now = time.time()
        self.fresh_feedback = {n: v for n, v in self.fresh_feedback.items() if v[1] > now}
        self.fresh_rung = {n: t for n, t in self.fresh_rung.items() if t > now}
        known = {n for n, _, _ in items}
        items = list(items) + [(n, t, False) for n, (t, _) in self.fresh_feedback.items() if n not in known]
        return sorted(((n, t, r or n in self.fresh_rung) for n, t, r in items), reverse=True)

    def _show_bell(self, items):
        self.open_feedback_items = items
        new = sum(1 for _, _, rung in items if not rung)
        if new:
            text, style = f"🔔 Claude rufen ({new})", "Accent.TButton"
        elif items:
            text, style = f"⏳ Claude arbeitet ({len(items)})", "TButton"
        else:
            text, style = "🔔 Claude rufen", "TButton"
        self.bell_btn.config(text=text, style=style)

    def feedback_created(self, number, title):
        self.fresh_feedback[number] = (title, time.time() + FRESH_SECONDS)
        self._show_bell(self._merge_fresh(self.open_feedback_items))
        self.refresh_bell()

    def refresh_bell(self):
        """Zahl der offenen (noch nicht gerufenen) Feedbacks auf dem Klingel-Button anzeigen."""
        try:
            client = self.client()
        except GitHubError:
            return
        def done(items):
            self._check_finished(items)
            self._show_bell(self._merge_fresh(items))

        self.run_job("Prüfe Feedback", client.open_feedback, done, quiet=True)

    def _check_finished(self, items):
        """Gerufene Feedbacks, die nicht mehr offen sind, hat Claude erledigt -> Bescheid geben."""
        open_now = {n for n, _, _ in items}
        known = getattr(self, "_rung_open", None)
        self._rung_open = {n: t for n, t, rung in items if rung or n in self.fresh_rung}
        if known is None:
            return  # erster Abgleich nach dem Start
        finished = [(n, t) for n, t in known.items() if n not in open_now]
        if not finished:
            return
        lines = "\n".join(f"  #{n}  {t}" for n, t in sorted(finished))
        self.set_status(f"✔ Claude hat erledigt: {', '.join(f'#{n}' for n, _ in sorted(finished))}")
        self.check_update(silent=True)
        self.bell()  # kurzer Ton
        self.after(
            0,
            lambda: messagebox.showinfo(
                APP_NAME,
                f"✔ Claude ist fertig:\n\n{lines}\n\n"
                "Die neue Version holst du oben über „⬆ Update“ (Details stehen im jeweiligen Issue).",
                parent=self,
            ),
        )

    def ring_claude(self):
        try:
            client = self.client()
        except GitHubError as e:
            messagebox.showinfo(APP_NAME, str(e), parent=self)
            return

        def loaded(items):
            items = self._merge_fresh(items)
            self._show_bell(items)
            if not items:
                messagebox.showinfo(
                    APP_NAME,
                    "Es gibt gerade kein offenes Feedback.\n\nErst über „💡 Feedback“ etwas eintragen, dann rufen.",
                    parent=self,
                )
                return
            new = [(n, t) for n, t, rung in items if not rung]
            if new:
                todo = new
                lines = "\n".join(f"  #{n}  {t}" for n, t in todo)
                question = f"Claude rufen, um diese {len(todo)} Feedbacks umzusetzen?\n\n{lines}"
            else:
                todo = [(n, t) for n, t, _ in items]
                lines = "\n".join(f"  #{n}  {t}" for n, t in todo)
                question = (
                    f"Claude wurde für diese Feedbacks schon gerufen und arbeitet daran:\n\n{lines}\n\n"
                    "Fertige Änderungen kommen über „⬆ Update“. Trotzdem nochmal rufen?"
                )
            if not messagebox.askyesno(APP_NAME, question, parent=self):
                return
            refs = ", ".join(f"#{n}" for n, _ in todo)
            text = f"{BELL_PREFIX} {refs}\n\n" + "\n".join(f"- #{n} {t}" for n, t in todo)

            def rung(ok):
                if ok:
                    until = time.time() + FRESH_SECONDS
                    self.fresh_rung.update({n: until for n, _ in todo})
                    self._show_bell(self._merge_fresh(self.open_feedback_items))
                    self.set_status(f"🔔 Claude wurde gerufen ({refs}). Neue Version später über „⬆ Update“.")
                else:
                    messagebox.showwarning(
                        APP_NAME, "Kein Feedback-Kanal gefunden (Pull Request „feedback-kanal“ fehlt).", parent=self
                    )

            self.run_job("Rufe Claude", lambda: client.ring_bell(text), rung)

        self.run_job("Lade offenes Feedback", client.open_feedback, loaded)

    def open_github(self):
        """Startseite des Repos im Browser öffnen."""
        webbrowser.open(f"https://github.com/{self.cfg.get('repo', DEFAULT_REPO)}")

    def open_repo(self):
        repo = self.cfg.get("repo", DEFAULT_REPO)
        branch = self.cfg.get("branch") or DEFAULT_BRANCH
        webbrowser.open(f"https://github.com/{repo}/tree/{branch}/{folder_dir(self.folder)}")

    # --------------------------------------------------------------- Ordner
    def _update_rename_btn(self):
        state = ["disabled"] if self.folder == DEFAULT_FOLDER else ["!disabled"]
        self.rename_btn.state(state)
        self.delete_folder_btn.state(state)

    def select_folder(self, name):
        self.folder = name
        self.folder_box.set(name)
        self.cfg["folder"] = name
        save_config(self.cfg)
        self._update_rename_btn()
        self.refresh_overview()

    def _on_folder_selected(self, _event):
        self.select_folder(self.folder_box.get())
        self.folder_box.selection_clear()

    def refresh_folders(self, select=None):
        if not self.cfg.get("token"):
            return
        tresor = self.tresor()

        def done(folders):
            self.folder_box.config(values=folders)
            target = select or self.folder
            self.select_folder(target if target in folders else DEFAULT_FOLDER)

        self.run_job("Lade Ordner", tresor.list_folders, done)

    def new_folder(self):
        tresor = self._tresor_or_warn()
        if not tresor:
            return
        dlg = NameDialog(self, "Neuer Ordner", "Name des neuen Ordners:")
        self.wait_window(dlg)
        if not dlg.result:
            return

        def done(name):
            self.set_status(f"✔ Ordner „{name}“ erstellt.")
            self.refresh_folders(select=name)

        self.run_job("Erstelle Ordner", lambda: tresor.create_folder(dlg.result), done)

    def delete_folder(self):
        if self.folder == DEFAULT_FOLDER:
            return
        tresor = self._tresor_or_warn()
        if not tresor:
            return
        name = self.folder
        if not messagebox.askyesno(
            APP_NAME,
            f"Den Ordner „{name}“ mit ALLEN Links, Notizen und Dateien darin löschen?\n\n"
            "Das kann in der App nicht rückgängig gemacht werden.",
            icon="warning",
            parent=self,
        ):
            return

        def done(_):
            self.cache.pop(name, None)
            self.set_status(f"🗑 Ordner „{name}“ gelöscht.")
            self.refresh_folders(select=DEFAULT_FOLDER)

        self.run_job("Lösche Ordner", lambda: tresor.delete_folder(name), done)

    def rename_folder(self):
        if self.folder == DEFAULT_FOLDER:
            return
        tresor = self._tresor_or_warn()
        if not tresor:
            return
        old = self.folder
        dlg = NameDialog(self, "Ordner umbenennen", f"Neuer Name für „{old}“:", old)
        self.wait_window(dlg)
        if not dlg.result or dlg.result == old:
            return

        def done(name):
            self.cache.pop(old, None)
            self.set_status(f"✔ „{old}“ heißt jetzt „{name}“.")
            self.refresh_folders(select=name)

        self.run_job("Benenne Ordner um", lambda: tresor.rename_folder(old, dlg.result), done)

    # -------------------------------------------------------------- Update
    def check_update(self, silent=False):
        try:
            client = self.client()
            # Updates kommen aus dem öffentlichen App-Repo (Token nur für die Rate-Limits)
            app_client = GitHubClient(client.token, APP_REPO)
        except GitHubError as e:
            if not silent:
                messagebox.showinfo(APP_NAME, str(e), parent=self)
            return

        def done(result):
            available, release, asset = result
            self.update_info = (app_client, asset) if available else None
            if available:
                self.update_btn.config(text="⬆ Update verfügbar", style="Accent.TButton")
                if silent:
                    self.set_status("Eine neue Version ist verfügbar – oben auf „Update verfügbar“ klicken.")
                    return
                self.ask_install(app_client, release, asset)
            else:
                self.update_btn.config(text="⬆ Update", style="TButton")
                if not silent:
                    self.set_status("✔ Du hast die neueste Version.")
                    msg = "Du hast bereits die neueste Version." if release else "Es ist noch keine Version veröffentlicht."
                    messagebox.showinfo(APP_NAME, msg, parent=self)

        self.run_job("Suche nach Updates", lambda: updater.check(app_client), done, quiet=silent)

    def ask_install(self, client, release, asset):
        new = (release.get("target_commitish") or "")[:7]
        if not updater.is_frozen():
            if messagebox.askyesno(
                APP_NAME,
                f"Neue Version {new} verfügbar.\n\nDie App läuft nicht als .exe – Download-Seite öffnen?",
                parent=self,
            ):
                webbrowser.open(release.get("html_url", ""))
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Neue Version {new} verfügbar (du hast {updater.current_version()}).\n\n"
            "Jetzt herunterladen und die App neu starten?",
            parent=self,
        ):
            return

        def progress(done, total):
            if total:
                self.jobs.put(("status", f"Lade Update herunter … {done * 100 // total} %"))
                self.transfer_progress(done, total)

        def installed(exe):
            self.transfer_end()
            self.set_status("Starte neu …")
            try:
                updater.restart(exe)
            except OSError as e:
                messagebox.showinfo(
                    APP_NAME, f"Update installiert. Bitte die App neu starten.\n\n({e})", parent=self
                )
            self.destroy()

        def failed(err):
            self.transfer_end()
            self.set_status("Update fehlgeschlagen.")
            messagebox.showerror(
                APP_NAME,
                f"Update fehlgeschlagen:\n{err}\n\nDu kannst die neue Version auch manuell herunterladen.",
                parent=self,
            )
            webbrowser.open(release.get("html_url", ""))

        self.transfer_start("⬇ Update")
        self.run_job("Lade Update herunter", lambda: updater.install(client, asset, progress), installed, failed)

    # ------------------------------------------------------------- Inhalte
    def choose_files(self):
        paths = filedialog.askopenfilenames(parent=self, title="Dateien für den Tresor auswählen")
        if paths:
            self.upload_files(list(paths))

    def choose_folder_upload(self):
        folder = filedialog.askdirectory(parent=self, title="Ordner für den Tresor auswählen")
        if folder:
            self.upload_files([folder])

    def _on_drop(self, event):
        self.upload_files([p for p in self.tk.splitlist(event.data) if os.path.exists(p)])

    @staticmethod
    def _expand_uploads(paths):
        """Dateien und Ordner -> [(datei, unterordner)]; Ordner behalten ihren Namen und ihre Struktur."""
        items = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isfile(p):
                items.append((p, ""))
            elif os.path.isdir(p):
                parent = os.path.dirname(p)
                for root, dirs, files in os.walk(p):
                    dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                    for name in sorted(files):
                        if name.startswith(".") or name.lower() in ("thumbs.db", "desktop.ini"):
                            continue
                        rel = os.path.relpath(root, parent).replace(os.sep, "/")
                        items.append((os.path.join(root, name), rel))
        return items

    def upload_files(self, paths):
        tresor = self._tresor_or_warn()
        if not tresor or not paths:
            return
        items = self._expand_uploads(paths)
        if not items:
            messagebox.showinfo(APP_NAME, "Der Ordner ist leer.", parent=self)
            return
        if len(items) > 50 and not messagebox.askyesno(
            APP_NAME, f"{len(items)} Dateien hochladen? Das kann eine Weile dauern.", parent=self
        ):
            return
        sizes = [os.path.getsize(p) for p, _ in items]
        total = sum(sizes)

        def job():
            saved, failed, done_bytes = [], [], 0
            for i, ((p, sub), size) in enumerate(zip(items, sizes), 1):
                name = f"{sub}/{os.path.basename(p)}" if sub else os.path.basename(p)
                self.jobs.put(("status", f"Lade hoch ({i}/{len(items)}): {name} …"))

                def progress(sent, length, base=done_bytes, size=size, i=i):
                    self.transfer_progress(base + size * sent // max(length, 1), total, note=f"Datei {i}/{len(items)}")

                try:
                    saved.append(tresor.add_file(p, sub, progress))
                except Exception as e:  # noqa: BLE001
                    failed.append(f"{name}: {e}")
                done_bytes += size
                self.transfer_progress(done_bytes, total, note=f"Datei {i}/{len(items)}")
            return saved, failed

        folder = self.folder
        files_dir = tresor.files_dir

        def done(result):
            self.transfer_end()
            saved, failed = result
            self.set_status(f"✔ {len(saved)} Datei(en) hochgeladen in „{folder}“.")
            for path in saved:
                self._add_local(folder, "files", (path[len(files_dir) + 1:], path))
            if failed:
                messagebox.showwarning(APP_NAME, "Nicht hochgeladen:\n\n" + "\n".join(failed[:20]), parent=self)

        def failed(err):
            self.transfer_end()
            messagebox.showerror(APP_NAME, str(err), parent=self)

        self.transfer_start("⬆ Hochladen")
        self.run_job("Lade Dateien hoch", job, done, failed)

    # ------------------------------------------------------------ TikTok
    def _tt_folder(self):
        return self.cfg.get("tiktok_folder") or tiktok.default_folder()

    def _tt_options_changed(self):
        self.cfg["tiktok_target"] = self.tt_target.get()
        self.cfg["tiktok_kind"] = self.tt_kind.get()
        self.cfg["tiktok_link"] = bool(self.tt_keep_link.get())
        save_config(self.cfg)
        on_pc = self.tt_target.get() == "pc"
        self.tt_folder_label.config(
            text=f"Ordner: {self._tt_folder()}" if on_pc else "Videos landen unter „Dateien“ im aktuellen Tresor-Ordner."
        )
        for b in (self.tt_change_btn, self.tt_open_btn):
            b.state(["!disabled"] if on_pc else ["disabled"])

    def _tt_choose_folder(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self._tt_folder(), title="Ordner für TikTok-Videos")
        if folder:
            self.cfg["tiktok_folder"] = os.path.normpath(folder)
            self._tt_options_changed()

    def _tt_open_folder(self):
        self._open_folder(self._tt_folder())

    def _open_folder(self, folder):
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        else:
            webbrowser.open("file://" + folder)

    def _tt_paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        current = self.tt_links.get("1.0", "end").strip()
        self.tt_links.insert("end", ("\n" if current else "") + text)

    def _tt_log(self, line):
        self.tt_log.config(state="normal")
        self.tt_log.insert("end", line + "\n")
        self.tt_log.see("end")
        self.tt_log.config(state="disabled")

    def download_tiktok(self):
        links = tiktok.find_links(self.tt_links.get("1.0", "end"))
        if not links:
            messagebox.showinfo(APP_NAME, "Bitte mindestens einen TikTok-Link einfügen.", parent=self)
            return
        to_tresor = self.tt_target.get() == "tresor"
        as_mp3 = self.tt_kind.get() == "mp3"
        keep_link = bool(self.tt_keep_link.get())
        tresor = self._tresor_or_warn() if (to_tresor or keep_link) else None
        if (to_tresor or keep_link) and not tresor:
            return
        if as_mp3 and not self._ensure_ffmpeg():
            return
        folder, target_dir = self.folder, self._tt_folder()
        log = lambda line: self.jobs.put(("call", lambda: self._tt_log(line)))  # noqa: E731

        def job():
            saved, links_saved, errors, seen = [], [], 0, set()
            for i, link in enumerate(links, 1):
                prefix = f"[{i}/{len(links)}]"
                try:
                    self.jobs.put(("status", f"TikTok {prefix}: hole Infos …"))
                    info = tiktok.fetch_info(link)
                    if info["id"] in seen:
                        log(f"{prefix} ↷ doppelt, übersprungen")
                        continue
                    seen.add(info["id"])
                    if to_tresor and not as_mp3 and info["size"] > MAX_FILE_BYTES:
                        raise tiktok.TikTokError("zu groß für den Tresor (max. 70 MB) – bitte „Auf diesem PC“ wählen")
                    urls = [info["video"]] if info["video"] else info["images"]
                    names = tiktok.file_names(info)
                    if as_mp3:
                        # Video laden und den Ton herauslösen; Foto-Beiträge haben keinen Videoton -> deren Musik
                        if not info["video"] and not info["music"]:
                            raise tiktok.TikTokError("dieser Beitrag hat keinen Ton")
                        urls = [info["video"] or info["music"]]
                        names = [names[0] if info["video"] else names[0].rsplit("_", 1)[0] + ".ton"]
                    out_dir = os.path.join(target_dir, tiktok.safe_name(info["user"]))
                    if to_tresor:
                        out_dir = tempfile.mkdtemp(prefix="tiktok-")
                    os.makedirs(out_dir, exist_ok=True)
                    for n, (url, name) in enumerate(zip(urls, names), 1):
                        part = f" Bild {n}/{len(urls)}" if len(urls) > 1 else ""

                        def progress(done, total, part=part):
                            if total:
                                self.jobs.put(("status", f"TikTok {prefix}{part}: {done * 100 // total} % …"))
                                self.transfer_progress(done, total, note=f"{prefix.strip('[]')}{part}")

                        path = tiktok.unique_path(out_dir, name)
                        tiktok.download(url, path, progress)
                        if as_mp3:
                            self.jobs.put(("status", f"TikTok {prefix}: wandle in MP3 um …"))
                            mp3 = tiktok.unique_path(out_dir, os.path.splitext(name)[0] + ".mp3")
                            converter.Conversion().to_mp3(path, mp3)
                            os.remove(path)
                            path = mp3
                        if to_tresor:
                            self.jobs.put(("status", f"TikTok {prefix}{part}: lade in den Tresor …"))
                            saved.append(tresor.add_file(path))
                            os.remove(path)
                    if to_tresor:
                        os.rmdir(out_dir)
                    kind = "MP3" if as_mp3 else "Video" if info["video"] else f"{len(urls)} Bilder"
                    log(f"{prefix} ✔ @{info['user']}: {info['title'][:60] or info['id']} ({kind})")
                    if keep_link:
                        url = f"https://www.tiktok.com/@{info['user']}/video/{info['id']}"
                        title = f"TikTok @{info['user']}: {info['title'][:80]}".rstrip(": ")
                        links_saved.append((title,) + tresor.add_link(url, title))
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    log(f"{prefix} ✖ {link[:60]}: {e}")
            return saved, links_saved, errors

        def done(result):
            saved, links_saved, errors = result
            self.transfer_end()
            self.tt_btn.state(["!disabled"])
            for path in saved:
                self._add_local(folder, "files", (path.rsplit("/", 1)[-1], path))
            for title, url, line in links_saved:
                self._add_local(folder, "links", (title, url, line))
            ok = len(links) - errors
            where = f"im Tresor-Ordner „{folder}“" if to_tresor else target_dir
            self.set_status(f"✔ TikTok: {ok} von {len(links)} gespeichert ({where})." if ok else "✖ TikTok: nichts gespeichert.")
            if ok:
                self.tt_links.delete("1.0", "end")

        def failed(err):
            self.transfer_end()
            self.tt_btn.state(["!disabled"])
            self._tt_log(f"✖ {err}")

        self.tt_btn.state(["disabled"])
        self.transfer_start("⬇ TikTok")
        self._tt_log(f"— {len(links)} Link(s) – Ziel: {'Tresor „' + folder + '“' if to_tresor else target_dir}")
        self.run_job("TikTok", job, done, failed)

    def _ensure_ffmpeg(self):
        """FFmpeg (für MP3) bei Bedarf nach Rückfrage laden. Gibt True zurück, wenn es da ist."""
        missing = converter.missing()
        if not missing:
            return True
        mb = sum(m for _, m in missing)
        if not messagebox.askyesno(
            APP_NAME,
            f"Für MP3 braucht die App einmalig FFmpeg (ca. {mb} MB).\n\nJetzt herunterladen?",
            parent=self,
        ):
            return False

        def progress(name, done, total):
            if total:
                self.jobs.put(("status", f"Lade {name} … {done * 100 // total} %"))

        self.run_job(
            "Lade FFmpeg",
            lambda: converter.install(progress),
            lambda _: self.set_status("✔ FFmpeg ist bereit – bitte nochmal starten."),
        )
        return False

    # --------------------------------------------------------- MP3-Konverter
    def _mp3_folder(self):
        return self.cfg.get("mp3_folder") or os.path.join(os.path.expanduser("~"), "Downloads", "MP3")

    def _mp3_options_changed(self):
        self.cfg["mp3_quality"] = self.mp3_quality_keys[max(self.mp3_quality.current(), 0)]
        self.cfg["mp3_target"] = self.mp3_target.get()
        save_config(self.cfg)
        self.mp3_folder_label.config(
            text=f"Ordner: {self._mp3_folder()}"
            if self.mp3_target.get() == "folder"
            else "Die MP3 landet im selben Ordner wie das Video."
        )

    def _mp3_choose_folder(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self._mp3_folder(), title="Ordner für MP3-Dateien")
        if folder:
            self.cfg["mp3_folder"] = os.path.normpath(folder)
            self.mp3_target.set("folder")
            self._mp3_options_changed()

    def _mp3_choose_files(self):
        paths = filedialog.askopenfilenames(parent=self, title="Videos für MP3 auswählen", filetypes=converter.VIDEO_TYPES)
        if paths:
            self.convert_mp3(list(paths))

    def _mp3_log(self, line):
        self.mp3_log.config(state="normal")
        self.mp3_log.insert("end", line + "\n")
        self.mp3_log.see("end")
        self.mp3_log.config(state="disabled")

    def _mp3_cancel(self):
        if self.mp3_running:
            self.mp3_running.cancel()

    def _mp3_busy(self, busy):
        self.mp3_btn.state(["disabled"] if busy else ["!disabled"])
        self.mp3_cancel_btn.state(["!disabled"] if busy else ["disabled"])

    def convert_mp3(self, paths):
        if not paths or self.mp3_running or not self._ensure_ffmpeg():
            return
        quality = self.mp3_quality_keys[max(self.mp3_quality.current(), 0)]
        out_dir = self._mp3_folder() if self.mp3_target.get() == "folder" else None
        conversion = converter.Conversion()
        self.mp3_running = conversion
        self._mp3_busy(True)
        log = lambda line: self.jobs.put(("call", lambda: self._mp3_log(line)))  # noqa: E731
        self._mp3_log(f"— {len(paths)} Datei(en) – {converter.QUALITIES[quality][0]}")

        def job():
            done = []
            for i, src in enumerate(paths, 1):
                name = os.path.basename(src)
                prefix = f"[{i}/{len(paths)}]"
                try:
                    dest = converter.mp3_path(src, out_dir)
                    conversion.to_mp3(
                        src, dest, quality, lambda p: self.jobs.put(("status", f"MP3 {prefix} {p} % – {name}"))
                    )
                    done.append(dest)
                    log(f"✔ {name} → {os.path.basename(dest)}")
                except converter.ConvertError as e:
                    log(f"✖ {name}: {e}")
                    if conversion.cancelled:
                        break
            return done

        def finished(done):
            self.mp3_running = None
            self._mp3_busy(False)
            where = out_dir or "neben den Videos"
            self.set_status(f"✔ {len(done)} von {len(paths)} in MP3 umgewandelt ({where})." if done else "✖ Nichts umgewandelt.")

        def failed(err):
            self.mp3_running = None
            self._mp3_busy(False)
            self._mp3_log(f"✖ {err}")

        self.run_job("MP3", job, finished, failed, quiet=True)

    # ----------------------------------------------------------- YouTube
    def _yt_folder(self):
        return self.cfg.get("youtube_folder") or youtube.default_folder()

    def _yt_format_key(self):
        if self.yt_kind.get() == "mp3":
            return "mp3"
        return self.yt_quality_keys[max(self.yt_format.current(), 0)]

    def _yt_options_changed(self):
        self.cfg["youtube_format"] = self._yt_format_key()
        self.yt_format.state(["disabled"] if self.yt_kind.get() == "mp3" else ["!disabled", "readonly"])
        self.cfg["youtube_subs"] = bool(self.yt_subs.get())
        self.cfg["youtube_link"] = bool(self.yt_keep_link.get())
        save_config(self.cfg)
        self.yt_folder_label.config(text=f"Ordner: {self._yt_folder()}")

    def _yt_choose_folder(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self._yt_folder(), title="Ordner für YouTube-Downloads")
        if folder:
            self.cfg["youtube_folder"] = os.path.normpath(folder)
            self._yt_options_changed()

    def _yt_paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        current = self.yt_links.get("1.0", "end").strip()
        self.yt_links.insert("end", ("\n" if current else "") + text)

    def _yt_log(self, line):
        self.yt_log.config(state="normal")
        self.yt_log.insert("end", line + "\n")
        self.yt_log.see("end")
        self.yt_log.config(state="disabled")

    def _yt_cancel(self):
        if self.yt_running:
            self.yt_running.cancel()

    def _yt_busy(self, busy):
        self.yt_btn.state(["disabled"] if busy else ["!disabled"])
        self.yt_cancel_btn.state(["!disabled"] if busy else ["disabled"])

    def download_youtube(self):
        links = [youtube.normalize_link(l) for l in youtube.find_links(self.yt_links.get("1.0", "end"))]
        if not links:
            messagebox.showinfo(APP_NAME, "Bitte mindestens einen YouTube-Link einfügen.", parent=self)
            return
        missing = youtube.missing_tools()
        if missing:
            total = sum(mb for _, mb in missing)
            names = ", ".join(n for n, _ in missing)
            if not messagebox.askyesno(
                APP_NAME,
                "Für YouTube braucht die App einmalig Hilfsprogramme:\n\n"
                f"{names} (zusammen ca. {total} MB)\n\n"
                "• yt-dlp lädt die Videos (wird automatisch aktuell gehalten)\n"
                "• FFmpeg fügt Bild und Ton zusammen bzw. macht MP3\n"
                "• Deno wird von yt-dlp für YouTube benötigt\n\n"
                "Jetzt herunterladen?",
                parent=self,
            ):
                return
        keep_link = bool(self.yt_keep_link.get())
        tresor = self._tresor_or_warn() if keep_link else None
        if keep_link and not tresor:
            return
        self._yt_busy(True)
        self.set_status("YouTube: prüfe Hilfsprogramme …")

        def prepare():
            def progress(name, done, total):
                if total:
                    self.jobs.put(("status", f"Lade {name} … {done * 100 // total} %"))

            youtube.install_tools(progress)
            self.jobs.put(("status", "YouTube: prüfe auf neue yt-dlp-Version …"))
            youtube.update_ytdlp()
            infos = {}
            for link in links:
                if youtube.is_collection(link):
                    self.jobs.put(("status", "YouTube: lese Playlist/Kanal …"))
                    try:
                        infos[link] = youtube.collection_info(link)
                    except youtube.YouTubeError as e:
                        infos[link] = e  # nur diesen Link überspringen
            return infos

        def prepared(infos):
            # Rückfragen erst nach dem Abarbeiten der Hintergrund-Ergebnisse zeigen
            self.after(0, lambda: confirm(infos))

        def confirm(infos):
            todo = list(links)
            for link, info in infos.items():
                if isinstance(info, Exception):
                    self._yt_log(f"✖ {link[:60]}: {info}")
                    todo.remove(link)
                    continue
                title, count = info
                if count > 1 and not messagebox.askyesno(
                    APP_NAME, f"„{title}“ enthält {count} Videos.\n\nAlle herunterladen?", parent=self
                ):
                    todo.remove(link)
            if not todo:
                self._yt_busy(False)
                self.set_status("Bereit.")
                return
            self._yt_start(todo, tresor)

        def failed(err):
            self._yt_busy(False)
            self._yt_log(f"✖ {err}")
            self.set_status("✖ YouTube: " + str(err))

        self.run_job("YouTube", prepare, prepared, failed, quiet=True)

    def _yt_start(self, links, tresor):
        fmt, folder = self._yt_format_key(), self._yt_folder()
        download = youtube.Download(links, folder, fmt, bool(self.yt_subs.get()))
        self.yt_running = download
        tresor_folder = self.folder
        log = lambda line: self.jobs.put(("call", lambda: self._yt_log(line)))  # noqa: E731
        self._yt_log(f"— {len(links)} Link(s) – {youtube.FORMATS[fmt][0]} – Ziel: {folder}")

        def progress(idx, total, percent, title, eta=None):
            where = f"[{idx}/{total}] " if idx and total else ""
            self.jobs.put(("status", f"YouTube {where}{percent} – {title[:60]}"))
            try:
                value = float(percent.strip().rstrip("%"))
            except ValueError:
                return
            self.transfer_progress(percent=value, eta=eta, note=f"Video {idx}/{total}" if idx and total else title[:40])

        def job():
            saved_links = []

            def done(item):
                log(f"✔ {item['uploader'] + ': ' if item['uploader'] else ''}{item['title'][:70]}")
                if tresor:
                    title = f"YouTube {item['uploader']}: {item['title'][:80]}".replace("YouTube : ", "YouTube: ")
                    try:
                        saved_links.append((title,) + tresor.add_link(item["url"], title))
                    except Exception as e:  # noqa: BLE001
                        log(f"  (Link nicht gemerkt: {e})")

            items, errors = download.run(progress, done, lambda msg: log(f"✖ {msg}"))
            return items, errors, saved_links

        def finished(result):
            self.transfer_end()
            items, errors, saved_links = result
            self.yt_running = None
            self._yt_busy(False)
            for title, url, line in saved_links:
                self._add_local(tresor_folder, "links", (title, url, line))
            self.set_status(
                f"✔ YouTube: {len(items)} gespeichert in {folder}" + (f" – {len(errors)} Fehler" if errors else "")
                if items
                else "✖ YouTube: nichts gespeichert" + (f" – {errors[-1]}" if errors else "")
            )
            if items and not errors:
                self.yt_links.delete("1.0", "end")

        def failed(err):
            self.transfer_end()
            self.yt_running = None
            self._yt_busy(False)
            self._yt_log(f"✖ {err}")
            self.set_status("✖ YouTube: " + str(err))

        self.transfer_start("⬇ YouTube")
        self.run_job("YouTube", job, finished, failed, quiet=True)

    # ------------------------------------------------- Übersicht (lokal)
    KEEP_SECONDS = 120  # so lange gilt eine eigene Änderung, auch wenn GitHub noch den alten Stand liefert

    @staticmethod
    def _key(kind, item):
        return ("link", item[2]) if kind == "links" else ("path", item[1])

    def _add_local(self, folder, kind, item):
        """Neuen Eintrag sofort anzeigen."""
        self.hidden.pop(self._key(kind, item), None)
        self.added.setdefault(folder, []).append((kind, item, time.time() + self.KEEP_SECONDS))
        data = self.cache.get(folder)
        if data is not None and self._key(kind, item) not in {self._key(kind, x) for x in data[kind]}:
            if kind == "files":
                data[kind] = sorted(data[kind] + [item], key=lambda x: x[0])
            else:
                data[kind].insert(0, item)
            if folder == self.folder:
                self._render()

    def _merge(self, folder, fresh):
        """Stand von GitHub übernehmen – eigene, noch nicht sichtbare Änderungen behalten."""
        now = time.time()
        self.hidden = {k: t for k, t in self.hidden.items() if t > now}
        recent = [(k, item) for k, item, t in self.added.get(folder, []) if t > now]
        self.added[folder] = [a for a in self.added.get(folder, []) if a[2] > now]
        data = {}
        for kind in ("links", "notes", "files"):
            items = [x for x in fresh[kind] if self._key(kind, x) not in self.hidden]
            keys = {self._key(kind, x) for x in items}
            for k, item in recent:
                if k == kind and self._key(kind, item) not in keys and self._key(kind, item) not in self.hidden:
                    items = items + [item] if kind == "files" else [item] + items
            data[kind] = sorted(items, key=lambda x: x[0]) if kind == "files" else items
        self.cache[folder] = data

    @staticmethod
    def _matches(words, *texts):
        hay = " ".join(texts).lower()
        return all(w in hay for w in words)

    def _render(self):
        data = self.cache.get(self.folder, {"links": [], "notes": [], "files": []})
        words = self.search_var.get().lower().split() if hasattr(self, "search_var") else []
        if words:
            # Suchen in Titel, Adresse und Notiz (Links) bzw. Namen (Notizen, Dateien)
            data = {
                "links": [x for x in data["links"] if self._matches(words, x[0], x[1], x[2])],
                "notes": [x for x in data["notes"] if self._matches(words, x[0], x[1].rsplit("/", 1)[-1])],
                "files": [x for x in data["files"] if self._matches(words, x[0])],
            }
        self._links = data["links"]
        self._link_urls = [u for _, u, _ in data["links"]]
        self._note_paths = data["notes"]
        self._files = data["files"]
        self._file_paths = [p for _, p in data["files"]]
        for lb, items in (
            (self.links_list, [t for t, _, _ in data["links"]]),
            (self.notes_list, [t for t, _ in data["notes"]]),
            (self.files_list, [n for n, _ in data["files"]]),
        ):
            lb.delete(0, "end")
            for item in items:
                lb.insert("end", "  " + item)
        self._selected_list = None
        self.delete_btn.state(["disabled"])
        self.edit_btn.state(["disabled"])

    def _summary(self):
        d = self.cache.get(self.folder)
        if not d:
            return ""
        if self.search_var.get().strip():
            found = self.links_list.size() + self.notes_list.size() + self.files_list.size()
            return f"🔍 {found} Treffer in „{self.folder}“"
        return f"📁 {self.folder}: {len(d['links'])} Links, {len(d['notes'])} Notizen, {len(d['files'])} Dateien"

    def refresh_overview(self, quiet=False):
        if not self.cfg.get("token"):
            return
        tresor = self.tresor()
        folder = self.folder
        if folder in self.cache:
            quiet = True  # bekannter Stand ist sofort da, Abgleich läuft leise
        self._render()  # sofort zeigen (oder leeren, damit nichts aus dem alten Ordner stehen bleibt)

        def load():
            # drei Anfragen gleichzeitig statt nacheinander
            with ThreadPoolExecutor(max_workers=3) as pool:
                links = pool.submit(tresor.recent_links)
                notes = pool.submit(tresor.list_notes)
                files = pool.submit(tresor.list_files)
                return {"links": links.result(), "notes": notes.result(), "files": files.result()}

        def done(fresh):
            self._merge(folder, fresh)
            if folder == self.folder:
                self._render()
                # auch leise aktualisieren, wenn noch ein „Lade …“-Text stehen geblieben ist
                if not quiet or self.status.cget("text").endswith(" …"):
                    self.set_status(self._summary())

        self.run_job("Lade Übersicht", load, done, quiet=quiet)

    @staticmethod
    def _on_item(lb, y):
        """Liegt die Mausposition y auf einem Eintrag (nicht auf der leeren Fläche darunter)?"""
        if lb.size() == 0:
            return False
        bbox = lb.bbox(lb.nearest(y))
        return bool(bbox) and y <= bbox[1] + bbox[3]

    def _only_on_item(self, handler, clear=False):
        """Event-Handler nur ausführen, wenn auf einen Eintrag geklickt wurde."""

        def wrapper(event):
            lb = event.widget
            if self._on_item(lb, event.y):
                return handler(event)
            if clear:
                lb.selection_clear(0, "end")
                if self._selected_list is lb:
                    self._selected_list = None
                    self.delete_btn.state(["disabled"])
                    self.edit_btn.state(["disabled"])
            return "break"

        return wrapper

    def _remember_list(self, lb):
        if lb.curselection():
            self._selected_list = lb
            self.delete_btn.state(["!disabled"])
            self.edit_btn.state(["!disabled"])

    def delete_selected(self):
        lb = self._selected_list
        sel = lb.curselection() if lb else ()
        if not sel:
            messagebox.showinfo(APP_NAME, "Bitte zuerst einen Eintrag in der Liste markieren.", parent=self)
            return
        i = sel[0]
        tresor = self.tresor()
        folder = self.folder
        if lb is self.links_list:
            kind, item = "links", self._links[i]
            what, job = f"den Link „{item[0]}“", lambda: tresor.delete_link(item[2], item[0])
        elif lb is self.notes_list:
            kind, item = "notes", self._note_paths[i]
            what, job = f"die Notiz „{item[0]}“", lambda: tresor.delete_entry(item[1])
        else:
            kind = "files"
            item = self._files[i]
            what, job = f"die Datei „{item[0]}“", lambda: tresor.delete_entry(item[1])
        if not messagebox.askyesno(APP_NAME, f"Willst du {what} wirklich löschen?", icon="warning", parent=self):
            return

        # Sofort aus der Liste nehmen – GitHub wird im Hintergrund aktualisiert
        key = self._key(kind, item)
        self.hidden[key] = time.time() + self.KEEP_SECONDS
        self.added[folder] = [a for a in self.added.get(folder, []) if self._key(a[0], a[1]) != key]
        data = self.cache.get(folder)
        if data:
            data[kind] = [x for x in data[kind] if self._key(kind, x) != key]
        self._render()
        name = what[what.index("„"):]
        self.set_status(f"🗑 Gelöscht: {name}")

        def failed(err):
            self.hidden.pop(key, None)
            self.set_status(f"Löschen fehlgeschlagen: {name}")
            messagebox.showerror(APP_NAME, f"{name} konnte nicht gelöscht werden:\n{err}", parent=self)
            self.refresh_overview(quiet=True)

        self.run_job("Lösche", job, None, on_error=failed, quiet=True)

    # ------------------------------------------------------- Rechtsklick
    def _context_menu(self, event):
        lb = event.widget
        on_item = self._on_item(lb, event.y)
        lb.selection_clear(0, "end")
        if on_item:
            lb.selection_set(lb.nearest(event.y))
            self._remember_list(lb)
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=C["surface"],
            fg=C["text"],
            activebackground=C["accent"],
            activeforeground=C["accent_text"],
            bd=0,
            font=(FONT, 10),
        )
        if lb is self.links_list:
            menu.add_command(label="＋  Neuen Link einfügen", command=self.new_link)
            open_label, edit_label = "↗  Öffnen", "✎  Bearbeiten"
            opener = self._open_selected_link
        elif lb is self.notes_list:
            menu.add_command(label="＋  Neue Notiz einfügen", command=self.new_note)
            open_label, edit_label = "📖  Öffnen", "✎  Bearbeiten"
            opener = self._open_selected_note
        else:
            menu.add_command(label="＋  Dateien hochladen …", command=self.choose_files)
            menu.add_command(label="＋  Ordner hochladen …", command=self.choose_folder_upload)
            open_label, edit_label = "↗  Auf GitHub öffnen", "✎  Umbenennen"
            opener = self._open_selected_file
        if on_item:
            menu.add_separator()
            menu.add_command(label=open_label, command=lambda: opener(None))
            menu.add_command(label=edit_label, command=self.edit_selected)
            menu.add_command(label="🗑  Entfernen", command=self.delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def new_link(self):
        tresor = self._tresor_or_warn()
        if not tresor:
            return
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            clip = ""
        url = clip if re.match(r"^(https?://|www\.)\S+$", clip) else ""
        dlg = EditLinkDialog(self, url, "", "", heading="Neuer Link")
        self.wait_window(dlg)
        if not dlg.result:
            return
        new_url, title, note = dlg.result
        folder = self.folder

        def done(result):
            saved_url, line = result
            self.set_status(f"✔ Link gespeichert in „{folder}“: {saved_url}")
            self._add_local(folder, "links", (title.strip() or saved_url, saved_url, line))

        self.run_job("Speichere Link", lambda: tresor.add_link(new_url, title, note), done)

    def new_note(self):
        tresor = self._tresor_or_warn()
        if not tresor:
            return
        dlg = EditNoteDialog(self, "", "", heading="Neue Notiz")
        self.wait_window(dlg)
        if not dlg.result:
            return
        title, text = dlg.result
        folder = self.folder

        def done(path):
            self.set_status(f"✔ Notiz gespeichert in „{folder}“.")
            self._add_local(folder, "notes", (note_label(path.rsplit("/", 1)[-1]), path))

        self.run_job("Speichere Notiz", lambda: tresor.add_note(title, text), done)

    # ------------------------------------------------------- Bearbeiten
    def edit_selected(self):
        lb = self._selected_list
        sel = lb.curselection() if lb else ()
        if not sel:
            messagebox.showinfo(APP_NAME, "Bitte zuerst einen Eintrag in der Liste markieren.", parent=self)
            return
        i = sel[0]
        if lb is self.links_list:
            self._edit_link(self._links[i])
        elif lb is self.notes_list:
            self._edit_note(self._note_paths[i])
        else:
            self._edit_file(self._files[i])

    def _replace_local(self, folder, kind, old, new):
        """Geänderten Eintrag sofort anzeigen (alter verschwindet, neuer an gleicher Stelle)."""
        old_key, new_key = self._key(kind, old), self._key(kind, new)
        if old_key != new_key:
            self.hidden[old_key] = time.time() + self.KEEP_SECONDS
        self.added[folder] = [a for a in self.added.get(folder, []) if self._key(a[0], a[1]) != old_key]
        data = self.cache.get(folder)
        if data:
            data[kind] = [new if self._key(kind, x) == old_key else x for x in data[kind]]
        self._add_local(folder, kind, new)
        if folder == self.folder:
            self._render()

    def _edit_link(self, item):
        title, url, line = item
        parsed = parse_link_line(line) or (title, url, "", "")
        dlg = EditLinkDialog(self, parsed[1], parsed[0], parsed[2])
        self.wait_window(dlg)
        if not dlg.result:
            return
        new_url, new_title, new_note = dlg.result
        tresor, folder = self.tresor(), self.folder

        def done(result):
            saved_url, new_line = result
            self._replace_local(folder, "links", item, (new_title.strip() or saved_url, saved_url, new_line))
            self.set_status(f"✔ Link geändert: {new_title.strip() or saved_url}")

        self.run_job("Speichere Link", lambda: tresor.edit_link(line, new_url, new_title, new_note), done)

    def _edit_note(self, item):
        label, path = item
        tresor, folder = self.tresor(), self.folder

        def loaded(parts):
            # Erst nach dem Abarbeiten der Hintergrund-Ergebnisse öffnen (sonst warten andere Aufgaben)
            self.after(0, lambda: ask(parts))

        def ask(parts):
            self.set_status("Bereit.")
            dlg = EditNoteDialog(self, *parts)
            self.wait_window(dlg)
            if not dlg.result:
                return

            def done(new_path):
                self._replace_local(folder, "notes", item, (note_label(new_path.rsplit("/", 1)[-1]), new_path))
                self.set_status(f"✔ Notiz geändert: {dlg.result[0].strip() or 'Notiz'}")

            self.run_job("Speichere Notiz", lambda: tresor.edit_note(path, *dlg.result), done)

        self.run_job("Lade Notiz", lambda: tresor.read_note_parts(path), loaded)

    def _edit_file(self, item):
        name, path = item
        dlg = NameDialog(self, "Datei umbenennen", f"Neuer Name für „{name}“:", name)
        self.wait_window(dlg)
        if not dlg.result or dlg.result == name:
            return
        tresor, folder = self.tresor(), self.folder

        def done(new_path):
            self._replace_local(folder, "files", item, (new_path.rsplit("/", 1)[-1], new_path))
            self.set_status(f"✔ Umbenannt in „{new_path.rsplit('/', 1)[-1]}“")

        self.run_job("Benenne Datei um", lambda: tresor.rename_file(path, dlg.result), done)

    def _open_selected_link(self, _event):
        sel = self.links_list.curselection()
        if sel:
            webbrowser.open(self._link_urls[sel[0]])

    def _open_selected_note(self, _event):
        sel = self.notes_list.curselection()
        if not sel:
            return
        label, path = self._note_paths[sel[0]]
        client = self.client()
        tresor = self.tresor()
        self.run_job(
            "Lade Notiz",
            lambda: tresor.read_note(path),
            lambda text: NoteViewer(
                self, label, text, client.file_url(path), on_edit=lambda: self._edit_note((label, path))
            ),
        )

    def _open_selected_file(self, _event):
        sel = self.files_list.curselection()
        if sel:
            webbrowser.open(self.client().file_url(self._file_paths[sel[0]]))

    # ---------------------------------------------- Tabs verschieben
    def _tab_at(self, x, y):
        try:
            return self.tabs.index(f"@{x},{y}")
        except tk.TclError:
            return None

    def _tab_press(self, event):
        idx = self._tab_at(event.x, event.y)
        self._dragged_tab = self.tabs.tabs()[idx] if idx is not None and idx != "" else None

    def _tab_drag(self, event):
        if not self._dragged_tab:
            return
        self.tabs.config(cursor="hand2")
        target = self._tab_at(event.x, event.y)
        if target not in (None, "") and target != self.tabs.index(self._dragged_tab):
            self.tabs.insert(target, self._dragged_tab)

    def _tab_release(self, _event):
        if not self._dragged_tab:
            return
        self._dragged_tab = None
        self.tabs.config(cursor="")
        order = [self.tabs.tab(t, "text") for t in self.tabs.tabs()]
        if order != self.cfg.get("tab_order"):
            self.cfg["tab_order"] = order
            save_config(self.cfg)

    def _apply_tab_order(self):
        """Gespeicherte Reihenfolge der Tabs wiederherstellen (neue Tabs bleiben hinten)."""
        by_text = {self.tabs.tab(t, "text"): t for t in self.tabs.tabs()}
        pos = 0
        for text in self.cfg.get("tab_order", []):
            if text in by_text:
                self.tabs.insert(pos, by_text[text])
                pos += 1
        self.tabs.select(0)

    def _on_tab_changed(self, _event):
        if self.tabs.select() == str(self.overview_tab):
            self.refresh_overview()

    def _tresor_or_warn(self):
        try:
            return self.tresor()
        except GitHubError as e:
            messagebox.showinfo(APP_NAME, str(e), parent=self)
            self.open_settings()
            return None


if __name__ == "__main__":
    enable_dpi_awareness()
    App().mainloop()
