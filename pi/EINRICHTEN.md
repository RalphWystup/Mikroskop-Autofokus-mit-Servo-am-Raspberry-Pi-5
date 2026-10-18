# Einrichten auf dem Raspberry Pi 5

1. `/boot/firmware/config.txt`: Zeile `dtoverlay=pwm-2chan` anhängen, neu starten (GPIO 18 wird PWM0-Kanal 2, `pinctrl get 18` zeigt `PWM0_CHAN2`).
2. `autofokus4.py` und `seite.html` nach `/home/pi/Desktop/autofokus4/`.
3. `mikroskop-fokus.service` nach `/etc/systemd/system/`, dann `sudo systemctl daemon-reload && sudo systemctl enable --now mikroskop-fokus`.
4. `mikroskop-fokus.desktop` nach `~/.config/autostart/` (Fenster beim Anmelden, lokal wie über Remote-Desktop).
5. Rechnername: `sudo hostnamectl set-hostname mikroskop`, Eintrag `127.0.1.1 mikroskop` in `/etc/hosts`. Die Seite ist dann unter `http://mikroskop:8090` erreichbar.

Braucht: Raspberry Pi OS 12, Python 3 mit OpenCV und NumPy (im Standard-Image enthalten). Keine weiteren Pakete.
