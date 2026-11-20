# Mitarbeit

Pythoncode, Bezeichner und Docstrings auf Englisch, Benutzerdokumentation zunächst
auf Deutsch. Kleine nachvollziehbare Änderungen mit Tests bevorzugen.

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
```

Keine echten Arbeitszeitdaten, Geräteadressen oder Geheimnisse als Testfixtures
commiten. Hardwaretests müssen ausdrücklich aktiviert werden. Eine Änderung an
Zeitsemantik oder Datenformat benötigt Dokumentation und Migrationstest.
