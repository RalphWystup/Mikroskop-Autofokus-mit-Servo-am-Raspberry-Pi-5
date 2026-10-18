# Einrichten auf dem Raspberry Pi 5

1. `/boot/firmware/config.txt`: Zeile `dtoverlay=pwm-2chan` anhängen, neu starten (GPIO 18 wird PWM0-Kanal 2, `pinctrl get 18` zeigt `PWM0_CHAN2`).
2. `autofokus4.py` und `seite.html` nach `/home/pi/Desktop/autofokus4/`.
3. `mikroskop-fokus.service` nach `/etc/systemd/system/`, dann `sudo systemctl daemon-reload && sudo systemctl enable --now mikroskop-fokus`.
4. Firefox-Profil anlegen: `firefox -headless -CreateProfile "fokus /home/pi/.mozilla/fokus"`; `mikroskop-fokus.desktop` nach `~/.config/autostart/` (Fenster beim Anmelden, lokal wie über Remote-Desktop; Chromium zeigt in der xrdp-Sitzung nur ein weißes Fenster, gemessen 18.10.2026).
5. Rechnername: `sudo hostnamectl set-hostname mikroskop`, Eintrag `127.0.1.1 mikroskop` in `/etc/hosts`. Die Seite ist dann unter `http://mikroskop:8090` erreichbar.

Braucht: Raspberry Pi OS 12, Python 3 mit OpenCV und NumPy (im Standard-Image enthalten). Keine weiteren Pakete.

## Der Weg der KI (optional)

`bruecke/pi.py` läuft auf dem Windows-Arbeitsrechner neben der Brücke (Repositorium „KI-steuert-lokale-Hardware-ueber-eine-Bruecke") und
braucht die Python-Räder paramiko, bcrypt und pynacl im selben Ordner (werden beim ersten Lauf nach `pylib/` entpackt). `python pi.py einrichten`
legt einen SSH-Schlüssel an und trägt ihn auf dem Pi ein; danach `python pi.py` mit dem Auftrag in `pi_auftrag.txt`. Für den Betrieb des
Mikroskops ist das nicht nötig.
