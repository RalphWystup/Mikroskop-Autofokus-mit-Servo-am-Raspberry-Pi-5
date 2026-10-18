#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messung am Mikroskop (ohne Bildschirm, ueber SSH): Servo-Verhalten und Schaerfekurve — unabhaengig vom
Fokus-Algorithmus. Sein Wort (18.10.2026): „der Servomotor zusammen mit dem Getriebe haengt manchmal;
Schritte muenden nicht immer in Verstellungen, nur der kontinuierliche Lauf scheint ohne Stick-Slip zu gehen —
probier es selbst mal aus."

Was gemessen wird:
  A  Rauschen: 40 Bilder ohne Bewegung -> Streuung der Schaerfe und der Bildaenderung (Nullmass).
  B  Dauerlauf 0 -> 180 -> 0 Grad in 0,25-Grad-Schritten alle 40 ms, Puls bleibt an; je Schritt: rohe Schaerfe
     (Tenengrad, NICHT geclippt), Laplace-Varianz, Bildaenderung zum Vorbild. -> Schaerfekurve, Gipfel hin/zurueck,
     Hysterese (Spiel von Servo+Getriebe).
  C  Einzelschritte am Gipfel: Schrittweiten 0,1/0,2/0,5/1/2 Grad, je 6 Wiederholungen, in zwei Betriebsarten:
     „Puls aus" (wie im alten Programm: Puls, warten, Duty 0) und „Puls an" (Puls bleibt stehen). Je Schritt: hat
     sich das Bild ueber das Rauschen hinaus geaendert? -> Anteil wirksamer Schritte je Weite und Betriebsart.
Ergebnis: CSV in ~/Desktop/messung/ und eine Zusammenfassung auf der Konsole. Servo bleibt am Ende am Gipfel stehen.
"""
import csv, os, sys, time
import cv2, numpy as np
import RPi.GPIO as GPIO

SERVO_PIN, PWM_FREQ = 18, 55
MIN_MS, MAX_MS = 0.40, 2.40
ROI = 0.33
AUS = os.path.expanduser("~/Desktop/messung"); os.makedirs(AUS, exist_ok=True)
Z = time.strftime("%Y-%m-%d_%H%M%S")


def dc(a):  # Winkel -> Duty in %
    return 100 * ((a / 180) * (MAX_MS - MIN_MS) + MIN_MS) / (1000 / PWM_FREQ)


GPIO.setmode(GPIO.BCM); GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, PWM_FREQ); pwm.start(0)
cap = cv2.VideoCapture(0); cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
if not cap.isOpened():
    print("Kamera nicht gefunden"); sys.exit(1)
for _ in range(10): cap.read()                                    # Belichtung einschwingen
prev = None


def messen():
    """Ein frisches Bild: rohe Schaerfe (Tenengrad-Mittel, ungeclippt), Laplace-Varianz, Bildaenderung zum Vorbild."""
    global prev
    cap.grab(); ok, img = cap.read()                               # grab+read: das aelteste Pufferbild verwerfen
    if not ok: return None
    h, w = img.shape[:2]; y0, y1 = int(h * (0.5 - ROI / 2)), int(h * (0.5 + ROI / 2)); x0, x1 = int(w * (0.5 - ROI / 2)), int(w * (0.5 + ROI / 2))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); roi = g[y0:y1, x0:x1]
    gx = cv2.Sobel(roi, cv2.CV_64F, 1, 0, 3); gy = cv2.Sobel(roi, cv2.CV_64F, 0, 1, 3)
    ten = float(np.mean(gx ** 2 + gy ** 2)); lap = float(cv2.Laplacian(roi, cv2.CV_64F).var())
    aend = float(np.mean(cv2.absdiff(g, prev))) if prev is not None else 0.0
    prev = g
    return ten, lap, aend, g


def fahre(a):
    pwm.ChangeDutyCycle(dc(a))


# ---------------- A Rauschen
fahre(0); time.sleep(1.5)
r = [messen() for _ in range(40)][5:]
ten0 = np.array([x[0] for x in r]); ae0 = np.array([x[2] for x in r])          # Aenderung zwischen aufeinanderfolgenden Bildern ohne Bewegung
rausch_ten = float(np.std(ten0) / max(np.mean(ten0), 1e-9) * 100); rausch_ae = float(np.mean(ae0) + 3 * np.std(ae0))
print(f"A Rauschen ohne Bewegung: Schaerfe {np.mean(ten0):.0f} +- {rausch_ten:.1f} % · Bildaenderung {np.mean(ae0):.2f}, Schwelle (Mittel+3s) {rausch_ae:.2f}")

# ---------------- B Dauerlauf hin und zurueck
w = csv.writer(open(f"{AUS}/kurve_{Z}.csv", "w", newline="")); w.writerow(["richtung", "winkel", "tenengrad", "laplace", "bildaenderung", "t"])
kurve = {}
t0 = time.time()
for richtung, winkel in (("hin", np.arange(0, 180.01, 0.25)), ("zurueck", np.arange(180, -0.01, -0.25))):
    reihe = []
    for a in winkel:
        fahre(a); time.sleep(0.04)
        m = messen()
        if m: reihe.append((float(a), m[0], m[1], m[2])); w.writerow([richtung, f"{a:.2f}", f"{m[0]:.1f}", f"{m[1]:.1f}", f"{m[2]:.2f}", f"{time.time() - t0:.2f}"])
    kurve[richtung] = np.array(reihe)
for richtung, k in kurve.items():
    ten = k[:, 1]; i = int(np.argmax(ten)); halb = ten >= ten[i] / 2
    br = k[halb, 0]
    print(f"B {richtung:7s}: Gipfel {k[i, 0]:.2f} Grad, Schaerfe {ten[i]:.0f} (Rand {ten[0]:.0f}/{ten[-1]:.0f}), Halbwertsbreite {br.min():.1f}..{br.max():.1f} Grad = {br.max() - br.min():.1f} Grad, Bildaenderung im Lauf Mittel {k[:, 3].mean():.2f}")
g_hin = kurve["hin"][np.argmax(kurve["hin"][:, 1]), 0]; g_zu = kurve["zurueck"][np.argmax(kurve["zurueck"][:, 1]), 0]
print(f"B Hysterese (Gipfel hin - zurueck): {g_hin - g_zu:+.2f} Grad   [Dauer B {time.time() - t0:.0f} s]")
gipfel = (g_hin + g_zu) / 2

# ---------------- C Einzelschritte am Gipfel, zwei Betriebsarten
w2 = csv.writer(open(f"{AUS}/schritte_{Z}.csv", "w", newline="")); w2.writerow(["betriebsart", "weite", "nr", "von", "nach", "bildaenderung", "schaerfe_vor", "schaerfe_nach", "wirksam"])
print(f"C Einzelschritte um {gipfel:.1f} Grad (Schwelle Bildaenderung {rausch_ae:.2f}):")
for art in ("puls_aus", "puls_an"):
    fahre(gipfel - 6); time.sleep(1.0); pos = gipfel - 6
    for _ in range(8): messen()
    print(f"  {art}:", end="")
    for weite in (0.1, 0.2, 0.5, 1.0, 2.0):
        wirksam = 0; n = 6
        for nr in range(n):
            s_vor = messen(); g_vor = s_vor[3]
            ziel = pos + weite
            fahre(ziel); time.sleep(0.08 + 0.004 * weite)
            if art == "puls_aus": pwm.ChangeDutyCycle(0)
            time.sleep(0.35)
            for _ in range(2): messen()                            # Pufferbilder nach der Bewegung verwerfen
            s_nach = messen()
            ae = float(np.mean(cv2.absdiff(s_nach[3], g_vor)))        # Bild vor dem Schritt gegen Bild danach
            ok = ae > rausch_ae
            wirksam += ok; w2.writerow([art, weite, nr, f"{pos:.2f}", f"{ziel:.2f}", f"{ae:.2f}", f"{s_vor[0]:.0f}", f"{s_nach[0]:.0f}", int(ok)])
            pos = ziel
        print(f"  {weite:.1f}°: {wirksam}/{n}", end="")
    print()
    if art == "puls_aus": pwm.ChangeDutyCycle(dc(pos))

fahre(gipfel); time.sleep(0.6)
print(f"Servo steht auf {gipfel:.1f} Grad (Gipfel, Puls an). Dateien: kurve_{Z}.csv, schritte_{Z}.csv in ~/Desktop/messung")
cap.release(); pwm.stop(); GPIO.cleanup()
