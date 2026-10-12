# Vorlage: Feedback, Klingel und Update für neue Projekte

So benutzt du die Vorlage: Den Block unten in eine **neue Claude-Code-Sitzung** kopieren und oben bei
„Mein Projekt“ eintragen, was die App können soll. Alles andere (Feedback-Button, Klingel, Update-Button,
automatischer Build) baut Claude dann genauso wie beim Link-Tresor.

---

```text
Mein Projekt: <HIER KURZ BESCHREIBEN, WAS DIE APP KÖNNEN SOLL, z. B. „Windows-App, mit der ich …“>
Plattform(en): <z. B. Windows (.exe) / Android (.apk) / beides>
GitHub-Repo: <besitzer/name> (privat)

Sprich mit mir Deutsch und erkläre einfach. Du darfst direkt auf `main` arbeiten, committen und pushen,
ohne zu fragen. Keine Pull Requests für normale Arbeit.

Baue neben der eigentlichen App dieses System ein – es ist bei meinem Projekt „Link-Tresor“ bewährt:

## 1. 💡 Feedback-Button (in der App)
- Kleiner Dialog: Art wählen („💡 Vorschlag“ / „🐞 Fehler“), Titel (Pflicht), Beschreibung.
- Speichert ein GitHub-Issue im Repo, Titel mit Emoji davor, Labels `feedback` + `vorschlag`/`fehler`
  (falls GitHub die Labels ablehnt: ohne Labels nochmal senden).
- Unter die Beschreibung automatisch: „---“ + „_Gesendet aus <App> <Version> · <Betriebssystem>_“.
- Feedback wird nur gesammelt, Claude wird dadurch NICHT geweckt (dafür gibt es die Klingel).

## 2. 🔔 „Claude rufen“-Button (die Klingel)
- Ein Draft-Pull-Request „🔔 Feedback-Kanal (nicht mergen)“ vom Branch `feedback-kanal` ist die Klingel.
  Leg ihn an (eine kleine Datei auf dem Branch genügt). Er wird NIE gemergt oder geschlossen.
- Klick auf den Button: offene `feedback`-Issues laden, Liste zeigen, nach Bestätigung EINEN Kommentar
  in den Klingel-PR schreiben. Erste Zeile exakt: „🔔 Bitte umsetzen: #12, #13“, darunter
  „- #12 <Titel>“ je Zeile. (Das Format nicht ändern, die App liest es wieder aus.)
- Der Button zeigt den Stand:
  - „🔔 Claude rufen (n)“ (hervorgehoben) = n offene Feedbacks, für die noch nicht gerufen wurde
  - „⏳ Claude arbeitet (n)“ = alle offenen sind schon gerufen; Klick fragt „Trotzdem nochmal rufen?“
  - „🔔 Claude rufen“ = nichts offen
  „Schon gerufen“ erkennt die App an den Klingel-Kommentaren im PR (nur Kommentare seit dem ältesten
  offenen Feedback lesen, `since=`). So stimmt es auch zwischen mehreren Geräten.
- Der Button gleicht sich jede Minute mit GitHub ab. Gerade erstellte Feedbacks und gerade gerufene
  Nummern zählen sofort lokal mit (ca. 2 Minuten lang), weil GitHubs Listen ein paar Sekunden nachhängen.
- Gibt es keinen Klingel-PR: verständliche Meldung statt Fehler.

## 3. ⬆ Update-Button (Selbst-Update)
- GitHub-Actions-Workflow: bei jedem Push auf `main` (nur bei Änderungen am App-Code) bauen und das
  Release mit festem Tag ersetzen (alte Version löschen inkl. Tag, neu anlegen) mit
  `target_commitish` = Commit-SHA. Der Build schreibt die SHA in die App (z. B. version.py / BuildConfig).
- Je Plattform ein eigenes Release/Tag (z. B. `latest` für Windows, `android` für Android, dort
  `make_latest: false`), damit sich die Builds nicht gegenseitig löschen. `concurrency` mit
  `cancel-in-progress`, damit immer die neueste Version im Release landet.
- Der Update-Button vergleicht `target_commitish` des Releases mit der eingebauten SHA. Neuer → fragen,
  herunterladen (Release-Asset über die API mit `Accept: application/octet-stream`; bei der Weiterleitung
  zum Speicher-Server den Token NICHT mitschicken, sonst Fehler 400), installieren, neu starten.
  Beim Start leise prüfen und den Button hervorheben, wenn es ein Update gibt.
- Windows (.exe, PyInstaller --onefile): laufende .exe in „.old“ umbenennen, neue an ihren Platz,
  neu starten, „.old“ beim nächsten Start löschen.
- Android (.apk): mit festem, im Repo liegenden Schlüssel signieren (sonst lassen sich Updates nicht
  installieren), versionCode = Build-Nummer; Download in den Cache, Installation über einen eigenen
  ContentProvider + REQUEST_INSTALL_PACKAGES („Aus dieser Quelle zulassen“ vorher erklären).
- Die App zeigt ihre Version (kurze SHA) neben dem Namen an.

## 4. Einstellungen
- ⚙-Dialog: Repo (besitzer/name), Branch (leer = main), Token mit Link „Token erstellen (Haken bei
  ‚repo‘)“: https://github.com/settings/tokens/new?scopes=repo&description=<App>
  Ich nutze einen klassischen Token (Scope `repo`). Beim Speichern prüfen (Repo erreichbar, Schreibrechte).
- Lange Aktionen im Hintergrund, Statuszeile unten, verständliche deutsche Fehlermeldungen
  (401 Token ungültig, 403 keine Rechte, 404 Repo nicht gefunden, 409 Konflikt → kurz warten, erneut).

## 5. Dein Ablauf als Claude (bitte auch in die CLAUDE.md schreiben)
1. Abonniere den Klingel-PR mit `subscribe_pr_activity`. Lege dafür KEINE Zeitpläne oder
   Sicherheits-Check-ins an (kein Token-Verbrauch ohne Klingeln).
2. Bei einem Ruf: IMMER ALLE offenen `feedback`-Issues bearbeiten, nicht nur die genannten Nummern.
   Rufe während der Arbeit kommen verspätet an (Warteschlange), deshalb vor dem Abschluss einer
   Runde nochmal nach offenen Feedbacks sehen und diese mit erledigen.
3. Umsetzen, testen, auf `main` pushen, Build abwarten (Actions-Run `success` UND Release zeigt auf
   den neuen SHA), erst dann im Issue kurz auf Deutsch erklären, was sich geändert hat +
   „Neue Version über ⬆ Update verfügbar (<sha>)“, Issue schließen (`completed`).
   Reine Test-Feedbacks nur bestätigen und schließen. Große oder unklare Wünsche erst mit mir klären.
4. Eigene Kommentare im Klingel-PR lösen keine Arbeit aus.
5. Testen vor jedem Push: Code kompilieren, Oberfläche (falls möglich) per Screenshot prüfen, Logik
   gegen einen kleinen Fake-GitHub-Server testen – nie gegen das echte Repo (erzeugt sonst
   Commits/Issues bei mir).
6. Kommentare auf GitHub enden mit „---“ + „_Generated by [Claude Code](https://claude.ai/code)_“.

Lege am Anfang eine CLAUDE.md an (Projekt, meine Regeln, Aufbau, Build & Release, Testen,
Feedback-Workflow), damit spätere Sitzungen alles wissen. Frag mich vor dem Start nur, was wirklich
unklar ist.
```

---

**Tipp:** Wenn eine Sitzung endet und eine neue übernimmt, reicht als erster Satz:
„Lies die CLAUDE.md, abonniere den Klingel-PR #<Nummer> und prüfe offene Feedback-Issues.“
