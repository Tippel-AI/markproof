<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Security policy

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting
on `Tippel-AI/markproof` (Security → Report a vulnerability), or write to
<lukas.friedrich@tippel.ai>.

Include what you did, what happened, and what you expected. markproof is
maintained by a one-person company, so expect a first response within a few
working days rather than within hours.

## Supported versions

Pre-release. Only the latest published version of `markproof` receives fixes;
there are no maintenance branches yet.

| Version | Supported |
|---|---|
| 0.1.x (pre-release) | yes |
| anything older | no |

## What we consider security-relevant

markproof produces signed evidence, so anything that lets someone forge or
weaken that evidence is a vulnerability, not a bug:

- a manipulated `report.json` that still passes `markproof verify-report`;
- a canonicalisation or signing defect that makes two different reports produce
  the same signed bytes;
- a check that reports PASS on evidence which does not satisfy the rule — a
  false green is the worst failure mode this tool has;
- leakage of a signing key, an endpoint token or a SynthID watermark
  configuration into logs, reports, evidence artefacts or error messages;
- code execution triggered by a hostile config file, rulepack, endpoint response
  or media asset (probed endpoints and their responses are untrusted input).

## Handling secrets

Signing keys, endpoint tokens and watermark configurations are read from
environment variables or files referenced by the config. They never belong in
`markproof.yaml`, in the repository, or in a report artefact. Reports are meant
to be shared with auditors; treat everything that reaches them as public.
