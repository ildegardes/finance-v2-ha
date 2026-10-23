# Unicode13 F06 — attribution, source and retained notices

The Unicode Consortium, The Unicode Standard, Version 13.0.0 (2020).
https://www.unicode.org/versions/Unicode13.0.0/
Unicode and the Unicode Logo are registered trademarks of Unicode, Inc.

## Data and transformations

unicode13_primitives.json is the separately generated OF-L3-03 dataset, obtained
from the installed CPython 3.10.0 reference (unicodedata UCD 13.0.0 and full
str.casefold). It is not an original proprietary Unicode database. SHA-256:
DE81088662045384D1F0B07FDF53A40BEE297843782FE80BF1AAEA94383BAAA4.

Changes from the reference representation: decimal-codepoint JSON primitives
for canonical decomposition, canonical combining class, Mn and full casefold.
The independent unicode13_f06.py algorithm uses those fixed primitives,
algorithmic Hangul, NFD/full casefold/NFD and the documented U31-A13 policy.
No CPython executable or CPython source algorithm is incorporated in that module.
The complete reference Python LICENSE.txt is retained without changes as
PYTHON_REFERENCE_LICENSE.txt. No historical F11/C09 payload was accessed,
incorporated or reclassified by this review.

## Primary evidence and copyrights

All four primitive maps were compared in OF-L3-13 with the final official files:
https://www.unicode.org/Public/13.0.0/ucd/UnicodeData.txt
https://www.unicode.org/Public/13.0.0/ucd/CaseFolding.txt
https://www.unicode.org/Public/13.0.0/ucd/ReadMe.txt
The comparisons were equal; no runtime data was replaced or regenerated.

The final UCD ReadMe is dated 2020-03-06 and states © 2020 Unicode®, Inc.
CaseFolding-13.0.0.txt is dated 2019-09-08 and states © 2019 Unicode®, Inc.
Those source headers refer to the Unicode terms of use. The current official
terms define Data Files to include computer data under /Public/ and apply
Unicode License v3 unless a specific release/file indicates other terms:
https://www.unicode.org/copyright.html (definitions and permissions).

## Complete permission notices shipped with this package

- UNICODE_DATA_LICENSE_2020.txt retains the complete 1991–2020 Unicode copyright,
  permission, warranty disclaimer and name-use condition from the first notice
  block of Unicode's official ICU 67.1 release. The original heading is retained;
  it does not assert that the Finance application incorporates ICU code.
  Immutable source: https://raw.githubusercontent.com/unicode-org/icu/125e29d54990e74845e1546851b5afa3efab06ce/icu4c/LICENSE
- UNICODE_LICENSE_V3.txt retains the complete current Unicode License v3 as
  retrieved from https://www.unicode.org/license.txt on 2026-10-19, including
  copyright 1991–2026. It is an additional current notice, not a statement that
  License v3 was the text published with UCD13 in 2020.
- PYTHON_REFERENCE_LICENSE.txt preserves the full Python reference notices.

Keep these complete notices with copies of the data/software or associated
documentation. Preserve copyright, permission and disclaimers; do not use
copyright-holder names for endorsement without prior permission.

DOCUMENTARY_NOTICE_REQUIREMENTS=SATISFIED_OF_L3_13
PUBLICATION_AUTHORIZED=False
PRODUCTION_AUTHORIZED=False

This is a source-based technical/documentary review, not a legal opinion,
signature, institutional reply or automatic permission to publish this project.
Final package identity and operational release still require owner approval.
