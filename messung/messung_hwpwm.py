#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messung mit Hardware-PWM (RP1, GPIO18 = pwmchip0/pwm2, 50 Hz, 0,40-2,40 ms): dieselben Fragen wie am Vormittag mit Software-PWM —
A Rauschen/Halten am Gipfel mit anliegendem Puls, B Einzelschritte aus dem Stand (Puls bleibt an), C langsamer Lauf hin/zurück um den Gipfel."""
import os, time, csv, cv2, numpy as np
P = "/sys/class/pwm/pwmchip0"; CH = f"{P}/pwm2"; PERIODE = 20_000_000
def w(pfad, wert):
    with open(pfad, "w") as f: f.write(str(wert))
if not os.path.isdir(CH): w(f"{P}/export", 2); time.sleep(0.3)
w(f"{CH}/period", PERIODE)
def winkel(a):
    a = float(np.clip(a, 0, 180)); w(f"{CH}/duty_cycle", int((0.40 + a / 180 * 2.00) * 1_000_000))
winkel(90); w(f"{CH}/enable", 1)
cap = cv2.VideoCapture(0); cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
for _ in range(10): cap.read()
prev = [None]
def mess():
    for _ in range(2): cap.grab()
    ok, img = cap.read(); g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); h, wd = g.shape; r = g[int(h*.335):int(h*.665), int(wd*.335):int(wd*.665)]
    t = float(np.mean(cv2.Sobel(r, cv2.CV_64F, 1, 0, 3)**2 + cv2.Sobel(r, cv2.CV_64F, 0, 1, 3)**2))
    ae = float(np.mean(cv2.absdiff(g, prev[0]))) if prev[0] is not None else 0.0; prev[0] = g
    return t, ae, g
AUS = "/home/pi/Desktop/messung"; Z = time.strftime("%H%M%S")
# C zuerst: langsamer Lauf um den Gipfel (hin/zurueck), findet den Gipfel fuer A und B
cw = csv.writer(open(f"{AUS}/hw_fein_{Z}.csv", "w", newline="")); cw.writerow(["richtung", "winkel", "tenengrad"])
erg = {}
winkel(125); time.sleep(1.5)
for richtung, wk in (("hin", np.arange(125, 155.01, 0.2)), ("zurueck", np.arange(155, 124.99, -0.2))):
    reihe = []
    for a in wk:
        winkel(a); time.sleep(0.15); t, _, _ = mess(); reihe.append((a, t)); cw.writerow([richtung, f"{a:.1f}", f"{t:.0f}"])
    k = np.array(reihe); i = int(np.argmax(k[:, 1])); halb = k[k[:, 1] >= k[i, 1] / 2, 0]; erg[richtung] = k[i, 0]
    print(f"C {richtung:7s}: Gipfel {k[i,0]:.1f} Grad, Schaerfe {k[i,1]:.0f}, Halbwertsbreite {halb.min():.1f}..{halb.max():.1f} = {halb.max()-halb.min():.1f} Grad")
print(f"C Hysterese: {erg['hin']-erg['zurueck']:+.1f} Grad")
g = erg["hin"]
# A Halten am Gipfel, Puls an (Hardware)
winkel(g - 5); time.sleep(0.8)
for a in np.arange(g - 5, g + 0.01, 0.2): winkel(a); time.sleep(0.12)
time.sleep(0.5); werte = []
for _ in range(60): time.sleep(0.25); werte.append(mess()[0])
v = np.array(werte); print(f"A Halten 15 s am Gipfel {g:.1f} Grad, Puls an (Hardware): Schaerfe {v.mean():.0f} +- {v.std()/v.mean()*100:.1f} %, Anfang {v[:8].mean():.0f} -> Ende {v[-8:].mean():.0f}")
# Rauschschwelle der Bildaenderung im Stand
ae0 = np.array([mess()[1] for _ in range(30)][5:]); schwelle = ae0.mean() + 3 * ae0.std()
# B Einzelschritte aus dem Stand, Puls an
winkel(g - 6); time.sleep(1.0); pos = g - 6
for _ in range(6): mess()
print(f"B Einzelschritte aus dem Stand, Puls an (Schwelle {schwelle:.2f}):", end="")
for weite in (0.1, 0.2, 0.3, 0.5, 1.0):
    n_ok = 0
    for nr in range(6):
        _, _, g_vor = mess(); pos += weite; winkel(pos); time.sleep(0.4)
        for _ in range(2): mess()
        _, _, g_nach = mess(); ae = float(np.mean(cv2.absdiff(g_nach, g_vor))); n_ok += ae > schwelle
    print(f"  {weite:.1f} Grad: {n_ok}/6", end="")
print()
winkel(g); time.sleep(0.5); cap.release()
print(f"Servo steht auf {g:.1f} Grad, Puls an (Hardware).")
