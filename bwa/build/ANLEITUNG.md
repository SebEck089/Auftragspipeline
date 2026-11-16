# BWA-Dashboard FEG Metalltechnik: Ablauf eines Updates

Seite: https://sebeck089.github.io/Auftragspipeline/bwa/ (Datei `bwa/index.html` in diesem Repository, Zweig `main`).
Die Seite enthält die Buchhaltungsdaten verschlüsselt, Passwort wie beim Dashboard Auftragspipeline.
Aktualisierung täglich um 17:00 Uhr über eine geplante Aufgabe. Die Seite nennt den Rhythmus im Kopf.
In diesem Ordner liegen nur Skripte und die Vorlage. Hier stehen keine Daten, kein Passwort und keine Kennungen.

## Schritte (eine Claude-Sitzung mit DATEV-Konnektor)

1. Abrufplan holen: `python3 bwa/build/bwa_daten.py plan`
2. Jeden Abruf des Plans mit dem Werkzeug `datev_accounting_list` ausführen, mit `clientId` (FEG Metalltechnik GmbH,
   Mandant 4089, aus `datev://accounting/clients`) und `fiscalYearId` aus dem Plan. Strikt nacheinander, nie parallel,
   Summen und Salden zuerst. Antworten nicht abschreiben. Schlägt ein Abruf fehl, einmal wiederholen. Fehlt danach ein Abruf,
   nicht veröffentlichen. Liefert ein Abruf statt der Daten einen Download-Link (Antwort zu groß für den Konnektor), das
   Datumsfenster dieses Abrufs teilen und beide Hälften abrufen.
3. Daten bauen: `python3 bwa/build/bwa_daten.py bauen --out <Arbeitsordner>/bwa_daten.json`
   Das Skript liest die Antworten aus dem Sitzungsprotokoll (`~/.claude/projects`, falls vorhanden) und aus den Dateien, in denen
   die Umgebung große Werkzeugergebnisse ablegt (`/tmp/claude-tool-results`). Ohne Sitzungsprotokoll, etwa in einer Chat-Sitzung,
   zählen nur diese Dateien: die neuesten Summen und Salden und alle danach abgerufenen Buchungen. Der Abrufplan ist deshalb so
   geschnitten, dass jede Antwort groß genug ist, um als Datei abgelegt zu werden (je Monat alle Erfolgskonten und die Konten
   1360 bis 1599, der laufende Monat ab dem 16. des Vormonats).
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

- Beide Sichten nutzen dieselben Konten und Buchungen wie die BWA. Die Zuordnung steht in `bwa_daten.py` (`DB_POS`, `GUV_POS`,
  aufgeteilte Konten in `DB_GETEILT`, `GUV_GETEILT`). Jedes Erfolgskonto steht in jeder Sicht in genau einer Zeile, ausgenommen die
  aufgeteilten Konten, deren Anteile je Monat zusammen 100 % ergeben.
- Kontrolle: `bwa_daten.py bauen` meldet „Kontrolle Sichten: jedes Konto vollständig zugeordnet, Ergebnis in Deckungsbeitragsrechnung
  und GuV je Monat = BWA“. Bei einer Abweichung baut `bwa_build.py` die Seite nicht und meldet FEHLER. Dann nicht veröffentlichen.
- Deckungsbeitragsrechnung: Deckungsbeitrag I nach variablen Kosten (Material, Fremdfertigung 3100 und 3102, Hilfs- und Betriebsstoffe
  und Entsorgung 4969, Verpackung und Ausgangsfrachten), Deckungsbeitrag II nach Fertigungspersonal (Fertigungslöhne der
  Stammbelegschaft mit Sozialaufwand und Arbeitskleidung 4400, Leiharbeit 4909) mit der Kennzahl Leiharbeitsquote, Deckungsbeitrag III
  nach Fertigungsgemeinkosten (Gehälter der Fertigungsbereiche, Gebäude, Energie und Maschinen, Abschreibungen). Deckungsbeitrag III
  zuzüglich Verpackung und Ausgangsfrachten ergibt das Bruttoergebnis vom Umsatz der GuV.
- GuV: Die sonstigen Steuern (Kraftfahrzeugsteuer 4510) stehen über dem Betriebsergebnis (EBIT). Ohne neutrale Posten ist das EBIT
  gleich dem Betriebsergebnis der BWA.
- Verrechnete Sachbezüge (8595, 8610, 8611, 8613) kommen aus der Lohnabrechnung und mindern die Gehälter.
- Konto 4130 (gesetzlicher Sozialaufwand) wird je Monat im Verhältnis Löhne (4110, 4190, 4195) zu Gehältern (4100, 4120) geteilt.
- Gehaltsschlüssel: Gehälter (4100, 4120), der Gehaltsanteil von 4130, die übrigen Personalkosten (4140 bis 4175, 4945, 4946) und die
  verrechneten Sachbezüge werden je Monat auf Herstellung, Vertrieb und Verwaltung geteilt (`GEHALT_SCHLUESSEL`, `SCHLUESSEL_KONTEN`).
  Der Schlüssel ist der Anteil der Gehälter je Funktionsbereich laut Lohnabrechnung des Monats (Gehaltsliste der FEG, Blatt
  Abrechnungen, Gehaltsempfänger und Geschäftsführung ohne Auszubildende). Herstellung: Arbeitsvorbereitung, Meister der Hallen,
  Einkauf, Instandhaltung, Logistik. Vertrieb: Vertrieb, Lkw-Fahrer. Verwaltung: Geschäftsführung, Buchhaltung und Personal.
  Ein Monat ohne Eintrag nutzt den letzten Eintrag davor. Pflege quartalsweise und bei Ein- und Austritten von Angestellten:
  neue Zeile `(Jahr, Monat): (Prozent Herstellung, Prozent Vertrieb)` ergänzen und `GEHALT_SCHLUESSEL_STAND` anpassen. Im Repository
  stehen nur Prozentsätze, keine Namen, Personalnummern oder Gehälter.
- Prozentwerte: In BWA, Deckungsbeitragsrechnung und GuV beziehen sich alle Prozentwerte auf den Nettoumsatz (Umsatzerlöse nach
  gewährten Skonti, ohne Schrotterlöse).
- `bwa_diff.py` nennt zusätzlich die Veränderung der Zwischensummen von Deckungsbeitragsrechnung und GuV je Monat.
- Neue Konten fallen über ihre BWA-Zeile in eine Zeile der Sicht (`DB_BWA`, `GUV_BWA`) und werden als „Zuordnung nicht geprüft“
  gekennzeichnet.
