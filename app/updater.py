"""Selbst-Update der Link-Tresor.exe über das GitHub-Release „latest“."""

import os
import subprocess
import sys

from version import BUILD_SHA

ASSET_NAME = "Link-Tresor.exe"


def is_frozen():
    """True, wenn die App als .exe (PyInstaller) läuft."""
    return bool(getattr(sys, "frozen", False))


def current_version():
    return BUILD_SHA[:7] if BUILD_SHA != "dev" else "dev"


def check(client):
    """Gibt (update_verfügbar, release, asset) zurück."""
    release = client.latest_release()
    if not release:
        return False, None, None
    asset = next((a for a in release.get("assets", []) if a.get("name") == ASSET_NAME), None)
    latest_sha = release.get("target_commitish", "")
    available = bool(asset) and latest_sha != BUILD_SHA
    return available, release, asset


def exe_path():
    return os.path.abspath(sys.executable)


def cleanup_old():
    """Entfernt die beim letzten Update zurückgelassene alte .exe."""
    if not is_frozen():
        return
    old = exe_path() + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass


def install(client, asset, progress=None):
    """Lädt die neue .exe herunter und tauscht sie gegen die laufende aus.

    Windows erlaubt kein Überschreiben einer laufenden .exe, aber Umbenennen:
    aktuelle -> .old, neue -> aktueller Name. Danach muss neu gestartet werden.
    """
    exe = exe_path()
    new = exe + ".new"
    old = exe + ".old"
    client.download_asset(asset["id"], new, progress)
    if os.path.getsize(new) < 1024 * 1024:
        os.remove(new)
        raise RuntimeError("Die heruntergeladene Datei ist unvollständig.")
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)  # zurückrollen
        raise
    return exe


def restart(exe):
    env = dict(os.environ)
    # Neue PyInstaller-.exe soll nicht die Umgebung der alten erben
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([exe], env=env, close_fds=True)
