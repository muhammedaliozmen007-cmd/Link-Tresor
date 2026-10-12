# Kurz-Vorlage: Klingel + Update für neue Projekte

In eine neue Claude-Sitzung kopieren und die erste Zeile ausfüllen:

```text
Projekt: <was die App können soll> · Plattform: <Windows/Android/beides> · Repo: <besitzer/name>

Sprich Deutsch und erkläre einfach. Arbeite direkt auf main, committe und pushe ohne zu fragen.

Baue zusätzlich in die App ein:
1. 💡 Feedback-Button: speichert ein GitHub-Issue (Labels „feedback“ + „vorschlag“/„fehler“).
2. 🔔 „Claude rufen“-Button: schreibt in einen Draft-PR „🔔 Feedback-Kanal (nicht mergen)“ (Branch
   feedback-kanal) den Kommentar „🔔 Bitte umsetzen: #1, #2“. Der Button zeigt „Claude rufen (n)“ für
   neue Feedbacks und „⏳ Claude arbeitet (n)“, wenn schon gerufen wurde. Sind gerufene Feedbacks
   geschlossen, meldet die App „✔ Claude ist fertig“.
3. ⬆ Update-Button: GitHub Actions baut bei jedem Push die App und legt sie ins Release (Tag mit
   Commit-SHA). Die App vergleicht die SHA, lädt die neue Version und startet neu. Beim Start leise prüfen.
4. ⚙ Einstellungen: Repo + Token (klassischer Token mit Haken bei „repo“).

Dein Ablauf: Abonniere den Klingel-PR (subscribe_pr_activity), keine Zeitpläne. Bei einem Ruf alle
offenen Feedback-Issues umsetzen, testen, pushen, Build abwarten, im Issue kurz erklären + „über ⬆ Update
verfügbar“, Issue schließen. Den Klingel-PR nie mergen oder schließen. Schreib das alles in eine CLAUDE.md.
```
