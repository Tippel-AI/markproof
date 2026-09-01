<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Launch-Audit — Compliance-Gate vor 0.1.0

> **Superseded, 1 September 2026.** This is the pre-0.1.0 self-audit and it is kept
> as a record rather than maintained. A second, adversarial audit — eight reviewers,
> each attacked by an independent skeptic — ran after it and found things this one
> did not, including a credential leak through redirect handling and a CI job named
> after a check it did not perform. Where the two disagree, this one is older.
>
> Kept rather than deleted because deleting a superseded record is the habit this
> project argues against everywhere else. Written in German, like
> `RULES_SOURCES.md`.

**Prüfdatum:** 31.08.2026 · **Stand:** `a6e86cf` (M5) plus uncommittete
Arbeitskopie von `README.md` · **Prüfer:** Audit-Durchlauf gegen den
tatsächlichen Repo-Inhalt, nicht gegen die Dokumentation über das Repo.

Geprüft wurde jede der sieben Auflagen einzeln am Dateiinhalt. Alle Befunde
unten sind am Repo verifiziert; wo ein Befund durch Ausführen des Codes belegt
ist, steht der Befehl dabei. Die Testsuite lief im Rahmen der Prüfung mit
`320 passed, 1 skipped` (übersprungen: `test_pdf.py:453`, braucht Pango/cairo).

**Vorbemerkung zur Arbeitskopie.** `README.md` ist gegenüber `main` geändert
(30 Zeilen +, 22 −) und noch nicht committet. Die Änderung korrigiert echte
Fehler — `markproof check` → `markproof run`, `synthid_config` →
`watermark_config`, `verify` → `verify-report`, die Statuszeile. Geprüft wurde
die Arbeitskopie, weil sie den Launch-Text darstellt. **Der Commit dieser
Änderung ist selbst ein Release-Blocker:** auf `main` steht derzeit ein README,
dessen Quickstart-Befehl nicht existiert.

---

## 1. Normtexte — **BESTANDEN**

### Geprüft

- Volltextdurchlauf über `src/markproof/rulepacks/`, `src/markproof/patterns/`,
  `src/markproof/prompts/`, `docs/` sowie sämtliche Modul-Docstrings.
- Regex-Scan über alle 112 Textdateien aus `git ls-files` nach Passagen in
  Anführungszeichen (`" " „ " « »`) ab 12 Wörtern.
- Extraktion und Längenmessung jedes YAML-Prosablocks (`note:`, `rationale:`,
  `purpose:`, `description:`) in Rulepack und Musterdateien — 104 Blöcke.
- Alle Markdown-Blockquotes (`grep -rn "^\s*>" --include="*.md"`).
- Gezielter Scan nach Normungs-Textmarkern:
  `grep -rniE "\b(BSI|CEN|CENELEC|prEN [0-9]|EN 1[0-9]{4}|DIN |ISO/IEC|JTC 21)\b"`.

### Ergebnis

Keine wörtliche Übernahme aus den Kommissions-Leitlinien, dem Code of Practice,
prEN/CEN-Texten oder BSI-Katalogen. Der Normungs-Scan liefert genau einen
Treffer, und der ist die Verneinung selbst: `NOTICE:55`, „No CEN, CENELEC, DIN
or prEN standard text is used or embedded in this project." Die Aussage hält.

Die längste fremdstämmige wörtliche Passage im Repo ist
`docs/RULES_SOURCES.md` §4.1: *„reasonably well-informed, observant and
circumspect"* — sechs Wörter, in Anführungszeichen, mit Fundstelle (Art. 50(1),
Rn. 43). Weit unter der 25-Wort-Schwelle und obendrein Verordnungstext.

Die längsten Prosablöcke sind durchweg Analyse in der Stimme des Autors, keine
Übernahme: der 198-Wörter-Block ist die `rationale` von `MPF-L-001` und
begründet, warum die Regel `warn` und nicht `fail` ist — ein Satz, der in keiner
Quelle stehen kann.

**Eine Stelle zur Kenntnis, ausdrücklich keine Auflage.** Der erste Satz der
`rationale` von `MPF-M-001`
(`src/markproof/rulepacks/art50-eu-2026.07.yaml:127-129`) folgt dem
Gesetzeswortlaut von Art. 50(2) enger als jede andere Passage im Repo
(~28 Wörter, „Providers of systems generating synthetic image, audio or video
content must mark their output in a machine-readable way and make it detectable
as artificially generated or manipulated"). Das ist unbedenklich: Es ist
Verordnungstext, nicht Leitlinientext, und `NOTICE:50-51` hält für die
Verordnung zutreffend fest, dass sie frei reproduzierbar ist. Der Satz ist
zudem eine Umstellung, keine Kopie. Aufgeführt, damit die Prüfung
nachvollziehbar bleibt und die Stelle bei einer künftigen Erweiterung des
Rulepacks bewusst bleibt.

---

## 2. Attribution — **AUFLAGE** (eine davon substanziell)

### Geprüft

- `NOTICE` vollständig gegen CC-BY-4.0 §3(a)(1) und gegen `LICENSE-DATA`.
- `NOTICE` §4 abgeglichen gegen `[project.dependencies]` und
  `[project.optional-dependencies]` in `pyproject.toml`.
- Existenz der in `NOTICE` und `ci.yml` referenzierten Dateien via `git ls-files`.
- Ausführung von `build_report()` und `render_summary()` gegen das
  ausgelieferte Rulepack, um zu prüfen, ob die Attribution im Produkt ankommt.

### A2.1 — Die CC-BY-Attribution erreicht den erzeugten Report nicht *(substanziell)*

Das ist der wichtigste Befund dieses Audits, weil er nicht die Dokumentation
betrifft, sondern das Artefakt, das der Nutzer weitergibt.

`src/markproof/report/model.py:156` baut den Rulepack-Block des Reports so:

```python
rulepack={"id": rulepack.rulepack, "version": rulepack.version},
```

`license` und `attribution` fehlen. Verifiziert durch Ausführung:

```
rulepack block: {"id": "art50-eu-2026.07", "version": "1.0.0"}
"attribution" in report.json -> False
```

Die Folge zieht sich durch alle drei Ausgabeformate:

- **`report.json`** trägt keine Attributionszeile — wohl aber pro Finding die
  Felder `title`, `article` und `guideline_ref`, die wörtlich aus dem
  CC-BY-lizenzierten Rulepack stammen. Der Report ist damit abgeleitetes
  Material, das ohne den Credit weitergegeben wird, den das Projekt selbst
  vorgesehen hat.
- **`summary.md`** ebenso — geprüft über `render_summary()`, die Ausgabe nennt
  weder „attribution" noch „CC-BY" noch „Commission".
- **Beide PDF-Renderer** lesen die Attribution über
  `pdf_reportlab.py:382` aus den Schlüsseln `rulepack_attribution` /
  `attribution` / `rulepack.attribution`. Keiner davon existiert im echten
  Report, `report_view(...).attribution` ist `''`, und die Bedingung in
  `pdf_reportlab.py:803` feuert nie. Der Docstring derselben Datei
  (`pdf_reportlab.py:50-51`) sagt: „CC-BY attribution line for the shipped
  rulepacks (Auflage H1). **Printed** […]". Sie wird nicht gedruckt.

Warum das durchgerutscht ist, ist der eigentlich lehrreiche Teil:
`tests/test_pdf.py:112` reicht dem Renderer ein handgebautes Dict mit dem
Schlüssel `"attribution"`. Getestet ist also, dass der Renderer eine
Attribution *drucken kann* — nicht, dass die Pipeline eine *liefert*.
`tests/test_integration.py:69` prüft nur, dass das Rulepack-Objekt eine hat.
Zwischen beiden klafft genau die Lücke.

**Vorgeschlagene Fassung**, `src/markproof/report/model.py:156`:

```python
        rulepack={
            "id": rulepack.rulepack,
            "version": rulepack.version,
            "license": rulepack.license,
            "attribution": " ".join(rulepack.attribution.split()),
        },
```

(Whitespace-Normalisierung, weil der YAML-Folded-Block Zeilenumbrüche trägt und
der Report byte-identisch reproduzierbar bleiben muss.)

Dazu eine Zeile in `src/markproof/report/summary.py`, vor dem
Disclaimer-Absatz (nach Zeile 133):

> Rulepack `art50-eu-2026.07` v1.0.0 is derived from CC-BY-4.0 material
> published by the European Commission; see the `attribution` field of this
> report.

Und ein Test, der die Lücke schließt: `report.json` eines echten Laufs muss
`rulepack.attribution` enthalten, und `report_view()` auf demselben Dict muss
eine nichtleere Attribution liefern.

### A2.2 — `NOTICE` erfüllt CC-BY-4.0 §3(a)(1) nicht vollständig

Vorhanden und in Ordnung: Urheber („European Commission", `NOTICE:38`), Titel
(`:38-40`), Datum (`:40`), Lizenzangabe mit Verweis auf `LICENSE-DATA` (`:9`,
`:43`), URI zum Werk (`:42`), Nicht-Endorsement-Klausel (`:53-54`, von
§2(a)(6) verlangt).

Es fehlen drei Elemente:

1. **Copyright-Vermerk** (§3(a)(1)(A)(ii)). Für Kommissionsmaterial ist die
   Formel aus Beschluss 2011/833/EU vorgesehen: `© European Union, 2026`.
2. **Änderungshinweis** (§3(a)(1)(B)). „derived from, and paraphrase"
   (`NOTICE:33`) beschreibt die Ableitung, sagt aber nicht ausdrücklich, *dass*
   und *wie* verändert wurde.
3. **Verweis auf den Gewährleistungsausschluss** (§3(a)(1)(A)(iv)).

**Vorgeschlagene Fassung**, einzufügen in `NOTICE` nach Zeile 48:

```
  Copyright: © European Union, 2024-2026. Reused under CC BY 4.0 pursuant to
  Commission Decision 2011/833/EU.

  Modifications: the obligations stated in these works have been paraphrased
  into machine-readable rules and curated matching patterns. No normative text
  is reproduced; rules cite the section and paragraph they rest on. The
  selection of which obligations became a rule, and the wording of every rule,
  pattern and rationale, are ours. Earlier modifications: none — these files
  are derived directly from the sources named above.

  The licensed material is provided by the licensor as-is and without
  warranties of any kind; see Section 5 of LICENSE-DATA.
```

### A2.3 — Datumswiderspruch beim Code of Practice

`NOTICE:45` datiert den Code of Practice auf „July 2026". Das Rulepack
(`art50-eu-2026.07.yaml:41`, `date: "2026-06-10"`) und
`docs/RULES_SOURCES.md` §1 nennen den **10.06.2026**, gestützt auf Fußnote 43
der Leitlinien. Das Repo weiß das bereits: `docs/RULES_SOURCES.md` §8 führt
unter „Anmerkung an die Wartung" genau diesen Punkt.

**Fix:** `NOTICE:45` → `AI-generated Content", 10 June 2026.`

### A2.4 — `NOTICE` verweist auf eine Datei, die es nicht gibt

`NOTICE:84-85`: „The complete, generated dependency license inventory lives in
**THIRD_PARTY_LICENSES.md** and is refreshed per release."

`git ls-files` kennt die Datei nicht. `ci.yml:11` nennt zusätzlich eine geplante
`licenses.yml`, die sie erzeugen soll — die ebenfalls nicht existiert. Das
`NOTICE` verspricht damit ein Release-Artefakt, das der Release nicht erzeugen
kann. Für ein Compliance-Werkzeug ist ein nicht eingelöstes Attributionsversprechen
die unangenehmste Sorte Fehler.

**Zwei zulässige Auflösungen**, beide vor dem Release:

- *(a)* `THIRD_PARTY_LICENSES.md` erzeugen (`uv pip list` +
  `pip-licenses`/`reuse`, inklusive transitiver Abhängigkeiten — `certifi` ist
  MPL-2.0 und taucht in der jetzigen Liste nirgends auf) und den
  Generierungsschritt in die Release-Checkliste aufnehmen; oder
- *(b)* `NOTICE:83-85` auf das reduzieren, was zutrifft:

  > The list below covers the direct dependencies. markproof vendors and
  > redistributes none of them — they are installed from PyPI by pip/uv — so
  > their own NOTICE files travel with those packages, not with this one.

### A2.5 — Abgleich gegen `pyproject.toml`: im Wesentlichen sauber

Alle sieben Runtime-Abhängigkeiten (`httpx`, `pydantic`, `typer`,
`ruamel.yaml`, `rfc8785`, `cryptography`, `c2pa-python`) und alle Extras
(`transformers`, `torch`, `reportlab`, `weasyprint`, `playwright`) stehen in
`NOTICE` §4 mit zutreffender Lizenzangabe. Einzige Lücke: **`pytest-cov`**
(`pyproject.toml:106`) fehlt in der Dev-Tool-Liste `NOTICE:108-111`.

Die Apache-2.0-NOTICE-Weitergabepflicht (§4(d)) greift korrekt **nicht**: das
Wheel enthält ausschließlich `src/markproof` (`pyproject.toml:128`), nichts ist
vendored. `NOTICE:82-85` stellt das richtig dar.

---

## 3. Fremde Binaries, Modelle, Zertifikate — **BESTANDEN**

### Geprüft

- `git ls-files` nach Dateityp: 134 Dateien, davon 22 binär (10 PNG, 4 JPG,
  4 MP4, 4 WAV). Jede einzeln mit `file` typisiert.
- Zertifikate aus `tests/fixtures/media/generate.py` extrahiert und mit
  `openssl x509 -subject -issuer -dates -fingerprint` geprüft.
- Die tatsächlich eingebetteten Zertifikate aus `signed-valid.png` per
  String-Extraktion gegengelesen.
- SHA-256 der drei Demo-PNG gegen die Tabelle in
  `examples/demo-bot/media/README.md` verglichen.
- `tests/fixtures/media/MANIFEST.json` strukturell gelesen (19 Einträge).

### Ergebnis

**Keine fremde Binärdatei, kein Modell, kein Container-Image, kein
Drittzertifikat.** Es gibt keine Wheels, keine `.so`/`.dylib`, keine
Modellgewichte. Der `Dockerfile` unter `examples/demo-bot/` ist ein Bauplan,
kein Image. `transformers`/`torch` laden zur Laufzeit, Playwright-Browser
ebenso — beides in `NOTICE:100-107` korrekt festgehalten.

**Testzertifikate: Eigenproduktion, verifiziert.**

```
subject=C = DE, O = markproof test fixtures, OU = NOT FOR PRODUCTION, CN = markproof test signer
issuer =C = DE, O = markproof test fixtures, OU = NOT FOR PRODUCTION, CN = markproof test root CA
notBefore=Jan 1 00:00:00 2026 GMT   notAfter=Jan 1 00:00:00 2036 GMT

subject=C = DE, O = markproof test fixtures, OU = NOT FOR PRODUCTION, CN = markproof test root CA
issuer =C = DE, O = markproof test fixtures, OU = NOT FOR PRODUCTION, CN = markproof test root CA
```

Die Wurzel ist self-signed (Subject == Issuer), liegt in keinem Trust Store, und
die Kette taucht unverändert in den signierten Fixtures wieder auf — die
String-Extraktion aus `signed-valid.png` liefert `markproof test fixtures`,
`NOT FOR PRODUCTION`, `markproof test root CA` und den Claim-Generator
`markproof-fixtures`.

**Kennzeichnung als Testmaterial: unmissverständlich, vierfach redundant.**

| Ort | Kennzeichnung |
|---|---|
| Zertifikat selbst | `OU = NOT FOR PRODUCTION` — reist mit jeder Kopie mit |
| `generate.py:123` | `# NOT A SECRET. Test-only ECDSA P-256 private key.` |
| `MANIFEST.json` → `signing.warning` | „TEST MATERIAL ONLY. This CA is self-signed, is in no trust store, and must never be trusted outside these tests." |
| `tests/fixtures/media/README.md:39-56` | eigener Abschnitt „Test signing material — NOT FOR PRODUCTION" |

Das ist mehr als ausreichend. Besonders gut: Die Kennzeichnung sitzt im
Zertifikatssubjekt, also an der einzigen Stelle, die auch dann noch da ist, wenn
jemand nur die PEM-Blöcke herauskopiert.

**Demo-Medien:** Die drei PNG unter `examples/demo-bot/media/` sind
Eigenproduktion (`make_fixtures.py`, handgeschriebener PNG-Encoder und
5×7-Bitmap-Font, kein Pillow, kein ffmpeg). Die Hashes stimmen mit der
dokumentierten Tabelle überein:

```
87bce4d4594f6cf1…  demo-signed.png
569a35540d1f61e9…  demo-unsigned.png
94b4d149f9287694…  demo-wrongtype.png
```

Die Signierkette dort ist ephemer, wird pro Lauf neu erzeugt und nie auf Platte
geschrieben — noch sauberer als die Test-Fixtures.

### Hinweis, keine Auflage: der Testschlüssel geht mit dem sdist an PyPI

`pyproject.toml:133` nimmt `/tests` in das sdist auf. Damit landet der
ECDSA-P-256-Privatschlüssel aus `tests/fixtures/media/generate.py:124-129` im
Release-Tarball auf PyPI. Inhaltlich harmlos — der Schlüssel ist per
Konstruktion wertlos —, aber die Secret-Scanner von PyPI und GitHub sowie
Distro-Packager (Debian/Fedora prüfen sdists auf eingebettete Schlüssel)
reagieren darauf. Zwei Optionen: den Fund in die Release-Notes aufnehmen, oder
`/tests` aus dem sdist nehmen und stattdessen auf das Git-Tag verweisen.
Bewusste Entscheidung treffen, nicht überrascht werden.

---

## 4. Lizenz-Konsistenz — **AUFLAGE**

### Geprüft

- SPDX-Header aller 112 Textdateien einzeln ausgelesen und gegen die in
  `NOTICE`, `CONTRIBUTING.md`, `pyproject.toml` und `README.md` deklarierten
  Perimeter gehalten.
- `LICENSE` (202 Zeilen, unveränderter Apache-2.0-Text) und `LICENSE-DATA`
  (unveränderter CC-BY-4.0-Text) gegen die Deklaration
  `license = "Apache-2.0 AND CC-BY-4.0"` (`pyproject.toml:32`).
- Existenz der Enforcement-Mechanismen, die die Header garantieren sollen.

### A4.1 — `prompts/` ist CC-BY-4.0 lizenziert und in keinem Perimeter genannt

`src/markproof/prompts/de.yaml` und `en.yaml` tragen
`SPDX-License-Identifier: CC-BY-4.0`. Alle vier Prosadeklarationen des
CC-BY-Perimeters nennen aber nur `rulepacks/`, `patterns/` und `docs/`:

| Ort | Wortlaut |
|---|---|
| `NOTICE:18-21` | `src/markproof/rulepacks/`, `src/markproof/patterns/`, `docs/` |
| `NOTICE:16` | Apache-2.0 gilt für „`src/` (except the directories named below)" |
| `CONTRIBUTING.md` (Ground rules) | „CC-BY-4.0 for anything under `src/markproof/rulepacks/`, `src/markproof/patterns/` and `docs/`" |
| `pyproject.toml:28-30` | „the shipped rulepacks and patterns […] are CC-BY-4.0" |
| `README.md:147` | „Rulepacks, patterns, and documentation are CC-BY-4.0" |

`NOTICE:16` behauptet also Apache-2.0 für `prompts/`, während die Dateien selbst
CC-BY-4.0 sagen — ein direkter Widerspruch, und zwar einer, der im Wheel
ausgeliefert wird.

CC-BY-4.0 ist hier die sachlich richtige Wahl: Die Prompt-Einträge tragen
`guideline_ref`-Felder und `purpose`-Paraphrasen der Leitlinien, sind also
dasselbe abgeleitete Material wie die Muster. **Der Fix gehört daher in die vier
Deklarationen, nicht in die Header.**

**Vorgeschlagene Fassung**, `NOTICE` nach Zeile 20 einfügen:

```
    src/markproof/prompts/      probe prompt sets, with their guideline refs
```

und dieselbe Ergänzung sinngemäß in `CONTRIBUTING.md`, `pyproject.toml:28-30`
und `README.md:147` („Rulepacks, patterns, prompt sets, and documentation are
CC-BY-4.0").

### A4.2 — 59 getrackte Dateien ohne SPDX-Header

`CONTRIBUTING.md` führt als Ground Rule: „**Every file carries an SPDX
header.**" Das Repo erfüllt die eigene Regel nicht.

| Gruppe | Anzahl | Bemerkung |
|---|---|---|
| Binärdateien (PNG/JPG/MP4/WAV) | 22 | keine Kommentarsyntax — brauchen `.license`-Sidecars oder `REUSE.toml`/DEP5 |
| `examples/demo-bot/text/{marked,plain}/*.txt` | 16 | Klartext, Header wäre möglich, würde aber die Token-Sequenz verändern → Sidecar |
| JSON-Datendateien (`tests/fixtures/text/*.json`, alle drei `MANIFEST.json`, `examples/demo-bot/watermark_config.json`) | 18 | JSON kennt keine Kommentare → Sidecar oder `REUSE.toml` |
| `LICENSE`, `LICENSE-DATA`, `NOTICE` | 3 | unkritisch, sind selbst die Lizenztexte |

Der pragmatische Fix ist eine `REUSE.toml` im Wurzelverzeichnis, die alle vier
Gruppen per Glob abdeckt — eine Datei statt 56 Sidecars. Alternativ: den
Anspruch in `CONTRIBUTING.md` auf das absenken, was gilt („Every file that can
carry a comment carries an SPDX header; data and media files are covered by
`REUSE.toml`").

### A4.3 — Nichts erzwingt die SPDX-Regel

`pyproject.toml:179-180`: „TODO(M0): SPDX-header presence is enforced by a separate
pre-commit hook (reuse lint), not by ruff — see `.pre-commit-config.yaml` once
it exists."

`.pre-commit-config.yaml` existiert nicht (`git ls-files`). `pre-commit` steht
im Dev-Extra (`pyproject.toml:111`), ist aber unkonfiguriert. Die dafür
vorgesehene `licenses.yml` (`ci.yml:11`) fehlt ebenfalls. Die Regel aus A4.2 ist
damit unbewehrt — was A4.2 erklärt.

### A4.4 — Die Deklaration selbst ist korrekt

Zur Klarstellung, weil es der geprüfte Punkt war:
`license = "Apache-2.0 AND CC-BY-4.0"` ist ein gültiger PEP-639-SPDX-Ausdruck,
beide Identifier sind SPDX-konform geschrieben, `license-files` (`:33`) nimmt
`LICENSE`, `LICENSE-DATA` und `NOTICE` mit ins Wheel, und es gibt korrekterweise
**keinen** `License ::`-Classifier (unter PEP 639 unzulässig neben dem
Ausdruck). `LICENSE` und `LICENSE-DATA` sind unverändert. Die CC-BY-Anteile sind
über die SPDX-Header sauber pro Datei abgegrenzt — der einzige Bruch ist A4.1.

---

## 5. Marken — **BESTANDEN**, zwei kleine Auflagen

### Geprüft

- Jede Nennung von SynthID (37 Fundstellen über 36 Dateien), C2PA, Content
  Credentials, Playwright, Adobe, CAI, Google DeepMind, Europäische Kommission.
- Modul-Docstrings von `checks/synthid.py`, `checks/c2pa_verify.py`,
  `probes/ui.py`.
- Namensraum: Distribution, Import-Package, Console-Script, Extras.
- Sichtbarkeit des Disclaimers in `README.md`, `NOTICE` §3,
  `docs/DISCLAIMER.md` und in den erzeugten Artefakten.

### Ergebnis

**Durchweg nominativ.** Die Marken erscheinen ausschließlich als Angabe dessen,
was das Werkzeug prüft („verifies C2PA manifests", „detects SynthID text
watermarks") oder welche Bibliothek es fährt. Kein fremdes Logo im Repo — es
gibt außer den selbst erzeugten Fixtures kein einziges Bildasset.

**Kein Bauteil trägt einen fremden Markennamen.** Distribution, Import-Package
und Kommando heißen alle `markproof` (`pyproject.toml:22`, `:116`). `synthid`
kommt nur als Extra-Name und als `method:`-Wert in der Config vor — also als
Bezeichnung des geprüften Verfahrens, nicht als Produktname. Der
Trademark-Abschnitt `NOTICE:66-72` sagt das ausdrücklich zu und die Prüfung
bestätigt es.

**Der Disclaimer steht an vier Stellen**, darunter in beiden PDF-Renderern als
gedruckter Absatz (`TRADEMARK_NOTICE`, `pdf_reportlab.py:148-152` → `:802`,
`pdf_weasy.py:318`). Anders als die Attribution aus A2.1 wird dieser Absatz
tatsächlich gerendert — er hängt an einer Konstante, nicht an Reportdaten.

### A5.1 — `README.md` verlinkt `docs/DISCLAIMER.md` nicht

Der Abschnitt `## Disclaimer` (`README.md:139-143`) wiederholt die zwei
Kernabsätze, verweist aber nirgends auf das ausführliche Dokument. Auf
`docs/DISCLAIMER.md` zeigen nur `NOTICE:74` und
`src/markproof/__init__.py:22` — beides Orte, die ein Leser des README nicht
aufsucht. Der Abschnitt „Scope limits" dort ist das inhaltlich Stärkste, was
das Projekt zu seinen eigenen Grenzen sagt; er sollte auffindbar sein.

**Vorschlag**, `README.md:143` anfügen:
`Die vollständigen Grenzen des Werkzeugs stehen in [`docs/DISCLAIMER.md`](docs/DISCLAIMER.md).`
(bzw. englisch: „The full scope limits are in [`docs/DISCLAIMER.md`](docs/DISCLAIMER.md).")

### A5.2 — „verbatim" stimmt nicht

`docs/DISCLAIMER.md:15-16`: „Those two paragraphs are reproduced verbatim in the
README and are part of the release checklist, not decoration."

Sie sind es nicht. `README.md:141` schreibt „Adobe **or** the Content
Authenticity Initiative", `DISCLAIMER.md:11` „Adobe **/** the Content
Authenticity Initiative"; `README.md:143` ergänzt „and produces no
certification". Kleine Sache — aber in einem Dokument, das Wortlauttreue zur
Auflage erklärt, ist sie sichtbar. Entweder die drei Strings angleichen (und
dann gegen `TRADEMARK_NOTICE` in `pdf_reportlab.py:148` mitziehen, das eine
vierte Variante ist) oder das Wort „verbatim" streichen.

### Anmerkung zur Standardausgabe

`summary.md` trägt den Rechtsberatungs-Disclaimer (`summary.py:133`), aber
nicht den Markenhinweis; nur das opt-in-PDF hat beide. Da die Markdown-Summary
das Artefakt ist, das in Tickets und Job-Summaries landet, wäre eine Zeile dort
konsequent. Kein Verstoß — die Marken werden in der Summary auch nicht genannt
—, aber die Asymmetrie ist unbeabsichtigt.

---

## 6. Versprechen — **BLOCKER**

Das ist der Punkt mit dem einzigen echten Blocker.

### Geprüft

- `grep -rniE "(compliant|compliance|guarantee|ensures? legal|certif|conformity|rechtskonform|garantie|zertifi)"` über alle Textdateien.
- Jede Zeile der README-Tabelle „What it checks" gegen die Regeln, die das
  ausgelieferte Rulepack tatsächlich definiert.
- `docs/RULES_SOURCES.md` gegen den Implementierungsstand nach M5.
- Die als Package-Data ausgelieferten `README.md` unter `rulepacks/` und
  `patterns/`.
- Die mitgelieferten Beispielkonfigurationen gegen das echte Config-Schema.

### Grundhaltung: vorbildlich

Das muss vorweg, weil die Befunde sonst falsch gewichtet wirken. Die
Wortdisziplin ist besser als in den meisten kommerziellen Werkzeugen dieser
Klasse. `Summary.conformant` trägt im Modell den Kommentar „Deliberately not
'compliant': the tool checked what it could check, and a green run means no rule
in this pack failed — not that the system satisfies Article 50 in full"
(`report/model.py:74-79`). Undecidability wird konsequent zu WARN statt zu
geratenem PASS. `docs/DISCLAIMER.md` §Scope limits benennt sechs Grenzen
freiwillig. Der Grep findet **keine** Zusicherung von Rechtskonformität, keine
Zertifizierungsbehauptung, kein „ensures compliance". Das ist der Standard, an
dem die folgenden Befunde gemessen sind.

### B6.1 — **BLOCKER**: Die README-Tabelle bewirbt eine Prüfung, die nicht ausgeliefert wird

`README.md:46`:

```
| `MPF-L-001` | Are deepfake / emotion-recognition labels present? (warns) | media, UI | Art. 50(4) |
```

Zwei Fehler in einer Zeile, beide am Rulepack verifiziert:

1. **Die Emotionserkennung wird nicht geprüft.** Das ausgelieferte Rulepack
   definiert `MPF-L-001` mit `category: deepfake`
   (`art50-eu-2026.07.yaml:208`). Die Muster für Art.-50(3)-Hinweise existieren
   — 24 Einträge mit `category: emotion-recognition` in `labels.de-en.yaml` —,
   aber **keine Regel konsumiert sie**. Die Regel-IDs im Rulepack sind
   vollständig: `MPF-D-001`, `-002`, `-003`, `MPF-M-001`, `MPF-T-001`,
   `MPF-L-001`. Kein `MPF-L-002`. Der Rulepack-Trailer selbst hält das fest,
   und `docs/RULES_SOURCES.md` §9.5 begründet über eine halbe Seite, warum die
   Regel *bewusst* fehlt: Ob ein Emotionserkennungssystem betrieben wird, ist
   eine Tatsache über die Installation, die keine Probe feststellen kann.
2. **Die falsche Norm.** Emotionserkennung ist **Art. 50(3)**, nicht 50(4). Die
   Zeile ordnet sie 50(4) zu.

Das ist genau die Stelle, an der ein Compliance-Werkzeug seine Glaubwürdigkeit
verliert — und zwar deshalb, weil die durchdachte Begründung für das Weglassen
schon im Repo steht und die Marketing-Tabelle sie überschreibt. Ein Leser, der
`RULES_SOURCES.md` §9.5 findet, nachdem er die Tabelle geglaubt hat, wird jeder
anderen Zeile der Tabelle misstrauen.

**Vorgeschlagene Fassung**, `README.md:46`:

```
| `MPF-L-001` | Does delivered content carry a perceivable deepfake label? (warns) | media, UI | Art. 50(4) |
```

Und, wenn die Art.-50(3)-Muster überhaupt beworben werden sollen, darunter als
eigener Absatz statt als Tabellenzeile:

> Patterns for the Art. 50(3) notice on emotion recognition and biometric
> categorisation ship in `labels.de-en.yaml`, but no rule uses them: whether
> such a system is in operation is a fact about your deployment that no probe
> can establish from a response. Write a local rule against the UI probe if you
> know it is. The reasoning is in
> [`docs/RULES_SOURCES.md`](docs/RULES_SOURCES.md) §9.5.

Das verkauft weniger und ist überzeugender.

### B6.2 — Ungeprüfte Amtsblatt-Fundstelle im Launch-Text

`README.md:135`: „The Digital Omnibus (**Reg. (EU) 2026/1744**) postponed the
Annex III high-risk obligations to December 2027 and August 2028 — it did
**not** touch Article 50."

Die inhaltliche Aussage stimmt. Die Fundstelle ist ungeprüft, und das Repo weiß
es: `docs/RULES_SOURCES.md` §9.7 führt „**VERIFIZIEREN: Fundstelle des
AI-Omnibus.** Rn. 153 beschreibt die Übergangsfrist […], nennt aber keine
Fundstelle im Amtsblatt. Für eine Veröffentlichung sollte die Verordnung selbst
zitiert werden."

Eine präzise Verordnungsnummer im README ist eine Behauptung, die der erste
juristisch geschulte Leser in EUR-Lex nachschlägt. Sitzt sie falsch, kostet das
mehr Vertrauen als jede fehlende Funktion.

**Auflage:** vor dem Launch gegen EUR-Lex verifizieren — oder die Nummer
streichen: „The Digital Omnibus postponed the Annex III high-risk obligations to
December 2027 and August 2028 — it did not touch Article 50."

### B6.3 — Unbelegte Zahlenbehauptung über Dritte

`README.md:33`: „Tools that *remove* C2PA manifests and text watermarks have
collected well over 30,000 GitHub stars; the official C2PA reference
implementation has about 410."

Kein Datum, keine Quelle, keine Nennung der gemeinten Repos. Sternzahlen
bewegen sich, und ein Leser prüft sie in dreißig Sekunden nach. Entweder
datieren und belegen („as of August 2026", mit Links) oder den Satz streichen —
das Argument darüber und darunter trägt auch ohne ihn.

Verwandt und ebenfalls vor dem Launch zu verifizieren: die drei fremden Repos
im Abschnitt „Related projects" (`README.md:117-120` — `Rubiss/art50-ci`,
`CreativeMayhemLtd/provcheck`, `MMVFIRM/AIMark-Sidecar`). Offline nicht
prüfbar. Ein toter oder falsch beschriebener Link in einem Abschnitt, dessen
ganzer Zweck faire Einordnung ist, wirkt schlechter als kein Abschnitt.

### B6.4 — `docs/RULES_SOURCES.md` ist gegenüber M3–M5 veraltet

Das Dokument ist die Begründungsschicht, auf die Rulepack, README und
Disclaimer verweisen. Es beschreibt den Stand nach M1:

- §5 führt `MPF-D-002` als „wartet auf die UI-Probe (M5)" und `MPF-D-003` als
  „**spezifiziert, blockiert**". Beide sind ausgeliefert.
- §6 beschreibt `prompt_ids` als die noch fehlende Erweiterung, die
  `MPF-D-003` blockiert. Sie ist da: `art50-eu-2026.07.yaml:111-113` nutzt sie,
  `checks/disclosure.py:168` implementiert sie.
- §3.3 überschreibt sich selbst mit „in M1 blockiert".

Ein Begründungsdokument, das die eigene Abdeckung **unter**treibt, ist der
seltenere und sympathischere Fehler — es bleibt einer. Ein Leser, der prüft, ob
die Doku zum Code passt, findet zuerst diese Stellen.

Zusätzlich sind zwei Punkte aus §9.7 im ausgelieferten Rulepack noch offen:
`MPF-M-001` (`:125`) und `MPF-T-001` (`:153`) zitieren „Code of Practice,
Commitment 2" bzw. „Commitment 1" **ohne Abschnittsangabe**, obwohl der Code
zwei Abschnitte mit je eigener Zählung führt. `MPF-L-001` (`:186`) macht es
richtig vor: „Code of Practice, Section 2, Commitment 1". Gemeint ist bei beiden
Abschnitt 1 — die Angabe gehört ergänzt, sonst ist die Zitatkette mehrdeutig,
und Zitierbarkeit ist bei diesem Werkzeug das Verkaufsargument.

### B6.5 — Zwei ausgelieferte README behaupten, ihr Verzeichnis sei leer

`src/markproof/rulepacks/README.md` und `src/markproof/patterns/README.md`
tragen beide einen Abschnitt:

```
## Status

Empty. The first rulepack is an M1 deliverable.
- TODO(M1): art50-eu-2026.07.yaml — ...
```

bzw.

```
## Status

Empty. The pattern files are M1/M5 deliverables.
- TODO(M5): deepfake-labels.yaml (Art. 50(4)).
- TODO(M5): emotion-labels.yaml (Art. 50(3)).
```

Beide Verzeichnisse sind nicht leer, und die dort angekündigten Dateinamen
existieren nicht — geliefert wurde die zusammengefasste `labels.de-en.yaml`.
Beide Dateien sind CC-BY-4.0-Package-Data und **gehen mit ins Wheel**:
`pip show -f markproof` und jeder Blick in `site-packages` stellt sie dem
Nutzer direkt vor Augen.

Ein ausgelieferter Hinweis „Empty" über einem Verzeichnis, das das
Herzstück des Produkts enthält, ist der Detailfehler, an dem ein Reviewer
entscheidet, ob er dem Rest glaubt. Beide `## Status`-Abschnitte streichen und
durch eine Zeile ersetzen, die den tatsächlichen Inhalt nennt.

### B6.6 — `examples/markproof.yaml` lädt nicht

Die Referenz-Beispielkonfiguration im Wurzelverzeichnis von `examples/` — die
erste Datei, die ein Interessent kopiert, und Teil des sdist
(`pyproject.toml:134`) — validiert nicht gegen das aktuelle Schema:

```
3 validation errors for MarkproofConfig
target.probes.2.media.formats     Extra inputs are not permitted  (['png','jpeg'])
text_marking.synthid_config       Extra inputs are not permitted  ('secrets/watermark_config.json')
text_marking.detector             Extra inputs are not permitted  ('mean-g')
```

`examples/demo-bot/markproof.yaml` lädt sauber; nur das Top-Level-Beispiel ist
auf dem Stand vor der Umbenennung `synthid_config` → `watermark_config`
(`config.py:305`). Es ist dieselbe Umbenennung, die die uncommittete
README-Änderung bereits nachzieht — die Beispieldatei wurde vergessen.

Streng genommen ein Funktions- und kein Compliance-Befund. Er steht hier, weil
er dieselbe Wurzel hat wie B6.1 und B6.4: Die *Beschreibung* des Werkzeugs ist
an mehreren Stellen hinter dem Werkzeug zurückgeblieben. Ein Gate, das
Beispielkonfigurationen gegen das Schema lädt, würde alle drei Klassen künftig
abfangen — und es kostet fünf Zeilen in `tests/`.

---

## 7. Daten — **BESTANDEN**, eine kleine Auflage

### Geprüft

- Grep über alle Textdateien nach E-Mail-Adressen, Hosts, und den üblichen
  Schlüsselpräfixen (`sk-`, `ghp_`, `gho_`, `AKIA`, `Bearer <token>`,
  `api_key = "…"`).
- Alle PEM-Blöcke im Repo (`BEGIN CERTIFICATE` / `PRIVATE KEY` / `PUBLIC KEY`).
- Beide Watermark-Konfigurationen und ihre Kennzeichnung.
- `.gitignore` gegen die tatsächlich eingecheckten Secret-Klassen.

### Ergebnis

**Keine personenbezogenen Daten, keine echten Kundennamen, keine produktiv
geltenden Schlüssel.**

Die einzige E-Mail-Adresse im Repo ist die des Maintainers selbst
(`pyproject.toml:35`, `SECURITY.md`) — gewollt und notwendig. Alle Endpunkte
sind reservierte Beispielnamen nach RFC 2606/6761: `example.invalid`,
`api.example.com`, `api.example.invalid`, `cdn.example.invalid`, `demo.example`,
`127.0.0.1`, `localhost`. Kein Produktivhost, kein Kundenname, nirgends.

Der Secret-Scan ist sauber.

**Testschlüssel (`tests/fixtures/`):** vierfach als Testmaterial gekennzeichnet
— siehe die Tabelle in Abschnitt 3. Bestanden.

**SynthID-Testschlüssel (`tests/fixtures/text/`):** Die Keys
`[654, 400, 836, 123, 340, 443, 597, 160, 57]` sind an zwei Stellen
gekennzeichnet: `MANIFEST.json` → `watermark_config_note` („The keys are the
public example keys from the transformers docs and are TEST KEYS -- never mark
production output with them") und `tests/fixtures/text/README.md:106-109` als
hervorgehobenes Blockquote („**These are TEST KEYS.** […] Committing them here is
safe only because nothing in this repository ever marks real output with them").
Bestanden.

**Demo-Watermark-Config:** `.gitignore:60` führt `watermark_config.json` als
Secret-Klasse und nimmt in `:65` genau diese eine Datei wieder aus — mit einer
vierzeiligen Begründung im `.gitignore` selbst. `examples/demo-bot/README.md`
erklärt die Ausnahme ausführlich („a demo target nobody can check is not a demo
target"). Die Kennzeichnung *um die Datei herum* ist vorbildlich.

### A7.1 — Die Demo-Config trägt selbst keine Kennzeichnung

`examples/demo-bot/watermark_config.json` ist ein nacktes Objekt:

```json
{ "tokenizer": "gpt2", "ngram_len": 5, "keys": [50841, 12703, 39218], … }
```

Kopiert jemand die Datei als Vorlage aus dem Repo heraus — und genau dazu lädt
eine Demo-Config ein —, bleibt jede Kennzeichnung zurück. Die naheliegende
Lösung, ein `"_comment"`-Feld, **funktioniert nicht**: `WatermarkConfig` in
`src/markproof/checks/synthid.py:72` steht auf
`model_config = ConfigDict(extra="forbid", frozen=True)`, ein Zusatzschlüssel
lässt die Datei nicht mehr laden. Das ist an sich die richtige Strenge, sie
verbaut hier nur den bequemen Weg.

Zwei gangbare Optionen:

- *(a)* In `WatermarkConfig` Schlüssel mit führendem `_` explizit ignorieren
  (`model_validator(mode="before")`, der sie herausfiltert). Erlaubt
  Kennzeichnung in jeder Kundenkonfiguration und ist eine defensive
  Verbesserung an sich — eine Config, die eine Notiz nicht tragen darf, wird
  ohne Notiz weitergereicht.
- *(b)* Die Datei nach `watermark_config.demo.json` umbenennen. Der Name reist
  mit. Kosten: sechs Fundstellen (`examples/demo-bot/markproof.yaml:30`,
  `text/make_texts.py:99`, `text/make_texts.py:521`,
  `text/MANIFEST.json:5`, `text/README.md:40`, `.github/workflows/dogfood.yml:94`)
  plus die `.gitignore`-Ausnahme.

Option (a) ist die wertvollere, weil sie auch echten Nutzern zugutekommt.

---

## Ampel

| # | Auflage | Befund | Vor 0.1.0 zwingend? |
|---|---|---|---|
| 1 | Normtexte | 🟢 **BESTANDEN** | — |
| 2 | Attribution | 🟡 **AUFLAGE** (A2.1 substanziell) | ja, A2.1–A2.4 |
| 3 | Fremde Binaries / Modelle / Zertifikate | 🟢 **BESTANDEN** | — |
| 4 | Lizenz-Konsistenz | 🟡 **AUFLAGE** | ja, A4.1 |
| 5 | Marken | 🟢 **BESTANDEN** | nein (A5.1/A5.2 kosmetisch) |
| 6 | Versprechen | 🔴 **BLOCKER** (B6.1) | ja, B6.1–B6.3, B6.5, B6.6 |
| 7 | Daten | 🟢 **BESTANDEN** | nein (A7.1 empfohlen) |

**Gesamtbild: 🔴 nicht launchreif** — wegen genau eines Blockers und zweier
Auflagen, die alle drei an einer Stelle liegen, die ein Nutzer sofort sieht.

Die inhaltliche Substanz ist es. Die juristisch heikelsten Punkte — kein
Normtext im Repo, saubere Marken-Nominativität, keine Konformitätszusicherung,
keine produktiven Daten, Testmaterial vierfach gekennzeichnet — sind erledigt,
und zwar mit einer Sorgfalt, die über das Übliche hinausgeht. Was fehlt, ist
durchweg **Nachführung**: Beschreibung, Attributionskette und Beispieldateien
sind an mehreren Stellen hinter dem Code zurückgeblieben, den M2 bis M5 gebaut
haben.

---

## Was vor dem Release erledigt sein muss

### Blocker

1. **`README.md:46`** — `MPF-L-001`-Zeile korrigieren: nur Deepfake-Label,
   Emotionserkennung als nicht ausgelieferte Muster in einen eigenen Absatz
   (Art. 50(3), nicht 50(4)). Fassung in **B6.1**.

### Auflagen mit Release-Bezug

2. **`src/markproof/report/model.py:156`** — `license` und `attribution` in den
   Rulepack-Block des Reports aufnehmen, damit die CC-BY-Attribution
   `report.json`, `summary.md` und beide PDF erreicht. Plus ein Test, der das
   festhält. Fassung in **A2.1**.
3. **`NOTICE`** — Copyright-Vermerk, Änderungshinweis und
   Gewährleistungsverweis ergänzen (**A2.2**); Datum des Code of Practice auf
   `10 June 2026` korrigieren (**A2.3**); `THIRD_PARTY_LICENSES.md` entweder
   erzeugen oder den Verweis darauf entfernen (**A2.4**); `pytest-cov`
   nachtragen (**A2.5**).
4. **CC-BY-Perimeter** — `src/markproof/prompts/` in `NOTICE:18-21`,
   `CONTRIBUTING.md`, `pyproject.toml:28-30` und `README.md:147` aufnehmen; die
   Header dort bleiben CC-BY-4.0 (**A4.1**).
5. **`README.md:135`** — Fundstelle `Reg. (EU) 2026/1744` gegen EUR-Lex
   verifizieren oder die Nummer streichen (**B6.2**).
6. **`README.md:33`** — Sternzahlen datieren und belegen oder streichen; die
   drei Repos unter „Related projects" gegenprüfen (**B6.3**).
7. **`src/markproof/rulepacks/README.md`** und
   **`src/markproof/patterns/README.md`** — die `## Status: Empty`-Abschnitte
   ersetzen. Beide gehen ins Wheel (**B6.5**).
8. **`examples/markproof.yaml`** — gegen das aktuelle Schema reparieren
   (`formats` entfernen, `synthid_config` → `watermark_config`, `detector`
   entfernen). Dazu ein Test, der jede mitgelieferte `markproof.yaml` lädt
   (**B6.6**).
9. **`README.md` committen.** Auf `main` steht derzeit ein Quickstart mit einem
   Kommando, das nicht existiert (`markproof check`).
10. **Version.** `pyproject.toml:23` steht auf `0.1.0.dev0`. Der Wert reist über
    `__version__` in jeden Report (`markproof 0.1.0.dev0` in der Summary) und
    macht `pipx install markproof` ohne `--pre` unmöglich. Auf `0.1.0` heben und
    `Development Status :: 2 - Pre-Alpha` (`:54`) auf
    `3 - Alpha` bzw. `4 - Beta` anpassen, passend zu „Status: 0.1.0, first
    release" im README.
11. **Tag `v0.1.0`** anlegen, bevor der README-Schnipsel
    `uses: Tippel-AI/markproof/action@v0.1.0` (`README.md:102`) stimmt.

### Nachziehen, nicht release-kritisch

12. `docs/RULES_SOURCES.md` §3.3, §5 und §6 auf den Stand nach M5 bringen
    (**B6.4**); in `art50-eu-2026.07.yaml:125` und `:153` die Abschnittsangabe
    zu „Commitment 1/2" ergänzen.
13. `REUSE.toml` für die 56 Binär- und Datendateien ohne SPDX-Header, oder den
    Anspruch in `CONTRIBUTING.md` auf das Erreichbare absenken (**A4.2**);
    `.pre-commit-config.yaml` mit `reuse lint` anlegen, damit die Regel
    bewehrt ist (**A4.3**).
14. `README.md` auf `docs/DISCLAIMER.md` verlinken (**A5.1**); „verbatim" in
    `docs/DISCLAIMER.md:15` einlösen oder streichen (**A5.2**).
15. Demo-Watermark-Config selbstkennzeichnend machen — bevorzugt über
    `_`-Präfix-Toleranz in `WatermarkConfig` (**A7.1**).
16. Entscheiden, ob der Test-Privatschlüssel im sdist bleibt (Abschnitt 3,
    Hinweis) — bewusst, nicht versehentlich.
