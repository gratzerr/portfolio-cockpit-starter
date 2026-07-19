# Portfolio-Cockpit — Starter-Kit (eigene Instanz für eine weitere Person)

Ergebnis: eine eigene, kostenlose Cockpit-Instanz (eigene Web-Adresse, eigene Datenbank,
eigene Minuten-Updates, eigene API-Kontingente). **Nichts** davon berührt Rafaels Instanz.

Am einfachsten macht ihr das zusammen mit Claude in einer Session (~1–2 h).
Alle Dienste sind im kostenlosen Tarif.

---

## Was der Freund braucht (alles gratis)

1. **GitHub-Konto** (github.com) — hostet die Web-App + Rechenzeit für die Minuten-Updates
2. **Google-Konto** — für Firebase (Datenbank) und ggf. Google Drive (Portfolio-Performance-Datei)
3. **RapidAPI-Konto** (optional) — für die Mehrjahres-Analystenschätzungen im Research-Tab
4. Depotquelle: **Portfolio Performance** (voller Funktionsumfang) **oder** **Parqet** (Snapshot-Modus)

---

## Schritt 1 — GitHub-Repo + Pages

1. Neues **öffentliches** Repo anlegen (öffentlich = unbegrenzte Gratis-Rechenzeit),
   Name egal, gern kryptisch (z. B. `dep-x3k9v2`) — die URL ist dann schwer zu erraten.
2. Repo-Einstellungen → Pages → Source: „Deploy from a branch" → Branch `main`, Ordner `/ (root)`.
3. Die Web-Adresse lautet dann `https://<name>.github.io/<repo>/`.

## Schritt 2 — Firebase-Projekt (Datenbank)

1. console.firebase.google.com → „Projekt hinzufügen" (Name z. B. `cockpit-max`), Analytics aus.
2. **Firestore Database** anlegen (Production-Modus, Region `eur3` o. ä.).
3. **Authentication** → Sign-in-Methode **Google** aktivieren.
4. Projekteinstellungen → „Web-App" hinzufügen → `apiKey`, `authDomain`, `projectId` notieren.
5. Authentication → Settings → Autorisierte Domains: `<name>.github.io` hinzufügen.
6. Firestore → **Regeln** — exakt diese einsetzen (Owner-Mail = Google-Mail des Freundes,
   wird beim ersten Sync automatisch ins Dokument geschrieben):

```
rules_version = '2';
service cloud.firestore {
  match /databases/{db}/documents {
    match /portfolios/{pid} {
      allow read: if resource.data.public == true
                  || (request.auth != null && request.auth.token.email == resource.data.owner);
      allow update: if request.auth != null
                    && request.auth.token.email == resource.data.owner
                    && request.resource.data.owner == resource.data.owner;
      allow create: if request.auth != null
                    && request.resource.data.owner == request.auth.token.email;
      allow delete: if false;
    }
  }
}
```

## Schritt 3 — Service-Account (für die Cloud-Schleife)

1. console.cloud.google.com → Projekt auswählen → IAM & Verwaltung → Dienstkonten →
   „Dienstkonto erstellen" (Name `cockpit-actions`), Rolle **Cloud Datastore User**.
2. Schlüssel → „Neuen Schlüssel erstellen" (JSON) → Datei herunterladen.
3. Im GitHub-Repo: Settings → Secrets and variables → Actions → **New repository secret**
   `GCP_SA_KEY` = kompletter Inhalt der JSON-Datei.

## Schritt 4 — Kit-Dateien einspielen

1. Alle Dateien aus diesem `starter-kit/`-Ordner ins Repo:
   - Skripte + `template.html` → in einen Ordner `pipeline/`
   - `.github/workflows/update.yml` → gleicher Pfad im Repo
   - `sw.js`, `robots.txt` → Repo-Wurzel
2. `cockpit_config.template.json` → als `pipeline/cockpit_config.json` speichern und
   **alle** Platzhalter füllen (Firebase-Werte, Name, Live-URL, Owner-Mail, ogHash —
   Kommando zum Erzeugen des Geheim-Tokens steht in der Datei; Token privat aufheben!).

## Schritt 5 — Depotquelle anschließen

**Variante A: Portfolio Performance (empfohlen — voller Funktionsumfang)**
1. In PP die Datei als `depot.xml` speichern (unverschlüsseltes XML).
2. depot.xml in einen Google-Drive-Ordner legen (PP direkt dort speichern lassen —
   dann ist jeder Speichern-Klick automatisch der Sync).
3. Diesen Drive-Ordner für die Service-Account-Mail (`cockpit-actions@<projekt>.iam.gserviceaccount.com`)
   als **Betrachter** freigeben.

**Variante B: Parqet (Snapshot-Modus)**
1. Parqet-Portfolio auf „öffentlich" stellen, ID aus dem Share-Link kopieren (`app.parqet.com/p/<ID>`).
2. Einmalig: `python3 parqet_scaffold.py <ID>` → erzeugt `portfolio.json` (ins `pipeline/` legen).
3. Ohne PP entfallen: exakte Renditekurve, FIFO-Trading-Bilanz, Zahlungsjournal.
   Positionen/Werte/Gewinne kommen live von Parqet; Research-Tab voll nutzbar.

## Schritt 6 — Research-Schätzungen (optional, eigener Key)

1. rapidapi.com → Konto anlegen → API „Seeking Alpha Finance" (Tipsters) → **Basic $0** abonnieren
   (Hard Limit 500 Calls/Monat — es kann nichts abgebucht werden).
2. Playground → `X-RapidAPI-Key` kopieren → GitHub-Secret `RAPIDAPI_KEY` setzen.
3. Ohne Key zeigt der Research-Tab automatisch die 2-Jahres-Yahoo-Schätzungen — alles andere
   (Charts, Financial Statements, Kennzahlen) funktioniert ohnehin ohne Keys.

## Schritt 7 — Erster Lauf

1. GitHub → Actions → Workflow `cockpit update` → „Run workflow".
2. Nach ~2 Minuten: Live-URL öffnen — Depot da, Minuten-Updates laufen
   (der Workflow hält sich per Self-Dispatch selbst am Laufen).
3. Auf der Seite einmal mit dem Google-Konto anmelden (Settings-Zahnrad) → Gerät ist
   dauerhaft als Besitzer markiert. Geheim-Link für weitere Geräte:
   `<liveUrl>?og=<TOKEN>` (Token aus Schritt 4).

## Bekannte Grenzen / Hinweise

- **Yahoo-Kurse** sind eine inoffizielle Quelle — bei Ausfällen greifen die eingebauten Fallbacks.
- **News-Tiefenrecherche** (Katalysatoren, „Pulse") läuft bei Rafael über eine Claude-Routine;
  dafür bräuchte der Freund ein eigenes Claude-Abo + Routine. Ohne sie füllt der eingebaute
  Google-News-Radar (alle ~2 Min) die News-Karten trotzdem.
- **Privatsphäre:** Öffentliches Repo = die Depot-Daten stecken in der veröffentlichten Seite.
  Kryptischer Repo-Name + „Privat"-Schalter (Sichtschutz) sind Hürden, kein Tresor.
- Bei Fragen: Rafael bringt Claude mit. 🙂
