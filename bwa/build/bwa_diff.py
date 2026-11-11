#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BWA-Dashboard FEG Metalltechnik: Veraenderung zwischen der veroeffentlichten Seite und dem neuen Datenstand.

  BWA_PASSWORT=... python3 bwa_diff.py --alt ../index.html --neu bwa_daten.json

Liest die verschluesselten Daten aus der bisherigen Seite (gleiches Passwort) und nennt je Buchungsperiode die neuen und
die entfallenen Buchungen, die Veraenderung je BWA-Zeile und das vorlaeufige Ergebnis alt und neu.
"""
import argparse
import base64
import collections
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bwa_daten as B  # noqa: E402

MK = ["Jan", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def alt_lesen(pfad, pw):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    m = re.search(r'const PAYLOAD = "([A-Za-z0-9+/=]+)";', Path(pfad).read_text(encoding="utf-8"))
    it = re.search(r"const KDF_ITER = (\d+);", Path(pfad).read_text(encoding="utf-8"))
    if not m:
        return None
    raw = base64.b64decode(m.group(1))
    key = hashlib.pbkdf2_hmac("sha256", pw.strip().lower().encode("utf-8"), raw[:16], int(it.group(1)), dklen=32)
    return json.loads(AESGCM(key).decrypt(raw[16:28], raw[28:], None).decode("utf-8"))


def poswerte(d, m):
    p = collections.defaultdict(float)
    for k in d["konten"]:
        v = k["s"].get(str(m), k["s"].get(m, 0.0))
        p[k["z"]] += -v if B.ART[k["z"]] == "e" else v
    return p


def f(v):
    return ("%.2f" % v).replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt", required=True)
    ap.add_argument("--neu", required=True)
    a = ap.parse_args()
    neu = json.loads(Path(a.neu).read_text(encoding="utf-8"))
    alt = alt_lesen(a.alt, os.environ.get("BWA_PASSWORT", "")) if Path(a.alt).exists() else None
    if not alt:
        print("Kein bisheriger Stand lesbar, kein Vergleich.")
        return
    print("Vergleich: Stand %s gegen Stand %s" % (alt["meta"]["stand"], neu["meta"]["stand"]))
    namen = {p["k"]: p["n"] for p in neu["pos"]}
    kn = {k["nr"]: k["n"] for k in neu["konten"]}

    def bz(d):
        c = collections.Counter()
        for nr, bs in d["buch"].items():
            if int(nr) not in {k["nr"] for k in d["konten"]}:
                continue
            for b in bs:
                c[(int(nr), b[8], b[0], b[1], b[2], b[4], b[5])] += 1
        return c
    ca, cn = bz(alt), bz(neu)
    dazu, weg = cn - ca, ca - cn
    if not dazu and not weg:
        print("Keine neue und keine entfallene Buchung auf Erfolgskonten.")
    for m in neu["meta"]["monate"]:
        dz = [(k, n) for k, n in dazu.items() if k[1] == m]
        wg = [(k, n) for k, n in weg.items() if k[1] == m]
        pa, pn = poswerte(alt, m), poswerte(neu, m)
        ea, en = B.summen(pa)["ergebnis"], B.summen(pn)["ergebnis"]
        if not dz and not wg and abs(ea - en) < 0.005:
            continue
        print("\n%s %d: %d neue, %d entfallene Buchungen | vorläufiges Ergebnis %s -> %s (Veränderung %s)" % (
            MK[m - 1], neu["meta"]["jahr"], sum(n for _, n in dz), sum(n for _, n in wg), f(ea), f(en), f(en - ea)))
        ch = sorted(((z, pn.get(z, 0) - pa.get(z, 0)) for z in set(pa) | set(pn)), key=lambda x: -abs(x[1]))
        for z, dv in ch:
            if abs(dv) >= 0.005:
                print("   %-55s %s -> %s (%s%s)" % (namen.get(z, z), f(pa.get(z, 0)), f(pn.get(z, 0)), "+" if dv > 0 else "", f(dv)))
        gr = sorted(dz, key=lambda x: -abs(x[0][5] - x[0][6]))[:8]
        for k, n in gr:
            print("      neu: Konto %d %s | %s | %s | %s | Soll %s Haben %s" % (k[0], kn.get(k[0], ""), k[2], k[3], k[4][:60], f(k[5]), f(k[6])))
    for m in neu["meta"]["monate"][-2:]:
        p = neu["pruef"][str(m)]
        print("\nVollständigkeit %s: %d Positionen wahrscheinlich fehlend, Kosten %s, Erlöse %s, Ergebnis laut Buchführung %s, nach fehlenden Buchungen %s%s" % (
            MK[m - 1], len(p["pos"]), f(p["fehl_kosten"]), f(p["fehl_erloese"]), f(p["ergebnis"]), f(p["ergebnis_bereinigt"]),
            " (Monat läuft, Tag %d von %d)" % (p["tag"], p["tage"]) if p["laeuft"] else ""))


if __name__ == "__main__":
    main()
