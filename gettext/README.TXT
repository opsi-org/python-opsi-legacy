# Beispiel fuer Modul System.py

# .pot Datei erstellen
pygettext -a System.py

# template .po Datei erstellen
msginit -l de_DE

# .po Datei bearbeiten
edit de.po

# .mo Datei erstellen
msgfmt -o locale/de/LC_MESSAGES/opsi_system.mo opsi_system_de.po

