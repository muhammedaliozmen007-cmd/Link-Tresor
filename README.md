# 🔐 Link-Tresor

Kleine App für **Windows** und **Android**: Links, Notizen und Dateien landen per Klick in einem
**privaten** GitHub-Repo. Dazu TikTok- und YouTube-Download, MP3-Konverter und eine „Claude rufen“-Klingel
für Feedback.

Dieses Repo enthält **nur den Programmcode** und die fertigen Versionen. Die gespeicherten Inhalte liegen
in einem separaten, privaten Repo (in der App unter ⚙ einstellbar).

## Herunterladen

- **Windows:** [Link-Tresor.exe](https://github.com/muhammedaliozmen007-cmd/Link-Tresor/releases/download/latest/Link-Tresor.exe)
  – doppelklicken, keine Installation nötig.
- **Android:** [Link-Tresor.apk](https://github.com/muhammedaliozmen007-cmd/Link-Tresor/releases/download/android/Link-Tresor.apk)
  – antippen und „Installation aus dieser Quelle“ erlauben.

Danach in der App unter ⚙ das private Daten-Repo und einen GitHub-Token (classic, Haken bei „repo“)
eintragen. Spätere Versionen kommen über **⬆ Update**.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `app/` | Windows-App (Python/Tkinter, nur Standardbibliothek) |
| `android/` | Android-App (Java, ohne AndroidX) |
| `.github/workflows/` | baut bei jedem Push die `.exe` bzw. `.apk` und legt sie in die Releases |
| `docs/` | Vorlagen, um Feedback-Klingel und Update-Button in andere Projekte einzubauen |
