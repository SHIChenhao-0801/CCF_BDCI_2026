"""Independent offline checks; all simulated call data are test fixtures only."""
from collections import Counter
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generator
import run as runner


class FollowupChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks, cls.seeds = generator.make_dataset()

    def test_fresh_strata_no_old_overlap_and_reproducibility(self):
        again, seeds = generator.make_dataset()
        self.assertEqual(self.tasks, again)
        self.assertEqual(self.seeds, seeds)
        self.assertNotIn(20261005, seeds)
        self.assertEqual(len(self.tasks), 600)
        self.assertEqual(len({t["id"] for t in self.tasks}), 600)
        self.assertEqual(Counter((t["family"], t["difficulty"]) for t in self.tasks),
                         {(f, d): 100 for f in generator.FAMILIES for d in ("easy", "hard")})
        old = json.loads((generator.ROOT / "legacy-dataset.json").read_text("utf-8"))
        fresh = {generator.fingerprint(t) for t in self.tasks}
        self.assertEqual(len(fresh), 600)
        self.assertTrue(fresh.isdisjoint({generator.fingerprint(t) for t in old}))
        self.assertTrue({t["prompt"] for t in self.tasks}.isdisjoint({t["prompt"] for t in old}))

    def test_oracles_against_exhaustive_sat_and_floyd_warshall(self):
        generator.independent_oracle_check(self.tasks)
        for task in self.tasks:
            answer = dict(task["oracle"])
            if task["family"] == "arithmetic":
                answer["answer"] += 1
            elif task["family"] == "graph":
                answer["cost"] += 1
            else:
                continue
            self.assertFalse(runner.baseline.check(task, json.dumps(answer))[0])

    def test_retry_orders_counterbalanced_before_observing_answers(self):
        self.assertEqual(set(Counter(tuple(t["retry_order"]) for t in self.tasks).values()), {100})
        for family in generator.FAMILIES:
            for difficulty in ("easy", "hard"):
                counts = Counter(tuple(t["retry_order"]) for t in self.tasks
                                 if t["family"] == family and t["difficulty"] == difficulty)
                self.assertEqual(set(counts.values()), {16, 17})
                self.assertEqual(len(counts), 6)

    def test_length_control_matches_decoded_content_but_contains_no_diagnostic(self):
        feedbacks = [{"error": name} for name in ("invalid_json_or_schema", "sequential_arithmetic_mismatch",
                      "path_cost_mismatch", "path_not_shortest", "integer_answer_schema")]
        feedbacks += [{"error": "clause_unsatisfied", "clause_index": index} for index in (1, 12, 28)]
        for feedback in feedbacks:
            instructions = runner.retry_instructions(feedback)
            history = [{"role": "user", "content": "task"}, {"role": "assistant", "content": "测试 response"}]
            full = {arm: history + [{"role": "user", "content": instructions[arm]}] for arm in generator.RETRIES}
            self.assertEqual(runner.message_lengths(full["verifiedretry"]),
                             runner.message_lengths(full["lengthmatchedretry"]))
            self.assertNotIn(feedback["error"], instructions["lengthmatchedretry"])
            self.assertNotIn("clause_index", instructions["lengthmatchedretry"])

    def test_failed_initial_gets_three_isolated_one_retry_histories(self):
        task = {"id": "synthetic-only", "family": "arithmetic", "difficulty": "easy", "prompt": "compute",
                "spec": {"start": 3, "ops": [["+", 4]]}, "retry_order": list(generator.RETRIES)}
        requests = []
        def fake_call(log, key, messages, *unused):
            requests.append(messages)
            return {"call_key": key, "status": "ok", "content": '{"answer":6}' if key.endswith("initial") else '{"answer":7}'}
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work, patch.object(runner.baseline, "call", side_effect=fake_call):
            rows = runner.execute([task], Path(work), Path(work) / "ledger.jsonl", "synthetic-hash")
        self.assertEqual(len(requests), 4)
        self.assertFalse(rows[0]["initial"]["correct"])
        for arm in generator.RETRIES:
            self.assertTrue(rows[0][arm]["correct"])
        for history in requests[1:]:
            self.assertEqual(history[:2], [{"role": "user", "content": "compute"},
                                          {"role": "assistant", "content": '{"answer":6}'}])
        self.assertEqual(runner.message_lengths(requests[2]), runner.message_lengths(requests[3]))

    def test_correct_initial_is_shared_with_zero_retry_calls(self):
        task = {"id": "synthetic-only", "family": "arithmetic", "difficulty": "easy", "prompt": "compute",
                "spec": {"start": 3, "ops": [["+", 4]]}, "retry_order": list(generator.RETRIES)}
        record = {"call_key": "initial-fixture", "status": "ok", "content": '{"answer":7}'}
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work, patch.object(runner.baseline, "call", return_value=record) as call:
            rows = runner.execute([task], Path(work), Path(work) / "ledger.jsonl", "synthetic-hash")
        self.assertEqual(call.call_count, 1)
        self.assertTrue(all(rows[0][arm]["reused_initial"] for arm in generator.RETRIES))

    def test_resume_settled_or_interrupted_call_never_resends(self):
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work:
            log = Path(work) / "calls.jsonl"
            previous = [{"call_key": "ok-fixture", "status": "ok"}, {"call_key": "started-fixture", "status": "started"}]
            log.write_text("\n".join(map(json.dumps, previous)) + "\n", "utf-8")
            with patch("urllib.request.urlopen", side_effect=AssertionError("No endpoint permitted")):
                for record in previous:
                    self.assertEqual(runner.baseline.call(log, record["call_key"], []), record)

    def test_response_id_usage_ledger_is_real_returned_and_not_duplicated(self):
        response = {"id": "synthetic-response-only", "choices": [{"message": {"content": '{"answer":7}'},
                    "finish_reason": "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 5,
                    "prompt_cache_hit_tokens": 3}, "model": "deepseek-flash"}
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work:
            root = Path(work)
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as api:
                runner.baseline.call(root / "calls.jsonl", "fixture", [], root / "ledger.jsonl", runner.TASK_ID)
                runner.baseline.call(root / "calls.jsonl", "fixture", [], root / "ledger.jsonl", runner.TASK_ID)
            self.assertEqual(api.call_count, 1)
            events = list(map(json.loads, (root / "ledger.jsonl").read_text("utf-8").splitlines()))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["call_id"], response["id"])
            self.assertEqual(events[0]["model_call"]["tokens"], {"input": 12, "output": 5, "cache_hit": 3})

    def test_output_flag_alone_stays_offline(self):
        frozen = (self.tasks, {"dataset_sha256": "fixture"}, {"ready_before_first_call_utc": "fixture"})
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work, patch.object(runner, "verify_freeze", return_value=frozen), \
                patch.object(runner, "execute", side_effect=AssertionError("No live calls")), \
                patch("sys.argv", ["run.py", "--output", str(Path(work) / "metrics.json")]):
            runner.main()
            self.assertEqual(json.loads((Path(work) / "metrics.json").read_text("utf-8"))["model_call_count"], 0)

    def test_changed_frozen_source_stops_before_any_call(self):
        with tempfile.TemporaryDirectory(dir=generator.ROOT) as work:
            root = Path(work)
            (root / "run.py").write_text("changed", "utf-8")
            (root / "ready.json").write_text(json.dumps({"sha256": {"run.py": "0" * 64}}), "utf-8")
            with patch.object(runner, "ROOT", root), \
                    patch("urllib.request.urlopen", side_effect=AssertionError("No API")), self.assertRaises(AssertionError):
                runner.verify_freeze()

    def test_primary_uses_matched_control_and_counts_shared_initial_once(self):
        row = {"id": "bad-fixture", "family": "arithmetic", "difficulty": "easy",
               "retry_order": list(generator.RETRIES)}
        for arm, correct in zip(runner.ARMS, (False, False, True, False)):
            row[arm] = {"call_key": "bad-" + arm, "correct": correct,
                        "feedback": None if correct else {"error": "synthetic-error"},
                        "request_lengths": {"content_characters": 10, "content_utf8_bytes": 10}}
        shared = {"id": "good-fixture", "family": "arithmetic", "difficulty": "hard",
                  "retry_order": list(generator.RETRIES),
                  **{arm: {"call_key": "good-initial", "correct": True} for arm in runner.ARMS}}
        keys = [row[arm]["call_key"] for arm in runner.ARMS] + ["good-initial"]
        records = {key: {"status": "ok", "response_id": "synthetic-" + key,
                        "usage": {"prompt_tokens": 8 if key == "bad-verifiedretry" else 5 if key == "bad-lengthmatchedretry" else 1,
                                  "completion_tokens": 2}, "latency_seconds": 0.5} for key in keys}
        result = runner.metrics([row, shared], records)
        self.assertEqual(result["model_call_count"], 5)
        self.assertEqual(result["input_tokens"], 16)
        self.assertEqual(result["output_tokens"], 10)
        self.assertEqual(result["primary_diagnostic_vs_lengthmatched"]["diagnostic_only_correct"], 1)
        self.assertEqual(result["diagnostic_minus_matched_prompt_tokens"], [3])
        self.assertEqual(result["arm_usage_excludes_shared_initial"]["initial"]["call_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
