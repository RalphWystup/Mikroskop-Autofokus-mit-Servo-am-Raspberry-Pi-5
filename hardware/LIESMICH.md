# Hardware — was zum Nachbau gehört

Stand 19.10.2026. Fotos des Aufbaus: `../bilder/aufbau_seite.jpg`, `../bilder/aufbau_oben.jpg`. Gemessen und bekannt:

| Teil | Angabe |
|:--|:--|
| USB-Mikroskop | einfaches Modell mit Rändelrad zur Schärfe; Wandler Genesys Logic 05e3:f12b, 640 × 480, YUYV, 30 Bilder/s |
| Servo | Modellbauservo, 0–180° bei Impulsen 0,40–2,40 ms, 50 Hz, Signal GPIO 18, 5 V, GND |
| Getriebe | kleines Zahnrad auf der Servowelle, großes Zahnrad auf der Welle zum Rändelrad, Untersetzung 1 : 2 |
| Halterung | 3D-Druck, trägt Mikroskop, Servo und beide Räder in festem Abstand |
| Beleuchtung | eingebaute LEDs des Mikroskops um das Objektiv (Auflicht), Helligkeit am Rädchen des USB-Kabels; keine zusätzliche Lampe; weißes Blatt als Hintergrund |
| Stativ | Metallstange, trägt Servomechanik und Mikroskop; die große Rändelschraube stellt die Höhe von Hand grob ein |
| Stromversorgung | ein Netzteil 5,1 V / 3 A am USB-C des Pi; der Servo hängt am 5-V-Pin des Pi (kein zweites Netzteil) — 19.10.2026 gemessen: get_throttled 0x0, keine Unterspannung |
| Rechner | Raspberry Pi 5, 4 GB |

**Noch nicht im Repositorium** (liegen beim Auftraggeber): die Druckdateien (STL/3MF) von Halterung und Zahnrädern, die Zähnezahlen,
der Servotyp und die Modellbezeichnung des Mikroskops. Sobald sie hier liegen, ist der Nachbau vollständig beschrieben.

Gemessene Eigenschaften der Mechanik, die ein Nachbau mitbringt: Spiel von 4,6° (am Servo) zwischen Hin- und Rückweg, Losbrechen erst
ab 0,5° Schritt ohne Rütteln, Rückstellkraft im Stand (Knurren bei anliegendem Puls). Das Programm ist darauf eingerichtet.
