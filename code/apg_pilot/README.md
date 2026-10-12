# APG Edition 1 controlled pilot

This directory contains a frozen, offline, 24-case fault-injection pilot for the
Artifact Provenance Gate (APG). It evaluates artifact-integrity checks only. It
does not measure scientific correctness, citation semantics, or generalization
to other agent frameworks.

## Protocol

- `manifest.json`: 4 valid controls and 20 blocking faults, with four faults for
  each of APG001-APG005. Control C02 verifies that missing AUX evidence produces
  `APG005=SKIPPED` without blocking completion.
- `B0_terminal_only`: trusts the Provider's durable completed status and performs
  no artifact check. All fixtures enter after that boundary, so this baseline
  never blocks a case.
- `B1_pdf_only`: predicts a block only when APG001 rejects the final PDF.
- `B2_full_apg`: uses the complete APG decision.
- `LOO_APG001` through `LOO_APG005`: use the complete decision after excluding
  the named rule. These are decision-level leave-one-rule-out ablations; the
  implementation still evaluates all rules.
- Latency is measured with `perf_counter_ns` for 30 evaluations of every case
  (720 evaluations total). This is local process time, not end-to-end PAPER RSI
  latency.
- Determinism requires all 30 outputs for each case to be byte-equivalent after
  removing only `evaluated_at`.
- APG token delta is computed from valid unique call records before and after
  evaluation. Ledger SHA-256 is also compared. The gate makes no model call.
- Audit size uses the same UTF-8, two-space-indented JSON representation as the
  JiuwenSwarm integration helper.

## Reproduce

From this directory, with Python 3.12:

```powershell
py -3.12 .\run_experiment.py
```

The default source checkout is `..\jiuwenswarm`. To use another checkout:

```powershell
py -3.12 .\run_experiment.py --source-root D:\path\to\jiuwenswarm
```

The runner recreates `fixtures/` and `audits/`, then writes `results.json` and
`results.csv`. It uses only the Python standard library and performs no network
or model operation.

## Interpretation boundary

Precision, recall, and F1 are exact only for this deliberately small frozen
pilot. The cases are specification-derived and are not a representative sample
of all failures in research agents. Results must be reported as pilot evidence,
not as proof of scientific validity or universal framework coverage.
