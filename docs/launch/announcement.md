<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0

ENTWURF — Material für den Launch-Post. Nichts hiervon ist veröffentlicht.
Titel, Eröffnung und die drei Abgrenzungssätze sind auf Englisch, weil der
Post auf Englisch läuft. Die Mail-Vorlage liegt in beiden Sprachen vor.
-->

# Launch-Material

Vorbemerkung zur Erwartung: Vergleichbare Posts zu Art.-50-Werkzeugen sind
sämtlich zwischen 1 und 5 Punkten gelandet. Die Nachfrage ist heute schwach, und
der Text sollte das nicht durch Lautstärke ausgleichen wollen. Ein Post, der wie
eine Produktankündigung klingt, wird als eine behandelt. Ein Post, der eine
Beobachtung teilt und das Werkzeug am Rand erwähnt, wird im schlechtesten Fall
ignoriert und im besten Fall von den drei Leuten gelesen, die das Problem haben.

---

## Titelvorschläge

Jeder führt mit der Beobachtung, nicht mit dem Werkzeug. Der zweite ist der
stärkste, weil er ohne Vorwissen funktioniert und die Zahlen im Titel
überprüfbar sind; er trägt aber auch das größte Risiko, dass die Diskussion nur
noch um die Sternzahlen geht.

1. **Content marks don't survive delivery**
2. **Two tools that strip AI watermarks have 25k GitHub stars; the C2PA reference implementation has 410**
3. **A C2PA manifest can be validly signed and still not mark the image as AI-generated**

Die Zahlen in Titel 2 sind am 31.08.2026 erhoben:
`guillaumemeyer/watermarks-remover` 19 617, `wiltodelta/remove-ai-watermarks`
5 343, `contentauth/c2pa-rs` 410. Falls sie bis zum Posten abweichen: Titel 2
mit den dann gemessenen Zahlen setzen oder fallen lassen. Eine gerundete Zahl,
die jemand in dreißig Sekunden widerlegt, kostet in einem Compliance-Kontext
mehr, als der Titel einbringt.

---

## Eröffnungsabsatz

> I spent the last months building a checker for the EU AI Act's Article 50
> transparency duties, and the thing that surprised me was not the regulation —
> it was how routinely the marks disappear before anyone reads them. A C2PA
> manifest is a chunk in a file, so it does not survive a thumbnailer, an image
> CDN that drops metadata, or a privacy step that strips EXIF and takes with it
> what it does not recognise. A text watermark lives in the token sequence, so a
> model swap or a rewriting layer in front of the response removes it. A
> disclosure notice lives in the frontend, so it loses an A/B test. None of these
> raise an error, so nobody finds out until an auditor asks. I wrote up what
> that means for testing, and the tool I ended up with is at the bottom.

Wenn der Post an einen Blogartikel hängt, ist dieser Absatz die Eröffnung des
Artikels und im Post steht nur der Link. Doppelt sollte er nicht stehen.

---

## Die drei Abgrenzungssätze

Für die Kommentare, in denen jemand — zu Recht — fragt, warum es das schon wieder
gibt. Jeder Satz räumt zuerst ein, was das andere Werkzeug besser kann. Das ist
kein Höflichkeitszug, sondern der Grund, warum die Antwort geglaubt wird.

**Auf „macht art50-ci das nicht schon?“**
> art50-ci drives a real browser and catches things I structurally cannot — an
> obscured notice, an overlay, a layout regression — so if your surface is a
> website it is the better starting point; markproof asks the API endpoint
> instead, which is where I could not otherwise see whether the bytes and the
> token sequence still carry their marks.

**Auf „wozu, es gibt doch c2patool und provcheck?“**
> Both are better than markproof at the question they answer, and provcheck also
> covers the file already sitting on your disk, which markproof does not touch;
> the gap I hit was that neither tells you whether the asset your *live endpoint*
> hands a user today still declares `trainedAlgorithmicMedia` rather than merely
> carrying a valid signature.

**Auf „ist das nicht wieder ein KI-Detektor?“**
> No, and it deliberately cannot be: verifying a text watermark needs the
> generation-side configuration, so markproof only proves that *your* declared
> marking survives *your* delivery chain, and universal detection is a lane I am
> staying out of because it is scientifically shaky and destructive when it is
> wrong about a person.

Der dritte ist der wichtigste. Er kommt garantiert, und wer ihn nicht sauber
beantwortet, wird mit den Detektor-Debakeln der letzten Jahre in einen Topf
geworfen.

---

## Was im Post nicht vorkommt

- Kein benanntes Fremdsystem, das eine Prüfung nicht besteht — auch nicht als
  Screenshot, auch nicht anonymisiert-aber-erkennbar. Die Belege im Repo kommen
  alle vom eigenen Demo-Endpunkt, und das ist genau deshalb so.
- Keine Zahl zur Verbreitung, zur Bußgeldhöhe oder zum Marktvolumen. Wer Angst
  verkauft, wird danach gefragt, was er sonst noch verkauft.
- Kein „Show HN“. Der Post ist ein Bericht, kein Stand.

---

## Outreach-Mail

Diese Mail geht an Teams, die sichtbar generierte Inhalte in die EU ausliefern.
Drei Bedingungen, sonst wird sie nicht abgeschickt:

1. **Der konkrete Grund steht im ersten Satz und ist wahr.** Wenn sich nicht in
   einem Satz sagen lässt, was an diesem Team den Ausschlag gab, ist es die
   falsche Adresse. „Ihr passt ins Zielprofil“ ist kein Grund.
2. **Kein Prüflauf gegen deren Systeme vor der Mail und kein Befund im Anhang.**
   Ungefragt geprüft und das Ergebnis mitgeschickt zu haben, ist der schnellste
   Weg, aus einer Mail einen Vorfall zu machen — technisch wie rechtlich.
3. **Kein Nachfassen.** Eine Mail, eine Antwort oder keine.

### Vorlage (Englisch)

> **Betreff:** Article 50 marking check — does your image pipeline keep the manifest?
>
> Hi [Name],
>
> I read your write-up on [konkrete Quelle — Blogpost, Talk, Changelog, Issue]
> where you described [konkrete Sache: das eigene Signieren der generierten
> Bilder / den Wechsel auf ein anderes Bildmodell / den Umbau des Chat-Widgets].
> That is the reason I am writing to you and not to a list: you are one of the
> few teams I have seen say out loud that you mark your output.
>
> I built an open-source checker for the Article 50 transparency duties, and the
> failure mode it keeps finding is the boring one — the generator signs
> correctly, and then a thumbnailer, a CDN or a metadata-stripping step downstream
> drops the manifest before the user sees the image. Nothing errors, so nobody
> notices. Same story for text watermarks after a model swap.
>
> I have not run anything against your systems and will not. If it is useful, the
> tool is at github.com/Tippel-AI/markproof — it takes a config file and a staging
> endpoint, and it is Apache-2.0, so there is nothing to buy and nothing to sign
> up for.
>
> What I would actually value more than a user is a correction: if you look at
> the rulepack and think a rule reads Article 50 wrongly, tell me. The rules are
> CC-BY, they cite the paragraph they rest on, and I would rather find out from
> you than from an auditor.
>
> Either way — the retrofit deadline for machine-readable marking is 2 December
> 2026, and it is worth checking that yours still arrives.
>
> Best,
> Lukas Friedrich
> Tippel · tippel.ai

### Vorlage (Deutsch)

> **Betreff:** Art.-50-Markierung — kommt Ihr Manifest beim Nutzer noch an?
>
> Hallo [Name],
>
> ich bin über [konkrete Quelle] auf Ihr Team gestoßen, wo Sie [konkrete Sache]
> beschrieben haben. Das ist der Grund für diese Mail und nicht ein Zielprofil:
> Sie sind eines der wenigen Teams, die öffentlich sagen, dass sie ihre
> Ausgaben markieren.
>
> Ich habe ein Open-Source-Werkzeug für die Transparenzpflichten aus Artikel 50
> gebaut, und der Fehler, den es am häufigsten findet, ist der unspektakuläre:
> Der Generator signiert korrekt, und weiter hinten wirft ein Thumbnailer, ein
> CDN oder ein Metadaten-Schritt das Manifest weg, bevor das Bild beim Nutzer
> ankommt. Es gibt keine Fehlermeldung, also fällt es niemandem auf. Beim
> Text-Wasserzeichen nach einem Modellwechsel ist es dieselbe Geschichte.
>
> Ich habe nichts gegen Ihre Systeme laufen lassen und werde das auch nicht tun.
> Falls es Ihnen nützt: github.com/Tippel-AI/markproof, Apache-2.0, es braucht
> eine Konfigurationsdatei und einen Staging-Endpunkt. Es gibt nichts zu kaufen
> und nichts zu registrieren.
>
> Mehr als über einen Nutzer würde ich mich über einen Widerspruch freuen: Wenn
> Sie in den Regelsatz sehen und eine Regel liest Artikel 50 Ihrer Ansicht nach
> falsch, schreiben Sie mir. Die Regeln stehen unter CC-BY und zitieren die
> Fundstelle, auf der sie beruhen — ich erfahre so etwas lieber von Ihnen als
> von einer Prüfstelle.
>
> Unabhängig davon: Die Nachrüstfrist für die maschinenlesbare Markierung endet
> am 2. Dezember 2026. Es lohnt sich, einmal nachzusehen, ob Ihre noch ankommt.
>
> Viele Grüße
> Lukas Friedrich
> Tippel · tippel.ai

### Was die Vorlage bewusst nicht enthält

Keine Frist im Betreff, kein „nur kurz“, kein Kalenderlink, kein zweiter
Absatz über den Nutzen für das Team. Der einzige Vorteil, der angeboten wird,
ist der Code selbst, und die einzige Bitte ist ein Widerspruch — was auch der
ehrlichste Stand der Sache ist, solange die Nachfrage so dünn ist wie jetzt.
