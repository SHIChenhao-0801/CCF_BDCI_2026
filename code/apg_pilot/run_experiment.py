"""Reproduce the frozen APG Edition 1 fault-injection pilot offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
FIXTURES_DIR = ROOT / "fixtures"
AUDITS_DIR = ROOT / "audits"
RESULTS_JSON = ROOT / "results.json"
RESULTS_CSV = ROOT / "results.csv"
EVALUATED_AT = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)
REPETITIONS = 30
RULES = ["APG001", "APG002", "APG003", "APG004", "APG005"]


def load_gate(source_root: Path):
    module_path = (
        source_root
        / "jiuwenswarm"
        / "agents"
        / "harness"
        / "common"
        / "rsi"
        / "artifact_provenance_gate.py"
    )
    if not module_path.is_file():
        raise FileNotFoundError(f"APG implementation not found: {module_path}")
    spec = importlib.util.spec_from_file_location("apg_experiment_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load APG implementation: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, module_path


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def manager_payload(manager_run_id: str) -> dict[str, Any]:
    return {
        "reports": [
            {
                "report_id": "reporting:1:1",
                "module": "reporting",
                "mode": "run",
                "attempt": 1,
                "outcome": "succeeded",
                "artifact_paths": [
                    f"experiments/{manager_run_id}/design/report.md"
                ],
            }
        ]
    }


def valid_ledger_record() -> dict[str, Any]:
    return {
        "call_id": "call-001",
        "status": "succeeded",
        "model_call": {"tokens": {"input": 12, "output": 7}},
    }


def build_valid_fixture(case_dir: Path, manager_run_id: str) -> None:
    experiment = case_dir / "experiments" / manager_run_id
    write(experiment / "paper" / "main.pdf", b"%PDF-1.7\n% frozen pilot fixture\n")
    write(
        experiment / "paper" / "main.aux",
        "\\citation{alpha,beta}\n\\bibcite{alpha}{1}\n\\bibcite{beta}{2}\n",
    )
    write(experiment / "design" / "report.md", "# Reporting artifact\n")
    write(
        experiment / "manager" / "state.json",
        json.dumps(manager_payload(manager_run_id), sort_keys=True) + "\n",
    )
    write(
        case_dir / "model_calls.jsonl",
        json.dumps(valid_ledger_record(), sort_keys=True) + "\n",
    )


def mutate_fixture(case_dir: Path, manager_run_id: str, mutation: str) -> None:
    experiment = case_dir / "experiments" / manager_run_id
    pdf = experiment / "paper" / "main.pdf"
    aux = experiment / "paper" / "main.aux"
    state = experiment / "manager" / "state.json"
    ledger = case_dir / "model_calls.jsonl"

    if mutation == "none":
        return
    if mutation == "remove_aux":
        aux.unlink()
    elif mutation == "zero_citations":
        write(aux, "\\relax\n")
    elif mutation == "duplicate_call_id":
        row = json.dumps(valid_ledger_record(), sort_keys=True) + "\n"
        write(ledger, row + row)
    elif mutation == "missing_pdf":
        pdf.unlink()
    elif mutation == "empty_pdf":
        write(pdf, b"")
    elif mutation == "pdf_is_directory":
        pdf.unlink()
        pdf.mkdir()
    elif mutation == "missing_paper_directory":
        shutil.rmtree(pdf.parent)
    elif mutation == "missing_manager_state":
        state.unlink()
    elif mutation == "malformed_manager_json":
        write(state, "{not-json\n")
    elif mutation == "reports_not_list":
        write(state, json.dumps({"reports": {}}, sort_keys=True) + "\n")
    elif mutation == "reporting_failed":
        payload = manager_payload(manager_run_id)
        payload["reports"][0]["outcome"] = "failed"
        write(state, json.dumps(payload, sort_keys=True) + "\n")
    elif mutation in {
        "empty_artifact_paths",
        "absolute_artifact_path",
        "traversal_artifact_path",
        "missing_artifact",
    }:
        payload = manager_payload(manager_run_id)
        paths = {
            "empty_artifact_paths": [],
            "absolute_artifact_path": [r"C:\outside\report.md"],
            "traversal_artifact_path": ["../outside/report.md"],
            "missing_artifact": [
                f"experiments/{manager_run_id}/design/missing.md"
            ],
        }
        payload["reports"][0]["artifact_paths"] = paths[mutation]
        write(state, json.dumps(payload, sort_keys=True) + "\n")
    elif mutation == "missing_ledger":
        ledger.unlink()
    elif mutation == "empty_ledger":
        write(ledger, "")
    elif mutation == "malformed_ledger_row":
        write(ledger, "not-json\n")
    elif mutation == "negative_token_count":
        record = valid_ledger_record()
        record["model_call"]["tokens"]["input"] = -1
        write(ledger, json.dumps(record, sort_keys=True) + "\n")
    elif mutation == "one_unresolved_citation":
        write(aux, "\\citation{alpha,missing}\n\\bibcite{alpha}{1}\n")
    elif mutation == "multiple_unresolved_citations":
        write(aux, "\\citation{missing_a,missing_b}\n\\bibcite{alpha}{1}\n")
    elif mutation == "no_bibcite_records":
        write(aux, "\\citation{alpha,beta}\n")
    elif mutation == "invalid_utf8_aux":
        write(aux, b"\\citation{alpha}\n\xff\xfe")
    else:
        raise ValueError(f"Unknown mutation: {mutation}")


def fixture_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix()):
        relative = item.relative_to(path).as_posix()
        kind = b"D" if item.is_dir() else b"F"
        digest.update(kind + b"\0" + relative.encode("utf-8") + b"\0")
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


def canonical_audit_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def checks_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in payload["checks"]}


def prediction(payload: dict[str, Any], method: str) -> bool:
    checks = checks_by_id(payload)
    if method == "B0_terminal_only":
        # Every fixture is evaluated after the Provider has published a durable
        # completed terminal state. This baseline trusts that state alone.
        return False
    if method == "B1_pdf_only":
        return checks["APG001"]["status"] == "FAIL"
    if method == "B2_full_apg":
        return payload["decision"] == "BLOCKED"
    if method.startswith("LOO_"):
        omitted = method.removeprefix("LOO_")
        return any(
            check["severity"] == "blocker"
            and check["status"] == "FAIL"
            and check["id"] != omitted
            for check in payload["checks"]
        )
    raise ValueError(f"Unknown method: {method}")


def classification_metrics(truth: list[bool], predicted: list[bool]) -> dict[str, Any]:
    tp = sum(expected and actual for expected, actual in zip(truth, predicted))
    fp = sum(not expected and actual for expected, actual in zip(truth, predicted))
    fn = sum(expected and not actual for expected, actual in zip(truth, predicted))
    tn = sum(not expected and not actual for expected, actual in zip(truth, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def percentile(values: list[int], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def ledger_tokens(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    unique: dict[str, tuple[int, int]] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            call_id = record["call_id"]
            tokens = record["model_call"]["tokens"]
            values = (tokens["input"], tokens["output"])
            if (
                isinstance(call_id, str)
                and call_id
                and all(isinstance(value, int) and value >= 0 for value in values)
            ):
                unique.setdefault(call_id, values)
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        return None
    if not unique:
        return None
    return sum(v[0] for v in unique.values()), sum(v[1] for v in unique.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT.parent / "jiuwenswarm",
        help="JiuwenSwarm checkout containing the APG implementation.",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    if len(cases) != 24:
        raise AssertionError(f"Expected 24 cases, found {len(cases)}")
    gate_module, module_path = load_gate(args.source_root.resolve())

    for generated in (FIXTURES_DIR, AUDITS_DIR):
        if generated.exists():
            shutil.rmtree(generated)
        generated.mkdir(parents=True)

    methods = ["B0_terminal_only", "B1_pdf_only", "B2_full_apg"] + [
        f"LOO_{rule}" for rule in RULES
    ]
    rows: list[dict[str, Any]] = []
    timings: list[int] = []
    all_deterministic = True
    all_expectations_met = True
    token_deltas: list[int] = []
    ledger_unchanged: list[bool] = []

    for case in cases:
        manager_run_id = f"pilot-{case['id'].lower()}-iteration-001"
        case_dir = FIXTURES_DIR / case["id"]
        build_valid_fixture(case_dir, manager_run_id)
        mutate_fixture(case_dir, manager_run_id, case["mutation"])
        context = gate_module.GateContext(
            task_id=f"pilot-{case['id'].lower()}",
            manager_run_id=manager_run_id,
            iteration=1,
            run_dir=case_dir,
        )

        ledger = case_dir / "model_calls.jsonl"
        ledger_hash_before = hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.is_file() else None
        tokens_before = ledger_tokens(ledger)
        case_timings: list[int] = []
        payloads: list[dict[str, Any]] = []
        for repetition in range(REPETITIONS):
            started = time.perf_counter_ns()
            audit = gate_module.ArtifactProvenanceGate().evaluate(
                context,
                evaluated_at=EVALUATED_AT + timedelta(seconds=repetition),
            )
            case_timings.append(time.perf_counter_ns() - started)
            payloads.append(audit.as_dict())
        timings.extend(case_timings)

        normalized = []
        for payload in payloads:
            item = dict(payload)
            item.pop("evaluated_at", None)
            normalized.append(json.dumps(item, sort_keys=True, separators=(",", ":")))
        deterministic = len(set(normalized)) == 1
        all_deterministic = all_deterministic and deterministic

        payload = payloads[0]
        (AUDITS_DIR / f"{case['id']}.json").write_bytes(canonical_audit_bytes(payload))
        check = checks_by_id(payload).get(case["expected_rule"]) if case["expected_rule"] else None
        status_met = check is None or check["status"] == case["expected_status"]
        expectation_met = payload["decision"] == case["expected_decision"] and status_met
        all_expectations_met = all_expectations_met and expectation_met

        ledger_hash_after = hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.is_file() else None
        tokens_after = ledger_tokens(ledger)
        if tokens_before is not None and tokens_after is not None:
            delta = sum(tokens_after) - sum(tokens_before)
            token_deltas.append(delta)
            ledger_unchanged.append(ledger_hash_before == ledger_hash_after)

        row = {
            "case_id": case["id"],
            "group": case["group"],
            "mutation": case["mutation"],
            "should_block": case["should_block"],
            "expected_rule": case["expected_rule"],
            "expected_status": case["expected_status"],
            "actual_rule_status": check["status"] if check else None,
            "expected_decision": case["expected_decision"],
            "actual_decision": payload["decision"],
            "expectation_met": expectation_met,
            "fixture_sha256": fixture_hash(case_dir),
            "audit_size_bytes": len(canonical_audit_bytes(payload)),
            "latency_median_ns": statistics.median(case_timings),
            "latency_p95_ns": percentile(case_timings, 0.95),
            "deterministic_30_runs": deterministic,
            "apg_token_delta": (sum(tokens_after) - sum(tokens_before)) if tokens_before is not None and tokens_after is not None else None,
            "ledger_sha256_unchanged": (
                ledger_hash_before == ledger_hash_after
                if ledger_hash_before is not None and ledger_hash_after is not None
                else None
            ),
        }
        for method in methods:
            row[method] = prediction(payload, method)
        rows.append(row)

    truth = [bool(row["should_block"]) for row in rows]
    method_metrics: dict[str, Any] = {}
    for method in methods:
        predicted = [bool(row[method]) for row in rows]
        metrics = classification_metrics(truth, predicted)
        metrics["per_rule_recall"] = {
            rule: (
                sum(row[method] for row in rows if row["group"] == rule)
                / sum(row["group"] == rule for row in rows)
            )
            for rule in RULES
        }
        method_metrics[method] = metrics

    results = {
        "schema_version": "1.0",
        "experiment": "APG Edition 1 controlled fault-injection pilot",
        "scope_note": "This controlled 24-case pilot measures artifact-integrity fault detection only; it does not establish scientific correctness or cross-framework generality.",
        "source": {
            "module_path": module_path.relative_to(args.source_root.resolve()).as_posix(),
            "module_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
            "python": sys.version.split()[0],
        },
        "protocol": {
            "case_count": len(rows),
            "valid_control_count": sum(not value for value in truth),
            "blocking_fault_count": sum(truth),
            "repetitions_per_case": REPETITIONS,
            "total_timed_evaluations": len(timings),
            "fixed_first_evaluated_at": EVALUATED_AT.isoformat(),
        },
        "metrics": method_metrics,
        "runtime": {
            "latency_ns": {
                "count": len(timings),
                "median": statistics.median(timings),
                "mean": statistics.fmean(timings),
                "p95": percentile(timings, 0.95),
                "min": min(timings),
                "max": max(timings),
            },
            "audit_size_bytes": {
                "count": len(rows),
                "median": statistics.median(row["audit_size_bytes"] for row in rows),
                "mean": statistics.fmean(row["audit_size_bytes"] for row in rows),
                "min": min(row["audit_size_bytes"] for row in rows),
                "max": max(row["audit_size_bytes"] for row in rows),
            },
            "determinism": {
                "all_cases_identical_excluding_evaluated_at": all_deterministic,
                "repetitions_per_case": REPETITIONS,
            },
            "apg_model_tokens": {
                "measured_token_delta": sum(token_deltas),
                "measured_ledgers": len(token_deltas),
                "all_measured_ledgers_byte_identical": all(ledger_unchanged),
                "method": "Sum valid unique ledger token counts before and after APG evaluation and compare ledger SHA-256.",
            },
        },
        "validation": {
            "all_manifest_expectations_met": all_expectations_met,
            "all_deterministic": all_deterministic,
            "full_apg_perfect_on_frozen_pilot": method_metrics["B2_full_apg"]["fp"] == 0 and method_metrics["B2_full_apg"]["fn"] == 0,
        },
        "cases": rows,
    }
    RESULTS_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    csv_fields = list(rows[0].keys())
    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(rows)

    if not all_expectations_met or not all_deterministic:
        raise AssertionError("Pilot validation failed; inspect results.json")
    print(f"Wrote {RESULTS_JSON}")
    print(f"Wrote {RESULTS_CSV}")
    print(f"B2 F1: {method_metrics['B2_full_apg']['f1']:.3f}")
    print(f"Median latency: {statistics.median(timings) / 1_000_000:.3f} ms")
    print(f"Measured APG token delta: {sum(token_deltas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
