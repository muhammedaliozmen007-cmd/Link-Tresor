# Link-Tresor – Hinweise für Claude

Windows- und Android-App, mit der der Besitzer Links, Notizen und Dateien in ein privates GitHub-Repo
legt. Sprache mit dem Besitzer: **Deutsch**, einfach erklären.

## Zwei Repos (wichtig!)

- **`muhammedaliozmen007-cmd/Link-Tresor` (öffentlich, dieses Repo):** nur Programmcode, Build-Workflows
  und Releases (`latest` = .exe, `android` = .apk). Öffentlich, damit GitHub Actions kostenlos baut.
- **`muhammedaliozmen007-cmd/Link-Tresor-Privat` (privat):** die Inhalte (`tresor/`), die Feedback-Issues
  und der Klingel-PR **#4**. Code-Änderungen gehören NICHT dorthin.
- Die Apps speichern in `DEFAULT_REPO` (= Privat) und holen Updates aus `APP_REPO` (= öffentlich).
  Alte Einstellungen mit dem öffentlichen Repo als Daten-Repo werden beim Start automatisch umgestellt.
- **Niemals Tresor-Inhalte, Tokens oder Schlüssel in dieses öffentliche Repo committen.**

## Regeln des Besitzers

- **Direkt auf `main` arbeiten**, committen und pushen – Änderungen ohne Rückfrage sind ausdrücklich erlaubt.
- Keine Pull Requests für normale Arbeit.
- Der Besitzer nutzt einen **klassischen Token** (Scope `repo`) in der App.

## Aufbau

```
app/link_tresor.pyw   Oberfläche (Dark Mode, Ordner-Leiste, Tabs Übersicht/TikTok/YouTube – per Ziehen
                      umsortierbar, Reihenfolge in cfg["tab_order"]; Links/Notizen/Dateien per Rechtsklick
                      in der Übersicht anlegen/hochladen/bearbeiten/entfernen, Dateien auch per Drag & Drop,
                      Suche, Feedback-Dialog, „🔔 Claude rufen“, Update-Button, Zahnrad = Einstellungen)
app/tresor.py         Ablage-Logik: Ordner, Links (links.md), Notizen, Dateien, Bearbeiten, Löschen
app/github_api.py     Mini-GitHub-Client (Contents API, Git-Data-API für Ordner verschieben/löschen,
                      Issues, Feedback-Kanal, Releases + Asset-Download aus privatem Repo)
app/tiktok.py         TikTok-Download (Idee aus Tikorgzo): Infos/Links über die TikWM-API
                      (https://www.tikwm.com/api/?url=…&hd=1, ~1 Anfrage/s), Video in HD ohne
                      Wasserzeichen bzw. Bilder bei Foto-Beiträgen; Tab „🎵 TikTok“, Ziel PC-Ordner
                      oder Tresor (max. 70 MB), optional Link im Tresor merken
app/youtube.py        YouTube-Download (Idee aus Tyrrrz/YoutubeDownloader) über yt-dlp: lädt beim ersten
                      Mal yt-dlp.exe, Deno (JS-Laufzeit, braucht yt-dlp für YouTube) und FFmpeg (gpl-shared,
                      bin/ inkl. DLLs) nach %APPDATA%\Link-Tresor\tools (~150 MB), `yt-dlp -U` max. 1×/Tag;
                      Tab „▶ YouTube“ (Video/1080p/720p/MP3, Untertitel, Playlists/Kanäle mit Rückfrage).
                      Am PC; Android hat eigenes YouTube.java (siehe unten). Aus der Cloud blockt YouTube (403) →
                      dort nur mit lokalem Testvideo + `pip install yt-dlp` testen (LT_YTDLP/PATH)
app/converter.py      MP3-Konverter (Tab „🎧 MP3“): Videos/Audio per FFmpeg in reine MP3 (nur 1. Tonspur,
                      Metadaten bleiben); FFmpeg teilt er sich mit youtube.py (install_tools(only=["FFmpeg"])).
                      TikTok/YouTube haben „Als: 🎬 Video / 🎵 Nur Ton (MP3)“ – TikTok-PC wandelt das Video per
                      FFmpeg um, Android nimmt TikToks eigene Ton-MP3 (Feld „music“), da es dort kein FFmpeg gibt
app/updater.py        Selbst-Update der .exe (laufende .exe -> .old, neue an ihren Platz, Neustart)
app/version.py        BUILD_SHA – wird vom Build überschrieben
app/icon.ico, logo-*  erzeugt mit tools/make_icon.py (16/24 px von Hand gezeichnet)
gear-*.png            Zahnrad (Einstellungen), erzeugt mit tools/make_gear.py (auch Android ic_settings)
android/              Handy-App (Java, nur Android-Framework, kein AndroidX): GitHub.java/Tresor.java
                      = Nachbau von github_api.py/tresor.py (gleiches Ablageformat!), MainActivity.java
                      = Oberfläche (Ordner, Tabs, „Teilen“-Ziel, Feedback, Klingel, Update),
                      TikTok.java = Gegenstück zu tiktok.py (Ziel Download/TikTok oder Tresor),
                      YouTube.java = YouTube am Handy ohne yt-dlp: InnerTube-API mit Client „ANDROID_VR“
                      (direkte URLs, keine JS-Entschlüsselung), lädt in 10-MB-Stücken (&range=), H.264+AAC
                      werden mit Muxer.java (MediaMuxer) zusammengefügt, „Nur Ton“ = M4A (kein MP3-Encoder);
                      keine Playlists. Aus der Cloud kommt „Sign in to confirm you're not a bot“ → nur mit
                      Fake-Server testbar (YouTube.API umbiegen),
                      FilesProvider.java = Dateien/APK an andere Apps freigeben, app/link-tresor.jks =
                      fester Signierschlüssel (nicht ändern, sonst lassen sich Updates nicht installieren)
```

Die Inhalte (`tresor/`) liegen im privaten Repo – dort NICHT anfassen außer auf ausdrücklichen Wunsch.

Ablage: Ordner „Allgemein“ = `tresor/links.md`, `tresor/notizen/`, `tresor/dateien/`;
eigene Ordner = `tresor/<Name>/…` (reservierte Namen: notizen, dateien, Allgemein).

## Build & Release

- `.github/workflows/build-exe.yml` baut bei jedem Push auf `main` mit Änderungen in `app/**`
  per PyInstaller eine einzelne `Link-Tresor.exe` und ersetzt das Release mit Tag `latest`
  (`target_commitish` = Commit-SHA; daran erkennt der Update-Button neue Versionen).
- `.github/workflows/build-apk.yml` baut bei Änderungen in `android/**` die `Link-Tresor.apk`
  und ersetzt das Release mit Tag `android` (eigenes Release, `make_latest: false`).
  Die Handy-App vergleicht dessen `target_commitish` mit `BuildConfig.BUILD_SHA`.
- Nach einem Push: Build abwarten (Actions-Run des Commits muss `success` sein, Release
  `latest` muss auf den neuen SHA zeigen), erst dann dem Besitzer „⬆ Update“ sagen.

## Testen (vor jedem Push)

- `python3 -m py_compile app/*.py app/link_tresor.pyw`
- In der Cloud-Umgebung hat nur `python3.12` Tkinter (ggf. `apt-get install -y python3-tk`);
  Oberfläche mit `xvfb-run python3.12 …` starten und per `import -window root shot.png` prüfen.
- Logik gegen einen kleinen Fake-GitHub-Server (http.server) testen, `github_api.API` darauf umbiegen.
  Nie gegen das echte Repo testen (das erzeugt Commits/Issues beim Besitzer).

- Android lokal: SDK nach `/opt/android` (cmdline-tools, `platforms;android-34`, `build-tools;34.0.0`),
  `android/local.properties` mit `sdk.dir=/opt/android`. Maven Central antwortet in der Cloud oft mit 429 →
  per Init-Skript auf `https://maven-central.storage-download.googleapis.com/maven2/` umleiten.
  Kein KVM → kein Emulator; Logik (GitHub.java/Tresor.java) mit Shim für `android.util.Base64` +
  org.json-Jar auf dem JVM gegen den Fake-Server testen, `./gradlew lintRelease` für den Rest.

## Feedback-Workflow („Klingel“)

1. Besitzer trägt in der App über **💡 Feedback** Issues ein (Labels `feedback` + `vorschlag`/`fehler`).
2. **🔔 Claude rufen** schreibt einen Kommentar „🔔 Bitte umsetzen: #…“ in den Draft-PR
   **#4 „🔔 Feedback-Kanal (nicht mergen)“** (Branch `feedback-kanal`) im **privaten** Repo
   `Link-Tresor-Privat`. Dort liegen auch die Feedback-Issues.
3. Die aktive Claude-Sitzung ist per `subscribe_pr_activity` auf PR #4 von `Link-Tresor-Privat` abonniert und wird
   dadurch geweckt. PR #4 **nie mergen oder schließen** – er ist nur die Klingel.
4. Bei einem Ruf: alle offenen `feedback`-Issues (im privaten Repo) lesen, umsetzen, auf `main` des
   **öffentlichen** Repos pushen, Build
   abwarten, im Issue kurz (auf Deutsch) erklären was geändert wurde + „über ⬆ Update
   verfügbar“, Issue schließen (`completed`). Reine Test-Feedbacks nur bestätigen und schließen.
   **Immer alle offenen `feedback`-Issues bearbeiten, nicht nur die im Ruf genannten Nummern.**
   Rufe, die während der Arbeit eintreffen, kommen erst verspätet an (Warteschlange) – deshalb
   vor dem Abschluss einer Runde nochmal nach offenen Feedback-Issues sehen und diese mit erledigen.
5. Kommentare im PR #4 von Claude selbst lösen keine Arbeit aus.
6. Die Apps lesen die Klingel-Kommentare (erste Zeile beginnt mit „🔔 Bitte umsetzen:“) aus PR #4:
   bereits gerufene offene Feedbacks zeigt der Button als „⏳ Claude arbeitet (n)“, neue als
   „🔔 Claude rufen (n)“. Format des Kommentars daher nicht ändern.

Kommentare auf GitHub enden mit der Fußzeile `---` / `_Generated by [Claude Code](https://claude.ai/code)_`.
