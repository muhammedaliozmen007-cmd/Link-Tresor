"""TikTok-Videos herunterladen (Idee wie Tikorgzo: Download-Links über die TikWM-API).

Nur Standardbibliothek. Liefert die beste verfügbare Qualität (HD, ohne Wasserzeichen);
Foto-Beiträge (Slideshows) werden als einzelne Bilder geladen.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

API = "https://www.tikwm.com/api/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Link-Tresor"
# TikWM erlaubt ohne Konto etwa eine Anfrage pro Sekunde
MIN_GAP = 1.2

# tiktok.com, vm./vt.tiktok.com und die neuen Kurzlinks tt.site/t/…
LINK_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:tiktok\.com|tt\.site)/[^\s<>\"']+", re.I)
ID_RE = re.compile(r"(?<!\d)\d{18,20}(?!\d)")

_last_call = 0.0


class TikTokError(Exception):
    pass


def find_links(text):
    """Alle TikTok-Links bzw. Video-IDs aus einem Text (ohne Doppelte, Reihenfolge bleibt)."""
    found = LINK_RE.findall(text or "")
    rest = LINK_RE.sub(" ", text or "")
    found += ID_RE.findall(rest)
    out = []
    for f in found:
        f = f.rstrip(".,;)")
        if f not in out:
            out.append(f)
    return out


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.geturl()
    except urllib.error.HTTPError as e:
        raise TikTokError(f"HTTP {e.code} von {urllib.parse.urlparse(url).hostname}") from e
    except urllib.error.URLError as e:
        raise TikTokError(f"Keine Verbindung: {e.reason}") from e


def _api(link):
    global _last_call
    wait = _last_call + MIN_GAP - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    raw, _ = _get(API + "?" + urllib.parse.urlencode({"url": link, "hd": 1}))
    try:
        result = json.loads(raw)
    except ValueError as e:
        raise TikTokError("Unerwartete Antwort vom Download-Dienst (TikWM).") from e
    return result


def _absolute(url):
    if url and url.startswith("/"):
        return "https://www.tikwm.com" + url
    return url


def safe_name(text, fallback="tiktok"):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text or "").strip(" ._")
    return text[:60] or fallback


def fetch_info(link):
    """-> dict mit id, user, title, date, video (URL oder None), images (Liste), size."""
    result = _api(link)
    if result.get("code") != 0 and urllib.parse.urlparse(link).hostname not in (None, "www.tiktok.com", "tiktok.com"):
        # Kurzlinks (vm./vt.tiktok.com, tt.site) selbst auflösen und nochmal versuchen
        try:
            _, final = _get(link)
        except TikTokError:
            final = link
        if final != link:
            result = _api(final.split("?")[0])
    if result.get("code") != 0 or not result.get("data"):
        msg = result.get("msg") or "unbekannter Fehler"
        if "parsing" in msg.lower():
            msg = "Link nicht erkannt – ist das ein TikTok-Video?"
        raise TikTokError(msg)

    d = result["data"]
    author = d.get("author") or {}
    created = d.get("create_time") or 0
    return {
        "id": str(d.get("id", "")),
        "user": author.get("unique_id") or "unbekannt",
        "title": (d.get("title") or "").strip(),
        "date": datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else "",
        "video": _absolute(d.get("hdplay") or d.get("play")) if not d.get("images") else None,
        "images": [_absolute(u) for u in d.get("images") or []],
        "size": d.get("hd_size") or d.get("size") or 0,
        "music": _absolute(d.get("music") or ""),  # Ton des Beitrags als MP3 (bei Foto-Beiträgen nützlich)
    }


def file_names(info):
    """Dateinamen für Video bzw. Bilder: <user>_<datum>_<id>.mp4 / …_1.jpg"""
    base = "_".join(p for p in (safe_name(info["user"]), info["date"], info["id"]) if p)
    if info["video"]:
        return [base + ".mp4"]
    return [f"{base}_{i}.jpg" for i in range(1, len(info["images"]) + 1)]


def download(url, dest, progress=None):
    """Lädt url nach dest (erst in .part, dann umbenennen)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if os.path.getsize(tmp) == 0:
            raise TikTokError("Leere Datei erhalten.")
        os.replace(tmp, dest)
    except urllib.error.HTTPError as e:
        raise TikTokError(f"Download fehlgeschlagen: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise TikTokError(f"Keine Verbindung: {e.reason}") from e
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def unique_path(folder, name):
    path = os.path.join(folder, name)
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base} ({n}){ext}"
        n += 1
    return path


def default_folder():
    """Downloads\\TikTok im Benutzerordner."""
    return os.path.join(os.path.expanduser("~"), "Downloads", "TikTok")
