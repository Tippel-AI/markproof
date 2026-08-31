<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Media fixtures — provenance record

**Hard rule (Auflage H2): every asset in this directory is our own production.**
No third-party copyrighted media enters the repository — not even a "harmless"
example image from the web. Assets are generated locally and signed with
`c2patool` (development-only tool; it is never a runtime requirement for users).
Official CAI test assets may be read from the c2pa-rs repository during
development, but are never copied in here.

Each fixture gets a row below before it is committed.

| File | Format | Generator / method | Created | Signed with | Variant | License |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

Variants planned for the M2 matrix: `signed`, `unsigned`, `stripped` (metadata
removed), `tampered` (one byte flipped, so the hash binding breaks) and
`wrong-assertion`, across PNG, JPEG, MP4 and WAV.

- TODO(M2): generate the assets, sign them, fill in this table, and record the
  `c2patool` version used for each signature.
