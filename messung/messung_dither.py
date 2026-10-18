#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frage: Die Software-PWM hatte beim langsamen Lauf 0,0 Grad Hysterese, die saubere Hardware-PWM 5,0 Grad — wirkte das Zittern der
Software-PWM als Ruettler (Dither), der die Haftreibung des Getriebes loest? Probe: langsamer Lauf hin/zurueck um den Gipfel OHNE und MIT
Ruetteln (waehrend der Fahrt +-D Grad im Wechsel alle 25 ms um den Sollwert, am Messpunkt still), dazu Einzelschritte aus dem Stand mit Ruetteln."""
import os, time, csv, cv2, numpy as np
P = "/sys/class/pwm/pwmchip0"; CH = f"{P}/pwm2"
def w(pfad, wert):
    with open(pfad, "w") as f: f.write(str(wert))
if not os.path.isdir(CH): w(f"{P}/export", 2); time.sleep(0.3)
w(f"{CH}/period", 20_000_000)
def winkel(a): w(f"{CH}/duty_cycle", int((0.40 + float(np.clip(a, 0, 180)) / 180 * 2.00) * 1_000_000))
winkel(90); w(f"{CH}/enable", 1)
cap = cv2.VideoCapture(0); cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
for _ in range(10): cap.read()
prev = [None]
def mess():
    for _ in range(2): cap.grab()
    ok, img = cap.read(); g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); h, wd = g.shape; r = g[int(h*.335):int(h*.665), int(wd*.335):int(wd*.665)]
    t = float(np.mean(cv2.Sobel(r, cv2.CV_64F, 1, 0, 3)**2 + cv2.Sobel(r, cv2.CV_64F, 0, 1, 3)**2)); prev[0] = g; return t, g
def fahre_ruettelnd(a, D, dauer=0.15):
    """Sollwert a; waehrend dauer s abwechselnd a+D / a-D alle 25 ms, zuletzt a."""
    t0 = time.time(); s = 1
    while time.time() - t0 < dauer: winkel(a + s * D); s = -s; time.sleep(0.025)
    winkel(a); time.sleep(0.05)
AUS = "/home/pi/Desktop/messung"; Z = time.strftime("%H%M%S")
cw = csv.writer(open(f"{AUS}/dither_{Z}.csv", "w", newline="")); cw.writerow(["D", "richtung", "winkel", "tenengrad"])
for D in (0.0, 0.3, 0.6, 1.0):
    erg = {}; winkel(125); time.sleep(1.2)
    for richtung, wk in (("hin", np.arange(125, 155.01, 0.2)), ("zurueck", np.arange(155, 124.99, -0.2))):
        reihe = []
        for a in wk:
            if D: fahre_ruettelnd(a, D)
            else: winkel(a); time.sleep(0.2)
            t, _ = mess(); reihe.append((a, t)); cw.writerow([D, richtung, f"{a:.1f}", f"{t:.0f}"])
        k = np.array(reihe); i = int(np.argmax(k[:, 1])); halb = k[k[:, 1] >= k[i, 1] / 2, 0]; erg[richtung] = (k[i, 0], k[i, 1], halb.max() - halb.min())
    print(f"Ruetteln +-{D:.1f} Grad: Gipfel hin {erg['hin'][0]:.1f} (Schaerfe {erg['hin'][1]:.0f}, Breite {erg['hin'][2]:.1f}) / zurueck {erg['zurueck'][0]:.1f} (Schaerfe {erg['zurueck'][1]:.0f}, Breite {erg['zurueck'][2]:.1f}) -> Hysterese {erg['hin'][0]-erg['zurueck'][0]:+.1f} Grad")
g = erg["hin"][0]
# Einzelschritte aus dem Stand mit Ruetteln +-0,6
ae0 = []; winkel(g - 6); time.sleep(1.0)
for _ in range(25): _, g1 = mess(); ae0.append(float(np.mean(cv2.absdiff(g1, prev[0]))) if _ else 0)
_, gref = mess(); ae0 = []
for _ in range(20): _, g1 = mess(); ae0.append(float(np.mean(cv2.absdiff(g1, gref)))); gref = g1
schwelle = float(np.mean(ae0) + 3 * np.std(ae0)); pos = g - 6
print(f"Einzelschritte aus dem Stand MIT Ruetteln +-0,6 (Schwelle {schwelle:.2f}):", end="")
for weite in (0.1, 0.2, 0.3, 0.5):
    n_ok = 0
    for nr in range(6):
        _, g_vor = mess(); pos += weite; fahre_ruettelnd(pos, 0.6); time.sleep(0.3)
        for _ in range(2): mess()
        _, g_nach = mess(); n_ok += float(np.mean(cv2.absdiff(g_nach, g_vor))) > schwelle
    print(f"  {weite:.1f} Grad: {n_ok}/6", end="")
print()
winkel(g); time.sleep(0.4); cap.release(); print(f"Servo steht auf {g:.1f} Grad.")
