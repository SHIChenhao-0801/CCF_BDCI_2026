"""Fixed supplementary task-level paired percentile bootstrap; no API calls."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from random import Random

REPLICATES = 10000
SEED = 20261008
CONFIDENCE_LEVEL = .95


def linear_quantile(values, probability):
    if not values or not 0 <= probability <= 1:
        raise ValueError("A nonempty sample and probability in [0,1] are required.")
    ordered = sorted(values)
    h = (len(ordered) - 1) * probability
    left, right = math.floor(h), math.ceil(h)
    return ordered[left] + (ordered[right] - ordered[left]) * (h - left)


def paired_percentile_interval(b, w, n, planned_n):
    if any(type(value) is not int for value in (b, w, n, planned_n)):
        raise ValueError("Pair counts and denominators must be integers, excluding bool.")
    if b < 0 or w < 0 or n <= 0 or b + w > n or planned_n < n:
        raise ValueError("Require nonnegative discordances, b+w<=n>0 and planned_n>=n.")
    differences = [1] * b + [-1] * w + [0] * (n - b - w)
    rng = Random(SEED)
    means = [sum(differences[rng.randrange(n)] for _ in range(n)) / n
             for _ in range(REPLICATES)]
    missing = planned_n - n
    return {"diagnostic_only": b, "comparator_only": w, "complete_pairs": n,
        "planned_items": planned_n, "missing_items": missing,
        "paired_difference": (b - w) / n,
        "ci95": [linear_quantile(means, .025), linear_quantile(means, .975)],
        "method": "supplementary paired percentile bootstrap with linear quantiles",
        "replicates": REPLICATES, "seed": SEED, "confidence_level": CONFIDENCE_LEVEL,
        "complete_case_conditional": missing > 0,
        "uncertainty_scope": "empirical complete-task distribution; no resampling of model generations",
        "full_planned_missing_difference_bounds": [(b - w - missing) / planned_n,
                                                     (b - w + missing) / planned_n],
        "missing_bounds_are_confidence_intervals": False,
        "missing_mechanism_assumption": "none; not MCAR or MAR",
        "primary_exact_mcnemar_replaced": False}


def analyze_cohort(summary):
    planned = {"old600": 600, "reused375": 375, "new240": 240}
    cohort = summary["cohort"]
    if cohort not in planned or summary["planned_n"] != planned[cohort]:
        raise ValueError("Use one registered cohort and its original planned denominator.")
    audit_digest = summary["independent_raw_audit_sha256"]
    if not isinstance(audit_digest, str) or len(audit_digest) != 64 or any(c not in "0123456789abcdef" for c in audit_digest):
        raise ValueError("A frozen independent raw-audit SHA256 receipt is required.")
    if not summary["contrasts"]:
        raise ValueError("At least one explicitly labelled audited contrast is required.")
    results = [{"name": contrast["name"], **paired_percentile_interval(
        contrast["b"], contrast["w"], summary["n"], summary["planned_n"])}
        for contrast in summary["contrasts"]]
    return {"cohort": cohort, "source_summary": copy.deepcopy(summary), "contrasts": results,
        "analysis_timing": "supplement_plan_fixed_before_first_initial_call" if cohort == "new240" else "posthoc_supplementary",
        "cohorts_pooled": False, "primary_exact_mcnemar_replaced": False,
        "audit_identity_role": "caller-supplied frozen audit receipt; this helper does not audit raw responses",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="One cohort's independently audited b/w/n summary JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError("The output must not overwrite its input.")
    raw = args.input.read_bytes()
    result = analyze_cohort(json.loads(raw))
    result["summary_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cohort": result["cohort"], "contrasts": len(result["contrasts"]), "model_calls": 0}))


if __name__ == "__main__":
    main()
