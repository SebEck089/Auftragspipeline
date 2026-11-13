# BWA-Dashboard FEG Metalltechnik: Ablauf eines Updates

Seite: https://sebeck089.github.io/Auftragspipeline/bwa/ (Datei `bwa/index.html` in diesem Repository, Zweig `main`).
Die Seite enthält die Buchhaltungsdaten verschlüsselt, Passwort wie beim Dashboard Auftragspipeline.
In diesem Ordner liegen nur Skripte und die Vorlage. Hier stehen keine Daten, kein Passwort und keine Kennungen.

## Schritte (eine Claude-Sitzung mit DATEV-Konnektor)

1. Abrufplan holen: `python3 bwa/build/bwa_daten.py plan`
2. Jeden Abruf des Plans mit dem Werkzeug `datev_accounting_list` ausführen, mit `clientId` (FEG Metalltechnik GmbH,
   Mandant 4089, aus `datev://accounting/clients`) und `fiscalYearId` aus dem Plan. Strikt nacheinander, nie parallel.
   Antworten nicht abschreiben. Schlägt ein Abruf fehl, einmal wiederholen. Fehlt danach ein Abruf, nicht veröffentlichen.
3. Daten bauen: `python3 bwa/build/bwa_daten.py bauen --out <Arbeitsordner>/bwa_daten.json`
   Die Ausgabe muss „Kontrolle: Buchungen je Konto und Monat = Summen und Salden, keine Abweichung“ melden.
   Bei „WARNUNG: nicht zugeordnete Erfolgskonten“ oder „Zuordnung nur nach Kontenbereich“ die Konten im Bericht nennen.
4. Veränderung zum bisherigen Stand: `BWA_PASSWORT=… python3 bwa/build/bwa_diff.py --alt bwa/index.html --neu <Arbeitsordner>/bwa_daten.json`
5. Seite bauen: `BWA_PASSWORT=… python3 bwa/build/bwa_build.py --daten <Arbeitsordner>/bwa_daten.json --out bwa/index.html`
6. Nur `bwa/index.html` committen (Text „BWA TT.MM.JJJJ HH:MM“) und nach `main` pushen (vorher `git pull --rebase origin main`).
   Die Datei `index.html` im Hauptordner gehört zur Auftragspipeline und wird nie angefasst.

## Regeln der Auswertung

- Monatswert je Konto: Monatsverkehrszahlen der Summen und Salden. Buchungsperiode ist der Monat des Buchungsstapels,
  nicht das Belegdatum.
- Zuordnung der Konten zu den BWA-Zeilen: `BELEGT` in `bwa_daten.py` (aus der DATEV-BWA der FEG, Wertenachweis
  Oktober und November 2026). Neue Konten fallen über den SKR03-Kontenbereich in eine Zeile und werden in der Seite als
  „Zuordnung nicht bestätigt“ gekennzeichnet.
- Vollständigkeit: regelmäßig ist ein Konto, das in jedem der bis zu drei Vormonate gebucht war. Abgelaufener Monat:
  gemeldet wird „nicht gebucht“ oder „weniger als die Hälfte des bisher niedrigsten Monatswerts“. Laufender Monat: nur
  Konten, deren Buchungen in den Vormonaten immer zum Monatsletzten kamen (Lohn und Gehalt), anteilig bis zum Tag des Updates.

## Deckungsbeitragsrechnung und GuV nach dem Umsatzkostenverfahren

- Beide Sichten nutzen dieselben Konten und Buchungen wie die BWA. Die Zuordnung steht in `bwa_daten.py` (`DB_POS`, `GUV_POS`).
  Jedes Erfolgskonto steht in jeder Sicht in genau einer Zeile, das Ergebnis muss je Monat mit der BWA übereinstimmen
  (die Seite prüft das und meldet Abweichungen).
- Konto 4130 (gesetzlicher Sozialaufwand) wird je Monat im Verhältnis Löhne (4110, 4190, 4195) zu Gehältern (4100, 4120) geteilt.
- Neue Konten fallen über ihre BWA-Zeile in eine Zeile der Sicht (`DB_BWA`, `GUV_BWA`) und werden als „Zuordnung nicht geprüft“
  gekennzeichnet.
