#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autofokus 4 — Raspberry Pi 5, USB-Mikroskop, Servo am Hardware-PWM (GPIO 18 = pwmchip0/pwm2). Bedienseite Port 8090.

Gebaut nach den Messungen vom 18.10.2026 (~/Desktop/messung/) und der Literatur (Knapper et al. 2022, OpenFlexure; Pertuz 2013):
  * Hardware-PWM statt Software-PWM: im Stand ±0,7-0,9 % Schärfestreuung statt ±47-63 % (die Software-PWM zitterte).
  * Puls bleibt an (Hardware-PWM steht still: 60 s ohne Sprung, ±0,7 %). Jeder Handschritt, auch Plus, geht 5° runter und von unten hoch.
  * Spiel von Servo + Getriebe: 4,6° zwischen Hin- und Rückweg — darum wird JEDES Ziel von unten angefahren (OpenFlexure).
  * Losbrechen: ein Schritt aus dem Stand wird mit kurzem Rütteln (±0,6°, 150 ms) gefahren — 0,2° dann 6 von 6 wirksam, ohne 1 von 6.
  * Nach jedem Schritt 250 ms Ruhe, dann erst messen (Nachlauf von Servo und Kamera).
  * Schärfemaß Tenengrad (Sobel-Energie) in der Mitte-ROI, ungeclippt. Die Ist-Lage ist nur über die Schärfe bekannt.
Ablauf Autofokus: 1 Suchlauf 0→180° aufwärts (8°/s) → Gegend · 2 Stapel: von 12° darunter in 0,3°-Schritten über den Gipfel, Parabel
durch die 7 Punkte um das Maximum → Gipfelwinkel · 3 Anfahrt von 5° darunter in 0,2°-Schritten, Halt sobald die Schärfe ≥ 92 % des
Stapelmaximums ist; sonst zweiter Versuch; am Ende die ehrliche Zahl. Dann Puls aus.
    sudo python3 autofokus4.py       (sysfs-PWM braucht root)   Seite: http://<pi>:8090
"""
import http.server, json, os, threading, time, urllib.parse
import cv2, numpy as np

PWM = "/sys/class/pwm/pwmchip0"; CH = f"{PWM}/pwm2"
MIN_MS, MAX_MS = 0.40, 2.40
ROI = 0.33; SCHRITT = 0.3; FEIN = 0.2; WARTE = 0.25; ANFAHRT = 5.0; RUETTEL = 0.6
PORT = 8090
HALTEN_STROMLOS = True    # im Stand stromlos: kein Knurren (sein Wort 16:02); der fruehere Sprung kam vom Ruetteln am gespannten Getriebe, nicht vom Stromlos-Stand
AUS = "/home/pi/Desktop/messung"; os.makedirs(AUS, exist_ok=True)
LOG = open(f"{AUS}/autofokus4_{time.strftime('%Y-%m-%d')}.log", "a", encoding="utf-8")
CSV = open(f"{AUS}/autofokus4_{time.strftime('%Y-%m-%d')}.csv", "a", encoding="utf-8")
if CSV.tell() == 0: CSV.write("t,phase,winkel_befehl,schaerfe\n")

Z = {"winkel": None, "schaerfe": 0.0, "phase": "bereit", "max": 0.0, "max_winkel": None, "kurve": [], "meldungen": [],
     "lauf": False, "stopp": False, "fps": 0.0, "ende": False, "puls": False, "ergebnis": "", "stromlos": True}   # stromlos: waehlbar auf der Seite (sein Wort 16:10)
sperre = threading.Lock()


def log(text):
    z = f"{time.strftime('%H:%M:%S')} {text}"; LOG.write(z + "\n"); LOG.flush(); print(z, flush=True)
    Z["meldungen"].append(z); Z["meldungen"] = Z["meldungen"][-40:]


# ------------------------------------------------------------------ Servo am Hardware-PWM
def _w(pfad, wert):
    with open(pfad, "w") as f: f.write(str(wert))


if not os.path.isdir(CH): _w(f"{PWM}/export", 2); time.sleep(0.3)
_w(f"{CH}/period", 20_000_000)


def setze(a):
    a = float(np.clip(a, 0, 180)); _w(f"{CH}/duty_cycle", int((MIN_MS + a / 180 * (MAX_MS - MIN_MS)) * 1_000_000)); Z["winkel"] = a; return a


def puls_an():
    if not Z["puls"]: _w(f"{CH}/enable", 1); Z["puls"] = True


def puls_aus():
    """Nur wenn HALTEN_STROMLOS: sonst bleibt der Puls im Stand an (Hardware-PWM, still, gemessen 0,7 %)."""
    if Z["stromlos"] and Z["puls"]: _w(f"{CH}/enable", 0); Z["puls"] = False


def schritt(ziel):
    """Ein Schritt aus dem Stand: Puls an, 150 ms Rütteln ±RUETTEL um das Ziel, dann Ziel, dann WARTE Ruhe."""
    puls_an(); t0 = time.time(); s = 1
    while time.time() - t0 < 0.15: setze(ziel + s * RUETTEL); s = -s; time.sleep(0.025)
    setze(ziel); time.sleep(WARTE)


def fahre(ziel, grad_je_s=8.0, messen=None):
    """Dauerlauf im 0,1°-Raster (Puls an). messen: Liste, in die alle 0,3° (Winkel, Schärfe) geschrieben wird."""
    a = Z["winkel"] if Z["winkel"] is not None else ziel
    if not Z["puls"] and ziel < a:
        # Aus dem stromlosen Stand (16:03 gemessen: 1 von 6 Schritten sprang): den Puls nicht auf dem alten Winkel einschalten —
        # das Getriebe ist stromlos abgerutscht und der Servo reisst zurueck. Stattdessen gleich auf das untere Ziel: die erste
        # Bewegung ist die geplante Abwaertsfahrt.
        setze(ziel); puls_an(); time.sleep(0.5 + abs(a - ziel) / grad_je_s); a = ziel
    puls_an(); r = 1 if ziel >= a else -1; dt = 0.1 / grad_je_s
    while abs(ziel - a) > 0.05 and not Z["stopp"]:
        a = setze(round(a + r * min(0.1, abs(ziel - a)), 2)); time.sleep(dt)
        if messen is not None and round(a * 10) % 3 == 0: messen.append((a, Z["schaerfe"])); CSV.write(f"{time.time():.2f},suchlauf,{a:.2f},{Z['schaerfe']:.0f}\n")
    time.sleep(0.3)


def messe(n=2):
    w = []
    for _ in range(n): time.sleep(0.07); w.append(Z["schaerfe"])
    return float(np.mean(w))


# ------------------------------------------------------------------ Kamera
bild_jpeg = [b""]


def kamera():
    cap = cv2.VideoCapture(0); cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened(): log("Kamera nicht gefunden"); Z["ende"] = True; return
    n, t0 = 0, time.time()
    while not Z["ende"]:
        ok, img = cap.read()
        if not ok: time.sleep(0.05); continue
        h, w = img.shape[:2]; y0, y1 = int(h * (0.5 - ROI / 2)), int(h * (0.5 + ROI / 2)); x0, x1 = int(w * (0.5 - ROI / 2)), int(w * (0.5 + ROI / 2))
        g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, 3); gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, 3)
        Z["schaerfe"] = float(np.mean(gx ** 2 + gy ** 2)); n += 1
        if n % 2 == 0:
            cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 1)
            cv2.putText(img, f"{Z['schaerfe']:.0f}  {Z['winkel']:.1f}" if Z["winkel"] is not None else f"{Z['schaerfe']:.0f}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            ok2, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok2: bild_jpeg[0] = jpg.tobytes()
        if n % 30 == 0: Z["fps"] = 30 / (time.time() - t0); t0 = time.time()
    cap.release()


# ------------------------------------------------------------------ Autofokus
def stapel(von, bis, weite, phase):
    """Von unten in Schritten (mit Rütteln) aufwärts; je Schritt Ruhe und Messung. Bricht ab, wenn nach dem Maximum die Schärfe auf
    < 40 % gefallen ist (Gipfel überschritten). Liefert [(winkel, schaerfe)]."""
    punkte = []; a = von; best = 0.0
    while a <= bis + 1e-6 and not Z["stopp"]:
        schritt(a); s = messe(); punkte.append((a, s)); CSV.write(f"{time.time():.2f},{phase},{a:.2f},{s:.0f}\n"); CSV.flush()
        with sperre: Z["kurve"] = punkte[-80:]
        best = max(best, s)
        if best > 2000 and s < 0.4 * best and a > von + 2: break
        a = round(a + weite, 2)
    return punkte


def anfahrt(a_ziel, s_max, phase):
    """Von ANFAHRT darunter in FEIN-Schritten hoch; Halt, sobald die Schärfe ≥ 92 % des Maximums ist. Liefert (Anteil %, Winkel)."""
    start = max(0.0, a_ziel - ANFAHRT); fahre(start, 10.0); time.sleep(0.4)
    a = start; best, a_best = 0.0, start
    while a <= a_ziel + 1.5 and not Z["stopp"]:
        schritt(a); s = messe(); CSV.write(f"{time.time():.2f},{phase},{a:.2f},{s:.0f}\n")
        if s > best: best, a_best = s, a
        if s >= 0.92 * s_max: return s / s_max * 100, a
        if best >= 0.6 * s_max and s < 0.7 * best: break                       # überfahren
        a = round(a + (SCHRITT if a < a_ziel - 1.0 else FEIN), 2)
    return best / s_max * 100, a_best


def autofokus(voll=True):
    """voll: Suchlauf über alles, dann Stapel und Anfahrt. Nachfokus (voll=False): nur Stapel um die jetzige Stellung (±8°) und Anfahrt."""
    Z["lauf"] = True; Z["stopp"] = False; Z["max"] = 0.0; Z["max_winkel"] = None; Z["ergebnis"] = ""
    try:
        if voll:
            Z["phase"] = "1 Suchlauf"; log("Autofokus: Suchlauf 0→180° aufwärts, 8°/s")
            fahre(0, 14.0); time.sleep(0.5); grob = []; fahre(180, 8.0, messen=grob)
            if Z["stopp"] or len(grob) < 10: return log("abgebrochen")
            k = np.array(grob); i = int(np.argmax(k[:, 1])); gegend, fuss = float(k[i, 0]), float(np.median(k[:, 1]))
            with sperre: Z["kurve"] = [(float(a), float(s)) for a, s in grob[::2]]
            log(f"Suchlauf: Maximum {k[i, 1]:.0f} bei Befehl {gegend:.1f}° (Fuß {fuss:.0f})")
            if k[i, 1] < 3 * fuss: puls_aus(); return log("kein Gipfel (Maximum < 3× Fuß) — liegt eine Probe unter dem Objektiv?")
            von, bis = max(0.0, gegend - 12), min(180.0, gegend + 4)
        else:
            gegend = Z["winkel"] if Z["winkel"] is not None else 90.0; log(f"Nachfokus um {gegend:.1f}°: nur Stapel ±8° und Anfahrt")
            von, bis = max(0.0, gegend - 8), min(180.0, gegend + 8)
        Z["phase"] = "2 Stapel"
        log(f"Stapel von {von:.1f}° aufwärts in 0,3°-Schritten mit Rütteln")
        fahre(von, 12.0); time.sleep(0.5); st = stapel(von, bis, SCHRITT, "stapel")
        if Z["stopp"] or len(st) < 5: return log("abgebrochen")
        f = np.array(st); j = int(np.argmax(f[:, 1])); a_max, s_max = float(f[j, 0]), float(f[j, 1])
        if s_max < 3 * float(np.median(f[:, 1])) or s_max < 1000:
            puls_aus(); Z["phase"] = "kein Gipfel"
            return log(f"kein Gipfel im Stapel (Maximum {s_max:.0f}, Median {np.median(f[:, 1]):.0f}) — " + ("Nachfokus liegt zu weit weg: Autofokus drücken" if not voll else "liegt eine Probe unter dem Objektiv?"))
        lo, hi = max(0, j - 3), min(len(f), j + 4)
        if hi - lo >= 5:
            p = np.polyfit(f[lo:hi, 0], f[lo:hi, 1], 2)
            if p[0] < 0:
                a_max = float(np.clip(-p[1] / (2 * p[0]), f[lo, 0], f[hi - 1, 0]))
                s_max = max(s_max, float(np.polyval(p, a_max)))             # Bezug: Parabelhöhe (sein Wort 16:00), nie unter dem besten Punkt
        breite = float(f[f[:, 1] >= s_max / 2, 0].ptp()); Z["max"], Z["max_winkel"] = s_max, a_max
        log(f"Stapel: Parabelhöhe {s_max:.0f}, Gipfel {a_max:.2f}°, Halbwertsbreite {breite:.1f}°, {len(st)} Punkte")
        anteil = 0.0
        for versuch in (1, 2):
            Z["phase"] = f"3 Anfahrt {versuch}"; anteil, a_ist = anfahrt(a_max, s_max, f"anfahrt{versuch}")
            log(f"Anfahrt {versuch}: Halt bei {a_ist:.2f}°, Schärfe {anteil * s_max / 100:.0f} = {anteil:.0f} % des Maximums")
            if anteil >= 85 or Z["stopp"]: break
        puls_aus(); time.sleep(0.4); s_end = messe(6)
        if Z["stromlos"] and s_end < 0.85 * s_max and anteil >= 85:
            # 16:32 gemessen: stromlos rutschte das Getriebe beim Abschalten von 94 % auf 8 % ab. Dann: neu anfahren, Puls bleibt an.
            log(f"stromlos abgerutscht: {s_end / s_max * 100:.0f} % — fahre neu an, Puls bleibt diesmal an (Haltung auf der Seite umschaltbar)")
            Z["phase"] = "3 Anfahrt nach Abrutschen"; anteil, a_ist = anfahrt(a_max, s_max, "anfahrt3"); time.sleep(0.4); s_end = messe(6)
        Z["ergebnis"] = f"{s_end / s_max * 100:.0f} %"; Z["phase"] = "fertig"
        if s_end >= 0.85 * s_max:
            with open(f"{AUS}/letzter_fokus.txt", "w") as fx: fx.write(f"{Z['winkel']:.2f}\n")   # fuer den naechsten Start des Dienstes
        log(f"STATUS {'BESTANDEN' if s_end >= 0.85 * s_max else 'NICHT ERREICHT'}: gehalten {s_end:.0f} = {s_end / s_max * 100:.0f} % der Parabelhöhe bei {Z['winkel']:.2f}°")
    except Exception as e:
        log(f"Fehler im Autofokus: {e!r}"); Z["phase"] = "Fehler"
    finally:
        puls_aus(); Z["lauf"] = False


def hand(richtung):
    if Z["lauf"] or Z["winkel"] is None: return
    Z["lauf"] = True
    try:
        alt = Z["winkel"]; ziel = float(np.clip(alt + richtung * SCHRITT, 0, 180)); s0 = messe(3)
        # Beide Richtungen von unten (15:50 gemessen: ein Plus-Schritt mit Rütteln am gespannten Getriebe lässt es um das Spiel
        # zurückschnappen, Schärfe 8813 → 193; von unten treffen 6 von 6)
        fahre(max(0.0, ziel - ANFAHRT), 10.0)
        for a in np.arange(max(0.0, ziel - ANFAHRT), ziel + 1e-6, SCHRITT): schritt(a)
        schritt(ziel)
        puls_aus(); time.sleep(0.3); log(f"Hand {'+' if richtung > 0 else '−'}: {alt:.2f} → {Z['winkel']:.2f}°, Schärfe {s0:.0f} → {messe(3):.0f}")
    finally: Z["lauf"] = False


def befund():
    """Paket für die Analyse durch die KI: Zustand, letzte 60 Protokollzeilen, letzte Kurve, aktuelles Bild — in einem Ordner."""
    o = f"{AUS}/befund_{time.strftime('%Y-%m-%d_%H%M%S')}"; os.makedirs(o, exist_ok=True)
    with sperre: k = list(Z["kurve"])
    with open(f"{o}/zustand.json", "w", encoding="utf-8") as f:
        json.dump({x: Z[x] for x in ("winkel", "schaerfe", "phase", "max", "max_winkel", "lauf", "fps", "puls", "ergebnis", "stromlos")} | {"kurve": k}, f, ensure_ascii=False, indent=1)
    try:
        with open(LOG.name, encoding="utf-8") as f: zeilen = f.read().splitlines()[-60:]
    except OSError: zeilen = Z["meldungen"]
    with open(f"{o}/protokoll.txt", "w", encoding="utf-8") as f: f.write("\n".join(zeilen) + "\n")
    if bild_jpeg[0]:
        with open(f"{o}/bild.jpg", "wb") as f: f.write(bild_jpeg[0])
    log(f"Befund gebündelt: {o} (zustand.json, protokoll.txt, bild.jpg) — für die KI")


def nach(ziel):
    if Z["lauf"]: return
    Z["lauf"] = True
    try:
        ziel = float(np.clip(ziel, 0, 180)); fahre(max(0.0, ziel - ANFAHRT), 10.0)
        for a in np.arange(max(0.0, ziel - ANFAHRT), ziel + 1e-6, SCHRITT): schritt(a)
        schritt(ziel); puls_aus(); time.sleep(0.3); log(f"gefahren nach {Z['winkel']:.2f}° (von unten), Schärfe {messe(3):.0f}")
    finally: Z["lauf"] = False


# ------------------------------------------------------------------ Seite
SEITE_DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seite.html")


def seite() -> bytes:
    """Die Bedienseite liegt als seite.html neben dem Programm und wird bei jedem Aufruf gelesen (Änderungen ohne Neustart)."""
    try:
        with open(SEITE_DATEI, "rb") as f: return f.read()
    except OSError as e:
        return f"seite.html fehlt neben autofokus4.py: {e}".encode()




class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, d, code=200):
        b = json.dumps(d).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/":
            b = seite(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif p == "/status":
            with sperre: k = list(Z["kurve"])
            self._json({x: Z[x] for x in ("winkel", "schaerfe", "phase", "max", "max_winkel", "lauf", "fps", "meldungen", "puls", "ergebnis", "stromlos")} | {"kurve": k})
        elif p == "/bild.jpg":
            b = bild_jpeg[0]; self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif p == "/strom":
            self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.end_headers()
            try:
                letzte = None
                while not Z["ende"]:
                    b = bild_jpeg[0]
                    if b and b is not letzte:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(b)).encode() + b"\r\n\r\n" + b + b"\r\n"); letzte = b
                    time.sleep(0.06)
            except (BrokenPipeError, ConnectionResetError): pass
        elif p.startswith("/bilder/") and "/.." not in p:
            # Fotos des Aufbaus neben dem Programm (bilder/), fuer die Seite; nur dieser Ordner
            d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilder", os.path.basename(p))
            try:
                with open(d, "rb") as f: b = f.read()
                self.send_response(200); self.send_header("Content-Type", "image/jpeg" if d.endswith(".jpg") else "image/png"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            except OSError:
                self.send_response(404); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: return self._json({"fehler": "kein JSON"}, 400)
        art = d.get("art")
        if art == "auto" and not Z["lauf"]: threading.Thread(target=autofokus, daemon=True).start()
        elif art == "nachfokus" and not Z["lauf"]: threading.Thread(target=autofokus, args=(False,), daemon=True).start()
        elif art == "haltung" and not Z["lauf"]:
            Z["stromlos"] = (d.get("wert") == "stromlos")
            if Z["stromlos"]: puls_aus()
            elif Z["winkel"] is not None: setze(Z["winkel"]); puls_an()
            log("Haltung im Stand: " + ("stromlos (still, etwa 1 von 10 Handschritten daneben)" if Z["stromlos"] else "Puls an (12 von 12 getroffen, knurrt)"))
        elif art == "stopp": Z["stopp"] = True; log("Stopp gedrückt")
        elif art == "plus": threading.Thread(target=hand, args=(+1,), daemon=True).start()
        elif art == "minus": threading.Thread(target=hand, args=(-1,), daemon=True).start()
        elif art == "nach": threading.Thread(target=nach, args=(float(d.get("wert") or 0),), daemon=True).start()
        elif art == "befund": befund()
        elif art == "ende": Z["ende"] = True; log("Ende gedrückt")
        self._json({"ok": True})


if __name__ == "__main__":
    threading.Thread(target=kamera, daemon=True).start()
    try:
        start_winkel = float(open(f"{AUS}/letzter_fokus.txt").read().strip())      # letzter bestandener Fokus, von unten anfahren
    except (OSError, ValueError):
        start_winkel = 90.0
    setze(max(0.0, start_winkel - ANFAHRT)); puls_an(); time.sleep(1.0)
    threading.Thread(target=nach, args=(start_winkel,), daemon=True).start()
    log(f"Autofokus 4 gestartet — Hardware-PWM, Seite Port {PORT}, fahre auf den letzten Fokus {start_winkel:.1f}° (von unten)")
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        while not Z["ende"]: time.sleep(0.5)
    finally:
        srv.shutdown(); puls_aus(); log("beendet")
