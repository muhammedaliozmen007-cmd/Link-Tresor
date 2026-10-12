# Vorlage: nur die Klingel (für Projekte, die schon einen Update-Button haben)

In eine Claude-Sitzung im jeweiligen Projekt kopieren und die erste Zeile ausfüllen:

```text
Repo: <besitzer/name> · Die App hat schon einen Update-Button – den nicht anfassen.

Sprich Deutsch und erkläre einfach. Arbeite direkt auf main, committe und pushe ohne zu fragen.

Baue nur die „Klingel“ ein:
1. 💡 Feedback-Button: speichert ein GitHub-Issue (Labels „feedback“ + „vorschlag“/„fehler“).
2. Lege einen Draft-PR „🔔 Feedback-Kanal (nicht mergen)“ vom Branch feedback-kanal an.
3. 🔔 „Claude rufen“-Button: schreibt dort den Kommentar „🔔 Bitte umsetzen: #1, #2“. Er zeigt
   „Claude rufen (n)“ für neue Feedbacks und „⏳ Claude arbeitet (n)“, wenn schon gerufen wurde.
   Sind gerufene Feedbacks geschlossen, meldet die App „✔ Claude ist fertig“.

Dein Ablauf: Abonniere den Klingel-PR (subscribe_pr_activity), keine Zeitpläne. Bei einem Ruf alle
offenen Feedback-Issues umsetzen, testen, pushen, Build abwarten, im Issue kurz erklären und das Issue
schließen. Den Klingel-PR nie mergen oder schließen. Schreib das alles in eine CLAUDE.md.
```
