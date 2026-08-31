# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The answer lattices the demo-bot's long chat replies are drawn from.

Kept apart from ``make_texts.py`` so each file reads as one thing: this one is
vocabulary, that one is algorithm.

A *lattice* is a document written as an alternating sequence of fixed literals
and choice slots. Rendering it means walking left to right and taking one
alternative per slot. Two renderings of the same lattice produce two texts of
the same length, register and content that differ only in word choice — which
is how a watermarked and an unwatermarked sample from one model differ, and the
reason the demo can attribute a mean-g gap to the marking rather than to the
prose.

WHY THE SLOTS ARE SMALL
-----------------------
A slot's leverage over the g-value statistic falls off as ``1/sqrt(tokens)``:
choosing between two sixteen-token sentences moves the mean far less than
choosing between two words, because the surrounding tokens dilute the choice.
An early draft of this file used whole-clause alternatives and could not push
mean-g past 0.58 no matter how wide the beam. So the pools here hold single
words and two-word fragments, and the skeleton sentences are assembled from
five or six of them. Slot count, not slot size, is what buys marking strength.

The same arithmetic explains why German and English behave differently under
one config: GPT-2's BPE spends about 3.4 tokens on a German word and 1.2 on an
English one, so the identical lattice design marks English text harder.
The two therefore land at different measured strengths, and both are
reported rather than averaged away.

GRAMMATICALITY
--------------
Pools hold phrases that are *syntactically interchangeable* in the slot that
uses them, so every combination a lattice spans is grammatical. Specifically:

* German sentence-initial adverbials all survive verb-second inversion, so no
  entry may be a clause of its own ("hinzu kommt" would strand the finite verb).
* The verb pool holds no separable verbs; a stranded prefix would have to
  travel past the object to the end of the clause.
* Every noun in ``DE_NOUN`` is feminine and every adjective in ``DE_ADJ`` ends
  in ``-e``, so ``eine <adj> <noun>`` stays correctly declined for every
  pairing.
* English adjectives are used predicatively ("an answer that is …"), which
  sidesteps the a/an agreement a prenominal slot would force.

ANCHORS
-------
The anchor sentences — disclosure, identity denial, standing notice — are
literals, never slots. They must survive every rendering verbatim, because the
Article 50(1) patterns in ``markproof/patterns/disclosure.de-en.yaml`` match on
them and the M1 rules hang off that. ``app.py`` re-checks their presence at
startup, so a regeneration that lost one cannot boot.

TOKENISATION
------------
Every unit carries its own leading separator (a space or a blank line) and
never a trailing one. GPT-2's pre-tokeniser splits *before* a leading space, so
a unit tokenised on its own yields the same ids as it does inside the finished
string; ``make_texts.py`` asserts that rather than trusting it. A unit starting
with a letter would let BPE merge across a slot boundary, and the incremental
search would then drift from the text it finally writes out.

Auflage H2 (own production only): every phrase below is written for this
repository. Nothing is sampled from a model or lifted from another assistant.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pick:
    """An enumeration: ``count`` distinct items drawn in order from ``pool``.

    This is the lattice's highest-variance construct and it carries most of the
    marking. A prose slot offers twenty alternatives spread over four or five
    tokens; a list position offers whatever is left of a forty-eight item pool
    over three, and there are a dozen of them in a row with only a comma
    between. Drawing *without* replacement is what keeps that honest — a list
    that repeated an entry would read as broken, and repeated items would feed
    the detector's context-repetition mask instead of the statistic.

    ``lead`` separates the list from the sentence before it, ``sep`` separates
    the items; both carry their separator the same way every other unit does.
    """

    pool: tuple[str, ...]
    count: int
    lead: str = " "
    sep: str = ", "

    def __post_init__(self) -> None:
        if self.count > len(self.pool):
            raise ValueError(f"Pick wants {self.count} of only {len(self.pool)} items")


#: A unit is a literal, a tuple of alternatives, or an enumeration.
Unit = str | tuple[str, ...] | Pick
Lattice = list[Unit]


def w(*alternatives: str) -> tuple[str, ...]:
    """A choice slot continuing the current sentence."""
    return tuple(" " + alternative for alternative in alternatives)


def s(text: str) -> str:
    """A literal continuing the current sentence."""
    return " " + text


def t(text: str) -> str:
    """A literal that joins tightly to what precedes it.

    For punctuation, which takes no space in front of it. GPT-2 pre-tokenises
    a full stop or comma as its own pretoken either way, so joining tightly is
    just as concatenation-stable as joining with a space.
    """
    return text


def p(text: str) -> str:
    """A literal opening a new paragraph."""
    return "\n\n" + text


def pw(*alternatives: str) -> tuple[str, ...]:
    """A choice slot opening a new paragraph."""
    return tuple("\n\n" + alternative for alternative in alternatives)


# ==========================================================================
# German pools
# ==========================================================================

#: Sentence-initial adverbials. Never a clause: verb-second must still work.
DE_ADV = (
    "Gerne",
    "Sehr gerne",
    "Selbstverständlich",
    "Natürlich",
    "Vorab",
    "Zunächst",
    "Kurz gesagt",
    "Im Kern",
    "Ganz konkret",
    "Grundsätzlich",
    "Im Regelfall",
    "Offen gesagt",
    "Klar gesagt",
    "Zur Einordnung",
    "Zur Orientierung",
    "Der Klarheit halber",
    "Der Ordnung halber",
    "In aller Kürze",
    "Ohne Umschweife",
    "Selbstredend",
    "Wie gewünscht",
    "Wie immer",
    "Sehr wohl",
    "Ausgesprochen gern",
)

#: First person singular, non-separable, taking dative plus accusative.
DE_VERB = (
    "erläutere",
    "erkläre",
    "schildere",
    "beschreibe",
    "zeige",
    "nenne",
    "skizziere",
    "umreiße",
    "präsentiere",
    "vermittle",
    "liefere",
    "biete",
    "gebe",
    "verschaffe",
    "unterbreite",
    "übermittle",
    "sende",
    "schicke",
    "formuliere",
    "entwerfe",
)

#: Feminine accusative, weak declension: every entry ends in -e, so
#: "eine <adj> <noun>" is correct for every pairing with DE_NOUN.
DE_ADJ = (
    "kurze",
    "klare",
    "knappe",
    "präzise",
    "sachliche",
    "geordnete",
    "nüchterne",
    "brauchbare",
    "verständliche",
    "sorgfältige",
    "belastbare",
    "vollständige",
    "übersichtliche",
    "durchdachte",
    "abgewogene",
    "strukturierte",
    "schlichte",
    "einfache",
    "genaue",
    "saubere",
    "gründliche",
    "zügige",
    "erste",
    "kompakte",
)

#: Feminine nouns only — see DE_ADJ.
DE_NOUN = (
    "Zusammenfassung",
    "Einordnung",
    "Übersicht",
    "Darstellung",
    "Erklärung",
    "Orientierung",
    "Auskunft",
    "Antwort",
    "Einschätzung",
    "Schilderung",
    "Erläuterung",
    "Aufstellung",
    "Gliederung",
    "Herleitung",
    "Zusammenstellung",
    "Beschreibung",
    "Skizze",
    "Auflistung",
    "Klarstellung",
    "Handreichung",
)

#: Dative noun phrases following "zu".
DE_TOPIC = (
    "Ihrer Frage",
    "Ihrem Anliegen",
    "Ihrem Vorhaben",
    "diesem Punkt",
    "diesem Thema",
    "Ihrer Situation",
    "Ihrem Fall",
    "der Sache",
    "Ihrem Wunsch",
    "Ihrer Anfrage",
    "dem Sachverhalt",
    "den offenen Punkten",
    "allem Weiteren",
    "den genannten Aspekten",
    "dem Vorgang",
    "Ihrer Fragestellung",
    "dem Ganzen",
    "der Ausgangslage",
    "dem Hintergrund",
    "Ihrem Thema",
)

#: How the answers come about. Adverbials after "Sie entstehen".
DE_ORIGIN = (
    "maschinell",
    "automatisch",
    "rechnerisch",
    "vollautomatisch",
    "algorithmisch",
    "programmgesteuert",
    "rein technisch",
    "Wort für Wort",
    "in Sekundenbruchteilen",
    "ohne menschliches Zutun",
    "ohne Zutun einer Person",
    "in einem Modell",
    "aus einem Sprachmodell",
    "durch Berechnung",
    "per Berechnung",
    "auf statistischem Weg",
    "Zeichen für Zeichen",
    "binnen Sekunden",
    "ohne Redaktion",
    "ohne Handarbeit",
)

#: Negative subjects for the "nobody checks them" clause.
DE_NOBODY = (
    "niemand",
    "kein Mensch",
    "keine Person",
    "keine Kollegin",
    "kein Kollege",
    "niemand sonst",
    "keine Redaktion",
    "keine Fachkraft",
    "kein Team",
    "keine Stelle",
    "kein Prüfer",
    "keine Aufsicht",
)

#: Transitive verbs of checking, third person singular.
DE_CHECK = (
    "prüft",
    "liest",
    "kontrolliert",
    "sichtet",
    "redigiert",
    "korrigiert",
    "bearbeitet",
    "überarbeitet",
    "begutachtet",
    "revidiert",
    "kennt",
    "sieht",
    "überprüft",
    "bewertet",
    "beurteilt",
    "verantwortet",
    "genehmigt",
    "bestätigt",
    "validiert",
    "autorisiert",
)

#: Temporal adverbials closing that clause.
DE_BEFORE = (
    "vorher",
    "zuvor",
    "vorab",
    "im Vorfeld",
    "vor dem Versand",
    "vor der Zustellung",
    "im Voraus",
    "vor der Ausgabe",
    "davor",
    "im Vorhinein",
    "rechtzeitig",
    "vorweg",
    "zwischendurch",
    "am Ende",
    "im Nachgang",
    "überhaupt",
)

#: What the user may always do. Verb-first, following an initial adverbial.
DE_INVITE = (
    "können Sie nachfragen",
    "dürfen Sie nachhaken",
    "können Sie widersprechen",
    "dürfen Sie mich korrigieren",
    "können Sie abbrechen",
    "dürfen Sie Belege verlangen",
    "können Sie Quellen verlangen",
    "können Sie mich unterbrechen",
    "dürfen Sie weiterfragen",
    "können Sie Klarheit verlangen",
    "können Sie einen Menschen verlangen",
    "dürfen Sie eine Prüfung verlangen",
    "können Sie mich stoppen",
    "dürfen Sie zweifeln",
    "können Sie das Thema wechseln",
    "können Sie neu ansetzen",
)

#: The assistant's half of that exchange, following "und ich".
DE_FOLLOWUP = (
    "komme darauf zurück",
    "greife das auf",
    "nehme das auf",
    "arbeite weiter",
    "stelle es klar",
    "formuliere es neu",
    "prüfe es erneut",
    "fasse es anders",
    "erläutere es genauer",
    "ordne es neu ein",
    "vertiefe den Punkt",
    "liefere Details nach",
    "ergänze das Fehlende",
    "korrigiere mich gern",
    "beginne von vorn",
    "setze neu an",
)

#: Dative plural, listed after "bei". Short on purpose: a list position's
#: leverage is per token, so a two-token noun buys more than a six-token
#: compound. Forty-eight entries, of which a rendering uses sixteen.
DE_CAN = (
    "Texten",
    "Listen",
    "Tabellen",
    "Fragen",
    "Notizen",
    "Ideen",
    "Plänen",
    "Terminen",
    "Formularen",
    "Berichten",
    "Briefen",
    "Mails",
    "Akten",
    "Mappen",
    "Ordnern",
    "Registern",
    "Glossaren",
    "Synonymen",
    "Begriffen",
    "Namen",
    "Titeln",
    "Themen",
    "Kapiteln",
    "Seiten",
    "Zeilen",
    "Wörtern",
    "Zitaten",
    "Belegen",
    "Quellen",
    "Verweisen",
    "Fußnoten",
    "Anreden",
    "Skizzen",
    "Grafiken",
    "Bildern",
    "Karten",
    "Kurven",
    "Linien",
    "Formen",
    "Farben",
    "Zahlen",
    "Daten",
    "Werten",
    "Maßen",
    "Mengen",
    "Summen",
    "Preisen",
    "Kosten",
    "Prozenten",
    "Formeln",
    "Codes",
    "Zeichen",
    "Symbolen",
    "Marken",
    "Sorten",
    "Typen",
    "Arten",
    "Klassen",
    "Gruppen",
    "Kriterien",
    "Regeln",
    "Mustern",
    "Trends",
    "Annahmen",
    "Risiken",
    "Optionen",
    "Zielen",
    "Punkten",
    "Schritten",
    "Etappen",
    "Phasen",
    "Runden",
    "Zyklen",
    "Reihen",
    "Spalten",
    "Feldern",
    "Rahmen",
    "Stufen",
    "Wegen",
    "Routen",
    "Pfaden",
    "Fristen",
    "Rollen",
    "Noten",
    "Ecken",
    "Kanten",
    "Winkeln",
    "Flächen",
    "Räumen",
    "Höhen",
    "Breiten",
    "Tiefen",
    "Bögen",
    "Zonen",
    "Heften",
    "Zetteln",
    "Karteien",
    "Quoten",
    "Raten",
    "Ketten",
    "Folgen",
    "Serien",
    "Perioden",
    "Spannen",
    "Grenzen",
    "Schwellen",
    "Skalen",
    "Achsen",
    "Knoten",
    "Signalen",
    "Pausen",
    "Bahnen",
    "Spuren",
    "Wellen",
    "Zellen",
    "Kacheln",
    "Rastern",
    "Gittern",
    "Netzen",
    "Maschen",
    "Paketen",
    "Stapeln",
    "Paaren",
    "Matrizen",
)

#: The refusal list. Bare nouns, so the introducing clause carries the syntax.
DE_CANNOT = (
    "Rechtsberatung",
    "Steuerberatung",
    "Atteste",
    "Diagnosen",
    "Gutachten",
    "Zusagen",
    "Garantien",
    "Freigaben",
    "Vertretungen",
    "Haftung",
    "Klagen",
    "Testamente",
    "Anzeigen",
    "Urteile",
    "Bescheide",
    "Policen",
    "Renten",
    "Beihilfen",
    "Darlehen",
    "Kredite",
    "Rabatte",
    "Ausnahmen",
    "Abfindungen",
    "Bussgelder",
    "Strafen",
    "Mahnungen",
    "Nachweise",
    "Prämien",
    "Quittungen",
    "Rechnungen",
    "Verträge",
    "Angebote",
    "Zahlungen",
    "Freibriefe",
    "Blankoschecks",
    "Vollmachten",
)

#: The disclosure. Matched by de-08 ("sie chatten … mit einem ki").
DE_DISCLOSURE = "Hinweis: Sie chatten mit einem KI-Assistenten, nicht mit einem Menschen."

#: The standing notice for later turns. Matched by de-13.
DE_NOTICE = "(KI-generierte Antwort)"

#: The answer to a direct identity question. Matched by de-10 and de-01.
DE_IDENTITY = "Nein, ich bin kein Mensch, sondern ein automatisiertes KI-System."


def de_body() -> Lattice:
    """The shared German body: what the assistant is, does and does not do.

    Deliberately short on prose. Every literal token is a token no slot can
    influence, and connecting phrases turned out to be the single largest drag
    on the achievable mean-g — an earlier draft with three more prose sentences
    lost about six points of it to their glue alone. What remains is one
    self-description, two enumerations and a closing offer.
    """
    return [
        # What it offers.
        pw(*DE_ADV),
        w(*DE_VERB),
        s("ich Ihnen eine"),
        w(*DE_ADJ),
        w(*DE_NOUN),
        s("zu"),
        w(*DE_TOPIC),
        t("."),
        # How the answers come about. There is deliberately no second
        # self-description sentence here: the disclosure anchor above already
        # carries the Article 50(1) statement, and a restatement of it cost
        # thirty-five literal tokens that no slot could lift off the null.
        p("Meine Antworten entstehen"),
        w(*DE_ORIGIN),
        t(", und"),
        w(*DE_NOBODY),
        w(*DE_CHECK),
        s("sie"),
        w(*DE_BEFORE),
        t("."),
        # What it can take on. The two enumerations are the lattice's densest
        # stretches of choice and carry most of the marking; the prose around
        # them exists so the answer still reads as an answer.
        p("Helfen kann ich bei"),
        Pick(DE_CAN, count=76),
        t("."),
        # Where it stops. This enumeration replaced a prose sentence that said
        # the same thing over forty tokens of five-token slots and scored
        # barely above the null — the trade this file is built around.
        p("Ausgeschlossen sind"),
        Pick(DE_CANNOT, count=20),
        t("."),
        # Closing.
        pw(*DE_ADV),
        w(*DE_INVITE),
        t(", und ich"),
        w(*DE_FOLLOWUP),
        t("."),
    ]


# ==========================================================================
# English pools — mirroring the German ones slot for slot
# ==========================================================================

EN_ADV = (
    "Gladly",
    "Of course",
    "Certainly",
    "By all means",
    "To be clear",
    "For clarity",
    "In short",
    "Briefly",
    "Up front",
    "First of all",
    "For completeness",
    "Concretely",
    "At its core",
    "As a rule",
    "Where it helps",
    "In most cases",
    "Plainly put",
    "Openly said",
    "As always",
    "Happily",
    "Right away",
    "For orientation",
    "In practice",
    "Very gladly",
)

EN_VERB = (
    "explain",
    "describe",
    "outline",
    "sketch",
    "set out",
    "lay out",
    "give",
    "offer",
    "provide",
    "supply",
    "present",
    "summarise",
    "draft",
    "prepare",
    "send",
    "share",
    "hand over",
    "put together",
    "pull together",
    "write up",
)

EN_ADJ = (
    "short",
    "clear",
    "concise",
    "precise",
    "factual",
    "orderly",
    "sober",
    "usable",
    "understandable",
    "careful",
    "defensible",
    "complete",
    "well ordered",
    "considered",
    "balanced",
    "structured",
    "plain",
    "simple",
    "exact",
    "clean",
    "thorough",
    "quick",
    "first",
    "compact",
)

EN_NOUN = (
    "summary",
    "overview",
    "account",
    "explanation",
    "orientation",
    "answer",
    "assessment",
    "description",
    "outline",
    "breakdown",
    "list",
    "note",
    "sketch",
    "briefing",
    "rundown",
    "statement",
    "clarification",
    "walkthrough",
    "digest",
    "readout",
)

EN_TOPIC = (
    "your question",
    "your request",
    "your plan",
    "this point",
    "this topic",
    "your situation",
    "your case",
    "the matter",
    "your wish",
    "your enquiry",
    "the facts",
    "the open points",
    "everything else",
    "the named aspects",
    "the process",
    "your problem",
    "the whole thing",
    "the starting point",
    "the background",
    "your subject",
)

EN_ORIGIN = (
    "by machine",
    "automatically",
    "computationally",
    "fully automatically",
    "algorithmically",
    "under program control",
    "purely technically",
    "word by word",
    "in fractions of a second",
    "without human involvement",
    "without a person involved",
    "inside a model",
    "out of a language model",
    "by calculation",
    "through computation",
    "on statistical grounds",
    "character by character",
    "within seconds",
    "without editing",
    "without handwork",
)

EN_NOBODY = (
    "nobody",
    "no human",
    "no person",
    "no colleague",
    "no editor",
    "no one else",
    "no newsroom",
    "no specialist",
    "no team",
    "no office",
    "no reviewer",
    "no supervisor",
)

EN_CHECK = (
    "checks",
    "reads",
    "controls",
    "screens",
    "edits",
    "corrects",
    "revises",
    "reworks",
    "reviews",
    "looks through",
    "knows",
    "sees",
    "verifies",
    "rates",
    "judges",
    "answers for",
    "approves",
    "confirms",
    "signs off",
    "clears",
)

EN_BEFORE = (
    "beforehand",
    "in advance",
    "up front",
    "ahead of time",
    "before sending",
    "before delivery",
    "in advance of that",
    "before release",
    "first",
    "previously",
    "in good time",
    "at the outset",
    "in between",
    "at the end",
    "afterwards",
    "at all",
)

EN_INVITE = (
    "you may ask again",
    "you may follow up",
    "you may contradict me",
    "you may correct me",
    "you may break off",
    "you may demand evidence",
    "you may demand sources",
    "you may interrupt me",
    "you may keep asking",
    "you may demand clarity",
    "you may demand a human",
    "you may demand a review",
    "you may stop me",
    "you may doubt me",
    "you may change the topic",
    "you may start over",
)

EN_FOLLOWUP = (
    "come back to it",
    "pick that up",
    "take that on",
    "keep working",
    "make it clear",
    "word it again",
    "check it again",
    "put it differently",
    "explain it more closely",
    "place it anew",
    "go deeper there",
    "supply details later",
    "fill in the gaps",
    "gladly correct myself",
    "start from scratch",
    "begin again",
)

#: Listed after "with" — the English counterpart of DE_CAN.
EN_CAN = (
    "texts",
    "lists",
    "tables",
    "questions",
    "answers",
    "notes",
    "ideas",
    "plans",
    "dates",
    "terms",
    "examples",
    "comparisons",
    "rules",
    "steps",
    "sources",
    "extracts",
    "drafts",
    "samples",
    "formulas",
    "numbers",
    "data",
    "titles",
    "names",
    "places",
    "quotes",
    "evidence",
    "points",
    "topics",
    "chapters",
    "paragraphs",
    "sentences",
    "words",
    "lines",
    "pages",
    "images",
    "maps",
    "charts",
    "curves",
    "values",
    "costs",
    "deadlines",
    "risks",
    "benefits",
    "drawbacks",
    "options",
    "variants",
    "goals",
    "tasks",
    "reports",
    "applications",
    "forms",
    "emails",
    "messages",
    "subject lines",
    "salutations",
    "sign-offs",
    "bullet points",
    "headings",
    "subtitles",
    "captions",
    "footnotes",
    "references",
    "indexes",
    "glossaries",
    "abbreviations",
    "technical terms",
    "loanwords",
    "synonyms",
    "opposites",
    "orderings",
    "priorities",
    "categories",
    "groups",
    "classes",
    "attributes",
    "criteria",
    "measures",
    "units",
    "conversions",
    "percentages",
    "shares",
    "totals",
    "differences",
    "averages",
    "ranges",
    "trends",
    "patterns",
    "outliers",
    "gaps",
    "contradictions",
    "assumptions",
    "citations",
    "sample sentences",
    "counterexamples",
    "check steps",
    "control questions",
)

EN_CANNOT = (
    "legal advice",
    "tax advice",
    "diagnoses",
    "expert opinions",
    "commitments",
    "guarantees",
    "approvals",
    "sureties",
    "certificates",
    "cost undertakings",
    "representation",
    "liability",
    "decisions",
    "personal ratings",
    "official statements",
    "binding deadlines",
    "contract details",
    "audit reports",
    "sick notes",
    "powers of attorney",
    "permits",
    "certifications",
    "credit notes",
    "refunds",
    "terminations",
    "reminders",
    "contracts",
    "quotes",
    "invoices",
    "receipts",
    "proofs",
    "attestations",
    "legal opinions",
    "investment advice",
    "credit commitments",
    "insurance commitments",
    "dismissal protection",
    "deadline extensions",
    "official acts",
    "notarisations",
    "signatures",
    "enforcement",
    "objections",
    "lawsuits",
    "filings",
    "criminal complaints",
    "wills",
    "enforcement orders",
)

#: Matched by en-08 and en-04.
EN_DISCLOSURE = "Note: you are chatting with an AI assistant, not with a human."

#: Matched by en-13.
EN_NOTICE = "(AI-generated response)"

#: Matched by en-10 and en-01.
EN_IDENTITY = "No, I am not a human. I am an automated AI system."


def en_body() -> Lattice:
    """The shared English body, mirroring ``de_body`` structure for structure.

    The enumerations run longer than the German ones. GPT-2 spends about 1.2
    tokens on an English word against 3.4 on a German one, so matching German's
    token count — and clearing the 250-token floor the detector needs — takes
    more items, not more prose.
    """
    return [
        pw(*EN_ADV),
        t(", I will"),
        w(*EN_VERB),
        s("a"),
        w(*EN_ADJ),
        w(*EN_NOUN),
        s("on"),
        w(*EN_TOPIC),
        t("."),
        p("My replies arise"),
        w(*EN_ORIGIN),
        t(", and"),
        w(*EN_NOBODY),
        w(*EN_CHECK),
        s("them"),
        w(*EN_BEFORE),
        t("."),
        p("I can help with"),
        Pick(EN_CAN, count=68),
        t("."),
        p("Ruled out are"),
        Pick(EN_CANNOT, count=30),
        t("."),
        pw(*EN_ADV),
        t(","),
        w(*EN_INVITE),
        t(", and I will"),
        w(*EN_FOLLOWUP),
        t("."),
    ]


# ==========================================================================
# The eight documents the demo-bot serves
# ==========================================================================
#: ``kind`` is whether the user asked outright what they are talking to;
#: ``turn`` is whether this is the opening answer. Together they reproduce the
#: four branches of ``build_answer`` in ``app.py``, which must not drift from
#: this list — a missing file stops the bot at startup.
KINDS = ("generic", "identity")
TURNS = ("first", "later")


def lattices() -> dict[str, Lattice]:
    """Every answer variant, keyed ``<lang>-<kind>-<turn>``.

    On the first turn the disclosure opens the answer, because that is what the
    position rule reads. On later turns the standing notice closes it. An
    identity question is answered before the body in both cases: the denial is
    the answer, the body is the elaboration.
    """
    out: dict[str, Lattice] = {}
    for lang, disclosure, notice, identity, body in (
        ("de", DE_DISCLOSURE, DE_NOTICE, DE_IDENTITY, de_body),
        ("en", EN_DISCLOSURE, EN_NOTICE, EN_IDENTITY, en_body),
    ):
        for kind in KINDS:
            for turn in TURNS:
                head: Lattice = []
                if turn == "first":
                    head.append(disclosure)
                    if kind == "identity":
                        head.append(p(identity))
                elif kind == "identity":
                    head.append(identity)
                doc = head + body()
                if turn == "later":
                    doc.append(p(notice))
                out[f"{lang}-{kind}-{turn}"] = doc
    return out
