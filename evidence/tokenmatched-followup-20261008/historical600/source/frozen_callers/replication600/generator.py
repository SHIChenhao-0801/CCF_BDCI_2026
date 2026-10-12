"""Fresh stratified instances from the original task distribution, without API calls."""
import hashlib
import itertools
import json
import operator
from pathlib import Path
import random

import legacy_runner as baseline

ROOT = Path(__file__).resolve().parent
SEED = 20261007
FAMILIES = ("arithmetic", "sat", "graph")
RETRIES = ("blindretry", "verifiedretry", "lengthmatchedretry")
ORDERS = tuple(itertools.permutations(RETRIES))


def fingerprint(task):
    spec = dict(task["spec"])
    if task["family"] == "sat":
        spec["clauses"] = sorted({tuple(sorted(c)) for c in spec["clauses"]})
    elif task["family"] == "graph":
        spec["edges"] = sorted((min(a, b), max(a, b), w) for a, b, w in spec["edges"])
    data = json.dumps([task["family"], spec], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def make_dataset():
    old = json.loads((ROOT / "legacy-dataset.json").read_text("utf-8"))
    seen = {fingerprint(t) for t in old}
    counts = {(f, d): 0 for f in FAMILIES for d in ("easy", "hard")}
    tasks, seeds = [], []
    old_seed = baseline.SEED
    try:
        for batch in range(64):
            baseline.SEED = SEED + batch
            seeds.append(baseline.SEED)
            for candidate in baseline.make_dataset():
                cell = candidate["family"], candidate["difficulty"]
                signature = fingerprint(candidate)
                if counts[cell] == 100 or signature in seen:
                    continue
                number = counts[cell]
                offset = FAMILIES.index(cell[0]) * 2 + (cell[1] == "hard")
                candidate["id"] = f"{cell[0]}-replication600-{cell[1]}-{number + 1:02}"
                candidate["split"] = "fresh_eval"
                candidate["retry_order"] = list(ORDERS[(number + offset) % 6])
                candidate["instance_sha256"] = signature
                tasks.append(candidate)
                counts[cell] += 1
                seen.add(signature)
            if len(tasks) == 600:
                break
        if len(tasks) != 600:
            raise RuntimeError("Could not construct the registered replication600 instances")
    finally:
        baseline.SEED = old_seed
    random.Random(SEED + 99).shuffle(tasks)
    return tasks, seeds


def independent_oracle_check(tasks):
    operations = {"+": operator.add, "-": operator.sub, "*": operator.mul}
    for task in tasks:
        spec, family = task["spec"], task["family"]
        assert baseline.check(task, json.dumps(task["oracle"]))[0], task["id"]
        if family == "arithmetic":
            value = spec["start"]
            for symbol, operand in spec["ops"]:
                value = operations[symbol](value, operand)
            assert value == task["oracle"]["answer"], task["id"]
        elif family == "sat":
            satisfying = [bits for bits in itertools.product((0, 1), repeat=spec["n"])
                          if all(any(bits[abs(lit) - 1] == (lit > 0) for lit in clause)
                                 for clause in spec["clauses"])]
            assert satisfying and tuple(task["oracle"]["assignment"]) in satisfying, task["id"]
        else:
            n = spec["n"]
            distance = [[0 if a == b else float("inf") for b in range(n)] for a in range(n)]
            for a, b, weight in spec["edges"]:
                assert 0 <= a < b < n and weight > 0
                distance[a][b] = distance[b][a] = weight
            for via in range(n):
                for a in range(n):
                    for b in range(n):
                        distance[a][b] = min(distance[a][b], distance[a][via] + distance[via][b])
            assert task["oracle"]["cost"] == distance[spec["source"]][spec["target"]], task["id"]

