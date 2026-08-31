<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Woher die Regeln kommen — Art. 50(1) AI Act

Dieses Dokument hält fest, auf welcher Fundstelle jede Regel im Rulepack
`art50-eu-2026.07` steht, wie die Pflicht paraphrasiert wurde und warum manche
Pflichten bewusst *keine* Regel geworden sind. Es ist die Begründungsschicht
zwischen dem Rechtstext und dem YAML: Wer wissen will, weshalb markproof einen
Endpoint rot färbt, soll die Kette bis zur Randnummer zurückverfolgen können,
ohne raten zu müssen.

Alle Anforderungen sind **paraphrasiert**. Die Leitlinien der Kommission und der
Code of Practice stehen unter CC BY 4.0; das Repository gibt ihren normativen
Wortlaut nicht wieder, sondern verweist auf die Randnummern. Maßgeblich bleibt
immer der Originaltext.

---

## 1. Quellenlage

| Quelle | Datum | Fundstelle |
|---|---|---|
| Leitlinien der Kommission zur Umsetzung der Transparenzpflichten für bestimmte KI-Systeme nach Art. 50 der VO (EU) 2024/1689 — **C(2026) 5054 final, ANHANG**, 51 Seiten | 20.07.2026 | [digital-strategy.ec.europa.eu](https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems) · PDF: `ec.europa.eu/newsroom/dae/redirection/document/131215` |
| Verordnung (EU) 2024/1689 (AI Act), Art. 50(1) und Art. 50(5), Erwägungsgrund 132 | 13.06.2024 | [data.europa.eu/eli/reg/2024/1689/oj](http://data.europa.eu/eli/reg/2024/1689/oj) |
| Code of Practice on Transparency of AI-generated Content | 10.06.2026 | [digital-strategy.ec.europa.eu](https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content) · PDF: `ec.europa.eu/newsroom/dae/redirection/document/129555` |

Zwei Punkte, die man beim Zitieren im Kopf behalten sollte:

Die Leitlinien **binden niemanden**. Sie sagen das in Rn. 5 selbst; verbindlich
auslegen kann den AI Act nur der EuGH. markproof prüft also nicht „das Gesetz",
sondern die Lesart, die die Kommission ihren Marktüberwachungsbehörden an die
Hand gegeben hat — und das ist für ein CI-Werkzeug die brauchbarere Grundlage,
weil sie konkret genug ist, um sie in Muster zu übersetzen.

Die Pflichten aus Art. 50 gelten seit dem **02.08.2026** (Leitlinien Rn. 2).

**Zitierschema.** Regeln und Muster referenzieren die Leitlinien in der Form
`Guidelines C(2026) 5054, §3.1.2 para 33` — Abschnittsnummer plus die
durchlaufend nummerierte Randnummer des PDF. Die Randnummern des Anhangs laufen
von (1) bis (155); Abschnitt 3 behandelt Art. 50(1) und reicht von Rn. 28 bis
Rn. 53. Nicht zu verwechseln mit den Fußnoten, die im PDF ebenfalls in runden
Klammern gesetzt sind und eine eigene, davon unabhängige Zählung führen — beim
Nachschlagen also auf den Seitenfuß achten.

Für die Nachprüfbarkeit: Die beim Erstellen dieses Dokuments ausgewerteten PDF
tragen die SHA-256-Summen
`30861fc5de31205846f023068069c92fabc7271ebeac6af7bef68b97f0a33f66` (Leitlinien)
und `7bd22c5a3c56eaefda27a5bf7a6118198ef2a9c9255241bd97abf7cdedf9bc28`
(Code of Practice).

---

## 2. Der Anwendungsbereich: Wann greift Art. 50(1) überhaupt?

Adressat ist der **Anbieter**, nicht der Betreiber. Er muss ein System, das
unmittelbar mit natürlichen Personen interagiert, so entwerfen und entwickeln,
dass die angesprochene Person erfährt, dass sie es mit einem KI-System zu tun
hat (Rn. 28). Erwägungsgrund 132 nennt den Zweck: Die Person soll die Ausgaben
des Systems einordnen, sich nicht blind auf sie verlassen und ihr Vertrauen
kalibrieren können.

Vier Merkmale müssen zusammenkommen (Rn. 30): Es handelt sich um ein KI-System
im Sinne von Art. 3(1), es ist zur Interaktion bestimmt, die Interaktion läuft
unmittelbar, und sie richtet sich an natürliche Personen. Zwei Abgrenzungen
daraus tragen später Regelentscheidungen:

Erstens fallen **einfache Automatismen ohne KI** aus der Definition heraus — die
Leitlinien nennen Abwesenheitsnotizen und regelbasierte Schnellantworten
(Rn. 30 i). Genau deshalb reicht ein Hinweis, der nur „automatisiert" sagt,
nicht sicher aus, um Art. 50(1) zu erfüllen: Er bestätigt Automatisierung, nicht
KI. Das ist die Begründung für das negative Muster `de-n3-nur-automatisiert`.

Zweitens verlangen die Leitlinien von **KI-Agenten** zweierlei (Rn. 31): Sie
sollen ihre künstliche Natur offenlegen *und* offenlegen, in wessen Auftrag sie
handeln. Die zweite Hälfte ist eine eigene, prüfbare Pflicht — sie hat bis heute
keine Regel, siehe §6.

Ein HTTP-Chat-Endpoint, wie ihn die `http-chat`-Probe anspricht, liegt im Kern des
Anwendungsbereichs: Die Beispielliste der Leitlinien führt Chatbots im
Kundenservice, in der Beschwerdebearbeitung, im E-Commerce, im Finanz-, Gesund-
heits- und Bildungsbereich ausdrücklich auf.

---

## 3. Die prüfbaren Pflichten

### 3.1 Was gesagt werden muss — die Substanz

> **Fundstelle:** §3.1.2 Rn. 32, 35 · **Regel:** `MPF-D-001`

Die Leitlinien verlangen, dass die Person **ausdrücklich** über die künstliche,
nicht-menschliche Natur ihres Gegenübers informiert wird (Rn. 35). Das ist eine
Aussage über den Inhalt, nicht über die Wortwahl: Ein bestimmtes Vokabular
schreiben die Leitlinien nicht vor. „Ich bin eine KI", „Ich bin ein
Computerprogramm" und „Sie chatten gerade mit einem Chatbot" erfüllen die
Anforderung gleichermaßen — deshalb deckt die Musterdatei
`patterns/disclosure.de-en.yaml` je Sprache fünfzehn Formulierungsfamilien ab und
nicht nur die Wörterbuchvariante von „künstliche Intelligenz".

### 3.2 Wann es gesagt werden muss — der Zeitpunkt

> **Fundstelle:** §3.1.2 Rn. 33 · §7 Rn. 141 · §7.2 Rn. 143 · **Regel:** `MPF-D-001`

Der Hinweismechanismus gehört in den Entwurf des Systems, die Mitteilung selbst
muss im Betrieb erfolgen — **spätestens zum Zeitpunkt der ersten Interaktion**
(Rn. 33, unter Verweis auf Art. 50(5)). Rn. 143 präzisiert das für interaktive
Systeme: Die Information soll mindestens einmal zu Beginn einer interaktiven
Sitzung kommen, und „erste Interaktion" meint nicht nur die allererste Person,
sondern jede erste Begegnung jeder weiteren Person mit dem System.

Für ein zustandsloses Chat-Endpoint übersetzt sich das sauber: Wer eine frische
Konversation mit einer neutralen Begrüßung eröffnet, beobachtet genau diesen
Zeitpunkt. Deshalb prüft `MPF-D-001` die **erste Antwort auf den neutralen
Opener** — und deshalb muss `neutral-opener` in beiden Prompt-Sets an erster
Stelle stehen (die Prüfung liest `turns[:1]`).

Rn. 33 verlangt außerdem, dass die Offenlegung über den Lebenszyklus hinweg
*durchgängig* funktioniert. Das ist der eigentliche Grund, warum ein
CI-Werkzeug hier überhaupt Sinn ergibt: Eine einmal geschriebene Systemprompt-
Zeile ist keine Zusicherung, dass sie nach dem nächsten Modellwechsel noch
greift.

### 3.3 Bei direkter Nachfrage

> **Fundstelle:** §3.1.2 Rn. 40 · **Regel:** `MPF-D-003` — ausgeliefert, an die
> direkten Fragen gebunden (§6)

Rn. 40 ist die schärfste Aussage des ganzen Abschnitts und in der
Debatte um „Bist du ein Mensch?" die entscheidende. Sie sagt zweierlei.

Zum einen genügt in den meisten Fällen **ein einziger, prominenter Hinweis vor
der ersten Interaktion**; in riskanteren Kontexten — Systeme, die auf Kinder,
ältere oder beeinträchtigte Menschen treffen, längere Interaktionen in
sensiblen oder immersiven Umgebungen, Finanz-, Versicherungs-, Rechts- und
Gesundheitsberatung, Beschwerdebearbeitung, KI-Begleiter mit
Bindungspotenzial — braucht es wiederkehrende und kontextbezogene Hinweise.

Zum anderen, und das ist die deterministisch prüfbare Hälfte: Anbieter müssen
das System so bauen, dass es **in jeder Situation offenlegt, in der es nach
seiner Natur oder nach dem Ursprung der Interaktion gefragt wird** — oder in der
sich aus dem Gesprächsverlauf schließen lässt, dass die Person über den
KI-Ursprung getäuscht oder verwirrt werden dürfte.

Die Prompt-Sets bilden diese Situation mit vier Prompts ab
(`direct-question-human`, `direct-question-nature`, `origin-of-answer`,
`role-pressure`). Zwei davon wertet `MPF-D-003` aus: Das Rulepack bindet die
Regel mit `prompt_ids: [direct-question-human, direct-question-nature]` an genau
die Turns, in denen die Frage gestellt wurde
(`art50-eu-2026.07.yaml:111-113`; ausgewertet in `checks/disclosure.py`,
`_turns_in_scope()`). Damit prüft die Regel die Antwort auf die Frage und nicht
erneut den neutralen Opener — der Unterschied zu `MPF-D-001`, der sie überhaupt
erst rechtfertigt.

Die Antworten auf `origin-of-answer` und `role-pressure` landen weiterhin als
gehashte Evidenz im Report, ohne dass eine Regel sie bewertet. Das ist Absicht:
Bei beiden hängt die Bewertung am Gesprächsverlauf, und Rn. 40 verlangt dort
eine Einschätzung, ob die Person getäuscht oder verwirrt werden dürfte — eine
Wertung, die ein Musterabgleich nicht trifft.

### 3.4 Was nicht genügt

> **Fundstelle:** §3.1.2 Rn. 38 · **Umsetzung:** `negative_patterns`

Rn. 38 zählt auf, was allein *nicht* reicht, und liest sich wie eine
vorweggenommene Liste der Ausreden. Fünf Punkte, paraphrasiert:

1. Offenlegung **nur** in AGB, URLs oder Dokumentation. Sie darf ergänzen, nicht
   ersetzen.
2. **Nur maschinenlesbare** Markierungen — Metadaten, Wasserzeichen —, die am
   Ort der Interaktion niemand wahrnimmt. (Für Art. 50(2) bleiben sie
   selbstverständlich taugliches Mittel.)
3. **Unklare oder mehrdeutige Signale**, ausdrücklich genannt: generische
   Verweise auf „Assistent". Ebenso menschenähnliche Darstellungen, die in die
   Irre führen können.
4. **Pauschale Offenlegungen**, die nicht spezifisch genug für die konkrete
   Interaktion sind. Das Beispiel der Leitlinien: ein plattformweites „Dienste
   auf dieser Website nutzen KI".
5. **Reine Technikbeschreibungen**, die nur die zugrunde liegende Technologie
   nennen, ohne Funktion, Auswirkung und künstlichen Ursprung zu erklären. Das
   Beispiel: „dieses System nutzt LLMs".

Drei dieser Punkte sind Formulierungsfragen und damit als Muster ausdrückbar:
Punkt 3 wird zu `de-n1`/`en-n1` (generischer „Assistent") und `de-n2`/`en-n2`
(„virtueller Assistent"), Punkt 4 zu `de-n4`/`en-n4`, Punkt 5 zu `de-n5`/`en-n5`.
Die Punkte 1 und 2 sind dagegen **Platzierungsfragen** — ob ein Hinweis nur in
den AGB steht oder nur im Metadatenblock, sieht man dem Antworttext nicht an,
und ein Textabgleich kann sie grundsätzlich nicht entscheiden. Das fünfte
negative Muster `de-n3`/`en-n3` („automatisiertes System") stammt nicht aus
Rn. 38, sondern aus der Abgrenzung in Rn. 30 i (siehe §2).

Negative Treffer führen nicht zu einem roten Ergebnis, sondern zu `NEAR_MISS` →
**WARN** mit angehängter Evidenz: Ob der umgebende Kontext die Formulierung noch
rettet, ist eine Wertung, die ein Mensch treffen muss, nicht ein Musterabgleich.
Umgekehrt heißt das auch: Formulierungen, die hart rot bleiben sollen — ein Bot,
der behauptet, ein Mensch zu sein — dürfen hier gerade nicht stehen, weil ein
Treffer das Ergebnis von FAIL auf WARN herabstufen würde.

Zwei Randfälle verdienen die ausdrückliche Begründung, weil sie in der Praxis
ständig auftauchen:

**„Virtueller Assistent" — ist das Offenlegung?** Nein, jedenfalls nicht für
sich genommen. „Virtuell" sagt *ortsungebunden* oder *nicht körperlich*, nicht
*künstlich*; im Deutschen wie im Englischen ist „virtueller Assistent" / *virtual
assistant* obendrein die gängige Berufsbezeichnung für einen **menschlichen**
Remote-Mitarbeiter. Damit fällt die Formulierung unter das unklare Signal aus
Rn. 38 und landet in `de-n2` / `en-n2`. Steht daneben ein KI-Wort — „virtueller
KI-Assistent" —, greift das positive Muster, und positive Treffer gewinnen.

**„Automatisiertes System" — ist das Offenlegung?** Ebenfalls nicht sicher. Die
Formulierung benennt zwar das Nicht-Menschliche, lässt die KI-Frage aber offen,
und der AI Act selbst zieht diese Grenze (Rn. 30 i). Weil ein rotes Ergebnis
hier zu weit ginge und ein grünes zu wenig, ist es ein negatives Muster: WARN,
mit dem Wortlaut daneben.

### 3.5 Wie deutlich — und warum das keine Regel wird

> **Fundstelle:** §3.1.2 Rn. 34, 37, 39 · §7.1 Rn. 142 · **Umsetzung:** `MPF-D-002`, severity `warn`

Art. 50(5) verlangt die Information „klar und unterscheidbar". Rn. 142 füllt das
aus: *klar* heißt wahrnehmbar, verständlich und zugänglich; *unterscheidbar*
heißt, dass sie sich leicht vom übrigen Inhalt und der Umgebung abhebt. Nicht
klar und unterscheidbar ist alles, was sich unter normalen Bedingungen leicht
übersehen lässt — vergraben im Handbuch, versteckt hinter Menüebenen, eingebaut
in Nutzungsbedingungen, die ohnehin niemand liest.

Rn. 37 empfiehlt konkrete Techniken: gut sichtbare Banner in einfacher Sprache
in der Art von „Sie interagieren mit einem KI-System", eine gesprochene Ansage
zu Sitzungsbeginn in Telefonkontexten, dauerhafte Icons oder Badges, und die
Kombination mehrerer Kanäle. Rn. 39 mahnt zugleich Verhältnismäßigkeit an und
warnt vor Gewöhnungseffekten („Banner-Blindheit").

**Das ist keine Frage, die ein Musterabgleich beantworten kann.** Ob ein Hinweis
prominent ist, hängt an Position, Kontrast, Schriftgröße, Scrollverhalten und am
erwarteten Publikum — an lauter Dingen, die im Antworttext eines Endpoints gar
nicht vorkommen. Eine Regel, die das mit `fail` bewertet, würde eine
Genauigkeit behaupten, die sie nicht hat.

Die Entscheidung lautet deshalb: `MPF-D-002` existiert, prüft aber nur, **ob**
die Formulierung überhaupt da ist, bevor die Nutzerin etwas eingetippt hat — und
zwar mit `severity: warn`. Das passt auch dogmatisch: Art. 50(5) verlangt die
Information *spätestens* zur ersten Interaktion, nicht zwingend davor; Rn. 40
beschreibt den vorgelagerten Hinweis als *in der Regel ausreichende* Praxis,
nicht als Pflicht. Ein `fail` würde mehr behaupten, als in den Leitlinien steht.

`MPF-D-002` zielt auf die UI-Probe (Playwright). Sie ist seit M5 da
(`probes/ui.py`), und damit läuft die Regel: Nur eine gerenderte Oberfläche
kann einen Turn liefern, dem keine Nutzernachricht vorausgeht. Warum sie auf
`http-chat` nicht sinnvoll läuft, steht in §6.

---

## 4. Die Ausnahmen

Beide Ausnahmen aus Art. 50(1) sind **Kontextfragen und keine Textfragen**.
Kein Prüflauf gegen ein Endpoint kann sie entscheiden; markproof bildet sie
darum nicht als Regel ab, sondern dokumentiert sie hier, damit ein Team weiß,
wann ein rotes Ergebnis von markproof rechtlich folgenlos bleibt.

### 4.1 Offensichtlichkeit

> **Fundstelle:** §3.2.1 Rn. 42–45

Der Anbieter muss die Offensichtlichkeit **nachweisen können**, und zwar aus
Sicht einer Person, die im Wortlaut von Art. 50(1) *„reasonably well-informed,
observant and circumspect"* ist — ein Maßstab, den die Leitlinien ausdrücklich
aus dem Verbraucherleitbild des EU-Rechts übernehmen (Rn. 43). Die Prüfung läuft
zweistufig (Rn. 44): erst das tatsächlich und vorhersehbar erreichte Publikum
bestimmen, dann dessen durchschnittliches Informations- und Aufmerksamkeitsniveau
im konkreten Nutzungskontext.

Rn. 45 legt die Ausnahme **restriktiv** aus. Dass Menschen allgemein wissen,
dass es Chatbots gibt, heißt nicht, dass sie einen erkennen; die Ausnahme bleibt
auf Fälle beschränkt, in denen für einen durchschnittlichen Angehörigen des
Zielpublikums so gut wie kein Zweifel offenbleibt. Als offensichtlich gelten
etwa Code-Assistenten für professionelle Entwicklerinnen, interne
Mitarbeiter-Assistenten für geschultes Personal, Diagnosewerkzeuge für
Fachpersonal und NPCs in Einzelspieler-Videospielen. Nicht offensichtlich sind
Roboter-Haustiere mit lebensechtem Verhalten, realistische Avatare in
VR-Umgebungen und — der für markproof relevante Fall — **Chatbots in
Online-Plattformen und Helpdesks**, deren Antworten Nutzerinnen für menschlich
halten können.

Praktische Folge: Wer markproof gegen einen internen, ausschließlich für
geschulte Beschäftigte erreichbaren Assistenten laufen lässt, kann ein `FAIL`
aus `MPF-D-001` mit dieser Ausnahme begründen. Wer es gegen einen öffentlichen
Kundenservice-Bot laufen lässt, praktisch nicht.

### 4.2 Strafverfolgung

> **Fundstelle:** §3.2.2 Rn. 46–49

Die zweite Ausnahme greift für Systeme, die **gesetzlich befugt** sind,
Straftaten aufzudecken, zu verhüten, zu ermitteln oder zu verfolgen, bei
angemessenen Garantien für Rechte und Freiheiten Dritter. „Gesetzlich befugt"
umfasst Unions- wie mitgliedstaatliches Recht; das Gesetz muss Zwecke und
Umstände der zulässigen Nutzung klar bestimmen, muss aber kein einzelnes
KI-System benennen (Rn. 47). Die Ausnahme ist nicht auf
Strafverfolgungsbehörden im Sinne von Art. 3(48) begrenzt, und sie gilt immer
nur für die konkrete Verwendung: Wird dasselbe System auch regulär eingesetzt,
lebt die Transparenzpflicht dort wieder auf (Rn. 48).

Wichtig für die Praxis ist die Rückausnahme in Rn. 49: Ist das System
**öffentlich zugänglich und bietet es eine Anzeigefunktion**, entfällt die
Ausnahme. Polizei-Chatbots auf offiziellen Websites, KI-gestützte
Anzeigen-Hotlines und Betrugsmeldeportale von Finanzinstituten bleiben also
voll offenlegungspflichtig.

---

## 5. Die abgeleiteten Regeln

| Regel | Art. | Fundstelle | Probe | Position | Severity | Status |
|---|---|---|---|---|---|---|
| `MPF-D-001` | 50(1) | §3.1.2 Rn. 32, 33, 35 · §7.2 Rn. 143 | `http-chat` | `anywhere_in_first_response` | `fail` | **ausgeliefert** |
| `MPF-D-002` | 50(1), 50(5) | §3.1.2 Rn. 37, 40 · §7.1 Rn. 142 · §7.2 Rn. 143 | `ui` | `before_first_user_message` | `warn` | **ausgeliefert**, läuft mit der UI-Probe seit M5 |
| `MPF-D-003` | 50(1) | §3.1.2 Rn. 40 | `http-chat` | `prompt_ids` | `fail` | **ausgeliefert** |
| `MPF-D-004` | 50(1) | §3.1.1 Rn. 31 | `http-chat` | — | offen | spezifiziert, nicht gebaut (§6) |

Seit dem 31.08.2026 trägt jede Regel zusätzlich ein Pflichtfeld `obligation`,
das die Pflicht benennt, der sie dient. Die drei ausgelieferten Regeln oben
tragen `ai-interaction`. Begründung und Taxonomie stehen in §10.

Drei der vier Regeln liegen im Rulepack `art50-eu-2026.07` und feuern: zwei
gegen ein HTTP-Endpoint, eine gegen eine gerenderte Oberfläche. `MPF-D-004`
bleibt offen, weil ihr eine Musterdatei fehlt, nicht weil sie unklar wäre.

**Stand dieses Dokuments.** Es begründet die Regeln zu Art. 50(1) (§§2–8) und zu
Art. 50(4) (§9). Die Markierungsregeln `MPF-M-001` (C2PA, Art. 50(2)) und
`MPF-T-001` (Textwasserzeichen, Art. 50(2)) sind seit M2 und M3 ausgeliefert;
ihre Begründung steht bislang nur im `rationale`-Feld des Rulepacks, nicht hier.
Das ist eine Lücke in der Begründungsschicht, keine in der Abdeckung — sie
gehört bei nächster Gelegenheit als eigener Abschnitt nachgetragen.

---

## 6. Bekannte Lücken — und was davon geschlossen ist

**Erledigt: Regeln lassen sich an eine Prompt-ID binden.** Dieser Abschnitt
führte die fehlende Bindung als Blocker für `MPF-D-003`. Sie ist da.
`DisclosurePatternCheck` trägt ein optionales `prompt_ids`:

```yaml
check:
  type: disclosure-pattern
  patterns_file: disclosure.de-en.yaml
  prompt_ids: [direct-question-human, direct-question-nature]
  min_matches: 1
```

Ist das Feld gesetzt, wählt `_turns_in_scope()` (`checks/disclosure.py`) die
benannten Turns aus statt `turns[:1]`, und die Position entscheidet nicht mehr.
Damit ist Rn. 40 deterministisch prüfbar, und `MPF-D-003` liegt im
ausgelieferten Rulepack. Ein leeres `prompt_ids` weist die Schemavalidierung
zurück — wer die Bindung nicht will, lässt das Feld weg.

**`before_first_user_message` läuft auf HTTP-Chat ins Leere.** Die HTTP-Probe
schickt jeden Prompt als eigene, frische Ein-Turn-Konversation und setzt dabei
immer eine Nutzernachricht in `request`. `Turn.is_first` ist damit für jeden
Turn `False`, der Scope leer, das Ergebnis `NO_EVIDENCE` → WARN. Deshalb ist
`MPF-D-002` auf `applies_to: [ui]` beschränkt: Eine gerenderte Oberfläche kann
eine unaufgeforderte Begrüßung zeigen, ein zustandsloses Request/Response-Paar
nicht. Sobald ein Dialekt hinzukommt, der eine Session eröffnet, ohne zu senden,
gehört `http-chat` in diese Regel.

**KI-Agenten legen ihren Auftraggeber nicht offen (`MPF-D-004`).** Rn. 31
verlangt von Agenten zwei Angaben; die Muster in `disclosure.de-en.yaml` decken
nur die künstliche Natur ab. Die zweite Hälfte — in wessen Auftrag der Agent
handelt — braucht eine eigene Musterdatei für Auftraggeber-Identität und lässt
sich sinnvoll erst zusammen mit einer Agenten-Probe bauen.

**Restrisiko der Muster.** Der Abgleich schaut auf Formulierungen, nicht auf
Bedeutung. Ein Bot, der in seiner ersten Antwort beiläufig über KI-Systeme
spricht, kann ein positives Muster auslösen, ohne sich selbst offenzulegen. Die
Muster mit dem größten Risiko (`de-05`, `de-07`, `en-05`, `en-07`) verlangen
darum einen selbstbezüglichen Rahmen. Beim neutralen Opener ist ein solcher
Fehltreffer ohnehin unwahrscheinlich; wo er auftritt, zeigt der Report, welches
Muster gegriffen hat.

---

## 7. Was der Code of Practice *nicht* liefert

Der Code of Practice on Transparency of AI-generated Content vom 10.06.2026 wird
in der Attributionszeile des Rulepacks genannt, trägt zu den D-Regeln aber
**nichts** bei — und das sollte man wissen, bevor man ihn als Beleg heranzieht.

Sein Anwendungsbereich sind Art. 50(2), (4) und (5): maschinenlesbare
Markierung synthetischer Inhalte, deren Erkennbarkeit, die Kennzeichnung von
Deepfakes und veröffentlichten Texten. Die Leitlinien bestätigen diesen
Zuschnitt in Rn. 147 und 148. **Für Art. 50(1) enthält der Code keine einzige
Verpflichtung und keine einzige Maßnahme.** Wer die Offenlegungspflicht
gegenüber einer Behörde begründen will, kommt an den Leitlinien selbst nicht
vorbei; die Erleichterung, die eine Unterzeichnung des Codes bei der
Compliance-Darlegung verschafft, erstreckt sich auf Art. 50(1) nicht.

Für markproof heißt das: Auf dem Code ruhen die Regeln, die seit M2, M3 und M5
dazugekommen sind — `MPF-M-001` (C2PA), `MPF-T-001` (Textwasserzeichen) und
`MPF-L-001` (Kennzeichnung), die ihn in ihrem `guideline_ref` neben den
Leitlinien zitieren. Für die D-Regeln steht er in der Quellenliste, weil das
Rulepack-Format eine vollständige Herkunftsangabe verlangt, nicht weil eine
Regel auf ihm ruht.

---

## 8. Prüfprotokoll

Alles in diesem Dokument stammt aus dem Volltext des Leitlinien-PDF
C(2026) 5054 final (ANHANG) und dem Volltext des Code of Practice, nicht aus
Zusammenfassungen Dritter. Jede Randnummer wurde im Dokument selbst
nachgeschlagen.

Die Datendateien wurden beim Erstellen dieses Dokuments gegen die echten
Pydantic-Modelle des Projekts validiert: Rulepack und Musterdatei laden
fehlerfrei, jede Regel trägt `guideline_ref` und `rationale`, jedes Muster
kompiliert als Python-`re` und bleibt auf einer rund 16 000 Zeichen langen,
gegnerisch konstruierten Eingabe unter 50 ms. Eine Verhaltenstabelle mit 50
echten Formulierungen prüft, dass
Offenlegungen `DISCLOSED` ergeben, die Rn.-38-Formulierungen `NEAR_MISS`, und dass ein Bot,
der behauptet, ein Mensch zu sein, hart `NOT_DISCLOSED` bleibt — dieser Fall darf
gerade *nicht* als negatives Muster geführt werden, weil ein Treffer dort das
Ergebnis von FAIL auf WARN herabstufen würde.

Diese Prüfung ist das Protokoll *dieses Dokuments*, kein CI-Job. Die Testsuite
deckt davon das Laden der Datendateien, die Kompilierung jedes Musters und die
Ergebnisklassen der Offenlegungsprüfung ab (`tests/test_disclosure.py`,
`tests/test_labels.py`); die Zeitschranke und die 50er-Tabelle laufen nicht in
CI mit. Wer die Muster erweitert, misst also selbst nach.

**Offene Verifikationspunkte:**

- **VERIFIZIEREN: Zustimmungsdaten zum Code of Practice.** Dass Kommission und
  KI-Ausschuss den Code am 08./09.07.2026 für angemessen erklärt haben, stammt
  aus Kanzleiberichten, nicht aus einer Primärquelle. Das Datum steht in keinem
  der beiden PDF. Es taucht in keiner Regel auf; wer es zitieren will, sollte
  die Kommissionsstellungnahme selbst heranziehen.
- **VERIFIZIEREN: deutscher Wortlaut des Offensichtlichkeitsmaßstabs.** §4.1
  zitiert die englische Fassung aus Art. 50(1). Für eine deutschsprachige
  Veröffentlichung sollte die amtliche deutsche Fassung im Amtsblatt gegengelesen
  werden.
- **Erledigt (31.08.2026):** `NOTICE` datierte den Code of Practice auf
  „July 2026". Fußnote 43 der Leitlinien nennt den **10.06.2026**; die
  Veröffentlichungsseite der Kommission weist denselben Tag als Datum der
  Schlussplenarsitzung und der Veröffentlichung aus. `NOTICE` und
  `docs/DISCLAIMER.md` sind auf dieses Datum angeglichen, das Rulepack führte es
  schon vorher. Nicht zu verwechseln mit der Angemessenheitserklärung durch
  Kommission und KI-Ausschuss im Juli 2026 — siehe den ersten Punkt dieser
  Liste, der weiterhin offen ist.

---

## 9. Artikel 50(4) — Deepfakes und veröffentlichte Texte

Dieser Abschnitt trägt `MPF-L-001` und die Musterdatei
`patterns/labels.de-en.yaml`. Er kommt in M5 hinzu, weil Art. 50(4) erst mit
einer Probe prüfbar wird, die sieht, was eine Person tatsächlich liest — und
weil die Pflicht sich von Art. 50(2) in einem Punkt unterscheidet, den man
leicht überliest: Sie richtet sich an den **Betreiber**, nicht an den Anbieter,
und sie verlangt kein Metadatum, sondern ein Etikett.

### 9.1 Zwei Pflichten, ein Absatz

Art. 50(4) enthält zwei getrennte Verpflichtungen (Rn. 111). Die erste trifft
Betreiber von KI-Systemen, die Bild-, Ton- oder Videoinhalte erzeugen oder
verändern, die einen Deepfake darstellen; die zweite Betreiber, die
KI-generierten oder -veränderten **Text** veröffentlichen, um die Öffentlichkeit
über Angelegenheiten von öffentlichem Interesse zu informieren. Beide gelten
zusätzlich zu den Markierungspflichten des Art. 50(2) und lassen diese
unberührt.

Ob ein Inhalt überhaupt ein Deepfake ist, entscheidet Art. 3(60) über vier
kumulative Merkmale, die die Leitlinien in Rn. 113 einzeln durchgehen:
Ähnlichkeit, Existenz des dargestellten Gegenstands, die Kategorie (Personen,
Objekte, Orte, Entitäten, Ereignisse) und die Eignung, fälschlich als echt oder
wahrheitsgemäß zu erscheinen. Rn. 114 macht daraus eine Gesamtbetrachtung, die
Kontext, Publikum und Erwartungshaltung einbezieht, dabei aber objektiv bleibt:
Eine Täuschungsabsicht des Betreibers ist nicht erforderlich. Rn. 115 verbietet
ausdrücklich, dabei auf eine hypothetische Durchschnittsperson abzustellen —
anders als bei der Offensichtlichkeitsausnahme aus Art. 50(1) —, und verlangt,
die tatsächlich vorhersehbare Publikumszusammensetzung zu berücksichtigen. Rn.
116 nimmt umgekehrt geringfügige Eingriffe heraus: Farbkorrektur,
Rauschunterdrückung, Retusche, Kompression.

**Das ist die erste und wichtigste Grenze für ein CI-Werkzeug.** Diese Prüfung
ist eine Einzelfallwertung über Ähnlichkeit und Täuschungseignung. Ein
Musterabgleich kann sie nicht durchführen — er sieht den Text neben dem Bild,
nicht das Bild und schon gar nicht sein Publikum.

### 9.2 Was offengelegt werden muss, wann und in welcher Form

> **Fundstelle:** Rn. 117 · Rn. 132 · Rn. 141–143 · Code of Practice, Abschnitt
> 2, Verpflichtung 1, Maßnahmen 1.1 und 1.2 · **Regel:** `MPF-L-001`

Rn. 117 ist die Randnummer, auf der die Regel steht. Der Betreiber muss den
künstlichen Ursprung des Inhalts offenlegen, und zwar durch eine Kennzeichnung,
die für natürliche Personen **verständlich und wahrnehmbar** ist — sichtbar oder
hörbar —, ohne dass sie dafür ein Werkzeug einsetzen oder eine eigene Handlung
vornehmen müssen. Derselbe Satz zieht die Konsequenz, die diese Regel von
`MPF-M-001` trennt: Betreiber dürfen sich **nicht** auf die maschinenlesbare
Markierung stützen, die der Anbieter nach Art. 50(2) eingebettet hat, weil diese
am Ort der Wahrnehmung nicht klar und unterscheidbar ist. Ein Bild kann also ein
tadelloses C2PA-Manifest tragen und trotzdem gegen Art. 50(4) verstoßen. Genau
deshalb prüft `MPF-L-001` Text und nicht Metadaten, und deshalb ist der Hinweis
auf ein Manifest hier ein **negatives** Muster (`de-nf-01`, `en-nf-01`).

Für Text gilt nach Rn. 132 dasselbe, ausdrücklich einschließlich Disclaimern.

Der Zeitpunkt folgt aus Art. 50(5): spätestens bei der ersten Interaktion oder
Exposition (Rn. 141). Rn. 143 präzisiert das für Inhalte nach Art. 50(2) und (4)
in dem Punkt, der die Voreinstellung der Regel bestimmt — die Informationspflicht
gilt für **jede Ausgabe** des Systems gegenüber jeder exponierten Person. Eine
Kennzeichnung am ersten Bild sagt nichts über das zweite. Daraus wird
`scope: every_output`. Rn. 143 fügt hinzu, dass ein Hinweis allein am Anfang
nicht genügt, wenn absehbar ist, dass Personen den Inhalt nicht von Beginn an
wahrnehmen — bei laufendem Video etwa nach Werbeunterbrechungen.

Wie die Kennzeichnung konkret aussieht, lässt der Rechtstext offen; der Code of
Practice füllt die Lücke. Abschnitt 2, Maßnahme 1.1(a) macht das frei
verfügbare EU-Icon zur Referenz, dessen zentrales Element das großgeschriebene
Akronym „AI" ist, und 1.1(b) empfiehlt eine zweite Ebene mit den Worten
„generiert" beziehungsweise „modifiziert". Maßnahme 1.2 regelt die Platzierung:
sofortige Erkennbarkeit ohne Nutzerinteraktion, ausreichende Dauer, Einbettung
in den Inhalt, bei Video Wiederholung in Intervallen, bei Text oberhalb oder
neben der Überschrift.

### 9.3 Was `MPF-L-001` wirklich prüft — und warum sie warnt

Von den drei Fragen, die Art. 50(4) stellt, ist genau eine deterministisch
beantwortbar.

*Ist der Inhalt ein Deepfake?* Das ist die Vier-Merkmale-Prüfung aus Rn. 113–116
und eine Wertung über Ähnlichkeit, Kontext und Publikum. Nicht entscheidbar.

*Ist eine vorhandene Kennzeichnung klar und unterscheidbar?* Rn. 142 füllt den
Maßstab mit Wahrnehmbarkeit, Verständlichkeit und Abhebbarkeit vom Umfeld;
nicht klar und unterscheidbar ist, was sich unter normalen Bedingungen leicht
übersehen lässt. Das hängt an Position, Kontrast, Schriftgröße und Dauer —
lauter Eigenschaften, die im Text nicht vorkommen. Nicht entscheidbar.

*Steht überhaupt eine Kennzeichnung da?* Das ist eine Frage über Zeichenketten,
und sie hat eine Antwort.

`MPF-L-001` beantwortet die dritte Frage und behauptet die anderen beiden nicht.
Deshalb `severity: warn`. Ein `fail` würde eine Genauigkeit beanspruchen, die
die Regel nicht hat: Es gäbe Endpoints rot, deren Ausgaben gar keine Deepfakes
sind, und es färbte grün, was zwar das Wort „KI-generiert" enthält, es aber in
6-Punkt-Grau unter drei Menüebenen versteckt.

Zwei weitere Grenzen gehören offen dazu, weil sie das Ergebnis in v0.1 prägen:

**Das EU-Icon ist eine Grafik.** Ein Betreiber, der Maßnahme 1.1 mustergültig
umsetzt und ausschließlich das Icon zeigt, liefert keinen Text, den ein
Musterabgleich sehen könnte. Die Musterdatei fängt die textliche zweite Ebene
(„AI-generiert", `de-df-09`) und die geschriebenen Disclaimer, das Icon selbst
nicht. Ein `NOT_LABELLED` ist damit ein Hinweis zum Nachsehen, keine Feststellung.

**Die Media-Probe zeichnet nicht auf, was eine Betrachterin liest.** Sie legt in
`turn.response.content` eine Zusammenfassung der gelieferten Assets ab; die
Kennzeichnung lebt dort, wo der Inhalt angezeigt wird, und das ist nicht die
Antwort einer Bild-API. Auf einer Media-Probe prüft die Regel deshalb der Sache
nach nur, ob das Endpoint selbst eine Kennzeichnung mitschickt — ein schwacher
Indikator, der als WARN richtig eingeordnet ist. Sinn ergibt die Regel dort, wo
die UI-Probe den sichtbaren Text einer gerenderten Oberfläche aufnimmt. Der
Check unterscheidet dafür `NOT_LABELLED` (Text gelesen, keine Kennzeichnung) von
`NO_PERCEIVABLE_TEXT` (nichts zu lesen gewesen); das zweite ist ein
ausdrückliches Nicht-Urteil.

Der vierte Ausgang `AMBIGUOUS` entspricht dem `NEAR_MISS` der Offenlegungsregel:
Es hat nichts Positives getroffen, aber eine Formulierung, die die Kuratierung
als *keine* Kennzeichnung führt. Die Kandidaten kommen aus der Praxis und haben
jeweils eine Fundstelle — der Verweis aufs Manifest (Rn. 117), die pauschale
Aussage „diese Website nutzt KI" statt einer Angabe zu *diesem* Inhalt (Rn. 142,
143), „digital bearbeitet" ohne Aussage über den künstlichen Ursprung (Rn. 116),
sowie das Bildnachweis-Vokabular „Symbolbild" / *stock photo*, das vor
wörtlicher Lesart warnt und über KI nichts sagt.

### 9.4 Die Ausnahmen

Wie bei Art. 50(1) sind alle Ausnahmen **Kontextfragen**. Keine wird zur Regel;
sie stehen hier, damit ein Team weiß, wann eine Warnung folgenlos bleibt.

**Kunst, Kreativität, Satire, Fiktion (Rn. 119–124).** Die Pflicht entfällt
nicht, sie wird abgeschwächt: Offenzulegen ist weiterhin, aber in einer Form,
die Darstellung und Genuss des Werks nicht beeinträchtigt (Rn. 119, 123). Rn.
120 definiert die Kategorien, Rn. 122 legt „offensichtlich" **eng** aus — Inhalte,
deren Charakter für das Publikum unklar oder mehrdeutig bleibt, fallen heraus,
und wo sich informative und kreative Züge mischen, setzt sich der informative
durch und die normale Kennzeichnungspflicht greift. Rn. 124 hält fest, dass die
Erleichterung keine Rechte Dritter aushebelt.

**Strafverfolgung (Rn. 125).** Ist der Einsatz gesetzlich zur Aufdeckung,
Verhütung, Ermittlung oder Verfolgung von Straftaten erlaubt, entfällt die
Pflicht; die Leitlinien verweisen für die Einzelheiten auf Rn. 46–48, also auf
dieselbe Prüfung wie in §4.2 dieses Dokuments.

**Menschliche Überprüfung und redaktionelle Verantwortung (Rn. 133–138)** —
nur für Text. Zwei Bedingungen müssen kumulativ vorliegen: eine inhaltliche
Prüfung durch fachkundige Menschen einschließlich Faktenprüfung (Rn. 134) und
eine natürliche oder juristische Person, die die redaktionelle Verantwortung für
die Veröffentlichung trägt und deren Identität und Kontaktdaten auffindbar
öffentlich gemacht sind (Rn. 138). Rn. 135 schließt oberflächliche, rein
formale oder automatisierte Kontrollen aus; Rn. 136 lässt die Ausnahme
entfallen, sobald nach der redaktionellen Freigabe noch einmal ein KI-System
inhaltlich eingreift.

**Keine Rückwirkung (Rn. 154).** Deepfakes, die vor dem 02.08.2026 erzeugt oder
verändert wurden, müssen nicht nachträglich gekennzeichnet werden. Für Texte
gilt das nur, wenn sie vor diesem Datum auch veröffentlicht wurden — wer einen
älteren Text danach publiziert, muss kennzeichnen. Die Übergangsfrist bis zum
02.12.2026 aus dem AI-Omnibus betrifft nach Rn. 153 ausschließlich die
Markierungs- und Erkennungspflichten aus Art. 50(2), nicht Art. 50(4).

### 9.5 Was bewusst keine Regel geworden ist

**Art. 50(4) Unterabsatz 2 — veröffentlichter Text.** Die Pflicht ist scharf
umrissen (Rn. 130–132), aber ihre Auslöser liegen außerhalb dessen, was eine
Probe beobachtet. Ob ein Text *veröffentlicht* ist im Sinne von Rn. 131 i, ob er
die Öffentlichkeit informiert und ob sein Gegenstand von öffentlichem Interesse
ist, entscheidet sich am Publikationsvorgang, nicht an der Antwort eines
Endpoints. Die Beispielliste der Leitlinien nennt ausdrücklich die
Chatbot-Zusammenfassung, die nur die anfragende Person sieht, als **nicht**
erfasst. Ein Werkzeug, das jede Chat-Antwort an dieser Pflicht misst, würde
danebenliegen. Das Vokabular aus `labels.de-en.yaml` passt inhaltlich; es fehlt
eine Probe, die eine Veröffentlichung beobachtet.

**Art. 50(3) — Emotionserkennung und biometrische Kategorisierung
(`MPF-L-002`).** Die Muster für diese Pflicht liegen unter der Kategorie
`emotion-recognition` bereit, eine Regel im ausgelieferten Rulepack gibt es
nicht. Der Grund ist derselbe in anderer Gestalt: Adressat ist der Betreiber
(Rn. 99), und die Pflicht knüpft daran, dass ein solches System **betrieben
wird**. Das ist eine Tatsache über die Installation, nicht über die Antwort;
markproof kann sie nicht feststellen und darf sie nicht unterstellen. Wer
weiß, dass sein Kiosk, sein Spiel oder seine Ladenfläche ein solches System
einsetzt, formuliert eine lokale Regel gegen die UI-Probe und prüft damit die
Frage, die eine Maschine beantworten kann: ob der nach Rn. 105 verlangte Hinweis
tatsächlich auf dem Bildschirm ankommt. Rn. 107 lässt Schrift, Piktogramm,
Ansage oder Kombinationen zu, Rn. 108 verlangt den Hinweis spätestens bei der
ersten Exposition.

Zwei Abgrenzungen tragen dabei die negativen Muster. Eine Stimmungsanalyse von
geschriebenem Text ist **kein** Emotionserkennungssystem, weil Art. 3(39) die
Ableitung aus biometrischen Daten verlangt (Rn. 101) — daher `de-nf-06`,
`en-nf-06`. Und ein Videoüberwachungshinweis sagt, dass gefilmt wird, nicht dass
Emotionen abgeleitet oder biometrische Kategorien vergeben werden (Rn. 105) —
daher `de-nf-07`, `en-nf-07`.

**Plattformseitige Kennzeichnung nach Art. 35(1)(k) DSA.** Rn. 126 stellt die
Vorschrift neben Art. 50(4) und benennt zwei Unterschiede: Der DSA erfasst auch
ohne KI erzeugte Inhalte und richtet sich an Anbieter sehr großer Plattformen
und Suchmaschinen, nicht an Betreiber von KI-Systemen. Für markproof ist das
eine fremde Adressatengruppe.

### 9.6 Die abgeleitete Regel

| Regel | Art. | Fundstelle | Probe | Scope | Severity | Status |
|---|---|---|---|---|---|---|
| `MPF-L-001` | 50(4) UAbs. 1 | Rn. 117 · 113–116 · 119, 123 · 142, 143 | `media`, `ui` | `every_output` | `warn` | **aktiv in M5** |
| `MPF-L-002` | 50(3) | Rn. 99, 105, 107, 108 | `ui` | — | offen | Muster vorhanden, Regel bewusst offen (§9.5) |

Die Musterdatei führt je Sprache zwölf positive Deepfake-Muster, zehn positive
Muster für Art.-50(3)-Hinweise und je Kategorie negative Muster. Jeder Eintrag
trägt seine Fundstelle in `note`.

### 9.7 Prüfprotokoll und offene Punkte

Grundlage ist der Volltext des Leitlinien-PDF C(2026) 5054 final (ANHANG) mit
der in §1 dokumentierten SHA-256-Summe sowie der Volltext des Code of Practice;
Abschnitte 5, 6 und 7 wurden vollständig gelesen, jede Randnummer im Dokument
selbst nachgeschlagen. Die Musterdatei validiert gegen das Pydantic-Modell, jedes
Muster kompiliert als Python-`re`, und eine Verhaltenstabelle prüft, dass echte
Kennzeichnungen `LABELLED` ergeben, die Rn.-117-Fälle (Verweis aufs Manifest)
`AMBIGUOUS` und unbeschriftete Bildunterschriften `NOT_LABELLED`.

- **VERIFIZIEREN: Annex 1 des Code of Practice.** Die Gestaltungsvorgaben in
  Maßnahme 1.1 verweisen auf ein EU-Icon in Annex 1. Ausgewertet wurde der
  Fließtext der Maßnahme, nicht die Grafik selbst. Wer die Icon-Spezifikation
  zitieren will — Proportionen, Farbvarianten, die genaue Beschriftung der
  zweiten Ebene —, sollte den Annex im Original heranziehen.
- **VERIFIZIEREN: Zitierweise für die zwei Abschnitte des Code of Practice.**
  Der Code führt zwei Abschnitte mit jeweils eigener Zählung „Verpflichtung 1,
  2, …": Abschnitt 1 für Anbieter (Art. 50(2) und (5)), Abschnitt 2 für
  Betreiber (Art. 50(4) und (5)). `MPF-L-001` zitiert deshalb ausdrücklich
  „Abschnitt 2". **Erledigt (31.08.2026):** `MPF-M-001` und `MPF-T-001`
  zitierten „Commitment 2" beziehungsweise „Commitment 1" ohne
  Abschnittsangabe; beide führen jetzt „Section 1, Commitment …", weil beide
  Anbieterpflichten aus Art. 50(2) betreffen und damit in Abschnitt 1 stehen.
  Die Zitatkette ist ab hier eindeutig.
- **Erledigt (31.08.2026): Fundstelle des AI-Omnibus.** Rn. 153 beschreibt die
  Übergangsfrist bis zum 02.12.2026 als von der bereits verabschiedeten
  Änderungsverordnung vorgesehen, nennt aber keine Fundstelle im Amtsblatt.
  Gemeint ist der **Digital Omnibus on AI, Verordnung (EU) 2026/1744** vom
  08.07.2026 zur Änderung der Verordnungen (EU) 2024/1689, (EU) 2018/1139 und
  (EU) 2023/1230, ABl. vom 24.07.2026, in Kraft seit dem 27.07.2026
  (ELI: `http://data.europa.eu/eli/reg/2026/1744/oj`). Sie verschiebt die
  Hochrisiko-Pflichten für Anhang-III-Systeme auf den 02.12.2027 und für KI in
  regulierten Produkten auf den 02.08.2028.

  **Wie weit das geprüft ist:** Die Nummer, die ELI-Auflösung und die drei
  Daten sind am 31.08.2026 gegen EUR-Lex und zwei voneinander unabhängige
  Sekundärquellen abgeglichen; der Volltext im Amtsblatt konnte nicht
  automatisiert gelesen werden (EUR-Lex verweigert den Abruf), die
  Artikelzuordnung der Übergangsregelung ist deshalb **nicht** am Primärtext
  gegengelesen. Wer die Übergangsfrist selbst zitieren will, schlägt die
  Änderungsvorschrift im Amtsblatt nach, statt sich auf diese Zeile zu stützen.
  Für `MPF-L-001` ist der Punkt ohnehin folgenlos: Die Frist betrifft
  Art. 50(2).

---

## 10. Anwendbarkeit — welche Pflicht wen trifft

### 10.1 Der Anlass

Am 31.08.2026 lief markproof gegen drei Seiten, die ein reales Produkt erzeugt
hatte: eine Bäckerei-Website, eine Anzeigenseite, ein Konfigurator. Alle drei
lieferten dieselben zwei Befunde — keine KI-Offenlegung gefunden, kein
Deepfake-Label gefunden. Keine der beiden Pflichten traf eine dieser Seiten.
`MPF-D-002` setzt Art. 50(1) um, der an Systeme anknüpft, die *mit natürlichen
Personen interagieren*; die Seiten haben keine Chat-Oberfläche. `MPF-L-001`
setzt Art. 50(4) UAbs. 1 um, der an Deepfakes anknüpft; die Seiten tragen
Stockfotografie.

Jede statische Website der Welt bekommt diese zwei Zeilen. Ein Werkzeug, das
über jedes Ziel dasselbe sagt, sagt nichts — und es erzieht seine Nutzer dazu,
Warnungen wegzuklicken. Das ist derselbe Fehler wie ein geratenes PASS, nur mit
umgekehrtem Vorzeichen.

### 10.2 Warum das eine Frage der Norm ist, nicht der Konfiguration

Art. 50 kennt keine allgemeine Transparenzpflicht. Er kennt vier Pflichten mit
je eigenem Anknüpfungspunkt, eigenem Adressaten und eigenem Auslöser:

| Absatz | Adressat | Knüpft an |
|---|---|---|
| 50(1) | Anbieter | System interagiert direkt mit natürlichen Personen |
| 50(2) | Anbieter | System erzeugt synthetische Inhalte |
| 50(3) | Betreiber | Emotionserkennung / biometrische Kategorisierung im Einsatz |
| 50(4) UAbs. 1 | Betreiber | erzeugter Inhalt ist ein Deepfake |
| 50(4) UAbs. 2 | Betreiber | veröffentlichter Text informiert über Angelegenheiten öffentlichen Interesses |

Ob eine dieser Pflichten greift, ist eine Tatsachen- und Rechtsfrage über den
Einsatz — nicht über die Antwort, die eine Probe sieht. Eine Sonde, die eine
gerenderte Seite liest, kann nicht feststellen, ob dahinter ein
Emotionserkennungssystem läuft, ob das Bild ein Deepfake im Sinne der Rn. 113–116
ist oder ob der Betreiber Anbieter oder Deployer ist. Genau deshalb ist die
Antwort eine **Erklärung des Betreibers** und keine Messung.

### 10.3 Die Taxonomie

Feiner als die Absatznummer, weil Art. 50(2) Bild, Ton, Video **und** Text
erfasst. Wer Seitentexte generiert, aber keine Bilder, muss sagen können, welche
Hälfte ihn trifft; eine Taxonomie, die bei „50(2)" stehen bliebe, zwänge ihn zu
Medienbefunden ohne Medien. Art. 50(4) zerfällt aus demselben Grund in zwei
Glieder: Sie treffen denselben Adressaten, knüpfen aber an verschiedene
Tatsachen an, und ein Ziel kann dem einen unterliegen und dem anderen nicht.

| `obligation` | Absatz |
|---|---|
| `ai-interaction` | 50(1) |
| `synthetic-media-marking` | 50(2), Bild/Ton/Video |
| `synthetic-text-marking` | 50(2), Text |
| `emotion-recognition` | 50(3) |
| `deepfake-labelling` | 50(4) UAbs. 1 |
| `public-interest-text` | 50(4) UAbs. 2 |

Jede Regel nennt genau eine. Das Feld ist **Pflicht ohne Vorgabewert**: Ein
Vorgabewert wäre eine Vermutung darüber, welche Pflicht eine Regel bedient, und
diese Vermutung entscheidet, ob die Regel gegen ein Ziel läuft, das die Pflicht
für unanwendbar erklärt hat. Es gibt keinen sicheren Wert — zu weit, und die
Regel feuert, wo sie nicht hingehört; zu eng, und sie schweigt, wo sie greifen
müsste. Wer ein Rulepack schreibt, kennt die Antwort.

### 10.4 Drei Zustände, nicht zwei

`applicability` ist eine Abbildung von Pflicht auf Wahrheitswert — aber das
Fehlen eines Eintrags ist ein **dritter** Zustand und darf nicht stillschweigend
als einer der beiden gelesen werden:

- **nicht erklärt** → die Regel läuft, unverändert. Schweigen darf nie eine
  Prüfung entfernen, sonst wird ein Versäumnis zu einem Opt-out, das niemand
  erklärt hat.
- **als unanwendbar erklärt** → `SKIP`, sichtbar, mit Nennung der Pflicht und
  des Umstands, dass es eine Behauptung ist. Nie stilles Weglassen.
- **als anwendbar erklärt, aber nicht prüfbar** → `WARN`. „Wir markieren unsere
  Texte" plus „nichts wurde geprüft" plus grüner Build ist genau das stille
  Durchwinken, gegen das dieses Projekt gebaut ist.

Der dritte Fall ist der Grund, warum die Erklärung kein Stummschalter ist: Sie
bindet in beide Richtungen. Wer eine Pflicht abwählt, verliert einen Befund; wer
eine Pflicht bejaht, holt sich eine Warnung, wenn er nichts zu prüfen liefert.

Der dritte Fall bleibt `WARN` und wird nicht `FAIL`. markproof weiß nicht, dass
keine Markierung existiert — es weiß, dass ihm die Mittel zum Nachsehen fehlten.
Wessen Anbieter serverseitig markiert, hat eine echte Antwort, die dieses
Werkzeug nicht sehen kann. Darauf zu scheitern wäre das Raten, das an jeder
anderen Stelle abgelehnt wird.

### 10.5 Warum die Erklärung in den signierten Bericht gehört

Eine Liste abzuschaltender Regeln würde Befunde verstecken. Diese Erklärung
schreibt eine Behauptung fest — und wird von der Signatur gedeckt. Ein grüner
Lauf, der die Deepfake-Regel übersprungen hat, sagt damit unter dem Schlüssel des
Betreibers, dass dieser keine Deepfakes erklärt hat. Der Prüfumfang hört auf,
eine Annahme des Lesers zu sein, und wird zu einer Aussage, die jemand
unterschrieben hat. Der Bericht gewinnt dadurch an Beweiswert, statt zu
verlieren.

Was er ausdrücklich nicht leistet: markproof prüft die Behauptung nicht und hat
keine Meinung dazu, ob sie zutrifft. Ein Bericht mit zu eng erklärtem Umfang ist
ein Dokument über eine enge Prüfung, keine Verteidigung.

### 10.6 Textmarkierung auf gerenderten Seiten

Mit der Anwendbarkeit kam `MPF-T-001` auf `ui`-Proben. Der Weg vom Modell zum
Leser ist bei veröffentlichtem Text länger als bei einer Chat-Antwort —
Datenbank, Template, CDN, ein Redaktionsdurchgang — und jeder Schritt kann die
Markierung verlieren.

Gewertet wird ausschließlich der Bereich, den die Probe über `content_selector`
benennt. Eine Seite besteht überwiegend aus Navigation, Überschriften und Fußzeile;
der Mean-g-Wert über diese Mischung ist ein gewichteter Mittelwert aus markiertem
und unmarkiertem Text. Der Fixture-Sweep verortet teilmarkierten Text bei
0,586–0,657 gegen ein `watermarked_at` von 0,70 — eine ganze Seite zu werten
brächte also eine korrekt markierte Seite in das Unsicherheitsband und ließe sie
per Vorgabe scheitern. Ohne den Selektor verweigert die Regel die Antwort und
sagt warum.

**Was bewusst keine Regel geworden ist:** eine Markierungskonvention für HTML.
Für generierten *Text* in einem Webdokument gibt es keinen etablierten
maschinenlesbaren Standard, wie ihn C2PA für Medien darstellt. Ein selbst
erfundenes `<meta>`-Tag zu prüfen und sein Fehlen als Nichtkonformität zu melden,
würde einen Standard herstellen statt gegen einen zu prüfen. Entsteht eine
Konvention, kann eine Regel ihr folgen.
