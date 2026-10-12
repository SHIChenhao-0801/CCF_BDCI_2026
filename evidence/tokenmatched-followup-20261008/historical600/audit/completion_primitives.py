"""Exact independent completion auditor functions."""
import ast
from datetime import datetime,timedelta
from pathlib import Path
from audit import base_primitives as base
from audit import continuation_primitives as amended
ARMS=base.ARMS

def generalized_recompute(tasks, calls, missing_ids):
    # The retained exact scientific function has one transport-only change: skip the registered missing-ID set.
    source = Path(amended.__file__).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "recompute")
    function = ast.get_source_segment(source, node)
    function = function.replace("def recompute(tasks, calls):", "def recompute(tasks, calls, missing_ids):", 1)
    function = function.replace('if task["id"] == FAILED_ITEM:', 'if task["id"] in missing_ids:', 1)
    function = function.replace("            break", "            continue")
    namespace = {"base": base, "ARMS": ARMS}
    exec(compile(function, "<exact-amended-recompute-with-missing-set>", "exec"), namespace)
    return namespace["recompute"](tasks, calls, missing_ids)


def missing_sensitivity(rows, missing):
    assert len(rows) + missing == 600
    result = {"planned_denominator": 600, "missing_items": missing, "not_an_imputed_dataset": True,
              "no_missing_at_random_assumption": True, "not_a_confidence_interval": True, "comparisons": {}}
    for name, control in (("primary", "lengthmatchedretry"), ("secondary_exploratory", "blindretry")):
        cases = []
        for i in range(missing + 1):
            for j in range(missing - i + 1):
                extension = ([{"verifiedretry": True, control: False}] * i
                    + [{"verifiedretry": False, control: True}] * j
                    + [{"verifiedretry": False, control: False}] * (missing - i - j))
                case = base.compare(rows + extension, control)
                cases.append({"missing_diagnostic_only": i, "missing_control_only": j, **case})
        observed = base.compare(rows, control)
        difference = observed["diagnostic_only_correct"] - observed["control_only_correct"]
        result["comparisons"][name] = {"observed_complete_case": observed, "enumerated_possible_missing_outcomes": cases,
            "p_value_range": [min(c["exact_mcnemar_p_two_sided"] for c in cases), max(c["exact_mcnemar_p_two_sided"] for c in cases)],
            "paired_difference_full600_range": [(difference - missing) / 600, (difference + missing) / 600],
            "paired_difference_percentage_point_range": [100 * (difference - missing) / 600, 100 * (difference + missing) / 600]}
    result["marginal_accuracy_full600_ranges"] = {a: [sum(r[a] for r in rows) / 600, (sum(r[a] for r in rows) + missing) / 600] for a in ARMS}
    return result


def verify_requests(tasks, records):
    """Check every attempted payload, including cost-only partial items and failed requests."""
    by_id = {t["id"]: t for t in tasks}
    groups = {}
    for record in records:
        groups.setdefault(record["call_key"], []).append(record)
    calls = {key: group[-1] for key, group in groups.items() if group[-1]["status"] == "ok"}
    per_item = {}
    for key, group in groups.items():
        prefix, item, arm = key.split(":")
        assert prefix == "7adae0c2cfac" and item in by_id and arm in ARMS
        assert len(group) in (1, 2) and group[0]["status"] == "started"
        if len(group) == 2:
            assert group[1]["status"] in ("ok", "error")
            assert group[0]["request"] == group[1]["request"] and group[0]["started_at"] == group[1]["started_at"]
        task = by_id[item]
        messages = [{"role": "user", "content": task["prompt"]}]
        if arm != "initial":
            initial = calls[prefix + ":" + item + ":initial"]
            correct, feedback = base.score(task, initial["content"])
            assert not correct, "Correct initial must be reused without retries"
            messages += [{"role": "assistant", "content": initial["content"]},
                         {"role": "user", "content": base.instructions(feedback)[arm]}]
        assert group[0]["request"] == {"model": "deepseek-flash", "messages": messages, "max_tokens": 2048,
            "temperature": 0, "stream": False, "thinking": {"type": "disabled"}}
        per_item.setdefault(item, []).append(group[0])
    for item, starts in per_item.items():
        starts.sort(key=lambda r: r["started_at"])
        arms = [r["call_key"].rsplit(":", 1)[1] for r in starts]
        assert arms == (["initial"] + by_id[item]["retry_order"])[:len(arms)], "Within-task order changed"
        for previous, current in zip(starts, starts[1:]):
            terminal = groups[previous["call_key"]][-1]
            assert terminal["status"] == "ok", "A task continued after failure"
            finished = datetime.fromisoformat(terminal["started_at"]) + timedelta(seconds=terminal["latency_seconds"])
            assert finished <= datetime.fromisoformat(current["started_at"]) + timedelta(milliseconds=2)
    return calls, groups, per_item
