# Software idea

> Status: `draft` · Last updated: 2026-10-10

Original software concept: start from one existing vehicle model, let the PM choose priorities
and successor targets, compare competitors per market, and refresh cited evidence and reports
regularly. The original German notes below are preserved as written.

The [architecture overview](architecture/00-overview.md) describes the requirement-evidence
pipeline, and the [functional requirements](requirements/README.md) specify its planned behavior.
These concept notes describe the product vision; they do not change the architecture's current
scope or turn proposed features into implemented functionality.

## Idee

Wir wollen ein neues Automodell auf einem bestehenden Modell aufbauen.

1. Bestehendes Modell mit Spezifikationen in die App reingeben
        - Eingabe: PDF, PowerPoint, Excel, Word
   -> Alles darauf folgende ist NUR für diesem Modell aufbauend

2. Die Daten für PM schön darstellen. Z.B. columns für die für dieses Modell wichtigste quantitative Daten
        - z.B. Reichweite, Kosten, Verbrauch (kW/100km, l/100km), Beschleunigung, verschiedene Benchmarks (komfort, v>
   -> qualitative Daten auf Benutzerstudien, Social Media,... über KI ranken und Schulnoten geben
   -> Auflisten von Sonderausstattung (Glasdach, Kühlschrank,...) -> Wie Wichtig für die Kunden? Ranking

3. PM entscheided die Wichtigkeit dieser Daten (Ranking der Daten) -> Fokussetzung
   -> Fokus kommt von PMs aufgrund von Kundenfeedback,...

4. PM gibt an wie das Folgemodell diese Daten anpassen möchte
        - qualitative/quantitative Daten und Sonderausstattung

5. Scraping der ausgewählten Daten bei Kompetitoren (Autos der gleichen Klasse, vllt gleiches Preissegment,...) die d>
        - Mit Mittelwert, Zusammenfassung der Competition,...
   -> Dort müsste man zwischen verscshiedenen Märkten unterscheiden (Europa, Amerika, Asien,...)

6. Für alle Autos ist auch die Entwicklung dieser Daten über die Jahre interessant um Entwicklungen in die Zukunft zu>
        - Preisentwicklung, Reichweiteentwicklung

-> Punkt 3-6 wird z.B. wöchentlich iteriert (Daten gescraped und verglichen)
        - Einmal automatisch und auf Nachfrage von PM auch auf spezifische Modelle, Märkte,...

-> Wöchentliche Dokumentation der Daten auch ausserhalb der APP (z.B. PDF)

-> WICHTIG: Alle Daten mit Quelle, entweder PDF, PowerPoint oder hyperlink

-> Aufgrund der gesammelten Daten und der Datenwichtigkeit (3. Punkt) gibt die KI Vorschläge
        - Vorschläge grounded in den dargestellten/erstellten Daten
