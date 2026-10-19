#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Brueckenweg zum Raspberry Pi (C:\\Bruecke\\pi.py) — SSH mit paramiko, Schluessel statt Passwort.

  python pi.py einrichten   einmalig: Schluessel erzeugen, mit dem Passwort aus pi_zugang.txt auf
                            dem Pi eintragen, pi_zugang.txt danach loeschen (das Passwort bleibt nirgends)
  python pi.py              fuehrt den Inhalt von pi_auftrag.txt (Shell-Befehle) auf dem Pi aus, Ausgabe hier
paramiko und Abhaengigkeiten liegen als Raeder neben diesem Programm und werden beim ersten Lauf
nach C:\\Bruecke\\pylib entpackt (nichts aus dem Netz, nichts im Kurs-Python).
"""
import os, pathlib, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows-Konsole ist cp1252; der Pi liefert UTF-8
H = pathlib.Path(__file__).resolve().parent
LIB = H / "pylib"; KEY = H / "pi_key"; ZUGANG = H / "pi_zugang.txt"; AUFTRAG = H / "pi_auftrag.txt"
PI, USER = "mikroskop", "pi"          # Name im Heimnetz (Fritz!Box-DNS); die Adresse darf sich aendern

if not (LIB / "paramiko").is_dir():
    raeder = sorted(H.glob("*.whl"))
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--find-links", str(H), "--target", str(LIB), "--no-deps",
                        *[w.name.split("-")[0] for w in raeder]], capture_output=True, text=True)
    print("pylib:", "eingerichtet" if (LIB / "paramiko").is_dir() else "FEHLER " + (r.stderr or r.stdout)[-300:])
sys.path.insert(0, str(LIB))
import paramiko                                                   # noqa: E402


def verbinden(passwort=None):
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if passwort:
        c.connect(PI, username=USER, password=passwort, timeout=10, look_for_keys=False, allow_agent=False)
    else:
        c.connect(PI, username=USER, key_filename=str(KEY), timeout=10, look_for_keys=False, allow_agent=False)
    return c


def lauf(c, befehl, zeit=600):
    _, out, err = c.exec_command(befehl, timeout=zeit)
    o = out.read().decode("utf-8", "replace"); e = err.read().decode("utf-8", "replace"); rc = out.channel.recv_exit_status()
    return rc, o, e


def einrichten():
    if not ZUGANG.is_file():
        print("pi_zugang.txt fehlt (eine Zeile: das Passwort)"); return 1
    pw = ZUGANG.read_text(encoding="utf-8").strip()
    if not KEY.is_file():
        k = paramiko.RSAKey.generate(3072); k.write_private_key_file(str(KEY))
        (H / "pi_key.pub").write_text(f"ssh-rsa {k.get_base64()} bruecke\n")
    pub = (H / "pi_key.pub").read_text().strip()
    c = verbinden(pw)
    rc, o, e = lauf(c, f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && grep -qF '{pub.split()[1][:40]}' ~/.ssh/authorized_keys 2>/dev/null || echo '{pub}' >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; echo eingetragen")
    c.close(); print("Schluessel:", o.strip() or e.strip())
    c = verbinden(); rc, o, e = lauf(c, "hostname && uname -m && cat /etc/os-release | head -2"); c.close()
    print("Probe mit Schluessel:", o.strip().replace("\n", " | "))
    ZUGANG.unlink(); print("pi_zugang.txt geloescht")
    return 0


HOCHLADEN = H / "pi_hochladen.txt"     # Zeilen „lokaler Name -> /pfad/auf/dem/pi": Dateien aus C:\Bruecke per SFTP vor dem Auftrag (grosse Dateien, 19.10.2026)


def hochladen(c):
    if not HOCHLADEN.is_file(): return
    sftp = c.open_sftp()
    for z in HOCHLADEN.read_text(encoding="utf-8").splitlines():
        if "->" not in z: continue
        lokal, _, ziel = z.partition("->"); lokal = H / lokal.strip(); ziel = ziel.strip()
        if not lokal.is_file(): print(f"hochladen: {lokal.name} fehlt"); continue
        try: sftp.put(str(lokal), ziel); print(f"hochladen: {lokal.name} -> {ziel} ({lokal.stat().st_size} Byte)")
        except OSError as e: print(f"hochladen: {lokal.name} -> {ziel}: {e}")
    sftp.close(); HOCHLADEN.unlink()


def auftrag():
    if not AUFTRAG.is_file():
        print("pi_auftrag.txt fehlt"); return 1
    c = verbinden(); hochladen(c); rc, o, e = lauf(c, AUFTRAG.read_text(encoding="utf-8")); c.close()
    print(o, end=""); 
    if e.strip(): print("[stderr]", e.strip()[-2000:])
    print(f"[rc {rc}]"); return rc


if __name__ == "__main__":
    sys.exit(einrichten() if "einrichten" in sys.argv else auftrag())
