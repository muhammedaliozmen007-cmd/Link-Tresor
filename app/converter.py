"""Videos (oder andere Audio-/Videodateien) in reine MP3-Dateien umwandeln – mit FFmpeg.

FFmpeg wird mit den YouTube-Hilfsprogrammen geteilt (youtube.install_tools(only=["FFmpeg"])).
"""

import os
import re
import subprocess

import youtube

FFMPEG = ["FFmpeg"]

QUALITIES = {
    "best": ("Beste Qualität (VBR, ~245 kbit/s)", ["-q:a", "0"]),
    "320": ("320 kbit/s", ["-b:a", "320k"]),
    "192": ("192 kbit/s", ["-b:a", "192k"]),
    "128": ("128 kbit/s (kleiner)", ["-b:a", "128k"]),
}

VIDEO_TYPES = [
    ("Videos und Audio", "*.mp4 *.mkv *.webm *.mov *.avi *.wmv *.flv *.m4v *.3gp *.ts *.mpg *.mpeg "
                         "*.m4a *.aac *.wav *.flac *.ogg *.opus *.wma"),
    ("Alle Dateien", "*.*"),
]


class ConvertError(Exception):
    pass


def missing():
    return youtube.missing_tools(FFMPEG)


def install(progress=None):
    youtube.install_tools(progress, only=FFMPEG)


def mp3_path(src, out_dir=None):
    """Zielname neben dem Video (bzw. in out_dir), ohne etwas zu überschreiben."""
    base = os.path.splitext(os.path.basename(src))[0]
    folder = out_dir or os.path.dirname(os.path.abspath(src))
    path = os.path.join(folder, base + ".mp3")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}).mp3")
        n += 1
    return path


def _seconds(text):
    m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


class Conversion:
    """Eine laufende Umwandlung (abbrechbar)."""

    def __init__(self):
        self.proc = None
        self.cancelled = False

    def to_mp3(self, src, dest, quality="best", progress=None):
        """Wandelt src nach dest (MP3) um. progress(prozent)."""
        ffmpeg = youtube._tool("ffmpeg")
        if not ffmpeg:
            raise ConvertError("FFmpeg fehlt.")
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        args = [
            ffmpeg, "-hide_banner", "-nostdin", "-y",
            "-i", src,
            "-map", "0:a:0",          # nur die (erste) Tonspur – kein Bild
            "-vn", "-sn", "-dn",
            "-c:a", "libmp3lame", *QUALITIES[quality][1],
            "-map_metadata", "0", "-id3v2_version", "3",
            "-progress", "pipe:1", "-nostats",
            dest,
        ]
        self.proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            **youtube._popen_args(),
        )
        duration, tail = 0.0, []
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if "Duration:" in line and not duration:
                duration = _seconds(line.split("Duration:", 1)[1].strip())
            elif line.startswith("out_time=") and duration and progress:
                progress(min(100, int(_seconds(line[9:]) * 100 / duration)))
            elif line and "=" not in line:
                tail = (tail + [line])[-6:]
        code = self.proc.wait()
        if self.cancelled or code != 0:
            if os.path.exists(dest):
                os.remove(dest)
            if self.cancelled:
                raise ConvertError("Abgebrochen.")
            text = " ".join(tail)
            if "matches no streams" in text or "does not contain any stream" in text:
                raise ConvertError("Die Datei hat keinen Ton.")
            raise ConvertError(tail[-1] if tail else f"FFmpeg-Fehler {code}")
        if progress:
            progress(100)
        return dest

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
