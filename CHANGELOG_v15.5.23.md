# CHANGELOG — v15.5.23

## Fixed — broken currency symbol on the Classic register
The total showed a garbled "ê" because the markup used the HTML entity
`&#xea;` (Latin e-circumflex) where a currency symbol was intended.

- The register now shows the **actual company currency code** (e.g. SAR,
  AED) next to the total, read from the boot payload's company currency —
  so it's correct for any currency, not a hardcoded/garbled symbol.
- The currency tag updates when the terminal boots.
- Card-payment requests now use the resolved currency instead of a
  hardcoded "SAR".

Display uses the ISO code (SAR) rather than a glyph on purpose: the new
2025 Saudi Riyal symbol has almost no font support yet and renders as an
empty box, while "SAR" is unambiguous and prints/renders everywhere.
