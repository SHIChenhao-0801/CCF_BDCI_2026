# Offline post-hoc analyses

Run `python replay_posthoc.py` from this directory, or pass the script path from another working directory. Python 3.12 and the standard library suffice; all scientific inputs are in the parent evidence directory. The original scientific manifest is left unchanged. Socket/network access is disabled by the reused frozen replay.

The script regenerates per-item classifications from the original three raw call segments, checks the parent source manifest and request/calibration contract, and independently reproduces all six task cells, 150 paired output measurements, successful phase usage and the exact illustrative SAT request/response. It compares these with the saved independent exports and writes `replay-proof.json`. The saved `evidence.json` retains its original workspace-relative provenance keys; the portable proof identifies the corresponding delivered raw/source paths and hashes. Neither file claims new model calls.

These analyses are descriptive and post-hoc. Input-token matching does not control output length, padding semantics, time or hidden compute. No individual cell reaches unadjusted p < .05. The equal-output subset is outcome-conditioned sensitivity only. Missing calls are retained as missing and never resent. The exact SAT example was selected after outcomes and is not a new benchmark.
