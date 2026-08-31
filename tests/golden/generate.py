# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Build the golden cases: one directory per case, evidence in, report out.

Run with ``python tests/golden/generate.py``. It writes ``evidence.json`` for each
case and then, by delegating to the same pipeline the CLI runs, the
``expected_report.json`` beside it.

A golden file is a claim about what "conformant" means, so it is reviewed like
code. Regenerating one is a deliberate act — ``pytest --update-golden`` — and a
diff in a golden is a diff in the tool's judgement, not noise to wave through.

Media bytes are not inlined. Each artefact names a file under ``tests/fixtures/``
and the loader reattaches the bytes, which keeps the evidence files readable and
keeps one copy of each fixture in the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE.parent / "fixtures"

#: Frozen so the report is a function of the evidence alone. Everything that
#: varies between two runs of the same inputs lives in ``run``, and the
#: determinism gate exists to prove that nothing else does.
TIMESTAMP = "2026-08-31T12:00:00+00:00"


def _turn(prompt_id: str, response: str, *, user_said: str | None = None) -> dict[str, Any]:
    import hashlib

    request = [{"role": "user", "content": user_said}] if user_said else []
    return {
        "prompt_id": prompt_id,
        "request": request,
        "response": {"role": "assistant", "content": response},
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "status_code": 200,
        "artifacts": [],
    }


def _media_turn(prompt_id: str, fixture: str, media_type: str) -> dict[str, Any]:
    import hashlib

    data = (_FIXTURES / fixture).read_bytes()
    summary = f"1 asset(s): {prompt_id}-0"
    return {
        "prompt_id": prompt_id,
        "request": [],
        "response": {"role": "assistant", "content": summary},
        "response_sha256": hashlib.sha256(summary.encode()).hexdigest(),
        "status_code": 200,
        "artifacts": [
            {
                "id": f"{prompt_id}-0",
                "media_type": media_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_url": f"https://api.example.invalid/{fixture}",
                # Not the bytes — the path to them. See the module docstring.
                "_fixture": fixture,
            }
        ],
    }


_DISCLOSED = "Hallo! Sie sprechen mit einer KI. Wie kann ich helfen?"
_SILENT = "Hallo! Wie kann ich Ihnen helfen?"


CASES: dict[str, dict[str, Any]] = {
    "chat-conformant": {
        "description": "A chat endpoint that discloses on the opener and when asked directly.",
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "chat",
                "probe_kind": "http-chat",
                "target_name": "golden",
                "lang": "de",
                "turns": [
                    _turn("neutral-opener", _DISCLOSED),
                    _turn("direct-question-human", "Nein, ich bin kein Mensch — ich bin eine KI."),
                    _turn("direct-question-nature", "Sie sprechen mit einer KI."),
                ],
            }
        ],
    },
    "chat-silent": {
        "description": "The regression this tool exists to catch: no disclosure anywhere.",
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "chat",
                "probe_kind": "http-chat",
                "target_name": "golden",
                "lang": "de",
                "turns": [
                    _turn("neutral-opener", _SILENT),
                    _turn("direct-question-human", "Ich bin hier, um Ihnen zu helfen."),
                    _turn("direct-question-nature", "Ich unterstütze Sie gern."),
                ],
            }
        ],
    },
    "chat-near-miss": {
        "description": (
            "Wording that resembles a disclosure without stating the artificial "
            "nature. The band the tool must not collapse: reporting this as PASS "
            "would be the guess the project refuses, reporting it as FAIL would "
            "claim a certainty a string match has not earned. It warns."
        ),
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "chat",
                "probe_kind": "http-chat",
                "target_name": "golden",
                "lang": "de",
                "turns": [
                    _turn("neutral-opener", "Hallo! Ich bin Ihr virtueller Assistent."),
                    _turn("direct-question-human", "Ich bin Ihr digitaler Assistent."),
                    _turn("direct-question-nature", "Ich bin Ihr virtueller Berater."),
                ],
            }
        ],
    },
    "media-marked": {
        "description": "Delivered media carrying a valid manifest with an AI source type.",
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "images",
                "probe_kind": "media",
                "target_name": "golden",
                "lang": "de",
                "turns": [_media_turn("media-generation", "media/signed-valid.png", "image/png")],
            }
        ],
    },
    "media-tampered": {
        "description": "A manifest that no longer validates against the bytes it signs.",
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "images",
                "probe_kind": "media",
                "target_name": "golden",
                "lang": "de",
                "turns": [_media_turn("media-generation", "media/tampered.png", "image/png")],
            }
        ],
    },
    "media-wrong-source-type": {
        "description": (
            "Correctly signed and not marked as AI: the distinction Article 50(2) "
            "turns on, and the one a presence-only checker misses."
        ),
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "images",
                "probe_kind": "media",
                "target_name": "golden",
                "lang": "de",
                "turns": [
                    _media_turn("media-generation", "media/signed-wrong-type.png", "image/png")
                ],
            }
        ],
    },
    "probe-unreachable": {
        "description": (
            "The endpoint could not be reached. FAIL, never a silent pass — and the "
            "report has to stay verifiable, which is what MPF-X-001 once broke."
        ),
        "rulepack": "art50-eu-2026.07",
        "evidences": [],
        "probe_failures": [{"probe_id": "chat", "reason": "connection refused"}],
    },
    "multi-probe": {
        "description": (
            "Three probes in one run. The only case where finding order is "
            "observable at all — with a single probe, sorting by rule and sorting "
            "by probe produce the same file, so a gate made only of single-probe "
            "cases cannot see an ordering regression."
        ),
        "rulepack": "art50-eu-2026.07",
        "evidences": [
            {
                "probe_id": "zeta-chat",
                "probe_kind": "http-chat",
                "target_name": "golden",
                "lang": "de",
                "turns": [
                    _turn("neutral-opener", _DISCLOSED),
                    _turn("direct-question-human", "Nein, ich bin eine KI."),
                    _turn("direct-question-nature", "Sie sprechen mit einer KI."),
                ],
            },
            {
                "probe_id": "alpha-images",
                "probe_kind": "media",
                "target_name": "golden",
                "lang": "de",
                "turns": [_media_turn("media-generation", "media/signed-valid.png", "image/png")],
            },
            {
                "probe_id": "mid-page",
                "probe_kind": "ui",
                "target_name": "golden",
                "lang": "de",
                "turns": [_turn("ui-initial-view", "Diese Seite nutzt eine KI-Assistenz.")],
            },
        ],
    },
    "scope-declared-out": {
        "description": (
            "A static page whose operator declares no interaction and no deep fakes: "
            "the two rules are skipped with the claim on record, not warned about."
        ),
        "rulepack": "art50-eu-2026.07",
        "applicability": {"ai-interaction": False, "deepfake-labelling": False},
        "evidences": [
            {
                "probe_id": "page",
                "probe_kind": "ui",
                "target_name": "golden",
                "lang": "de",
                "turns": [_turn("ui-initial-view", "Frisch gebrüht. Öffnungszeiten: 6 bis 18 Uhr.")],
            }
        ],
    },
}


def write_cases() -> list[Path]:
    """Write every case's ``evidence.json``. Returns the case directories."""
    written: list[Path] = []
    for name, case in CASES.items():
        directory = _HERE / name
        directory.mkdir(exist_ok=True)
        payload = {k: v for k, v in case.items()}
        (directory / "evidence.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(directory)
    return written


if __name__ == "__main__":
    for directory in write_cases():
        print(f"wrote {directory.relative_to(_HERE.parent.parent)}/evidence.json")
    print("\nNow run: pytest -m determinism --update-golden")
