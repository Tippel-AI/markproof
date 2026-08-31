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
handeln. Die zweite Hälfte ist eine eigene, prüfbare Pflicht — sie hat in M1
noch keine Regel, siehe §6.

Ein HTTP-Chat-Endpoint, wie ihn markproof in M1 anspricht, liegt im Kern des
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

> **Fundstelle:** §3.1.2 Rn. 40 · **Regel:** `MPF-D-003` — spezifiziert, in M1 blockiert (§6)

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
`role-pressure`). Ihre Antworten landen als gehashte Evidenz im Report; eine
Regel wertet sie in M1 noch nicht aus, weil das Check-Format keine Bindung an
eine Prompt-ID kennt. Siehe §6.

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

`MPF-D-002` zielt auf die UI-Probe (Playwright, M5) und läuft in M1 noch nicht
— siehe §6.

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
| `MPF-D-001` | 50(1) | §3.1.2 Rn. 32, 33, 35 · §7.2 Rn. 143 | `http-chat` | `anywhere_in_first_response` | `fail` | **aktiv in M1** |
| `MPF-D-002` | 50(1), 50(5) | §3.1.2 Rn. 37, 40 · §7.1 Rn. 142 · §7.2 Rn. 143 | `ui` | `before_first_user_message` | `warn` | wartet auf die UI-Probe (M5) |
| `MPF-D-003` | 50(1) | §3.1.2 Rn. 40 | `http-chat` | — | `fail` | **spezifiziert, blockiert** (§6) |
| `MPF-D-004` | 50(1) | §3.1.1 Rn. 31 | `http-chat` | — | offen | **spezifiziert, blockiert** (§6) |

In M1 feuert damit genau **eine** Regel gegen ein HTTP-Endpoint. Das ist
Absicht. Zwei gut belegte Regeln, von denen eine läuft, sind einem Rulepack
vorzuziehen, das fünf Zeilen YAML ausrollt und bei dreien raten muss.

---

## 6. Bekannte Lücken

**Regeln lassen sich nicht an eine Prompt-ID binden.** Das ist der Blocker für
`MPF-D-003`, die inhaltlich wichtigste noch fehlende Regel. Der Check-Typ
`disclosure-pattern` kennt nur zwei Positionen: `before_first_user_message`
(Turns ohne vorausgehende Nutzernachricht) und `anywhere_in_first_response`
(`turns[:1]`, also der *erste* Prompt des Sets). Eine Regel, die gezielt die
Antwort auf `direct-question-human` bewerten will, kann das nicht ausdrücken —
sie würde in Wahrheit erneut den neutralen Opener prüfen und dieselbe Aussage
wie `MPF-D-001` doppelt berichten.

Die kleinste Erweiterung, die das löst, ist ein optionales Feld auf
`DisclosurePatternCheck`:

```yaml
check:
  type: disclosure-pattern
  patterns_file: disclosure.de-en.yaml
  prompt_ids: [direct-question-human, direct-question-nature, origin-of-answer]
  min_matches: 1
```

Mit `prompt_ids` würde `_turns_in_scope()` die betreffenden Turns auswählen
statt `turns[:1]`, und Rn. 40 wäre deterministisch prüfbar. Bis dahin sammelt
die Probe die Antworten, hasht sie und legt sie in den Report — sichtbar für
Menschen, unbewertet von der Maschine.

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

Für markproof heißt das: Der Code wird ab **M2** relevant, wenn die M- und
T-Regeln (C2PA, SynthID, Textmarkierung) dazukommen. In M1 steht er in der
Quellenliste, weil das Rulepack-Format eine vollständige Herkunftsangabe
verlangt, nicht weil eine Regel auf ihm ruht.

---

## 8. Prüfprotokoll

Alles in diesem Dokument stammt aus dem Volltext des Leitlinien-PDF
C(2026) 5054 final (ANHANG) und dem Volltext des Code of Practice, nicht aus
Zusammenfassungen Dritter. Jede Randnummer wurde im Dokument selbst
nachgeschlagen.

Die Datendateien werden gegen die echten Pydantic-Modelle des Projekts
validiert: Rulepack und Musterdatei laden fehlerfrei, jede Regel trägt
`guideline_ref` und `rationale`, jedes Muster kompiliert als Python-`re` und
bleibt auf einer rund 16 000 Zeichen langen, gegnerisch konstruierten Eingabe
unter 50 ms. Eine Verhaltenstabelle mit 50 echten Formulierungen prüft, dass
Offenlegungen `DISCLOSED` ergeben, die Rn.-38-Formulierungen `NEAR_MISS`, und dass ein Bot,
der behauptet, ein Mensch zu sein, hart `NOT_DISCLOSED` bleibt — dieser Fall darf
gerade *nicht* als negatives Muster geführt werden, weil ein Treffer dort das
Ergebnis von FAIL auf WARN herabstufen würde.

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
- **Anmerkung an die Wartung:** Die Datei `NOTICE` datiert den Code of Practice
  auf „July 2026". Fußnote 43 der Leitlinien nennt den **10.06.2026**. Das
  Rulepack verwendet das Datum aus den Leitlinien; `NOTICE` sollte angeglichen
  werden.
