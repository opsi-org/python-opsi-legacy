# Example for System.py

# Create .pot file
pygettext -a path/to/System.py

# Create .po template
msginit -l de_DE

# Edit .po file
edit de.po

# Compile .mo file
msgfmt -o locale/de/LC_MESSAGES/opsi_system.mo opsi_system_de.po

