"""Meaningful positive/negative checks of the portable evidence reconstruction."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

from audit import completion_primitives as completion
from replay import replay

BUNDLE = Path(__file__).resolve().parent


class PortableReplayChecks(unittest.TestCase):
    def test_rebuilds_all_scientific_and_cost_scopes_without_network(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            result = replay(BUNDLE)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual((result["complete_items"], result["missing_items"]), (592, 8))
        self.assertEqual(result["statistics"]["correct_counts"], {"initial": 217, "blindretry": 240, "verifiedretry": 271, "lengthmatchedretry": 241})
        self.assertEqual((result["scientific_complete_pair_calls"], result["all_successful_calls"], result["partial_missing_cost_only_calls"]), (1717, 1721, 4))
        self.assertEqual(result["usage_all_successful"]["input_tokens"] - result["usage_scientific_complete_pairs"]["input_tokens"], 667)
        self.assertEqual(result["usage_all_successful"]["output_tokens"] - result["usage_scientific_complete_pairs"]["output_tokens"], 70)

    def test_modified_original_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "bundle"
            shutil.copytree(BUNDLE, copied)
            path = copied / "history/replication600/calls.jsonl"
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaises(AssertionError):
                replay(copied)

    def test_manifest_cannot_read_outside_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "bundle"
            shutil.copytree(BUNDLE, copied)
            outside = Path(temp) / "outside.txt"
            outside.write_text("outside", "utf-8")
            path = copied / "public-manifest.json"
            manifest = json.loads(path.read_text("utf-8"))
            manifest["files"]["../outside.txt"] = hashlib.sha256(outside.read_bytes()).hexdigest()
            path.write_text(json.dumps(manifest), "utf-8")
            with self.assertRaisesRegex(AssertionError, "leaves bundle"):
                replay(copied)

    def test_eight_missing_pairs_have_45_discordance_allocations(self):
        neutral = {"initial": False, "blindretry": False, "verifiedretry": False, "lengthmatchedretry": False}
        rows = [{**neutral, "verifiedretry": True} for _ in range(32)]
        rows += [{**neutral, "lengthmatchedretry": True} for _ in range(2)]
        rows += [dict(neutral) for _ in range(558)]
        result = completion.missing_sensitivity(rows, 8)["comparisons"]["primary"]
        self.assertEqual(len(result["enumerated_possible_missing_outcomes"]), 45)
        self.assertEqual(result["paired_difference_full600_range"], [22 / 600, 38 / 600])
        self.assertEqual(result["p_value_range"], [4.1109160520136356e-10, 0.0009406740282429382])


if __name__ == "__main__":
    unittest.main()
