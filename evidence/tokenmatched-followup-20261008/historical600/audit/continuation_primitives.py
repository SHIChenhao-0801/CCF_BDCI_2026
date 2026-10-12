"""Exact frozen continuation science functions."""
from collections import Counter
from audit import base_primitives as base
ARMS=base.ARMS
FAILED_ITEM="graph-replication600-easy-64"

def recompute(tasks, calls):
    rows, details, lengths, used, order = [], [], [], set(), []
    for task in tasks:
        if task["id"] == FAILED_ITEM:
            continue
        prefix = "7adae0c2cfac:" + task["id"]
        initial = calls.get(prefix + ":initial")
        if initial is None:
            break
        correct, feedback = base.score(task, initial["content"])
        needed = ["initial"] + ([] if correct else task["retry_order"])
        if any(prefix + ":" + arm not in calls for arm in needed):
            break
        retry = base.instructions(feedback) if not correct else {}
        row = {"id": task["id"], "family": task["family"], "difficulty": task["difficulty"]}
        item = {**row, "retry_order": task["retry_order"]}
        sizes = {}
        for arm in ARMS:
            key = prefix + ":" + ("initial" if correct else arm)
            reply = calls[key]
            messages = [{"role": "user", "content": task["prompt"]}]
            if arm != "initial" and not correct:
                messages += [{"role": "assistant", "content": initial["content"]}, {"role": "user", "content": retry[arm]}]
            assert reply["request"] == {"model": "deepseek-flash", "messages": messages, "max_tokens": 2048,
                                         "temperature": 0, "stream": False, "thinking": {"type": "disabled"}}
            valid, error = base.score(task, reply["content"])
            row[arm] = valid
            item[arm] = {"call_key": key, "correct": valid}
            if arm == "initial" or not correct:
                item[arm]["feedback"] = error
            if arm != "initial":
                item[arm]["reused_initial"] = correct
            if arm != "initial" and not correct:
                sizes[arm] = {"content_characters": sum(len(m["content"]) for m in messages),
                              "content_utf8_bytes": sum(len(m["content"].encode()) for m in messages)}
                item[arm]["request_lengths"] = sizes[arm]
            used.add(key)
        if not correct:
            assert sizes["verifiedretry"] == sizes["lengthmatchedretry"]
            lengths.append({"id": task["id"], "decoded_content_lengths": sizes["verifiedretry"], "matched_lengths_equal": True,
                "diagnostic_prompt_tokens": calls[prefix+":verifiedretry"]["usage"]["prompt_tokens"],
                "matched_prompt_tokens": calls[prefix+":lengthmatchedretry"]["usage"]["prompt_tokens"]})
        order.extend(prefix+":"+arm for arm in needed)
        rows.append(row)
        details.append(item)
    return rows, details, lengths, used, order


def statistics(rows, details, lengths, calls):
    n = len(rows)
    counts = {arm: sum(r[arm] for r in rows) for arm in ARMS}
    result = {"valid_eval_count": n, "correct_counts": counts,
        "accuracies": {a: counts[a] / n for a in ARMS}, "accuracy_wilson_95": {a: base.wilson(counts[a], n) for a in ARMS},
        "primary_diagnostic_vs_lengthmatched": base.compare(rows, "lengthmatchedretry"),
        "secondary_diagnostic_vs_generic": base.compare(rows, "blindretry"),
        "cell_counts": {f+":"+d: {a: sum(r[a] for r in rows if r["family"] == f and r["difficulty"] == d) for a in ARMS}
                        for f in ("arithmetic", "graph", "sat") for d in ("easy", "hard")},
        "cell_denominators": {f+":"+d: sum(r["family"] == f and r["difficulty"] == d for r in rows)
                        for f in ("arithmetic", "graph", "sat") for d in ("easy", "hard")},
        "initial_errors_repaired": {a: sum(not r["initial"] and r[a] for r in rows) for a in ARMS[1:]},
        "error_class_counts": {a: dict(Counter(r[a]["feedback"]["error"] for r in details if r[a].get("feedback"))) for a in ARMS},
        "actual_retry_orders": dict(Counter(",".join(r["retry_order"]) for r in details if not r["initial"]["correct"])),
        "diagnostic_minus_matched_prompt_tokens": [r["diagnostic_prompt_tokens"] - r["matched_prompt_tokens"] for r in lengths],
        "length_match_audit": lengths, "arm_usage_excludes_shared_initial": {}}
    for arm in ARMS:
        actual = [calls[r[arm]["call_key"]] for r in details if arm == "initial" or not r["initial"]["correct"]]
        result["arm_usage_excludes_shared_initial"][arm] = {"call_count": len(actual),
            "input_tokens": sum(r["usage"]["prompt_tokens"] for r in actual),
            "output_tokens": sum(r["usage"]["completion_tokens"] for r in actual),
            "client_call_seconds": sum(r["latency_seconds"] for r in actual)}
    return result
