# APG Edition 1 fault-injection pilot report

## Result

The frozen pilot contains 24 cases: 4 valid controls and 20 blocking faults,
with 4 faults assigned to each of APG001-APG005. The full APG classified every
case as annotated (precision 1.00, recall 1.00, F1 1.00; 0 false positives and
0 false negatives).

| Method | Precision | Recall | F1 | False positives | False negatives |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 terminal-only | 0.00 | 0.00 | 0.00 | 0 | 20 |
| B1 PDF-only | 1.00 | 0.20 | 0.33 | 0 | 16 |
| B2 full APG | 1.00 | 1.00 | 1.00 | 0 | 0 |
| Leave out APG001 | 1.00 | 0.80 | 0.89 | 0 | 4 |
| Leave out APG002 | 1.00 | 1.00 | 1.00 | 0 | 0 |
| Leave out APG003 | 1.00 | 0.80 | 0.89 | 0 | 4 |
| Leave out APG004 | 1.00 | 0.80 | 0.89 | 0 | 4 |
| Leave out APG005 | 1.00 | 0.80 | 0.89 | 0 | 4 |

`LOO_APG002` retains full recall because all four APG002 fault fixtures also
cause APG003 to fail: without a successful Reporting report, there is no valid
Reporting artifact declaration. This pilot therefore does not show that APG002
is redundant; it exposes a dependency between the two checks in these fixtures.

## Runtime evidence

The authoritative recorded rerun on 2026-10-05 used bundled Python 3.12.14 and
executed 30 repetitions for each case, for 720 timed evaluations. Median gate
latency was 11.58445 ms and p95 was 23.923825 ms on this machine. Median serialized audit size was 4,602.5 bytes and
mean size was 4,572.3 bytes. These timings are local process measurements and
exclude PAPER RSI generation, model inference, and packaging.

The earlier 2026-09-30 pilot used Python 3.12.10 and reported a median of
8.745 ms and p95 of 12.503 ms. Those historical timings are a separate run;
they are not the current `results.json` values and are not pooled with the
2026-10-05 rerun. The fixture set and classification protocol are unchanged.

All 30 normalized outputs for every case were identical after removing only the
expected `evaluated_at` field. A separate full rerun reproduced every fixture
hash, rule status, decision, determinism flag, and token delta.

For ledgers that were valid enough to aggregate, the runner compared unique-call
token totals and ledger SHA-256 before and after gate evaluation. Across 20 such
fixtures, the measured input-plus-output token delta was 0 and every ledger was
byte-identical. This supports the narrower claim that APG itself added no model
tokens in this offline pilot.

## Evidence files

- `manifest.json` defines the frozen labels and mutations.
- `fixtures/` contains the materialized filesystem inputs.
- `audits/` contains one APG audit for every case.
- `results.json` is the authoritative machine-readable result, including exact
  unrounded metrics, timing distribution, source/manifest hashes, and case
  hashes.
- `results.csv` is the flat case-level export.
- `run_experiment.py` recreates every generated artifact using Python 3.12 and
  the APG implementation from the adjacent JiuwenSwarm checkout.

## Claim boundary

This is a specification-derived controlled pilot. Perfect classification on 24
hand-built cases does not demonstrate scientific correctness, semantic support
for claims, robustness to arbitrary corruption, or generalization to other
research-agent frameworks. The timing sample characterizes one local machine
run and should not be presented as a platform-independent performance bound.
