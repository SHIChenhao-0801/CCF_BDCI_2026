"""Exact independent-auditor science functions; no network or host calls."""
from collections import Counter
import hashlib,itertools,json,math,operator
from pathlib import Path
ARMS=("initial","blindretry","verifiedretry","lengthmatchedretry")
RECONSIDER="Reconsider your previous answer and return only the requested final JSON object."
NEUTRAL="Check your answer carefully. "

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal(path, final):
    records, truncated = [], 0
    data = path.read_bytes() if path.exists() else b""
    lines = data.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line, object_pairs_hook=unique_object))
        except ValueError:
            if final or index != len(lines) - 1:
                raise
            truncated += 1
    return records, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "records": len(records), "partial_last_line": truncated}


def fingerprint(task):
    spec = dict(task["spec"])
    if task["family"] == "sat":
        spec["clauses"] = sorted({tuple(sorted(clause)) for clause in spec["clauses"]})
    elif task["family"] == "graph":
        spec["edges"] = sorted((min(a, b), max(a, b), w) for a, b, w in spec["edges"])
    return hashlib.sha256(json.dumps([task["family"], spec], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def distances(spec):
    n = spec["n"]
    table = [[0 if a == b else math.inf for b in range(n)] for a in range(n)]
    for a, b, weight in spec["edges"]:
        assert 0 <= a < b < n and type(weight) is int and weight > 0
        table[a][b] = table[b][a] = min(table[a][b], weight)
    for via in range(n):
        for a in range(n):
            for b in range(n):
                table[a][b] = min(table[a][b], table[a][via] + table[via][b])
    return table


def score(task, content):
    try:
        answer = json.loads(content, object_pairs_hook=unique_object)
        spec, family = task["spec"], task["family"]
        if not isinstance(answer, dict):
            return False, {"error": "json_object_required"}
        if family == "arithmetic":
            if set(answer) != {"answer"} or type(answer["answer"]) is not int:
                return False, {"error": "integer_answer_schema"}
            expected = spec["start"]
            for symbol, operand in spec["ops"]:
                expected = {"+": operator.add, "-": operator.sub, "*": operator.mul}[symbol](expected, operand)
            if answer["answer"] != expected:
                return False, {"error": "sequential_arithmetic_mismatch"}
        elif family == "sat":
            bits = answer.get("assignment")
            if set(answer) != {"assignment"} or not isinstance(bits, list) or len(bits) != spec["n"] or any(type(bit) is not int or bit not in (0, 1) for bit in bits):
                return False, {"error": "binary_assignment_schema"}
            for index, clause in enumerate(spec["clauses"], 1):
                if not any(bool(bits[abs(lit) - 1]) == (lit > 0) for lit in clause):
                    return False, {"error": "clause_unsatisfied", "clause_index": index}
        else:
            path = answer.get("path")
            if set(answer) != {"path", "cost"} or not isinstance(path, list) or len(path) < 2 or type(answer["cost"]) is not int or any(type(v) is not int or v not in range(spec["n"]) for v in path):
                return False, {"error": "path_schema"}
            if path[0] != spec["source"] or path[-1] != spec["target"] or len(set(path)) != len(path):
                return False, {"error": "path_endpoints_or_repetition"}
            edges = {(a, b): weight for a, b, weight in spec["edges"]}
            edges.update({(b, a): weight for a, b, weight in spec["edges"]})
            if any((a, b) not in edges for a, b in zip(path, path[1:])):
                return False, {"error": "nonexistent_edge"}
            cost = sum(edges[a, b] for a, b in zip(path, path[1:]))
            if answer["cost"] != cost:
                return False, {"error": "path_cost_mismatch"}
            if cost != distances(spec)[spec["source"]][spec["target"]]:
                return False, {"error": "path_not_shortest"}
        return True, None
    except (ValueError, TypeError, KeyError):
        return False, {"error": "invalid_json_or_schema"}


def instructions(feedback):
    diagnostic = RECONSIDER + "\nDeterministic checker feedback: " + json.dumps(feedback, separators=(",", ":"))
    repetitions, remainder = divmod(len(diagnostic) - len(RECONSIDER) - 1, len(NEUTRAL))
    return {"blindretry": RECONSIDER, "verifiedretry": diagnostic,
            "lengthmatchedretry": RECONSIDER + "\n" + NEUTRAL * repetitions + "." * remainder}


def initial_prompt(task):
    spec = task["spec"]
    if task["family"] == "arithmetic":
        wording = 'Apply ops sequentially to start, using exact integer arithmetic. Return {"answer": integer}.'
        ordered = {"start": spec["start"], "ops": spec["ops"]}
    elif task["family"] == "sat":
        wording = 'Find any satisfying assignment for this CNF. Each clause is OR, clauses combine by AND, positive literals mean x_i and negative literals mean NOT x_i. Return {"assignment": [0 or 1 for x_1 through x_n]}. All instances are satisfiable.'
        ordered = {"n": spec["n"], "clauses": spec["clauses"]}
    else:
        wording = 'Find a shortest simple path from source to target in this undirected positive-weight graph. Each edge is [a,b,weight]. Return {"path": [integer vertices], "cost": integer total weight}. Any tied optimum is accepted.'
        ordered = {"n": spec["n"], "edges": spec["edges"], "source": spec["source"], "target": spec["target"]}
    return wording + "\nInput: " + json.dumps(ordered, separators=(",", ":")) + "\nOutput only the requested JSON object, without code fences or other keys."


def compare(rows, control):
    better = sum(r["verifiedretry"] and not r[control] for r in rows)
    worse = sum(r[control] and not r["verifiedretry"] for r in rows)
    n = better + worse
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(better, worse) + 1)) / 2 ** n) if n else 1.0
    return {"diagnostic_only_correct": better, "control_only_correct": worse,
            "difference": (better - worse) / len(rows), "exact_mcnemar_p_two_sided": p}


def wilson(count, n):
    z, proportion = 1.959963984540054, count / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return [max(0, center - radius), min(1, center + radius)]
