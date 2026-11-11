#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BWA-Dashboard FEG Metalltechnik: aus bwa_daten.json und bwa_template.html die verschluesselte Seite bauen.

  BWA_PASSWORT=... python3 bwa_build.py --daten bwa_daten.json --out ../index.html
  python3 bwa_build.py --daten bwa_daten.json --out vorschau.html --klartext     (nur zum Testen, nie veroeffentlichen)

Verfahren wie beim Dashboard Auftragspipeline: PBKDF2-SHA256 (300000 Runden) auf das kleingeschriebene Passwort,
AES-256-GCM, Salt 16 Byte + IV 12 Byte vor dem Chiffrat, Base64. Das Passwort steht nie in einer Datei des Repositories.
"""
import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

KDF_ITER = 300000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=str(Path(__file__).resolve().parent / "bwa_template.html"))
    ap.add_argument("--klartext", action="store_true")
    a = ap.parse_args()
    d = json.loads(Path(a.daten).read_text(encoding="utf-8"))
    if d["kontrolle"]["abweichungen"]:
        print("HINWEIS: %d Abweichungen Buchungen gegen Summen und Salden, sie stehen in der Fussnote der Seite"
              % len(d["kontrolle"]["abweichungen"]))
    plain_json = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    tpl = Path(a.template).read_text(encoding="utf-8")
    s = d["meta"]["stand"]
    stand = "%s.%s.%s, %s Uhr" % (s[8:10], s[5:7], s[0:4], s[11:16])
    if a.klartext:
        blob, plain_js = "", plain_json.replace("</", "<\\/")
    else:
        pw = (os.environ.get("BWA_PASSWORT") or "").strip().lower()
        if not pw:
            sys.exit("FEHLER: Umgebungsvariable BWA_PASSWORT fehlt")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        key = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, KDF_ITER, dklen=32)
        blob = base64.b64encode(salt + iv + AESGCM(key).encrypt(iv, plain_json.encode("utf-8"), None)).decode("ascii")
        plain_js = "null"
        # Gegenprobe: entschluesseln und vergleichen
        raw = base64.b64decode(blob)
        k2 = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), raw[:16], KDF_ITER, dklen=32)
        assert AESGCM(k2).decrypt(raw[16:28], raw[28:], None).decode("utf-8") == plain_json
    frag = tpl.replace("__PAYLOAD__", blob).replace("__ITER__", str(KDF_ITER)).replace("__PLAIN__", plain_js).replace("__STAND__", stand)
    cut = frag.index('<div class="wrap">')
    full = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            + frag[:cut] + '</head>\n<body>\n' + frag[cut:] + '\n</body>\n</html>\n')
    Path(a.out).write_text(full, encoding="utf-8")
    print("geschrieben: %s (%d Byte, Daten %d Byte, %s)" % (a.out, len(full), len(plain_json), "Klartext" if a.klartext else "verschluesselt"))


if __name__ == "__main__":
    main()
