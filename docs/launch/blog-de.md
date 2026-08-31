<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0

ENTWURF — nicht veröffentlicht. Vor dem Publizieren prüfen:
  - Sternzahlen im Aufhänger (Stand nachziehen, s. TODO im Text)
  - Links auf die Fremdprojekte auf Erreichbarkeit
  - Versionsnummer im Konsolen-Transkript (aktuell 0.1.0.dev0 im Report)
-->

# Markierungen überleben die Auslieferung nicht

Zwei Zahlen aus GitHub, die zusammen mehr über den Stand der Inhaltsmarkierung
sagen als jedes Positionspapier. Werkzeuge, deren erklärter Zweck es ist, C2PA-
Manifeste und Text-Wasserzeichen zu *entfernen*, haben zusammen weit über 30.000
Sterne gesammelt. Die offizielle Referenzimplementierung von C2PA hat rund 410.

<!-- TODO vor Veröffentlichung: beide Zahlen neu erheben und Stand datieren. -->

Man kann daraus eine Geschichte über Böswilligkeit machen, und die stimmt auch.
Mich interessiert die langweiligere Hälfte. Wer eine Markierung mutwillig
entfernen will, schafft das; dagegen hilft kein Prüfwerkzeug. Viel häufiger
verschwindet die Markierung, ohne dass jemand sie angefasst hat — weil sie eine
Eigenschaft der Auslieferungskette ist und nicht ein Häkchen in einer
Konfiguration.

## Markierung ist eine Eigenschaft der Pipeline, kein Schalter

Ein C2PA-Manifest hängt als Chunk in der Datei. Es überlebt keinen Thumbnailer,
der neu encodiert, keinen Bild-CDN, der Metadaten wegwirft, und keinen
Datenschutz-Schritt, der beim EXIF-Strippen mitnimmt, was er nicht kennt. Der
Generator hat korrekt signiert. Beim Nutzer kommt ein nacktes JPEG an, das
pixelgleich aussieht und sich nur in der Provenienz unterscheidet.

Ein Text-Wasserzeichen liegt in der Tokenfolge. Es stirbt, wenn jemand das
Modell tauscht, die Sampling-Parameter dreht oder eine Umschreibe-Schicht vor die
Antwort hängt, die aus Höflichkeit noch einmal glättet. Niemand hat das
Wasserzeichen abgeschaltet. Es ist nur nicht mehr da.

Eine Offenlegung steht im Frontend. Sie verschwindet beim Refactoring, im A/B-Test
gegen eine wärmere Begrüßung, oder sie rutscht hinter die erste Nutzereingabe,
weil das Widget den Hinweis erst nach dem Öffnen des Chats nachlädt — was
technisch dasselbe ist wie: keine Offenlegung vor der ersten Interaktion.

Alle drei Fälle haben dieselbe Eigenschaft, und die ist das eigentliche Problem:
Sie scheitern still. Nichts stürzt ab, kein Test wird rot, keine Logzeile warnt.
Man erfährt es, wenn jemand von außen fragt — eine Prüferin, eine Aufsicht, eine
Redaktion.

## Warum das in die CI gehört

Artikel 50 der KI-Verordnung gilt seit dem 2. August 2026. Systeme, die vorher
schon auf dem Markt waren, haben bis zum **2. Dezember 2026** Zeit, die
maschinenlesbare Markierung nach Art. 50(2) nachzurüsten. Das ist der Termin,
der die Sache dringlich macht, aber er ist nicht der Grund, warum ich das
Werkzeug gebaut habe.

Der Grund ist die Frage danach. Wenn jemand fragt „woher wissen Sie, dass Ihre
Bilder mit Manifest ausgeliefert wurden?“, lautet die ehrliche Antwort heute in
den meisten Teams: es steht so in der Konfiguration, und der Anbieter sagt es.
Eine Konfiguration ist eine Behauptung über das System. Ein Abruf des laufenden
Endpoints ist eine Messung an ihm. Der Unterschied fällt nicht auf, solange
niemand nachfragt, und er ist der ganze Unterschied, sobald jemand nachfragt.

Deshalb liegt der richtige Ort für diese Prüfung dort, wo schon alle anderen
Regressionen auffallen: in der Pipeline, mit einem Exit-Code, an dem man ein
Deployment aufhängen kann.

## Was markproof tut

markproof ruft den laufenden Endpoint so auf, wie eine Nutzerin es täte, und
prüft, was tatsächlich zurückkommt. Es gibt drei Sonden — HTTP-Chat, Medien und
optional eine Playwright-Sonde gegen die gerenderte Oberfläche — und einen
Regelsatz, der die maschinell entscheidbaren Teile von Artikel 50 abbildet:
Offenlegung in der ersten Antwort und auf direkte Nachfrage, Offenlegung vor der
ersten Eingabe im Interface, ein gültiges C2PA-Manifest mit passendem
Quellentyp, das deklarierte Text-Wasserzeichen, und ein wahrnehmbares
Deepfake-Label.

So sieht ein Lauf gegen einen absichtlich nicht-konformen Testendpunkt aus:

```console
$ markproof run --config markproof.yaml --report-dir report/
  probing chat → http://127.0.0.1:8099/v1/chat/completions
  probing images → http://127.0.0.1:8099/v1/images/generations

  demo-bot · rulepack art50-eu-2026.07 (1.0.0)

Rule       Result  Probe   Detail
MPF-D-001  FAIL    chat    no AI disclosure found in the responses in scope
MPF-D-003  FAIL    chat    no AI disclosure found in the responses in scope
MPF-L-001  WARN    images  no deepfake label found in the perceivable text
MPF-M-001  FAIL    images  1 of 1 asset(s) failed: no C2PA manifest embedded in
                           the delivered bytes
MPF-T-001  SKIP    chat    18 tokens is below the 100 needed for a meaningful
                           score — the detector's confidence grows with length,
                           and a short sample would be noise dressed as a verdict

  3 fail · 1 warn · 1 skip
```

An diesem Ausschnitt hängen die vier Entscheidungen, über die ich beim Bauen am
längsten nachgedacht habe.

**Kein LLM im Bewertungspfad.** Dieselbe Eingabe erzeugt dasselbe Urteil, jedes
Mal. Ein Prüfwerkzeug, das schätzt, verschiebt das Problem nur an eine Stelle, an
der man es nicht mehr sieht — man tauscht eine unbekannte Auslieferungskette
gegen einen unbekannten Richter. Wo die Entscheidbarkeit endet, etwa bei der
Frage, ob eine Offenlegung „klar und erkennbar“ formuliert ist, gibt markproof
`WARN` mit der zitierten Fundstelle aus und nie ein geratenes `PASS`.

**Der `SKIP` oben ist keine Ausrede, sondern die Regel.** Ein Wasserzeichen ist
eine statistische Eigenschaft der Tokenfolge; 18 Tokens tragen kein Signal, das
ein Urteil rechtfertigt. Die Regel verlangt 100. Lieber keine Aussage als eine
falsche.

**Eine Sonde, die nicht durchlief, ist ein Fehlschlag, kein übersprungener
Test.** „Der Endpoint war nicht erreichbar“ und „der Endpoint ist konform“
dürfen in einem Bericht nie gleich aussehen. Eine Pipeline, die grün wird, weil
nichts geprüft werden konnte, ist das schlechteste Ergebnis, das dieses Werkzeug
haben kann. Solche Fälle bekommen deshalb eine eigene Kennung, `MPF-X-001`, und
zählen als Fehlschlag.

**Geprüft wird auf Assertion-Ebene, nicht auf Anwesenheit.** Der Unterschied
klingt akademisch und ist es nicht. Ein Bild kann ein eingebettetes, gültig
signiertes Manifest tragen, dessen Hash-Bindungen halten — und als Quellentyp
`algorithmicMedia` deklarieren statt `trainedAlgorithmicMedia`. Algorithmisch
erzeugt, aber nicht von einem trainierten Modell. Jedes „hat diese Datei Content
Credentials?“-Werkzeug sagt hier ja. Art. 50(2) ist trotzdem nicht erfüllt. Ich
habe für diesen Fall einen eigenen Modus im Testendpunkt gebaut, weil er der
einzige ist, den eine Prüfung auf Assertion-Ebene fängt und eine Prüfung auf
Anwesenheit durchwinkt.

Das Text-Wasserzeichen prüft markproof gegen die Konfiguration des Betreibers.
Um zu zeigen, dass der Detektor wirklich die Tokenfolge liest und nicht die
Wortwahl, zieht der Testendpunkt markierte und unmarkierte Antworten aus
demselben Gitter austauschbarer Formulierungen: gleiche Länge, gleiches Register,
gleiche Aufzählungen, unterschiedlich nur darin, welches Synonym an welcher
Stelle steht. Gemessen liegen die markierten Antworten bei einem mean-g-Wert
zwischen 0,75 und 0,85, die unmarkierten bei 0,49 bis 0,53 — Zufallsniveau. Die
Regel zieht die Grenzen bei 0,70 und 0,56; was dazwischen landet, gilt als
unentschieden und wird im mitgelieferten Regelsatz als Fehlschlag gewertet. Das
ist die konservative Lesart, und sie hat einen Grund: Wer erklärt, seine Ausgaben
zu markieren, sollte die Schwelle auch erreichen.

Am Ende steht ein Bericht in kanonischem JSON nach RFC 8785, signiert mit
Ed25519. Wer ihn prüft, braucht das geprüfte System nicht:

```console
$ markproof verify-report report.json --key public.pem
  ✓ signature valid against the supplied public key
  demo-bot · art50-eu-2026.07 v1.0.0 · 2026-08-31T14:40:28+00:00
```

Ändert man im Bericht ein einziges `FAIL` in ein `PASS`, sagt derselbe Befehl
`✗ signature does not match the report contents`. Das ist der Punkt: Der Bericht
ist als Beleg gegenüber Dritten gedacht, und ein Beleg, den der Belegte
nachträglich umschreiben kann, ist keiner.

## Was das Werkzeug nicht kann

Das gehört in denselben Text wie das, was es kann, und nicht in eine FAQ weiter
unten.

markproof ist ein **Selbst-Konformitätstest, kein Detektor**. Die Prüfung des
Text-Wasserzeichens braucht die generierungsseitige Konfiguration — die Schlüssel
sind das Wasserzeichen. Wer sie hat, kann prüfen *und* fälschen. Das Werkzeug
weist also nach, dass Ihre eigene Markierung Ihre eigene Kette überlebt. Es kann
nicht sagen, ob irgendein Text von einer KI stammt, und wird es nicht versuchen:
Universaldetektion ist wissenschaftlich wackelig und im Schadensfall
rufschädigend.

Die **Trust-List bleibt in v1 außen vor**. Die Medienprüfung validiert
Anwesenheit, Hash-Bindungen und die geforderten Assertions. Ob der Signierende
auf der offiziellen Conformance Trust List steht, beantwortet sie nicht; das ist
für v1.1 vorgesehen. Bis dahin ist ein `PASS` bei `MPF-M-001` die Aussage „das
Manifest ist da, es passt zu den Bytes und es deklariert den richtigen
Quellentyp“ — nicht „der Signierende ist vertrauenswürdig“.

**Prominenz wird nicht bewertet.** Ob ein vorhandener Hinweis auch klar und
unterscheidbar ist, hängt an Position, Kontrast und Standzeit. Nichts davon steht
im extrahierten Text. Die betroffenen Regeln melden deshalb `WARN` und legen den
Nachweis bei — bei der Oberflächen-Offenlegung ebenso wie beim Deepfake-Label.
Beim Label kommt hinzu, dass die Vorfrage, ob ein Inhalt überhaupt ein Deepfake
ist, eine Einzelfallabwägung über Ähnlichkeit und Publikum verlangt, die kein
Stringvergleich leistet.

Die **Abdeckung ist bewusst unvollständig**. Zwei Pflichten liegen als reservierte
Kennungen im Regelsatz und sind nicht implementiert: die Offenlegung, in wessen
Auftrag ein Agent handelt, und der Hinweis nach Art. 50(3) bei Emotionserkennung.
Bei der zweiten liegt es nicht am Werkzeug — ob ein solches System im Einsatz
ist, ist eine Tatsache über den Betrieb, die aus keiner Antwort ablesbar ist.
Lieber eine dokumentierte Lücke als eine Regel, die immer besteht.

Und schließlich: Das ist ein technischer Konformitätstest, keine Rechtsberatung.
Ein grüner Lauf ist ein Beleg, kein Gutachten.

## Was es sonst noch gibt

Das Feld ist besetzt, und für mehrere Aufgaben ist markproof nicht das richtige
Werkzeug.

[art50-ci](https://github.com/Rubiss/art50-ci) fährt einen echten Browser gegen
Ihre Seite und findet Dinge, die eine API-Sonde prinzipiell nicht sehen kann —
verdeckte Hinweise, Overlays, Regressionen im Layout. Wenn Ihre Oberfläche eine
Website ist, fangen Sie dort an.
[provcheck](https://github.com/CreativeMayhemLtd/provcheck) prüft C2PA lokal, mit
Wasserzeichen-Gegenprobe, als Rust-CLI und Desktop-App; für Dateien, die schon
auf der Platte liegen, ist das die bessere Wahl.
[c2patool](https://github.com/contentauth/c2patool) und das offizielle
[c2pa-conformance-tool-cli](https://github.com/contentauth/c2pa-conformance-tool-cli)
beantworten „ist dieses eine Asset gültig signiert?“ — inklusive Trust List, die
markproof eben noch nicht mitbringt. Die Medienprüfung hier baut auf
`c2pa-python` auf und ersetzt diese Werkzeuge nicht.

markproof steht daneben, nicht darüber. Anders ist es in vier Punkten: Es fragt
den laufenden API-Endpunkt statt einer gerenderten Seite oder einer lokalen
Datei; es bewertet Artikel-50-Semantik auf Assertion-Ebene statt nur die
Anwesenheit eines Manifests; es verifiziert das Text-Wasserzeichen
Ende-zu-Ende gegen die Konfiguration des Betreibers; und es ist Python, also dort
zu Hause, wo die Teams arbeiten, die das jetzt nachrüsten.

## Was als Nächstes kommt

Für v1.1 steht die Trust-List-Auswertung an, dazu weitere API-Dialekte und
Musterdateien für mehr Sprachen — der Regelsatz deckt heute Deutsch und Englisch
ab. Die Prominenzfrage bleibe ich vorerst schuldig; ich habe keinen Vorschlag,
wie man sie deterministisch prüft, ohne mehr zu behaupten, als man gemessen hat.

Der Code liegt unter Apache-2.0, die Regelsätze unter CC-BY-4.0, damit sie auch
außerhalb dieses Werkzeugs verwendbar sind. Wenn Sie sichtbar generierte Inhalte
in die EU ausliefern: Lassen Sie es einmal gegen Ihren Staging-Endpunkt laufen.
Interessanter als ein grüner Lauf ist für mich der Fall, in dem das Werkzeug
etwas behauptet, das nicht stimmt — davon möchte ich hören.
