"""Original pure fixed240 numerical audit functions; internal workflow entry points excluded."""

import argparse

import ast

from collections import Counter

from datetime import datetime, timezone

import hashlib

import heapq

import importlib.util

import itertools

import json

from pathlib import Path

import random

ROOT = Path(__file__).resolve().parent

PROJECT = ROOT.parents[1]

STUDY = PROJECT / "process/tokenmatched-holdout240-20261008"

PREFIX = "tokenmatched-holdout240-20261008:"

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def historical_auditor():
    path = PROJECT / "process/tokenmatched-followup-20261008-independent-audit/audit.py"
    spec = importlib.util.spec_from_file_location("independent_prior_audit",path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.PREFIX = PREFIX
    return module

BASE = historical_auditor()

ORACLE = BASE.scorer_module()

def regenerated(excluded):
    # Only extract the historical generator's two pure functions, not its caller.
    path = PROJECT / "process/replication600/legacy_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {"shortest","make_dataset"}]
    assert len(nodes) == 2
    environment = {"random":random,"heapq":heapq,"json":json}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),environment)
    fingerprints = {ORACLE.fingerprint(task) for task in excluded}
    prompts = {task["prompt"] for task in excluded}
    counts = Counter();tasks=[];seeds=[]
    families = ("arithmetic","sat","graph")
    for batch in range(64):
        seed = 20261024 + batch;seeds.append(seed);environment["SEED"] = seed
        for task in environment["make_dataset"]():
            cell = task["family"],task["difficulty"]
            signature = ORACLE.fingerprint(task)
            if counts[cell] == 40 or signature in fingerprints or task["prompt"] in prompts:
                continue
            number = counts[cell]
            offset = families.index(cell[0])*2 + (cell[1]=="hard")
            choices = list(itertools.permutations(("full","neutral","coarse"))) if cell[0]=="sat" else [("full","neutral"),("neutral","full")]
            task.update(id=f"{cell[0]}-holdout240-{cell[1]}-{number+1:02}",split="independent_holdout",
                retry_order=list(choices[(number+offset)%len(choices)]),instance_sha256=signature)
            tasks.append(task);counts[cell]+=1;fingerprints.add(signature);prompts.add(task["prompt"])
        if len(tasks)==240:
            break
    assert len(tasks)==240, "Bounded generator cannot fill fixed240"
    random.Random(20261024+99).shuffle(tasks)
    return tasks,seeds

def initial_payload(task):
    return {"model":"deepseek-flash","messages":[{"role":"user","content":task["prompt"]}],"max_tokens":2048,
        "temperature":0,"stream":False,"thinking":{"type":"disabled"}}

def inspect_item(task,records):
    key = PREFIX + task["id"] + ":initial"
    if key not in records:
        return {"id":task["id"],"status":"unattempted","checked_keys":[],"initial_observed":False}
    record = records[key]
    assert record["request"]==initial_payload(task), "Initial request contract changed"
    if record["status"]!="ok":
        return {"id":task["id"],"status":record["status"],"checked_keys":[key],"initial_observed":False}
    correct,feedback = ORACLE.score(task,record["content"])
    if correct:
        return {"id":task["id"],"status":"initial_correct","checked_keys":[key],"initial_observed":True,
            "initial_correct":True,"SAT_eligible":False,"primary_pair":(True,True)}
    eligible = task["family"]=="sat" and "clause_index" in feedback
    case = {"task":task,"initial_content":record["content"],"initial_feedback":feedback,
        "retry_order":[arm for arm in task["retry_order"] if arm!="coarse" or eligible]}
    result = BASE.inspect_case(case,records,False)
    result.update(initial_observed=True,initial_correct=False,initial_feedback=feedback,SAT_eligible=eligible)
    result["checked_keys"]=[key]+result["checked_keys"]
    if result["status"]=="complete_primary_pair":
        result["primary_pair"] = tuple(ORACLE.score(task,result["primary_records"][arm]["content"])[0] for arm in ("full","neutral"))
        if result["SAT_ablation_status"]=="complete":
            result["ablation_pair"]=(result["primary_pair"][0],ORACLE.score(task,result["coarse_record"]["content"])[0])
    return result

def paired(pairs,planned):
    if not planned:
        assert not pairs
        return {"planned":0,"valid":0,"not_complete":0,"difference":None,"exact_two_sided_McNemar":None,
            "planned_possible_outcome_bounds_not_CI":None,"full_only_correct":0,"control_only_correct":0}
    result = BASE.paired(pairs,planned)
    result["not_complete"]=planned-len(pairs)
    return result

def estimands(tasks,items):
    overall = [item["primary_pair"] for item in items if "primary_pair" in item]
    errors = [item for item in items if item.get("initial_observed") and item.get("initial_correct") is False]
    eligible = [item for item in errors if item["SAT_eligible"]]
    unresolved = sum(task["family"]=="sat" and not item["initial_observed"] for task,item in zip(tasks,items))
    observed = sum(item["initial_observed"] for item in items)
    correct = sum(item.get("initial_correct") is True for item in items)
    return {"primary_overall240":paired(overall,240),
        "conditional_repair":paired([item["primary_pair"] for item in errors if "primary_pair" in item],len(errors)),
        "exploratory_SAT_ablation":paired([item["ablation_pair"] for item in eligible if "ablation_pair" in item],len(eligible)),
        "SAT_eligibility_unresolved_initials":unresolved,"SAT_possible_eligibility_denominator_range":[len(eligible),len(eligible)+unresolved],
        "conditional_initial_error_eligibility_unresolved":240-observed,
        "initial":{"planned":240,"observed":observed,"correct":correct,"not_observed":240-observed,
            "possible_full240_accuracy_bounds_not_CI":[correct/240,(correct+240-observed)/240]},
        "scope":"independent holdout240; reused375/old600/old120 never pooled; missing bounds are not CIs and assume no MCAR"}
