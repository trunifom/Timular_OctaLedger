# GUI-Konzept: Recherche, Entscheidungen und Design-System

Dieses Dokument hält fest, **warum** die Oberfläche so aufgebaut ist. Grundlage war eine Internet-
Recherche (vier parallele Recherche-Agenten: Timeular/EARLY, andere Zeiterfassungs-Tools,
Layout/Farben/Typografie, Navigation/Barrierefreiheit). Die Quellenlage war teils dünn; wo etwas nur
Erfahrungswert oder eigene Ableitung ist, steht das ausdrücklich dabei.

## 1. Was die Recherche ergeben hat

### 1.1 Timeular / EARLY (seit 18.03.2025 umbenannt)

Belegt (Hilfeseiten, Capterra-Zusammenfassung):

- Vertikale Seitenleiste; Bereiche **Calendar**, **Activities**, **Insights**, **Tracker** und
  **Quicktrack** (die beiden letzten unter *Settings*). Hauptansicht ist der Kalender/die Timeline.
- **Würfel-Einrichtung:** Aktivitäten zuerst anlegen, Würfel auf eine Seite legen, Schalter neben der
  Aktivität umlegen, Seite physisch beschriften, wiederholen. Eine Seite darf leer bleiben. **Keine
  Kalibrierung** – die Lage wird erkannt.
- **Insights:** Filterleiste (Zeitraum, Ordner, Personen, Aktivitäten, Tags, Notizen, Abrechenbar),
  speicherbare Filter; Donut-Diagramm mit zwei Ringen, Zeitverlauf pro Tag/Woche/Monat, Stunden/Prozent-
  Umschalter; Export CSV/XLSX/PDF nur für die gefilterten Daten; Rundung wirkt nur auf die Anzeige.
- **Kritik der Nutzer:** Das häufigste Problem ist die **Bluetooth-Verbindung** (Abbrüche, mehrere
  Anläufe, Nutzer bemerken die Trennung nicht); acht Aktivitäten reichen bei komplexer Arbeit nicht;
  Klick in die Timeline startet versehentlich Einträge.
- *Nicht belegt:* Farben, Rundungen, Schriftart, Icons, Dark Mode (keine Screenshots/Tokens gefunden).

### 1.2 Andere Zeiterfassungs-Tools (Toggl, RescueTime, Clockify u. a.)

Belegt bzw. aus Hersteller-Hilfen abgeleitet:

- Reihenfolge üblich: **Timer/Heute → Journal/Kalender → Berichte → Projekte → Einstellungen**.
- Startseite: laufender Timer groß, Schnellstart, heutige Einträge, Summen „Heute“/„Woche“.
- Leerzustände sollen den **nächsten Schritt** nennen; ein Onboarding besteht besser aus einer
  **Checkliste mit 3–5 Punkten** als aus einer Tour.
- Undo ist besser als Bestätigungsdialoge für umkehrbare Aktionen; Dialoge nur für Unumkehrbares.
- Typische Fehler: überladener Timer-Screen, vergessene Timer, Berichte leer, weil Einträge nicht
  zugeordnet/bestätigt sind, generische „Keine Daten“-Leerzustände.

### 1.3 Layout, Farben, Typografie

Belegt (Streamlit-Doku, Okabe-Ito, Urteil LG München): Streamlit-Theming/`fontFaces`, statische Auslieferung
eigener Schriften, Okabe-Ito-Palette, **Google Fonts per CDN verletzt die DSGVO** (LG München, 20.01.2022,
Az. 3 O 17493/20 – deshalb Schrift lokal hosten). Kontrastwerte wurden nach der WCAG-Formel selbst berechnet.
*Erfahrungswerte* (nicht aus Primärquellen): 4/8-px-Raster, Radien 6–12 px, Borders statt Schatten, Inter als
Schrift, Gewichte 400/500/600, `tabular-nums` für Timer.

### 1.4 Navigation, Nutzerführung, Barrierefreiheit

Belegt (NN/g, GitLab Design, W3C): die **aktive Seite muss klar markiert** sein (häufigster Menüfehler);
Labels konkret und ohne Jargon; die „7-Elemente-Regel“ gilt für Menüs nicht, acht Einträge sind
**gruppiert** unkritisch; Leerzustände mit nächster Handlung; WCAG 2.2: Zielgröße ≥ 24 px (AA), Fokus nicht
verdeckt (AA). *Erfahrungswert:* Gruppen „Alltag / Einrichten / System“, Du/Sie nicht mischen, einheitliche
Begriffe, Status immer Icon **und** Text.

## 2. Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Wie ist das Menü aufgebaut? | Seitenleiste, **vier Gruppen**: *Start* (Startseite mit Erklärung, geführter Einrichtung und Handbuch; jede neue Sitzung beginnt dort), *Alltag* (Übersicht, Würfel live, Zeitjournal, Statistik), *Einrichten* (Geräte, Seiten zuordnen, Verbindungen, Verwaltung), *System* (Daten, Einstellungen, Diagnose) | Häufiges oben, Einmal-Aufgaben in der Mitte, Technik unten; Kernaufgabe ≤ 1 Klick |
| Wie wird die aktive Seite gezeigt? | gefüllter (primärer) Menü-Button mit Icon **und** Text; Seitentitel = Menülabel | NN/g: Position muss erkennbar sein; Farbe nie allein |
| Was sieht man auf *jeder* Seite? | **Statusleiste** oben: laufender Eintrag + Timer, Tracker-Verbindung (Text+Symbol), Warnung bei Verbindungsverlust, Hinweis auf unbestätigte Einträge, Stopp-Knopf | Timeular-Hauptproblem: Abbruch unbemerkt |
| Was zeigt die Startseite? | (1) *Erste Schritte*-Checkliste, (2) großer Timer, (3) *Schnellstart*-Kacheln der meistgenutzten Tätigkeiten, (4) *Heute*/*Woche* + Einträge des Tages, (5) Start mit Projekt/Notiz eingeklappt | Toggl/RescueTime-Muster, schlanker Timer-Screen |
| Wie wird ein neuer Nutzer geführt? | Checkliste mit Fortschritt und **einem** hervorgehobenen nächsten Schritt (Tätigkeiten → Tracker → Adresse → Seiten → erster Eintrag), ausblendbar, verschwindet bei Abschluss; erklärende Leerzustände; Info-Expander je Seite; Tooltip an jedem Feld | Appcues/NN/g: Checkliste statt Tour |
| Was wird ein-/ausgeblendet? | Filter der Statistik, Start mit Projekt/Notiz und Bearbeiten-Formulare in **Expandern/Tabs**; Technisches (Diagnose, Rohwerte) im Bereich *System*; Warnungen und Fehler **nie** versteckt | Progressive Disclosure; Auffindbarkeit durch sprechende Titel |
| Wo wird was eingestellt? | Zeitzone, Erkennung, Protokoll im Bereich *Einstellungen*; **Darstellung (Hell/Dunkel, Schrift) direkt in der Seitenleiste**, weil man sie sofort ausprobieren will; Tracker-Details in *Geräte* | Häufige Schnellschalter nah, seltene Konfiguration gebündelt |
| Wie werden Zeiträume gewählt? | Schnellauswahl **Heute / Gestern / Letzte 7 / 30 Tage** plus Datumsfelder | die häufigsten Fragen mit einem Klick |
| Begriffe | **Tätigkeit**, **Eintrag** (statt „Sitzung“), **Sie**-Form, Datum TT.MM.JJJJ, 24-h-Uhr, Dauer h:mm | einheitlich, deutsch, konsistent |
| Destruktives | getrennt von Primäraktionen, mit Bestätigung und Pflichtgrund; Restore mit Vorschau | Smashing/NN/g |
| Diagramme | nur Okabe-Ito-/Tätigkeitsfarben, jedes Diagramm mit Tabelle darunter | farbenblind-freundlich, barrierefrei |

Bewusst **nicht** übernommen: Undo-Toast (das Löschen ist per Audit-Log nachvollziehbar, aber nicht
umkehrbar – bleibt Bestätigung mit Grund), Leerlauf-/Vergessen-Erkennung (kein Idle-Signal im Agenten),
Kalender-Drag-&-Drop, gespeicherte Filter, Top-Navigation (Streamlit-Version dafür nicht geprüft).

## 3. Design-System

### 3.1 Farben (alle Paare per Test auf WCAG geprüft)

| Rolle | Hell | Dunkel |
|---|---|---|
| Seitenhintergrund | `#F7F8FA` | `#14171C` (kein reines Schwarz) |
| Karte / Seitenleiste / Eingabe | `#FFFFFF` | `#1C2027` |
| Text | `#1F2937` | `#E6E9EE` |
| Gedämpfter Text | `#4B5563` | `#A3ABB8` |
| Primär (Aktionen, aktive Seite) | `#2563EB` (Text darauf `#FFFFFF`) | `#8CB4FF` (Text darauf `#0B1220`) |
| Rand dekorativ (Karten) | `#D0D5DD` | `#3C4350` |
| Rand interaktiv (≥ 3:1) | `#8A94A3` | `#6C7686` |
| Erfolg / Warnung / Fehler | `#067647` / `#B54708` / `#B42318` | `#4ADE80` / `#FBBF24` / `#FF8A80` |

Prinzip: **eine** Primärfarbe, neutrale Flächen, drei Statusfarben; kräftige Farbe tragen nur die
**Tätigkeitsfarben** (Okabe-Ito-Palette: `#0072B2 #E69F00 #009E73 #D55E00 #CC79A7 #56B4E9 #F0E442 #7F7F7F`).
Status wird immer mit Symbol **und** Text gezeigt (✔ / ▲ / ✖).

### 3.2 Formen und Abstände

Radien: 8 px (Knöpfe, Eingaben), 12 px (Karten, Expander, Formulare). **Keine Schatten** (wirken im
Dunkelmodus nicht), stattdessen 1-px-Ränder und Flächenstufen. Abstände im 4/8-px-Raster; Inhaltsbreite
max. 1200 px; mittlere Dichte. Knopfhierarchie: *primär* höchstens einmal je Bereich (gefüllt),
*sekundär* (umrandet), *tertiär* (Textlink-artig) für Nebenaktionen. Icons: Material Symbols
(`:material/…:`) statt Emoji, weil sie überall gleich aussehen und Farbe erben.

### 3.3 Typografie

**Inter** (variabel, WOFF2, ≈ 48 KB, SIL OFL) **lokal gehostet** unter `dashboard/static/` (Streamlit-
Static-Serving; keine Verbindung zu Google → DSGVO). Fallback `system-ui`, Segoe UI, Roboto. Gewichte 400/
500/600; Überschriften 1,25 Zeilenhöhe, Text 1,5; **tabellarische Ziffern** für Timer und Kennzahlen,
damit nichts springt. Textfarben: Text → gedämpft → (deaktiviert wird nicht als Information genutzt).
Zwei Schriftgrößen per Umschalter (16 px / 20 px), alles skaliert über `rem`.

### 3.4 Barrierefreiheit

Kontrast: Text ≥ 7:1, gedämpfter Text und Statusfarben ≥ 4,5:1, Rand interaktiver Elemente ≥ 3:1;
sichtbarer Fokusring (3 px) für die Tastaturbedienung; Menü, Knöpfe und Formulare sind echte
Streamlit-Widgets (per Tab erreichbar); Farbe ist nie das einzige Signal; Diagramme haben Tabellen.

## 4. Grenzen dieses Entwurfs

- Das Design ist aus **Best Practices** abgeleitet, nicht in Nutzertests belegt. Insbesondere das
  Timeular-Aussehen konnte mangels Screenshots nicht nachgebaut werden.
- Streamlit erlaubt keine echte Laufzeit-Themenumschaltung; Farben werden per CSS injiziert. Selektoren
  nutzen bevorzugt `data-testid` und `st-key-*`-Klassen, können aber bei Streamlit-Updates anzupassen sein.
- Die automatischen Tests prüfen Struktur, Texte, Kontraste und Auslieferung der Schrift, **nicht** das
  visuelle Ergebnis im Browser. Ein manueller Blick durch alle Seiten in Hell und Dunkel, beide Schriftgrößen
  und ein schmales Fenster ist nötig.

## 5. Quellen

- Timeular/EARLY: https://support.early.app/en/articles/675063-get-started-with-the-tracker ·
  https://support.early.app/en/articles/3035771-the-insights-tab ·
  https://support.early.app/en/articles/1146536-how-to-filter-round-and-export-your-data ·
  https://early.app/blog/timeular-is-now-early/ · https://www.capterra.com/p/176609/ZEI-by-Timeular/reviews/ ·
  https://chrisbailey.com/timeular-review-my-time-tracker-of-choice/
- Zeiterfassungs-UX: https://support.toggl.com/the-timer-page · https://support.toggl.com/tracking-time-in-the-calendar-view ·
  https://help.rescuetime.com/article/30-dashboard · https://www.eleken.co/blog-posts/time-tracking-app-design-how-to-make-an-app-that-increases-productivity ·
  https://www.appcues.com/blog/user-onboarding-guide · https://clockify.me/help/features/idle-detection ·
  https://smashingmagazine.com/2024/09/how-manage-dangerous-actions-user-interfaces
- Layout/Typografie/Streamlit: https://docs.streamlit.io/develop/concepts/configuration/theming ·
  https://docs.streamlit.io/develop/concepts/configuration/theming-customize-fonts ·
  https://docs.streamlit.io/develop/tutorials/configuration-and-theming/static-fonts ·
  https://docs.streamlit.io/develop/api-reference/navigation/st.navigation ·
  https://www.ihk.de/bergische/recht-und-steuern/wettbewerbsrecht/google-fonts-5646176
- Navigation/Barrierefreiheit: https://www.nngroup.com/articles/menu-design/ ·
  https://www.nngroup.com/topic/navigation/ · https://design.gitlab.com/usability/navigation-sidebar ·
  https://nngroup.com/articles/empty-state-interface-design ·
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum ·
  https://germanupa.de/sites/default/files/2024-05/leitfaden_ux-writing_heuristiken_v1.01_0.pdf
