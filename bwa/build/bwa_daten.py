#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BWA-Dashboard FEG Metalltechnik: Daten aus den DATEV-Abrufen der laufenden Claude-Sitzung lesen.

Aufruf:
  python3 bwa_daten.py plan  [--heute JJJJ-MM-TT]         -> Liste der DATEV-Abrufe (JSON), strikt nacheinander ausfuehren
  python3 bwa_daten.py bauen --out bwa_daten.json [--heute JJJJ-MM-TT] [--protokolle ORDNER]

Die Abrufe laufen ueber den DATEV-Konnektor (Werkzeug ...datev_accounting_list). Die Antworten stehen im
Sitzungsprotokoll (jsonl) oder in ausgelagerten Dateien, von dort werden sie gelesen. Es wird nichts abgetippt.
Dieses Skript enthaelt keine Buchhaltungsdaten und keine Zugangsdaten.
"""
import argparse
import calendar
import collections
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys

START_MONAT = 8          # erster Monat mit Geschaeftsbetrieb der FEG im Wirtschaftsjahr 2026 (Asset Deal August 2026)
START_JAHR = 2026
BAGATELLE = 250.0        # Konten mit ueblichem Monatswert oder fehlendem Betrag unter dieser Grenze werden nicht gemeldet
RX_STAPEL = re.compile(r"^(\d{2})-(\d{4})/")
RX_DATEI = re.compile(r"Output has been saved to (\S+?\.(?:txt|json))")

# ------------------------------------------------------------------ BWA-Aufbau (DATEV-BWA, Form 01, SKR03)
# art: e = Ertrag (Haben minus Soll), a = Aufwand (Soll minus Haben). Bereiche = Kontonummern von bis (einschliesslich).
POS = [
    ("umsatz", "Umsatzerlöse", "e", [(8000, 8499), (8700, 8799), (8900, 8959)]),
    ("bestand", "Bestandsveränderungen fertige und unfertige Erzeugnisse", "e", [(8960, 8989)]),
    ("eigen", "Aktivierte Eigenleistungen", "e", [(8990, 8999)]),
    ("material", "Material- und Wareneinkauf", "a", [(3000, 3999), (8591, 8591), (8595, 8595)]),
    ("soerl", "Sonstige betriebliche Erlöse", "e", [(8500, 8699)]),
    ("personal", "Personalkosten", "a", [(4100, 4199)]),
    ("raum", "Raumkosten", "a", [(4200, 4299)]),
    ("bsteuern", "Betriebliche Steuern", "a", [(4300, 4319), (4321, 4359), (4510, 4510)]),
    ("versich", "Versicherungen und Beiträge", "a", [(4360, 4399)]),
    ("besondere", "Besondere Kosten", "a", [(4400, 4499)]),
    ("fahrzeug", "Fahrzeugkosten (ohne Kraftfahrzeugsteuer)", "a", [(4500, 4599)]),
    ("werbung", "Werbe- und Reisekosten", "a", [(4600, 4699)]),
    ("warenabgabe", "Kosten der Warenabgabe", "a", [(4700, 4799)]),
    ("afa", "Abschreibungen", "a", [(4815, 4889)]),
    ("reparatur", "Reparatur und Instandhaltung", "a", [(4800, 4809)]),
    ("sonstige", "Sonstige Kosten", "a", [(4810, 4814), (4890, 4999)]),
    ("zinsaufw", "Zinsaufwand", "a", [(2100, 2149)]),
    ("neutraufw", "Sonstiger neutraler Aufwand", "a", [(2000, 2099), (2150, 2199), (2300, 2499)]),
    ("zinsertr", "Zinserträge", "e", [(2650, 2699)]),
    ("neutrertr", "Sonstiger neutraler Ertrag", "e", [(2500, 2649), (2700, 2889), (2896, 2999), (8800, 8899)]),
    ("kalk", "Verrechnete kalkulatorische Kosten", "e", [(2890, 2895)]),
    ("unbesetzt", "Kontenklasse unbesetzt", "a", [(5000, 6999)]),
    ("steuern", "Steuern vom Einkommen und Ertrag", "a", [(2200, 2299), (4320, 4320)]),
    ("nz", "Nicht zugeordnete Erfolgskonten", "a", []),
]
# Reihenfolge, in der die Bereiche geprueft werden (erster Treffer gilt): Sonderfaelle vor den grossen Bereichen
PRUEF_REIHENFOLGE = ["material", "bsteuern", "steuern", "afa", "reparatur", "sonstige", "umsatz", "bestand", "eigen",
                     "soerl", "personal", "raum", "versich", "besondere", "fahrzeug", "werbung", "warenabgabe",
                     "zinsaufw", "neutraufw", "zinsertr", "kalk", "neutrertr", "unbesetzt"]
# Zuordnung, die durch die DATEV-BWA der FEG (Wertenachweis Oktober und November 2026, Stand 06.11.2026) belegt ist
BELEGT = {
    "umsatz": [8120, 8400, 8736],
    "material": [3100, 3102, 3400, 3425, 3736, 8595],
    "soerl": [8520, 8610, 8611, 8613, 8640],
    "personal": [4100, 4110, 4120, 4130, 4140, 4144, 4149, 4152, 4165, 4170, 4175, 4190, 4194, 4195],
    "raum": [4240, 4250, 4260],
    "bsteuern": [4510],
    "versich": [4360, 4380],
    "besondere": [4400],
    "fahrzeug": [4530, 4540, 4560, 4570, 4595],
    "werbung": [4600, 4653, 4663, 4664, 4666],
    "warenabgabe": [4710, 4730],
    "reparatur": [4800, 4806],
    "sonstige": [4810, 4900, 4909, 4910, 4925, 4930, 4931, 4940, 4945, 4946, 4950, 4955, 4960, 4969, 4970, 4980,
                 4981, 4982, 4985],
    "zinsertr": [2650],
}
BELEGT_KONTO = {k: z for z, ks in BELEGT.items() for k in ks}
ART = {p[0]: p[2] for p in POS}
# Darstellung: Positionen und Zwischensummen in der Reihenfolge der DATEV-BWA
AUFBAU = [
    ("pos", "umsatz"), ("pos", "bestand"), ("pos", "eigen"),
    ("sum", "gesamtleistung", "Gesamtleistung", "Umsatzerlöse + Bestandsveränderungen + aktivierte Eigenleistungen"),
    ("pos", "material"),
    ("sum", "rohertrag", "Rohertrag", "Gesamtleistung − Material- und Wareneinkauf"),
    ("pos", "soerl"),
    ("sum", "betrrohertrag", "Betrieblicher Rohertrag", "Rohertrag + sonstige betriebliche Erlöse"),
    ("kopf", "Kostenarten"),
    ("pos", "personal"), ("pos", "raum"), ("pos", "bsteuern"), ("pos", "versich"), ("pos", "besondere"),
    ("pos", "fahrzeug"), ("pos", "werbung"), ("pos", "warenabgabe"), ("pos", "afa"), ("pos", "reparatur"),
    ("pos", "sonstige"),
    ("sum", "gesamtkosten", "Gesamtkosten", "Summe der Kostenarten von Personalkosten bis sonstige Kosten"),
    ("sum", "betriebsergebnis", "Betriebsergebnis", "Betrieblicher Rohertrag − Gesamtkosten"),
    ("pos", "zinsaufw"), ("pos", "neutraufw"),
    ("sum", "neutraleraufwand", "Neutraler Aufwand", "Zinsaufwand + sonstiger neutraler Aufwand"),
    ("pos", "zinsertr"), ("pos", "neutrertr"), ("pos", "kalk"),
    ("sum", "neutralerertrag", "Neutraler Ertrag",
     "Zinserträge + sonstiger neutraler Ertrag + verrechnete kalkulatorische Kosten"),
    ("pos", "unbesetzt"), ("pos", "nz"),
    ("sum", "ergebnisvorsteuern", "Ergebnis vor Steuern",
     "Betriebsergebnis − neutraler Aufwand + neutraler Ertrag − Kontenklasse unbesetzt − nicht zugeordnete Erfolgskonten"),
    ("pos", "steuern"),
    ("sum", "ergebnis", "Vorläufiges Ergebnis", "Ergebnis vor Steuern − Steuern vom Einkommen und Ertrag"),
]
KOSTEN = ["personal", "raum", "bsteuern", "versich", "besondere", "fahrzeug", "werbung", "warenabgabe", "afa",
          "reparatur", "sonstige"]


def jetzt():
    """Aktuelle Zeit in Deutschland."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=1)))


def summen(p):
    """Zwischensummen aus den Positionswerten p[key] (jeweils in Darstellungsrichtung, also Ertraege und Kosten positiv)."""
    g = lambda k: p.get(k, 0.0)
    s = {}
    s["gesamtleistung"] = g("umsatz") + g("bestand") + g("eigen")
    s["rohertrag"] = s["gesamtleistung"] - g("material")
    s["betrrohertrag"] = s["rohertrag"] + g("soerl")
    s["gesamtkosten"] = sum(g(k) for k in KOSTEN)
    s["betriebsergebnis"] = s["betrrohertrag"] - s["gesamtkosten"]
    s["neutraleraufwand"] = g("zinsaufw") + g("neutraufw")
    s["neutralerertrag"] = g("zinsertr") + g("neutrertr") + g("kalk")
    s["ergebnisvorsteuern"] = (s["betriebsergebnis"] - s["neutraleraufwand"] + s["neutralerertrag"]
                               - g("unbesetzt") - g("nz"))
    s["ergebnis"] = s["ergebnisvorsteuern"] - g("steuern")
    return s


def zeile_von(konto):
    """(Positionsschluessel, Herkunft der Zuordnung). Herkunft: belegt (DATEV-BWA der FEG) oder bereich (SKR03-Kontenbereich)."""
    if konto in BELEGT_KONTO:
        return BELEGT_KONTO[konto], "belegt"
    ber = {p[0]: p[3] for p in POS}
    for z in PRUEF_REIHENFOLGE:
        for a, b in ber[z]:
            if a <= konto <= b:
                return z, "bereich"
    return "nz", "offen"


def ist_erfolgskonto(konto):
    return 2000 <= konto <= 6999 or 8000 <= konto <= 8999


# ------------------------------------------------------------------ Abrufplan
def plan(heute):
    cid, fj = "<clientId FEG Metalltechnik GmbH, Mandant 4089>", "%d0101" % heute.year
    calls = [{"schritt": "Summen und Salden", "resourceUri": "datev://accounting/accounting_sums_and_balances",
              "top": 1000, "skip": 0,
              "select": "id,account_number,caption,accounting_sums_and_balances_month_values,annual_value_debit,"
                        "annual_value_credit,balance,balance_debit_credit_identifier"}]
    erster = START_MONAT if heute.year == START_JAHR else 1
    fenster = []
    for m in range(erster, heute.month + 1):
        von = dt.date(heute.year, 1 if m == erster else m, 1)
        bis = dt.date(heute.year, 12, 31) if m == heute.month else dt.date(heute.year, m, calendar.monthrange(heute.year, m)[1])
        fenster.append((von, bis))
    for a, b, name in ((20000000, 69999999, "Aufwands- und neutrale Konten"), (80000000, 89999999, "Erlöskonten")):
        for von, bis in fenster:
            calls.append({"schritt": "Buchungen %s %s bis %s" % (name, von.strftime("%d.%m."), bis.strftime("%d.%m.%Y")),
                          "resourceUri": "datev://accounting/account_postings",
                          "filter": "account_number ge %d and account_number le %d and date ge %sT00:00:00 and date le %sT00:00:00"
                                    % (a, b, von.isoformat(), bis.isoformat())})
    for a, b, name in ((13600000, 13999999, "Verrechnungskonten"), (15900000, 15999999, "Durchlaufende Posten")):
        calls.append({"schritt": "Buchungen %s" % name, "resourceUri": "datev://accounting/account_postings",
                      "filter": "account_number ge %d and account_number le %d and date ge %d-01-01T00:00:00 and date le %d-12-31T00:00:00"
                                % (a, b, heute.year, heute.year)})
    return {"werkzeug": "datev_accounting_list (DATEV-Konnektor)", "clientId": cid, "fiscalYearId": fj,
            "hinweis": "Abrufe strikt nacheinander, nie parallel. Jeder Abruf mit clientId und fiscalYearId. "
                       "Antworten nicht abschreiben, das Skript liest sie aus dem Sitzungsprotokoll.",
            "abrufe": calls}


# ------------------------------------------------------------------ Werkzeugergebnisse lesen
def _text(c):
    x = c.get("content")
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "".join(t.get("text", "") for t in x if isinstance(t, dict) and t.get("type") == "text")
    return ""


def tool_ergebnisse(dateien):
    for f in dateien:
        uses = {}
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            m = o.get("message") or {}
            cont = m.get("content")
            if not isinstance(cont, list):
                continue
            for c in cont:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    uses[c["id"]] = (c.get("name", ""), c.get("input") or {})
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in uses:
                    name, inp = uses[c["tool_use_id"]]
                    if not name.endswith("datev_accounting_list"):
                        continue
                    t = _text(c)
                    mm = RX_DATEI.search(t)
                    if mm and os.path.exists(mm.group(1)):
                        t = open(mm.group(1), encoding="utf-8").read()
                    elif c.get("is_error"):
                        continue
                    try:
                        d = json.loads(t)
                    except ValueError:
                        continue
                    if d.get("status") != 200:
                        continue
                    b = d.get("body")
                    items = b.get("items") if isinstance(b, dict) else b
                    if isinstance(items, list):
                        yield inp, items


def kto(n):
    return int(n) // 10000


def lesen(dateien):
    susa, post, namen, abrufe = None, {}, {}, []
    for inp, items in tool_ergebnisse(dateien):
        uri = inp.get("resourceUri", "")
        if uri.endswith("accounting_sums_and_balances"):
            if inp.get("skip") in (None, 0):
                susa = list(items)
            elif susa is not None:
                susa.extend(items)
        elif uri.endswith("account_postings"):
            abrufe.append((inp.get("filter", ""), len(items)))
            for x in items:
                post[x["id"]] = x
        elif uri.endswith("debitors") or uri.endswith("creditors"):
            for x in items:
                if x.get("caption"):
                    namen[kto(x["account_number"])] = x["caption"].strip()
    return susa, post, namen, abrufe


# ------------------------------------------------------------------ Aufbereitung
def r2(v):
    return round(v + 0.0, 2)


def bauen(dateien, heute):
    susa, post, namen, abrufe = lesen(dateien)
    if not susa:
        raise SystemExit("FEHLER: keine Summen und Salden in den Protokollen gefunden")
    if not post:
        raise SystemExit("FEHLER: keine Kontobuchungen in den Protokollen gefunden")
    jahr = heute.year
    # --- Konten aus den Summen und Salden (Monatsverkehrszahlen, Soll positiv)
    konten, verr = {}, {}
    for it in susa:
        n = int(it["account_number"])
        if n >= 100000000:      # Personenkonten
            continue
        k = kto(n)
        mv = {}
        for m in it.get("accounting_sums_and_balances_month_values") or []:
            v = float(m.get("monthly_balance") or 0)
            mv[int(m["month"])] = r2(v if m.get("debit_credit_identifier") == "S" else -v)
        namen.setdefault(k, (it.get("caption") or "").strip())
        if ist_erfolgskonto(k):
            z, herkunft = zeile_von(k)
            konten[k] = {"nr": k, "n": (it.get("caption") or "").strip(), "z": z, "h": herkunft, "s": mv}
        elif 1360 <= k <= 1399 or 1590 <= k <= 1599:
            bal = float(it.get("balance") or 0)
            verr[k] = {"nr": k, "n": (it.get("caption") or "").strip(),
                       "saldo": r2(bal if it.get("balance_debit_credit_identifier") == "S" else -bal), "s": mv}
    # --- Buchungen
    name_zaehler = collections.defaultdict(collections.Counter)
    for x in post.values():
        t = (x.get("posting_description") or "").strip()
        g = kto(x.get("contra_account_number") or 0)
        if t and g >= 10000:
            name_zaehler[g][t.split(",")[0].strip()] += 1
    for g, c in name_zaehler.items():
        namen.setdefault(g, c.most_common(1)[0][0])
    buch = collections.defaultdict(list)
    for x in post.values():
        k = kto(x["account_number"])
        if k not in konten and k not in verr:
            if ist_erfolgskonto(k):          # Konto mit Buchungen, aber ohne Zeile in den Summen und Salden
                z, herkunft = zeile_von(k)
                konten[k] = {"nr": k, "n": namen.get(k, ""), "z": z, "h": herkunft, "s": {}}
            else:
                continue
        d = x["date"][:10]
        g = kto(x.get("contra_account_number") or 0)
        soll, haben = float(x.get("amount_debit") or 0), float(x.get("amount_credit") or 0)
        t = (x.get("posting_description") or "").strip()
        if not t and g in namen:
            t = namen[g]
        beleg = str(x.get("document_field1") or "").strip()
        stapel = x.get("accounting_sequence_id") or ""
        ms = RX_STAPEL.match(stapel)
        # Buchungsperiode = Monat des Buchungsstapels (so rechnen Summen und Salden und die DATEV-BWA), nicht das Belegdatum
        periode = int(ms.group(1)) if ms and int(ms.group(2)) == jahr else int(d[5:7])
        buch[k].append([d, "" if beleg == "0" else beleg, t, g, r2(soll), r2(haben),
                        stapel, 1 if x.get("general_reversal") else 0, periode])
    for k in buch:
        buch[k].sort(key=lambda b: (b[0], b[1], b[2]))
    # --- Kontrolle: Buchungen je Konto und Monat gegen die Summen und Salden
    abw = []
    for k, info in list(konten.items()) + list(verr.items()):
        ist = collections.defaultdict(float)
        for b in buch.get(k, []):
            ist[b[8]] += b[4] - b[5]
        for m in set(ist) | set(info["s"]):
            diff = r2(ist.get(m, 0.0) - info["s"].get(m, 0.0))
            if abs(diff) > 0.005:
                abw.append({"nr": k, "m": m, "buch": r2(ist.get(m, 0.0)), "susa": info["s"].get(m, 0.0), "diff": diff})
    # --- Monate mit Erfolgsbuchungen
    monate = sorted({m for i in konten.values() for m, v in i["s"].items() if abs(v) > 0.005} | {heute.month})
    monate = [m for m in monate if m <= heute.month]

    def wert(k, m):          # Kontowert in Darstellungsrichtung der Zeile
        i = konten[k]
        v = i["s"].get(m, 0.0)
        return -v if ART[i["z"]] == "e" else v

    def poswerte(ms):
        p = collections.defaultdict(float)
        for k, i in konten.items():
            for m in ms:
                p[i["z"]] += wert(k, m)
        return p

    # --- Vollstaendigkeitspruefung je Monat
    def monatsende(k, m):
        bs = [b for b in buch.get(k, []) if b[8] == m]
        letzter = calendar.monthrange(jahr, m)[1]
        return bool(bs) and all(int(b[0][5:7]) == m and int(b[0][8:10]) == letzter for b in bs)

    pruef = {}
    for M in monate:
        vor = [m for m in monate if m < M]
        laeuft = (M == heute.month)
        tage = calendar.monthrange(jahr, M)[1]
        anteil = heute.day / tage if laeuft else 1.0
        basis = vor[-3:]
        res = {"m": M, "laeuft": laeuft, "tag": heute.day if laeuft else tage, "tage": tage, "basis": basis,
               "pos": [], "genug": len(basis) >= 2}
        if res["genug"]:
            for k, i in sorted(konten.items()):
                vw = [wert(k, m) for m in basis]
                if not all(abs(v) > 0.005 for v in vw):
                    continue
                ueblich = statistics.median(vw)
                if abs(ueblich) < BAGATELLE:
                    continue
                ist = wert(k, M)
                me = all(monatsende(k, m) for m in basis)
                kleinster = min(vw, key=abs)
                status = None
                if laeuft:
                    # Laufender Monat: nur Abrechnungsbuchungen zum Monatsende (z. B. Lohn und Gehalt), anteilig bis heute.
                    # Laufend gebuchte Konten (Material, Frachten usw.) werden im laufenden Monat nicht gemeldet.
                    soll_bisher = ueblich * anteil
                    if me and abs(ist) < 0.5 * abs(soll_bisher):
                        status = "abrechnung"
                else:
                    soll_bisher = ueblich
                    if abs(ist) < 0.005:
                        status = "fehlt"
                    elif ist / kleinster < 0.5:
                        # weniger als die Haelfte des bisher niedrigsten Monatswerts
                        status = "niedrig"
                fehl = soll_bisher - ist
                if status and abs(fehl) >= BAGATELLE:
                    res["pos"].append({"nr": k, "z": i["z"], "ist": r2(ist), "ueblich": r2(ueblich),
                                       "vor": [r2(v) for v in vw], "soll": r2(soll_bisher), "fehl": r2(fehl),
                                       "status": status, "me": 1 if me else 0})
            res["pos"].sort(key=lambda p: -abs(p["fehl"]))
        pw = poswerte([M])
        res["ergebnis"] = r2(summen(pw)["ergebnis"])
        res["fehl_kosten"] = r2(sum(p["fehl"] for p in res["pos"] if ART[p["z"]] == "a"))
        res["fehl_erloese"] = r2(sum(p["fehl"] for p in res["pos"] if ART[p["z"]] == "e"))
        res["ergebnis_bereinigt"] = r2(res["ergebnis"] - res["fehl_kosten"] + res["fehl_erloese"])
        pruef[M] = res

    # --- Positionen, die im ganzen Jahr fehlen
    jahr_p = poswerte(monate)
    hat = lambda a, b: any(a <= k <= b and any(abs(v) > 0.005 for v in i["s"].values()) for k, i in konten.items())
    struktur = []
    if abs(jahr_p.get("afa", 0)) < 0.005:
        struktur.append({"k": "afa", "t": "Abschreibungen",
                         "x": "Im Wirtschaftsjahr %d ist keine Abschreibung gebucht (Konten 4815 bis 4889). Abschreibungen auf das "
                              "gekaufte Anlagevermögen mindern das Ergebnis, sobald sie gebucht werden. Die Höhe lässt sich aus der "
                              "Buchführung nicht ableiten, sie hängt vom Anlagenverzeichnis ab." % jahr})
    if not hat(4210, 4229):
        struktur.append({"k": "miete", "t": "Miete und Pacht",
                         "x": "In den Raumkosten ist im Wirtschaftsjahr %d keine Miete und keine Pacht gebucht (Konten 4210 bis 4229). "
                              "Wird Pacht gezahlt, fehlt dieser Aufwand in der BWA, solange die Zahlung auf einem anderen Konto steht." % jahr})
    if abs(jahr_p.get("zinsaufw", 0)) < 0.005:
        struktur.append({"k": "zins", "t": "Zinsaufwand",
                         "x": "Im Wirtschaftsjahr %d ist kein Zinsaufwand gebucht (Konten 2100 bis 2149). Zinsen aus Darlehen oder "
                              "Finanzierungen fehlen in der BWA, bis sie gebucht werden." % jahr})
    if abs(jahr_p.get("bestand", 0)) < 0.005 and not hat(3960, 3999):
        struktur.append({"k": "bestand", "t": "Bestandsveränderungen",
                         "x": "Es sind keine Bestandsveränderungen gebucht (Konten 8960 bis 8989 und 3960 bis 3999). Die BWA zeigt deshalb "
                              "den Material- und Wareneinkauf des Monats und nicht den Materialverbrauch. Unfertige und fertige "
                              "Erzeugnisse sind nicht bewertet. Der Rohertrag eines einzelnen Monats ist dadurch nur eingeschränkt aussagefähig."})
    if abs(jahr_p.get("steuern", 0)) < 0.005:
        struktur.append({"k": "steuern", "t": "Steuern vom Einkommen und Ertrag",
                         "x": "Im Wirtschaftsjahr %d ist weder Körperschaftsteuer noch Gewerbesteuer gebucht (Konten 2200 bis 2299 und "
                              "4320). Das vorläufige Ergebnis ist deshalb ein Ergebnis vor Ertragsteuern. Die Steuern mindern das "
                              "Ergebnis, sobald Vorauszahlungen oder eine Steuerrückstellung gebucht werden." % jahr})
    vk = [v for v in verr.values() if abs(v["saldo"]) > 0.005]
    vk.sort(key=lambda v: -abs(v["saldo"]))

    daten = {
        "meta": {"stand": jetzt().strftime("%Y-%m-%dT%H:%M"),
                 "heute": heute.isoformat(), "jahr": jahr, "monate": monate, "start": START_MONAT if jahr == START_JAHR else 1,
                 "mandant": "FEG Metalltechnik GmbH", "mandantnr": 4089, "bagatelle": BAGATELLE,
                 "quelle": "DATEV-Konnektor: Summen und Salden und Kontobuchungen, Wirtschaftsjahr %d" % jahr},
        "aufbau": [list(a) for a in AUFBAU],
        "pos": [{"k": p[0], "n": p[1], "art": p[2], "ber": p[3], "belegt": BELEGT.get(p[0], [])} for p in POS],
        "konten": sorted(konten.values(), key=lambda i: i["nr"]),
        "buch": {str(k): v for k, v in buch.items()},
        "namen": {str(k): v for k, v in namen.items() if v},
        "pruef": {str(m): v for m, v in pruef.items()},
        "struktur": struktur,
        "verr": vk,
        "kontrolle": {"abweichungen": abw, "buchungen": sum(len(v) for v in buch.values()), "konten": len(konten),
                      "abrufe": len(abrufe)},
    }
    return daten


def protokolle(ordner):
    fs = sorted(glob.glob(os.path.join(ordner, "**", "*.jsonl"), recursive=True), key=os.path.getmtime)
    if not fs:
        raise SystemExit("FEHLER: keine Sitzungsprotokolle unter %s" % ordner)
    return fs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modus", choices=["plan", "bauen"])
    ap.add_argument("--heute")
    ap.add_argument("--out", default="bwa_daten.json")
    ap.add_argument("--protokolle", default=os.path.expanduser("~/.claude/projects"))
    a = ap.parse_args()
    heute = dt.date.fromisoformat(a.heute) if a.heute else jetzt().date()
    if a.modus == "plan":
        print(json.dumps(plan(heute), ensure_ascii=False, indent=1))
        return
    d = bauen(protokolle(a.protokolle), heute)
    json.dump(d, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    k = d["kontrolle"]
    print("Stand %s | %d Erfolgskonten | %d Buchungen aus %d Abrufen | Monate %s" % (
        d["meta"]["stand"], k["konten"], k["buchungen"], k["abrufe"], d["meta"]["monate"]))
    nz = [i["nr"] for i in d["konten"] if i["z"] == "nz"]
    ber = [i["nr"] for i in d["konten"] if i["h"] == "bereich"]
    print("Zuordnung nur nach Kontenbereich (nicht durch die DATEV-BWA belegt): %s" % (ber or "keine"))
    if nz:
        print("WARNUNG: nicht zugeordnete Erfolgskonten: %s" % nz)
    if k["abweichungen"]:
        print("WARNUNG: Buchungen ungleich Summen und Salden bei %d Konto-Monaten:" % len(k["abweichungen"]))
        for x in k["abweichungen"][:30]:
            print("   Konto %s Monat %s: Buchungen %.2f, Summen und Salden %.2f, Differenz %.2f" % (
                x["nr"], x["m"], x["buch"], x["susa"], x["diff"]))
    else:
        print("Kontrolle: Buchungen je Konto und Monat = Summen und Salden, keine Abweichung")
    for m in d["meta"]["monate"]:
        p = d["pruef"][str(m)]
        print("Monat %02d: Ergebnis %.2f | wahrscheinlich fehlend Kosten %.2f, Erlöse %.2f | %d Positionen%s" % (
            m, p["ergebnis"], p["fehl_kosten"], p["fehl_erloese"], len(p["pos"]), " | läuft" if p["laeuft"] else ""))


if __name__ == "__main__":
    main()
