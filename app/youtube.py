"""YouTube-Videos herunterladen (Idee wie Tyrrrz/YoutubeDownloader) – über yt-dlp.

YouTube ändert seine Seite ständig; deshalb nutzt die App das bewährte yt-dlp als
Hilfsprogramm und hält es aktuell. Dazu kommen FFmpeg (Bild + Ton zusammenfügen, MP3)
und Deno (JavaScript-Laufzeit, die yt-dlp für YouTube braucht).

Windows: die drei Programme werden beim ersten Mal in den App-Ordner geladen (~150 MB).
Andere Systeme (nur zum Testen): yt-dlp, ffmpeg und deno werden im PATH gesucht.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

IS_WINDOWS = sys.platform == "win32"

TOOLS = [
    # (Name, Datei im Tools-Ordner, Download-URL, Größe in MB, Datei im ZIP oder None)
    ("yt-dlp", "yt-dlp.exe", "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", 18, None),
    (
        "Deno",
        "deno.exe",
        "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
        42,
        "deno.exe",
    ),
    (
        "FFmpeg",
        os.path.join("ffmpeg", "ffmpeg.exe"),
        "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip",
        89,
        "/bin/",
    ),
]

FORMATS = {
    "best": ("🎬 Video – beste Qualität (MP4)", ["-S", "res,ext:mp4:m4a", "--merge-output-format", "mp4"]),
    "1080": ("🎬 Video – höchstens 1080p (MP4)", ["-S", "res:1080,ext:mp4:m4a", "--merge-output-format", "mp4"]),
    "720": ("🎬 Video – höchstens 720p (MP4)", ["-S", "res:720,ext:mp4:m4a", "--merge-output-format", "mp4"]),
    "mp3": ("🎵 Nur Ton (MP3)", ["-x", "--audio-format", "mp3", "--audio-quality", "0"]),
}

LINK_RE = re.compile(
    r"https?://(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/[^\s<>\"']+", re.I
)
UPDATE_EVERY = 24 * 3600

# Zeilen, die yt-dlp für uns ausgibt (siehe download())
PROGRESS = "LTPROG"
DONE = "LTDONE"


class YouTubeError(Exception):
    pass


def find_links(text):
    """Alle YouTube-Links aus einem Text (ohne Doppelte, Reihenfolge bleibt)."""
    out = []
    for link in LINK_RE.findall(text or ""):
        link = link.rstrip(".,;)")
        if link not in out:
            out.append(link)
    return out


SINGLE_RE = re.compile(r"/watch\?|youtu\.be/|/shorts/|/live/|/embed/", re.I)


def normalize_link(link):
    """Einzelvideo-Links ohne Playlist-Anhang (sonst lädt yt-dlp die ganze Playlist)."""
    if SINGLE_RE.search(link):
        link = re.sub(r"[?&](list|index|start_radio|pp)=[^&#]*", "", link)
        if "?" not in link and "&" in link:
            link = link.replace("&", "?", 1)
    return link


def is_collection(link):
    """Playlist oder Kanal (kann sehr viele Videos enthalten)?"""
    return not SINGLE_RE.search(link)


def default_folder():
    return os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")


# ------------------------------------------------------------- Hilfsprogramme
def tools_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Link-Tresor", "tools")


def _tool(name):
    """Pfad zu yt-dlp / deno / ffmpeg (oder None, wenn nicht vorhanden)."""
    if IS_WINDOWS:
        rel = {"yt-dlp": "yt-dlp.exe", "deno": "deno.exe", "ffmpeg": os.path.join("ffmpeg", "ffmpeg.exe")}[name]
        path = os.path.join(tools_dir(), rel)
        return path if os.path.isfile(path) else None
    return os.environ.get(f"LT_{name.upper().replace('-', '')}") or shutil.which(name)


def missing_tools(only=None):
    """-> Liste von (Name, MB) der noch fehlenden Hilfsprogramme (only: z. B. ["FFmpeg"])."""
    wanted = [t for t in TOOLS if not only or t[0] in only]
    if not IS_WINDOWS:
        return [(name, 0) for name, *_ in wanted if not _tool(name.lower())]
    return [(name, mb) for name, rel, _, mb, _ in wanted if not os.path.isfile(os.path.join(tools_dir(), rel))]


def _download(url, dest, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Link-Tresor"})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(512 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        os.replace(tmp, dest)
    except (urllib.error.URLError, OSError) as e:
        raise YouTubeError(f"Download fehlgeschlagen ({url.rsplit('/', 1)[-1]}): {e}") from e
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def install_tools(progress=None, only=None):
    """Lädt fehlende Hilfsprogramme (nur Windows). progress(name, done, total)."""
    if not IS_WINDOWS:
        missing = missing_tools(only)
        if missing:
            raise YouTubeError("Bitte installieren: " + ", ".join(n for n, _ in missing))
        return
    root = tools_dir()
    os.makedirs(root, exist_ok=True)
    for name, rel, url, _, inner in TOOLS:
        if only and name not in only:
            continue
        target = os.path.join(root, rel)
        if os.path.isfile(target):
            continue
        cb = (lambda d, t, name=name: progress(name, d, t)) if progress else None
        if inner is None:
            _download(url, target, cb)
            continue
        archive = os.path.join(root, f"{name}.zip")
        _download(url, archive, cb)
        try:
            with zipfile.ZipFile(archive) as z:
                if inner.startswith("/"):
                    # ganzen bin-Ordner (ffmpeg.exe + DLLs) übernehmen
                    out_dir = os.path.dirname(target)
                    os.makedirs(out_dir, exist_ok=True)
                    for member in z.namelist():
                        if inner in "/" + member and not member.endswith("/"):
                            with z.open(member) as src, open(os.path.join(out_dir, os.path.basename(member)), "wb") as dst:
                                shutil.copyfileobj(src, dst)
                else:
                    member = next(m for m in z.namelist() if os.path.basename(m) == inner)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except (zipfile.BadZipFile, StopIteration, OSError) as e:
            raise YouTubeError(f"{name} konnte nicht entpackt werden: {e}") from e
        finally:
            os.remove(archive)
        if not os.path.isfile(target):
            raise YouTubeError(f"{name} fehlt nach dem Entpacken.")


def _popen_args():
    # Unter Windows kein schwarzes Konsolenfenster aufblitzen lassen
    return {"creationflags": 0x08000000} if IS_WINDOWS else {}


def update_ytdlp():
    """yt-dlp höchstens einmal am Tag aktualisieren (YouTube ändert sich oft)."""
    if not IS_WINDOWS:
        return
    stamp = os.path.join(tools_dir(), "last-update.txt")
    try:
        if time.time() - os.path.getmtime(stamp) < UPDATE_EVERY:
            return
    except OSError:
        pass
    try:
        subprocess.run([_tool("yt-dlp"), "-U"], capture_output=True, timeout=120, **_popen_args())
    except (OSError, subprocess.SubprocessError):
        return
    with open(stamp, "w") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M"))


def _base_args():
    ytdlp = _tool("yt-dlp")
    if not ytdlp:
        raise YouTubeError("yt-dlp fehlt.")
    args = [ytdlp, "--no-colors", "--ignore-config", "--remote-components", "ejs:github"]
    deno = _tool("deno")
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    ffmpeg = _tool("ffmpeg")
    if ffmpeg:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg) if IS_WINDOWS else ffmpeg]
    return args


def collection_info(link):
    """Playlist/Kanal: -> (Titel, Anzahl Videos) ohne die Videos selbst abzurufen."""
    args = _base_args() + ["--flat-playlist", "-J", link]
    try:
        r = subprocess.run(args, capture_output=True, timeout=180, **_popen_args())
    except subprocess.TimeoutExpired as e:
        raise YouTubeError("YouTube antwortet nicht.") from e
    if r.returncode != 0:
        raise YouTubeError(_last_error(r.stderr.decode("utf-8", "replace")))
    data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    entries = data.get("entries") or []
    # Kanäle liefern Unterlisten (Videos, Shorts, …)
    count = sum(len(e.get("entries") or []) if e.get("_type") == "playlist" else 1 for e in entries)
    return data.get("title") or link, count


def _last_error(text):
    errors = [l[len("ERROR: "):] for l in text.splitlines() if l.startswith("ERROR: ")]
    msg = errors[-1] if errors else (text.strip().splitlines() or ["unbekannter Fehler"])[-1]
    if "Sign in to confirm" in msg or "403" in msg:
        msg += " (YouTube blockiert gerade – später nochmal versuchen)"
    return msg


class Download:
    """Ein laufender yt-dlp-Download (abbrechbar)."""

    def __init__(self, links, folder, fmt="best", subtitles=False):
        self.links, self.folder, self.fmt, self.subtitles = links, folder, fmt, subtitles
        self.proc = None
        self.cancelled = False

    def command(self):
        args = _base_args() + [
            "--newline",
            "--progress",
            "--windows-filenames",
            "--no-mtime",
            "--embed-metadata",
            "--embed-thumbnail",
            "--ignore-errors",
            "-P",
            self.folder,
            "-o",
            # MP3 mit eigenem Namen, sonst würde yt-dlp ein gleichnamiges Video als Quelle nehmen und löschen
            "%(uploader|Unbekannt)s/%(title).120B [%(id)s]" + (" (Audio)" if self.fmt == "mp3" else "") + ".%(ext)s",
            "--progress-template",
            f"download:{PROGRESS}|%(info.playlist_index|)s|%(info.n_entries|)s|%(progress._percent_str)s|%(info.title)s",
            "--print",
            f"after_move:{DONE}|%(webpage_url)s|%(uploader|)s|%(title)s|%(filepath)s",
        ]
        args += FORMATS[self.fmt][1]
        if self.subtitles and self.fmt != "mp3":
            args += ["--embed-subs", "--sub-langs", "de.*,en.*", "--convert-subs", "srt"]
        return args + ["--"] + self.links

    def run(self, on_progress, on_done, on_error):
        """Startet yt-dlp und meldet Fortschritt. Gibt (fertige, fehler) zurück."""
        done, errors = [], []
        self.proc = subprocess.Popen(
            self.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **_popen_args(),
        )
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line.startswith(PROGRESS + "|"):
                _, idx, total, percent, title = (line.split("|", 4) + [""] * 5)[:5]
                on_progress(idx, total, percent.strip(), title)
            elif line.startswith(DONE + "|"):
                _, url, uploader, title, path = (line.split("|", 4) + [""] * 5)[:5]
                item = {"url": url, "uploader": uploader, "title": title, "path": path}
                done.append(item)
                on_done(item)
            elif line.startswith("ERROR: "):
                msg = _last_error(line)
                errors.append(msg)
                on_error(msg)
        self.proc.wait()
        if self.cancelled:
            raise YouTubeError("Abgebrochen.")
        return done, errors

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
