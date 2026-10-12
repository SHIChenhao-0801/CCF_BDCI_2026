# Matching natbib source

The parent directory retains the original ICLR-distributed natbib.sty, version2009/07/16 8.31, with its original notice. This directory supplies its matching original natbib.dtx and natbib.ins, fetched from the official Debian historical texlive-base2009 source. Debian distribution copyright material is retained separately; no blanket MIT license is asserted for the template dependencies.

The source files retain all original headers. Actual TeX/docstrip generation with package,all exited0 and produced45154bytes exactly equal to the parent style, SHA25688bc70c0e48461934cab5b2accef06b74a8b3ac45ad03ccd3f2a6b7e0d6d530d. No header exclusion or line-ending normalization was used. Public source URLs, download times and byte hashes are in source-receipts.json; generation-binding.json binds the actual original generation receipt.

To regenerate for inspection, copy this directory to a separate writable work directory and run `tex -interaction=nonstopmode -halt-on-error natbib.ins`. Do not overwrite the frozen parent style or any reviewed PDF. The same unchanged style is used in retained historic paper evidence; this source material is included once in the delivered template tree.
