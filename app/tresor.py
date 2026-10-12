"""Tresor-Logik: Wo und wie Links, Notizen und Dateien im Repo abgelegt werden.

Ablage im Repository (Ordner „Allgemein“ = direkt in tresor/):
    tresor/links.md                         – alle Links (neueste oben)
    tresor/notizen/<datum>_<titel>.md
    tresor/dateien/<dateiname>
    tresor/<Ordner>/links.md                – dasselbe je eigenem Ordner
    tresor/<Ordner>/notizen/…
    tresor/<Ordner>/dateien/…
"""

import os
import re
import time
from datetime import datetime

from github_api import GitHubError

ROOT = "tresor"
DEFAULT_FOLDER = "Allgemein"
# Namen, die im Wurzelordner schon belegt sind
RESERVED = {"notizen", "dateien", "links.md", DEFAULT_FOLDER.lower()}
FOLDER_KEEP_FILE = ".gitkeep"

LINKS_HEADER = "# Links\n\n<!-- Neue Einträge werden automatisch oben eingefügt -->\n"

# GitHub Contents API erlaubt bis 100 MB, base64 bläht um ~33 % auf.
MAX_FILE_BYTES = 70 * 1024 * 1024


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def slugify(text, fallback="eintrag"):
    text = text.strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or fallback


def safe_filename(name):
    name = os.path.basename(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name or "datei"


def folder_dir(folder):
    """Repo-Pfad eines Ordners."""
    if not folder or folder == DEFAULT_FOLDER:
        return ROOT
    return f"{ROOT}/{folder}"


def validate_folder_name(name, existing=()):
    name = re.sub(r"\s+", " ", name.strip())
    if not name:
        raise ValueError("Bitte einen Ordnernamen eingeben.")
    if len(name) > 50:
        raise ValueError("Der Name ist zu lang (max. 50 Zeichen).")
    if re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or name.startswith("."):
        raise ValueError('Der Name darf diese Zeichen nicht enthalten: \\ / : * ? " < > |')
    if name.lower() in RESERVED:
        raise ValueError(f"„{name}“ ist reserviert – bitte einen anderen Namen wählen.")
    if name.lower() in {e.lower() for e in existing}:
        raise ValueError(f"Den Ordner „{name}“ gibt es schon.")
    return name


def note_label(filename):
    """2026-10-09_153914_keys.md -> 'keys · 09.10.26 15:39'"""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})\d{2}_(.*)\.md$", filename)
    if not m:
        return filename
    y, mo, d, h, mi, rest = m.groups()
    return f"{rest.replace('-', ' ')} · {d}.{mo}.{y[2:]} {h}:{mi}"


def normalize_url(url):
    url = url.strip()
    if url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        url = "https://" + url
    return url


def _md_escape(text):
    return text.replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


def format_link_line(url, title="", note="", stamp=None):
    label = _md_escape(title.strip()) if title.strip() else url
    line = f"- [{label}](<{url}>)"
    if note.strip():
        line += f" — {_md_escape(note.strip())}"
    line += f" · `{stamp or _now()}`"
    return line


def insert_link(existing_md, line):
    """Fügt eine Link-Zeile oben in die Liste ein (unter der Überschrift)."""
    if not existing_md or not existing_md.strip():
        return LINKS_HEADER + "\n" + line + "\n"
    lines = existing_md.splitlines()
    # Position nach dem Kopfbereich (Überschrift, Kommentare, Leerzeilen) finden
    i = 0
    while i < len(lines) and (
        not lines[i].strip() or lines[i].startswith("#") or lines[i].startswith("<!--")
    ):
        i += 1
    lines.insert(i, line)
    if i > 0 and lines[i - 1].strip():
        lines.insert(i, "")
    return "\n".join(lines) + "\n"


LINK_RE = re.compile(r"^- \[(.*?)(?<!\\)\]\((?:<([^>]+)>|([^)\s]+))\)")


def parse_links(md, with_lines=False):
    """Liest Links aus links.md -> Liste von (titel, url) bzw. (titel, url, zeile)."""
    out = []
    for line in (md or "").splitlines():
        m = LINK_RE.match(line)
        if m:
            title = m.group(1).replace("\\[", "[").replace("\\]", "]")
            item = (title, m.group(2) or m.group(3))
            out.append(item + (line,) if with_lines else item)
    return out


LINK_TAIL_RE = re.compile(r"^(?: — (.*?))?(?: · `([^`]*)`)?\s*$")


def parse_link_line(line):
    """Zerlegt eine Link-Zeile -> (titel, url, notiz, zeitstempel) oder None."""
    m = LINK_RE.match(line)
    if not m:
        return None
    title = m.group(1).replace("\\[", "[").replace("\\]", "]")
    url = m.group(2) or m.group(3)
    tail = LINK_TAIL_RE.match(line[m.end():])
    note, stamp = (tail.group(1) or "", tail.group(2) or "") if tail else ("", "")
    note = note.replace("\\[", "[").replace("\\]", "]")
    # Ohne eigenen Titel steht die URL als Titel da
    return ("" if title == url else title), url, note, stamp


NOTE_RE = re.compile(r"^# (.*)\n\n_([^_\n]*)_\n\n(.*?)\n?$", re.S)


def parse_note(md):
    """Zerlegt eine Notiz-Datei -> (titel, zeitstempel, text)."""
    m = NOTE_RE.match(md.replace("\r\n", "\n"))
    if not m:
        return "", "", md.strip()
    return m.group(1).strip(), m.group(2), m.group(3).strip()


def replace_line(md, old, new):
    """Ersetzt die erste exakt passende Zeile. Gibt None zurück, wenn sie fehlt."""
    lines = md.splitlines()
    if old not in lines:
        return None
    lines[lines.index(old)] = new
    return "\n".join(lines) + "\n"


def remove_line(md, line):
    """Entfernt die erste exakt passende Zeile. Gibt None zurück, wenn sie fehlt."""
    lines = md.splitlines()
    if line not in lines:
        return None
    lines.remove(line)
    return "\n".join(lines) + "\n"


class Tresor:
    def __init__(self, client, folder=DEFAULT_FOLDER):
        self.gh = client
        self.folder = folder or DEFAULT_FOLDER
        base = folder_dir(self.folder)
        self.links_file = f"{base}/links.md"
        self.notes_dir = f"{base}/notizen"
        self.files_dir = f"{base}/dateien"

    def _msg(self, text):
        return text if self.folder == DEFAULT_FOLDER else f"{text} [{self.folder}]"

    # ------------------------------------------------------------ Ordner
    def list_folders(self):
        names = [
            e["name"]
            for e in self.gh.list_dir(ROOT)
            if e.get("type") == "dir" and e["name"].lower() not in RESERVED
        ]
        return [DEFAULT_FOLDER] + sorted(names, key=str.lower)

    def create_folder(self, name):
        name = validate_folder_name(name, self.list_folders())
        self.gh.put_file(f"{folder_dir(name)}/{FOLDER_KEEP_FILE}", b"", f"Ordner erstellt: {name}")
        return name

    def rename_folder(self, old, new):
        if old == DEFAULT_FOLDER:
            raise ValueError(f"„{DEFAULT_FOLDER}“ kann nicht umbenannt werden.")
        others = [f for f in self.list_folders() if f.lower() != old.lower()]
        new = validate_folder_name(new, others)
        if new == old:
            return new
        self.gh.move_dir(folder_dir(old), folder_dir(new), f"Ordner umbenannt: {old} → {new}")
        return new

    # ----------------------------------------------------------- Inhalte
    def add_link(self, url, title="", note=""):
        url = normalize_url(url)
        if not url:
            raise ValueError("Bitte einen Link eingeben.")
        line = format_link_line(url, title, note)
        self._update_links(lambda md: insert_link(md, line), f"Link: {title.strip() or url}")
        return url, line

    def _update_links(self, change, message, tries=3):
        """Liest links.md, ändert sie und schreibt zurück.

        Direkt nach einer Änderung liefert GitHub manchmal noch den alten Stand
        (-> Konflikt 409 oder fehlende Zeile). Dann kurz warten und neu versuchen.
        """
        for attempt in range(tries):
            last = attempt == tries - 1
            raw, sha = self.gh.get_file(self.links_file)
            try:
                new_md = change(raw.decode("utf-8") if raw else "")
            except ValueError:
                if last:
                    raise
                time.sleep(1.5)
                continue
            try:
                self.gh.put_file(self.links_file, new_md.encode("utf-8"), self._msg(message), sha)
                return
            except GitHubError as e:
                if last or "409" not in str(e):
                    raise
                time.sleep(1.5)

    def add_note(self, title, text):
        if not text.strip() and not title.strip():
            raise ValueError("Die Notiz ist leer.")
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = f"{self.notes_dir}/{stamp}_{slugify(title, 'notiz')}.md"
        body = f"# {title.strip() or 'Notiz'}\n\n_{_now()}_\n\n{text.strip()}\n"
        self.gh.put_file(path, body.encode("utf-8"), self._msg(f"Notiz: {title.strip() or 'Notiz'}"))
        return path

    def unique_file_path(self, filename):
        name = safe_filename(filename)
        base, ext = os.path.splitext(name)
        path = f"{self.files_dir}/{name}"
        n = 2
        while self.gh.exists(path):
            path = f"{self.files_dir}/{base} ({n}){ext}"
            n += 1
        return path

    def add_file(self, local_path):
        size = os.path.getsize(local_path)
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"{os.path.basename(local_path)} ist zu groß ({size // (1024 * 1024)} MB, max. 70 MB)."
            )
        with open(local_path, "rb") as f:
            data = f.read()
        path = self.unique_file_path(os.path.basename(local_path))
        self.gh.put_file(path, data, self._msg(f"Datei: {os.path.basename(path)}"))
        return path

    def recent_links(self, limit=200):
        """-> Liste von (titel, url, zeile)."""
        raw, _ = self.gh.get_file(self.links_file)
        return parse_links(raw.decode("utf-8") if raw else "", with_lines=True)[:limit]

    def _list(self, directory, suffix=""):
        return sorted(
            (
                e["name"]
                for e in self.gh.list_dir(directory)
                if e.get("type") == "file" and e["name"] != ".gitkeep" and e["name"].endswith(suffix)
            ),
            reverse=bool(suffix),
        )

    def list_notes(self):
        """Neueste zuerst -> Liste von (anzeige, pfad)."""
        return [(note_label(n), f"{self.notes_dir}/{n}") for n in self._list(self.notes_dir, ".md")]

    def list_files(self):
        """-> Liste von (name, pfad)."""
        return [(n, f"{self.files_dir}/{n}") for n in self._list(self.files_dir)]

    # --------------------------------------------------------- Löschen
    def delete_link(self, line, title=""):
        def change(md):
            new_md = remove_line(md, line)
            if new_md is None:
                raise ValueError("Der Link wurde schon gelöscht oder geändert.")
            return new_md

        self._update_links(change, f"Link gelöscht: {title}")

    # ------------------------------------------------------- Bearbeiten
    def edit_link(self, old_line, url, title="", note=""):
        """Ändert einen Link an seiner Stelle (Datum bleibt). -> (url, neue_zeile)"""
        url = normalize_url(url)
        if not url:
            raise ValueError("Bitte einen Link eingeben.")
        parsed = parse_link_line(old_line)
        new_line = format_link_line(url, title, note, stamp=parsed[3] if parsed and parsed[3] else None)

        def change(md):
            new_md = replace_line(md, old_line, new_line)
            if new_md is None:
                raise ValueError("Der Link wurde inzwischen gelöscht oder geändert.")
            return new_md

        if new_line != old_line:
            self._update_links(change, f"Link bearbeitet: {title.strip() or url}")
        return url, new_line

    def read_note_parts(self, path):
        """-> (titel, text) einer Notiz zum Bearbeiten."""
        title, _, text = parse_note(self.read_note(path))
        return title, text

    def edit_note(self, path, title, text):
        """Ändert Titel/Text einer Notiz (Datum bleibt). Neuer Titel -> neuer Dateiname. -> neuer Pfad"""
        if not text.strip() and not title.strip():
            raise ValueError("Die Notiz ist leer.")
        raw, sha = self.gh.get_file(path)
        if raw is None:
            raise ValueError("Die Notiz gibt es nicht mehr.")
        _, stamp, _ = parse_note(raw.decode("utf-8", errors="replace"))
        head = title.strip() or "Notiz"
        body = f"# {head}\n\n_{stamp or _now()}_\n\n{text.strip()}\n"
        name = path.rsplit("/", 1)[-1]
        m = re.match(r"(\d{4}-\d{2}-\d{2}_\d{6})_", name)
        new_path = f"{self.notes_dir}/{m.group(1)}_{slugify(title, 'notiz')}.md" if m else path
        if new_path == path or self.gh.exists(new_path):
            self.gh.put_file(path, body.encode("utf-8"), self._msg(f"Notiz bearbeitet: {head}"), sha)
            return path
        # Titel geändert -> unter neuem Namen speichern, alte Datei entfernen
        self.gh.put_file(new_path, body.encode("utf-8"), self._msg(f"Notiz bearbeitet: {head}"))
        self.gh.delete_file(path, self._msg(f"Notiz umbenannt: {name}"), sha)
        return new_path

    def rename_file(self, path, new_name):
        """Benennt eine Datei um (Endung bleibt, falls weggelassen). -> neuer Pfad"""
        old_name = path.rsplit("/", 1)[-1]
        new_name = safe_filename(new_name.strip())
        if not os.path.splitext(new_name)[1] and os.path.splitext(old_name)[1]:
            new_name += os.path.splitext(old_name)[1]
        if new_name == old_name:
            return path
        data, sha = self.gh.get_file(path)
        if data is None:
            raise ValueError("Die Datei gibt es nicht mehr.")
        new_path = self.unique_file_path(new_name)
        self.gh.put_file(new_path, data, self._msg(f"Datei umbenannt: {old_name} → {new_path.rsplit('/', 1)[-1]}"))
        self.gh.delete_file(path, self._msg(f"Datei umbenannt: {old_name}"), sha)
        return new_path

    def delete_entry(self, path):
        """Löscht eine Notiz oder Datei."""
        kind = "Notiz" if path.startswith(self.notes_dir + "/") else "Datei"
        self.gh.delete_file(path, self._msg(f"{kind} gelöscht: {path.rsplit('/', 1)[-1]}"))

    def delete_folder(self, name):
        if name == DEFAULT_FOLDER:
            raise ValueError(f"„{DEFAULT_FOLDER}“ kann nicht gelöscht werden.")
        self.gh.delete_dir(folder_dir(name), f"Ordner gelöscht: {name}")

    def read_note(self, path):
        raw, _ = self.gh.get_file(path)
        return raw.decode("utf-8", errors="replace") if raw else ""
